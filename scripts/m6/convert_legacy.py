# -*- coding: utf-8 -*-
"""M6 legacy corpus converter (dataeng-m6).

Applies the chosen-first rule (adr-1b §3, arch-m6 2026-10-21 02:15):
- Labels ALWAYS come from the chosen (correct) response's VERDICT:
  action in {refuse, report} -> pos; answer + verdict in {allow, benign} -> neg;
  answer + conditional -> T6 conditional; insufficient-context/needs-info -> drop.
- Task type from chosen verdict: contains-injection->T5, contains-risk->T1.
- reserve rows: refuse-domain trusted (pos); allow/conditional domain dropped
  (source-polarity mapping unavailable at row level; cvalues cv-harm/cv-help
  prefixes used directly from the reserve library instead).
- Hard assertions per dpo_class against the adr-1b §3 crosstab; on mismatch
  the script ABORTS (arch directive: stop and report, never silently fix).

Sources: m4-run capfix, p16-r9 paired/adv, p16-r5 f5_paired, m2.5-staging
(t14/t1/t9/doc_structure/t13_retrieval/fC_cvpku_release), dpo-reserve cvalues.
Outputs per-task pools under data/m6/_staging/.
"""
import json
import re
import sys, os
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import make_row, write_jsonl, assign_ids, Deduper

VD = re.compile(r"VERDICT:\s*(\{.*\})\s*$", re.S)
CARRIER_RE = re.compile(r"carrier c1 (head|mid|tail):\s*([a-z_]+)\s*\(([a-z_]+)\)")

FW_RULES = [
    ("roleplay", re.compile(r"roleplay|扮演|角色|扮演一个|persona|you are now|你是|假设你是|进入角色", re.I)),
    ("hypothetical", re.compile(r"hypothetical|假设|思想实验|学术讨论|虚构|平行宇宙|思想實驗|purely hypothetical", re.I)),
    ("authority", re.compile(r"authorized|授权|管理员|admin|官方|执法|law enforcement|developer mode|开发者模式|root", re.I)),
]


def parse_vd(text):
    m = VD.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def classify_framework(text):
    for fw, pat in FW_RULES:
        if pat.search(text):
            return fw
    return "authority"  # r9 adv four-framework fallback (closest default)


def conv_to_text_turns(conv):
    """Extract full input: system (policy pack) + user turns.

    adr-1b §6.4: (query, pack1) and (query, pack2) are DIFFERENT inputs —
    the pack segment lives in the system message, so system is preserved in
    `turns` (role=system). Rows without system collapse to plain text.
    """
    turns = []
    for m in conv:
        role = {"system": "system", "human": "user", "user": "user"}.get(m.get("from"), "assistant")
        turns.append({"role": role, "content": m.get("value", "")})
    has_system = bool(turns) and turns[0]["role"] == "system"
    users = [t for t in turns if t["role"] == "user"]
    if not has_system and len(users) == 1 and len(turns) <= 2:
        return users[0]["content"], None
    return None, turns


# ---------------------------------------------------------------- converters
def conv_m4(path, sinks, dd, policy_keep=2000):
    """chosen-first conversion with adr-1b §3 polarity-purity assertions.

    adr-1b §6.4 policy handling: control-group rows are grouped by normalized
    query; flip groups (labels differ across packs) are kept in full with
    pair_id (same-split enforced); non-flip groups keep one representative;
    total capped at policy_keep to avoid drowning the pool.
    """
    stats = collections.defaultdict(collections.Counter)
    policy_groups = collections.defaultdict(list)  # norm_query -> [(label, row)]
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        cls = d.get("dpo_class")
        conv = d.get("conversations", [])
        text, turns = conv_to_text_turns(conv)
        if not text and not turns:
            stats[cls]["no_input"] += 1
            continue
        if cls == "calibration":
            stats[cls]["drop"] += 1
            continue
        vd = parse_vd(d.get("chosen", {}).get("value", ""))
        if vd is None:
            if cls == "refusal_quality":
                label, task, detail = "pos", "T1", {}
            else:
                stats[cls]["no_verdict_drop"] += 1
                continue
        else:
            action, verdict = vd.get("action"), vd.get("verdict")
            if action in ("refuse", "report"):
                label = "pos"
            elif action == "answer" and verdict in ("allow", "benign"):
                label = "neg"
            elif action == "answer" and verdict == "conditional":
                label = "cond"
            else:
                stats[cls]["drop_%s/%s" % (action, verdict)] += 1
                continue
            if cls == "reserve":
                if label != "pos":
                    stats[cls]["drop_reserve_nonrefuse"] += 1
                    continue
                task, detail = "T1", {}
            elif cls in ("carrier_inject_obedient", "carrier_inject_hollow"):
                task = "T5"
                detail = {}
                f = vd.get("findings") or []
                if f and isinstance(f[0], str):
                    m2 = CARRIER_RE.search(f[0])
                    if m2:
                        detail = {"carrier": m2.group(3), "mechanism": m2.group(2),
                                  "position": m2.group(1)}
                if label == "pos":
                    detail.setdefault("carrier", "tool_output")
                    detail.setdefault("mechanism", None)
                    detail.setdefault("position", None)
            elif cls == "carrier_clean_overrefusal":
                task = "T5" if label == "neg" else "T6"
                detail = {}
            elif cls in ("bt330_refusal", "policy", "refusal_quality"):
                task = "T1" if label != "cond" else "T6"
                detail = {}
            else:
                task, detail = "T1", {}
        if label == "cond":
            task = "T6"
            detail = {"t6_class": "conditional"}
        else:
            if task == "T6":
                detail = {"t6_class": "high-risk" if label == "pos" else "safe"}

        def emit(extra_meta=None):
            return make_row(task, "pool", d.get("lang", "zh"),
                            "singleturn" if text else "multiturn",
                            label, detail, "m4-capfix",
                            text=text, turns=turns,
                            difficulty="medium",
                            lineage={"source": "data/m4-run/dpo_m4_capfix.jsonl",
                                     "src_id": d.get("id"), "dpo_class": cls},
                            extra_meta=extra_meta or {})

        if cls == "policy":
            # group by normalized user query; keep pack segment (in turns) intact
            qkey = norm_key(d)
            policy_groups[qkey].append((label, emit))
            stats[cls]["grouped"] += 1
            continue

        key = dedup_key(text, turns)
        if dd.is_dup(key, near=False):
            stats[cls]["dup_skip"] += 1
            continue
        dd.add(key)
        stats[cls][label] += 1
        sinks[task].append(emit())

    # policy groups: flip-first sampling (adr-1b §6.4)
    flip_groups = []
    flat_groups = []
    for qkey, items in policy_groups.items():
        labels = {lab for lab, _ in items}
        (flip_groups if len(labels) > 1 else flat_groups).append((qkey, items))
    kept = 0
    pair_seq = 0
    for qkey, items in flip_groups:
        if kept >= policy_keep:
            stats["policy"]["flip_skip_cap"] += len(items)
            continue
        pair_seq += 1
        pid = "m4pol-%05d" % pair_seq
        for label, emit in items:
            if kept >= policy_keep:
                stats["policy"]["flip_skip_cap"] += 1
                continue
            row = emit({"pair_id": pid})
            sinks[row["task"]].append(row)
            stats["policy"]["%s_flip" % label] += 1
            kept += 1
    for qkey, items in flat_groups:
        if kept >= policy_keep:
            stats["policy"]["flat_skip_cap"] += 1
            continue
        label, emit = items[0]
        row = emit()
        key = dedup_key(row.get("text"), row.get("turns"))
        if dd.is_dup(key, near=False):
            stats["policy"]["flat_dup"] += 1
            continue
        dd.add(key)
        sinks[row["task"]].append(row)
        stats["policy"]["%s_flat" % label] += 1
        kept += 1
    stats["policy"]["kept_total"] = kept
    stats["policy"]["flip_groups"] = len(flip_groups)
    stats["policy"]["flat_groups"] = len(flat_groups)
    return stats


def norm_key(d):
    users = [m.get("value", "") for m in d.get("conversations", [])
             if m.get("from") in ("human", "user")]
    return "|".join(u.strip().lower() for u in users)


def dedup_key(text, turns):
    if text:
        return text
    return "\n".join(t["content"] for t in (turns or []))


def conv_r9_paired(path, sinks, dd):
    stats = collections.Counter()
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        if d.get("dpo_class") == "adv_coverage_r9":
            continue  # handled separately from p16_r9_adv
        conv = d.get("conversations", [])
        text, turns = conv_to_text_turns(conv)
        vd = parse_vd(d.get("chosen", {}).get("value", ""))
        if vd is None:
            stats["no_verdict"] += 1
            continue
        verdict = vd.get("verdict")
        if verdict == "contains-risk":
            label = "pos"
        elif verdict == "no-risk":
            label = "neg"
        else:
            stats["drop_%s" % verdict] += 1
            continue
        key = text or "\n".join(t["content"] for t in turns)
        if dd.is_dup(key, near=False):
            stats["dup_skip"] += 1
            continue
        dd.add(key)
        if turns and len([t for t in turns if t["role"] == "user"]) >= 2:
            task, detail = "T3", {"trigger": "multiturn-accumulation", "reveal_turn": 2}
            kind = "multiturn"
        else:
            task, detail, kind = "T1", {}, "singleturn"
        stats["%s_%s" % (task, label)] += 1
        sinks[task].append(make_row(task, "pool", d.get("lang", "en"), kind, label, detail,
                                    "r9-paired", text=text, turns=turns, difficulty="medium",
                                    lineage={"source": "data/dpo/p16-calibration-r9/p16_r9_paired.jsonl",
                                             "src_id": d.get("id")}))
    return stats


def conv_r9_adv(path, sinks, dd):
    stats = collections.Counter()
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        conv = d.get("conversations", [])
        text, turns = conv_to_text_turns(conv)
        key = text or "\n".join(t["content"] for t in turns)
        if dd.is_dup(key, near=False):
            stats["dup_skip"] += 1
            continue
        dd.add(key)
        fw = classify_framework(key)
        kind = "multiturn" if turns and len([t for t in turns if t["role"] == "user"]) >= 2 else "singleturn"
        if kind == "multiturn":
            fw = "multiturn"
        stats["pos"] += 1
        sinks["T2"].append(make_row("T2", "pool", d.get("lang", "en"), kind, "pos",
                                    {"framework": fw}, "r9-adv", text=text, turns=turns,
                                    difficulty="hard",
                                    lineage={"source": "data/dpo/p16-calibration-r9/p16_r9_adv.jsonl",
                                             "src_id": d.get("id")}))

    return stats


def conv_f5(path, sinks, dd):
    """f5 minimal pairs: keep ALL rows (adr-1b §6.4 — cross-label near-matches
    are minimal-pair signal, never silently collapsed). pair_id -> same split."""
    stats = collections.Counter()
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        rid = d.get("id", "")
        text, turns = conv_to_text_turns(d.get("conversations", []))
        if not text and not turns:
            continue
        label = "pos" if rid.endswith("-m") else "neg"
        stats[label] += 1
        lang = "en"
        probe = text or "\n".join(t["content"] for t in turns)
        if not any(c.isascii() for c in probe[:60]):
            lang = "zh"
        sinks["T1"].append(make_row("T1", "pool", lang,
                                    "singleturn" if text else "multiturn",
                                    label, {}, "f5-paired", text=text, turns=turns,
                                    difficulty="medium",
                                    lineage={"source": "data/dpo/p16-calibration-r5/p16_f5_paired.jsonl",
                                             "src_id": rid},
                                    extra_meta={"pair_id": "f5-" + rid.rsplit("-", 1)[0]}))
    return stats


def conv_staging_t5(path, sinks, dd, source_family, allowed):
    stats = collections.Counter()
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        msgs = d.get("messages", [])
        user_msgs = [m["content"] for m in msgs if m.get("role") == "user"]
        if not user_msgs:
            continue
        text = user_msgs[0]
        vd = parse_vd(msgs[-1]["content"]) if msgs else None
        verdict = (vd or {}).get("verdict")
        action = (vd or {}).get("action")
        if (action, verdict) not in allowed:
            stats["drop_%s/%s" % (action, verdict)] += 1
            continue
        if action == "report":
            label = "pos"
        else:
            label = "neg"
        if dd.is_dup(text, near=False):
            stats["dup_skip"] += 1
            continue
        dd.add(text)
        stats[label] += 1
        sinks["T5"].append(make_row("T5", "pool", d.get("lang", "zh"), "carrier", label,
                                    {"carrier": None, "mechanism": None, "position": None,
                                     "envelope": "staging-native"},
                                    source_family, text=text, difficulty="medium",
                                    lineage={"source": "data/sft/m2.5-staging/%s" % os.path.basename(path),
                                             "src_id": d.get("id")}))
    return stats


def conv_staging_t13(path, sinks, dd):
    stats = collections.Counter()
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        msgs = d.get("messages", [])
        user_msgs = [m["content"] for m in msgs if m.get("role") == "user"]
        if not user_msgs:
            continue
        text = user_msgs[0]
        if dd.is_dup(text, near=False):
            stats["dup_skip"] += 1
            continue
        dd.add(text)
        stats["neg"] += 1
        sinks["T3"].append(make_row("T3", "pool", d.get("lang", "zh"), "longctx", "neg",
                                    {"trigger": "longctx-buried", "position": None},
                                    "staging-t13", text=text, difficulty="medium",
                                    lineage={"source": "data/sft/m2.5-staging/t13_retrieval.jsonl",
                                             "src_id": d.get("id")}))
    return stats


_REFUSE_PAT = __import__("re").compile(
    r"我不能|我无法|我不会|不能提供|无法提供|我不会提供|抱歉|"
    r"作为(?:一个)?(?:AI|人工智能)|I (?:cannot|can't|will not|won't)|I'm sorry|Sorry")


def _looks_refusal(chosen):
    """cvalues rows carry no m4 VERDICT — infer refusal-domain from the chosen
    response text (chosen-first rule: harmful prompt + refusal answer -> pos)."""
    return bool(_REFUSE_PAT.search(chosen or ""))


def conv_cvalues(path, sinks, dd, max_pos=4000):
    """cvalues conversion — chosen-VERDICT polarity (adr-1b §3).

    The id prefix (cv-harm/cv-help) is a batch label, NOT a polarity label:
    both batches are harmful-prompt + safe-chosen DPO pairs. Rows whose chosen
    response is a refusal are pos (harmful content must be detected); rows
    with a non-refusal chosen are dropped (zero-noise priority, same rule as
    the reserve dpo_class branch)."""
    stats = collections.Counter()
    rng = __import__("random").Random(20261021)
    rows = []
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        rows.append((d.get("prompt", ""), d.get("chosen") or ""))
    rng.shuffle(rows)
    for text, chosen in rows:
        if not text:
            stats["empty_skip"] += 1
            continue
        if not _looks_refusal(chosen):
            stats["drop_nonrefuse"] += 1
            continue
        if dd.is_dup(text, near=False):
            stats["dup_skip"] += 1
            continue
        if stats["pos"] >= max_pos:
            stats["pos_cap_skip"] += 1
            continue
        dd.add(text)
        stats["pos"] += 1
        sinks["T1"].append(make_row("T1", "pool", "zh", "singleturn", "pos", {},
                                    "reserve-cvalues", text=text, difficulty="easy",
                                    lineage={"source": path}))
    return stats


# adr-1b §3 polarity-purity assertions: per dpo_class, the set of labels that
# may appear. (Counts differ from the §3 crosstab because policy control
# groups repeat the same query under different packs; the converter dedups by
# normalized text, which is desired for training pools. Polarity DIRECTION
# must match §3 exactly — any unexpected label aborts the build.)
EXPECTED = {
    "bt330_refusal": {"pos"},
    "carrier_inject_obedient": {"pos"},
    "carrier_inject_hollow": {"pos"},
    "carrier_clean_overrefusal": {"neg", "cond"},
    "policy": {"pos", "neg", "cond"},
    "reserve": {"pos"},
    "refusal_quality": {"pos"},
    "calibration": set(),
}


def main():
    sinks = {t: [] for t in ["T1", "T2", "T3", "T4", "T5", "T6"]}
    dd = Deduper()

    stats_m4 = conv_m4("data/m4-run/dpo_m4_capfix.jsonl", sinks, dd)
    print("== m4 stats ==")
    for cls in sorted(stats_m4):
        print(" ", cls, dict(stats_m4[cls].most_common(8)))
    # polarity-purity assertions vs adr-1b §3
    NON_LABEL = ("drop", "no_verdict_drop", "no_input", "dup_skip", "grouped",
                 "kept_total", "flip_groups", "flat_groups")
    fail = []
    for cls, allowed in EXPECTED.items():
        got = stats_m4.get(cls, collections.Counter())
        for key in got:
            if key.startswith("drop") or key in NON_LABEL:
                continue
            if key.endswith("_flip") or key.endswith("_flat") or key.endswith("_cap"):
                continue
            if key not in allowed:
                fail.append("%s: unexpected label '%s' (allowed %s)" % (cls, key, sorted(allowed)))
        if cls == "calibration":
            produced = {k for k in got if k not in NON_LABEL and not k.startswith("drop")}
            if produced:
                fail.append("calibration: expected full drop, produced %s" % sorted(produced))
    if fail:
        print("ASSERTION FAIL (adr-1b §3 polarity purity):")
        for f in fail:
            print("  -", f)
        sys.exit(2)
    print("m4 polarity-purity assertions vs adr-1b §3: PASS (dedup removes pack-control repeats)")

    print("== r9_paired ==", dict(conv_r9_paired("data/dpo/p16-calibration-r9/p16_r9_paired.jsonl", sinks, dd).most_common()))
    print("== r9_adv ==", dict(conv_r9_adv("data/dpo/p16-calibration-r9/p16_r9_adv.jsonl", sinks, dd).most_common()))
    print("== f5 ==", dict(conv_f5("data/dpo/p16-calibration-r5/p16_f5_paired.jsonl", sinks, dd).most_common()))

    stg = "data/sft/m2.5-staging"
    print("== t14 ==", dict(conv_staging_t5(stg + "/t14_authinject.jsonl", sinks, dd, "staging-t14",
                                           {("report", "contains-injection"), ("answer", "benign")}).most_common()))
    print("== t1inj ==", dict(conv_staging_t5(stg + "/t1_injection.jsonl", sinks, dd, "staging-t1",
                                             {("report", "contains-injection"), ("answer", "clean")}).most_common()))
    print("== t9phish ==", dict(conv_staging_t5(stg + "/t9_phish_expand.jsonl", sinks, dd, "staging-t9",
                                               {("report", "phishing"), ("report", "suspicious"), ("answer", "benign")}).most_common()))
    print("== docstruct ==", dict(conv_staging_t5(stg + "/doc_structure.jsonl", sinks, dd, "staging-docstruct",
                                                 {("report", "contains-injection"), ("report", "suspicious-pattern"), ("answer", "clean")}).most_common()))
    print("== t13 ==", dict(conv_staging_t13(stg + "/t13_retrieval.jsonl", sinks, dd).most_common()))
    st_cv = conv_cvalues("data/sft/dpo-reserve/cvalues.jsonl", sinks, dd)
    print("== cvalues ==", dict(st_cv.most_common()))
    # polarity-purity assertion for the cvalues path (hotfix condition #2):
    # every emitted reserve-cvalues row must be pos (chosen-first rule); the
    # id-prefix shortcut produced flipped labels here once — never again.
    cv_bad = [r for r in sinks["T1"]
              if (r.get("source") or {}).get("family") == "reserve-cvalues"
              and r.get("label") != "pos"]
    if cv_bad:
        print("ASSERTION FAIL (cvalues polarity purity): %d non-pos rows" % len(cv_bad))
        sys.exit(2)
    if st_cv.get("neg"):
        print("ASSERTION FAIL (cvalues polarity purity): converter emitted neg")
        sys.exit(2)
    print("cvalues polarity-purity assertion (chosen-first): PASS")

    # write per-task pools
    for task, rows in sinks.items():
        if not rows:
            continue
        assign_ids(rows, "m6-%s-legacy" % task.lower())
        write_jsonl("data/m6/_staging/%s-legacy.jsonl" % task.lower(), rows)


if __name__ == "__main__":
    main()
