# -*- coding: utf-8 -*-
"""M6 dataset assembly (dataeng-m6) — staging pools -> final v0.3.0 schema.

Steps:
1. Load all staging pools (per-task synth + legacy + shared benign/challenge/ood).
2. Convert to m6-sample v0.3.0 rows: nested input (text/turns/messages/carrier),
   labels map, source, flags, est_tokens.
   - T3 shape mix: user-only turns (primary, matches eval main caliber) vs
     full messages incl. assistant (r9-paired seeds) ~60/40.
   - T5 std_tag envelope rows -> CarrierInput; other envelope variants stay
     TextInput (envelope-diversity axis, arch ADR-1b).
   - T1 risk_domain via keyword classifier (enum registered in manifest).
   - T4 spans carried with type/sub/risk (risk derived from type table).
3. Split per task: train/dev/heldout with pair_id and dialog_id group locks
   (same split mandatory), dev gets challenge-mirror + ood-mirror.
4. challenge/ + ood/ eval dirs (six-key labels; medical-PII subset T4=pos).
5. pool/ joint view: merge by input hash, union labels (six-key negatives for
   shared benign rows).
6. Write data/m6/manifest.json (per-file lineage/scale/scale_gates/disjointness)
   and run split isolation checks (exact hash + 8-gram).
"""
import json
import os
import re
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import read_jsonl, write_jsonl, sha16, norm_text, ngrams

SCHEMA = "m6-sample"
SCHEMA_VERSION = "0.3.0"

RISK_OF_TYPE = {
    "person": "low", "phone": "medium", "email": "low", "gov_id": "high",
    "address": "medium", "bank_card": "high", "credential": "high",
    "dob": "medium", "license_plate": "medium", "medical_id": "medium",
    "other_id": "medium",
}

RISK_DOMAIN_RULES = [
    ("malware", r"恶意软件|木马|病毒|蠕虫|malware|trojan|ransomware|勒索|keylog|键盘记录|后门|backdoor"),
    ("phishing", r"钓鱼|phish|诈骗|scam|假登录|伪造.*邮件|假冒"),
    ("credential", r"密码|password|口令|credential|爆破|brute.?force|撞库|hash.*recover|字典攻击"),
    ("data-theft", r"导出|外发|打包.*带走|exfiltrat|customer table|客户表|聊天记录|copy.*repo"),
    ("intrusion", r"入侵|渗透|intrusion|提权|domain.?controller|端口|scan.*weak|默认口令|factory.?default"),
    ("surveillance", r"监控|spyware|跟踪|stalker|定位|camera.*record|微信.*监视|位置"),
    ("doxxing", r"人肉|dox|住址.*查|license plate.*owner|曝光页|网暴|mass.?mention|骚扰|轰炸"),
    ("forgery", r"伪造|fake|假证|成绩单|transcript|发票|invoice.*edit|健康证明|假条"),
    ("weapons", r"枪|消音器|suppressor|3D.?print.*gun|弹药|武器"),
    ("drugs", r"毒品|methamphetamine|冰毒|大麻|cannabis|兴奋剂|前体|cold medicine.*extract"),
    ("explosives", r"爆炸|炸药|detonator|引信|fertilizer.*fuel|燃烧弹|arson"),
    ("privacy-abuse", r"手机号|身份证号|证件号|开房记录|轨迹|通话记录|个人信息.*批量"),
]
RISK_DOMAIN_DEFAULT = "other"


def classify_risk_domain(text):
    t = text or ""
    for dom, pat in RISK_DOMAIN_RULES:
        if re.search(pat, t, re.I):
            return dom
    return RISK_DOMAIN_DEFAULT


def est_tokens(text):
    if not text:
        return 0
    zh = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - zh
    return int(zh * 0.75 + other / 4.0 * 1.3)


def make_final(task, split, lang, kind, input_obj, labels, source, meta=None,
               flags=None, est_tok=None, rid=None):
    row = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "id": rid,
        "task": task,
        "split": split,
        "lang": lang,
        "kind": kind,
        "input": input_obj,
        "labels": labels,
        "flags": flags or {"ood": False, "challenge": False, "holdout_family": None,
                           "ambiguous": False},
        "source": source,
    }
    if meta:
        row["meta"] = meta
    if est_tok is not None:
        row["est_tokens"] = est_tok
    return row


def staging_to_final(r, split, task_override=None, force_label=None, t4_pos=False):
    """Convert one staging row to a final m6-sample row (single-task label)."""
    task = task_override or r["task"]
    ld = r.get("label_detail") or {}
    label = force_label or r["label"]
    lang = r.get("lang", "zh")
    meta = dict(r.get("meta") or {})
    meta.pop("_raw_body", None)
    lineage = meta.pop("lineage", {}) or {}
    pair_id = (meta.pop("pair_id", None) or lineage.get("pair_id"))
    text = r.get("text")
    turns = r.get("turns")
    kind = r.get("kind", "singleturn")

    # ---- input construction (each shape carries ONLY its own keys + optional
    # system; the oneOf forms are additionalProperties:false)
    input_obj = {}
    if task == "T5" and kind == "carrier":
        # Option A (arch ruling / schema v0.3.4): ALL synth carrier rows go
        # through input.carrier + envelope_style; gold anchors on carrier.body
        # raw text (decoupled from envelope template). Legacy T5 rows
        # (envelope=staging-native) keep input.text as protocol-free coverage.
        raw_body = (r.get("meta") or {}).get("_raw_body")
        if raw_body is not None:
            op_task = (r.get("meta") or {}).get("_operator_task") or "Review this external content."
            input_obj = {
                "operator_task": op_task,
                "carrier": {
                    "type": ld.get("carrier") or "other",
                    "trust": "untrusted",
                    "id": "c1",
                    "body": raw_body,
                    "envelope_style": ld.get("envelope") or "std_tag",
                },
            }
        else:
            input_obj = {"text": text}
    elif turns:
        roles = [t["role"] for t in turns]
        if "assistant" in roles or "system" in roles:
            sysm = None
            msgs = []
            for t in turns:
                if t["role"] == "system":
                    sysm = t["content"]
                else:
                    msgs.append({"role": t["role"], "content": t["content"]})
            input_obj = {"messages": msgs}
            if sysm:
                input_obj["system"] = sysm
        else:
            input_obj = {"turns": [t["content"] for t in turns]}
    else:
        input_obj = {"text": text}

    # ---- T3 shape mix: user-only primary (eval caliber) vs messages w/ assistant
    if task == "T3" and input_obj.get("messages"):
        msgs = input_obj["messages"]
        has_asst = any(m["role"] == "assistant" for m in msgs)
        # deterministic 60/40: user-only primary unless row carries assistant
        # replies from r9-paired seeds (keep ~40% messages form)
        if has_asst:
            sysm = input_obj.get("system")
            if sha16(json.dumps([m["content"] for m in msgs], ensure_ascii=False))[-1] >= "a":
                input_obj = {"turns": [m["content"] for m in msgs if m["role"] != "assistant"]}
                if sysm:
                    input_obj["system"] = sysm
                kind = "multiturn"

    # ---- labels
    detail = {}
    if task == "T1":
        detail = {"risk_domain": classify_risk_domain(text or (turns and "\n".join(t["content"] for t in turns)) or "")} \
            if label == "pos" else {}
    elif task == "T2":
        fw = ld.get("framework")
        detail = {"framework": fw if fw in ("roleplay", "hypothetical", "multiturn",
                                            "authority", "encoding", "other") else "other"} if fw else {}
    elif task == "T3":
        trig = ld.get("trigger") or "singleturn"
        detail = {"trigger": trig if trig in ("multiturn-accumulation", "longctx-buried", "singleturn") else "singleturn"}
        if ld.get("reveal_turn"):
            detail["reveal_turn"] = ld["reveal_turn"]
    elif task == "T4":
        spans = []
        for sp in (ld.get("spans") or []):
            s2 = {"start": sp["start"], "end": sp["end"], "type": sp["type"],
                  "risk": RISK_OF_TYPE.get(sp["type"], "medium")}
            if sp.get("sub"):
                s2["sub"] = sp["sub"]
            spans.append(s2)
        detail = {"spans": spans}
        if t4_pos and not spans:
            detail = {"spans": []}  # caller decides label; pos requires >=1 span
    elif task == "T5":
        carrier = ld.get("carrier")
        mech = ld.get("mechanism")
        detail = {
            "carrier": carrier if carrier in ("tool_output", "search_result", "email",
                                              "doc_fragment", "document", "webpage", "log",
                                              "code", "other") else "other",
            "mechanism": mech if mech in ("ai_directive", "fake_system_prompt", "policy_claim",
                                          "task_hijack", "exfil_authorize", "verdict_suppress",
                                          "encoding_obfuscation", "relationship_target",
                                          "hidden_text", "other") else "other",
            "carrier_site": ld.get("position") or "",
        }
        if ld.get("envelope") in ("std_tag", "simple_tag", "markdown", "plain"):
            detail["envelope"] = ld["envelope"]
        if label == "neg":
            detail["mechanism"] = None
    elif task == "T6":
        t6c = ld.get("t6_class")
        if label == "pos":
            t6c = "high-risk"
        elif t6c not in ("conditional", "safe"):
            t6c = "safe"
        detail = {"t6_class": t6c}
        if ld.get("op"):
            detail["op"] = ld["op"]

    if task == "T6":
        label = "pos" if detail["t6_class"] == "high-risk" else "neg"

    gold = {"label": label}
    if detail:
        gold["label_detail"] = detail

    if task == "pool":
        # joint-view row (schema v0.3.4 RowTask "pool"): labels expand to the
        # six task keys; T4 pos iff meta.t4_pos (sparse challenge positives)
        t4_pos = (r.get("meta") or {}).get("t4_pos", False)
        t4_spans = (r.get("meta") or {}).get("t4_spans")
        labels = {t: {"label": "neg"} for t in ["T1", "T2", "T3", "T5", "T6"]}
        if t4_pos:
            spans = []
            for sp in (t4_spans or []):
                s2 = {"start": sp["start"], "end": sp["end"], "type": sp["type"],
                      "risk": RISK_OF_TYPE.get(sp["type"], "medium")}
                if sp.get("sub"):
                    s2["sub"] = sp["sub"]
                spans.append(s2)
            labels["T4"] = {"label": "pos", "label_detail": {"spans": spans}}
        else:
            labels["T4"] = {"label": "neg", "label_detail": {"spans": []}}
        labels_out = labels
    else:
        labels_out = {task: gold}

    src = {
        "family": r.get("source_family", "synth"),
        "src_id": lineage.get("src_id") or r.get("id"),
        "generator": lineage.get("generator"),
        "license": None,
    }
    meta2 = {k: v for k, v in meta.items() if v is not None}
    if pair_id:
        meta2["pair_id"] = pair_id
    if input_obj.get("messages"):
        full_text = "\n".join([m["content"] for m in input_obj["messages"]])
    elif input_obj.get("carrier"):
        full_text = input_obj["carrier"].get("body") or ""
    else:
        full_text = text or ("\n".join((t["content"] if isinstance(t, dict) else t) for t in turns) if turns else "")
    et = est_tokens(full_text) or None
    if kind == "longctx" and et and et < 8000:
        et = 8000 if et >= 5000 else et  # only long paras qualify; leave small ones as-is
    row = make_final(task, split, lang, kind, input_obj, labels_out, src,
                     meta2 or None, est_tok=et, rid=r.get("id"))
    return row


def row_sig(r):
    """Input signature for isolation/locking: system prompt included (policy
    packs live there — (query, pack1) vs (query, pack2) are different inputs)."""
    inp = r.get("input") or {}
    if inp.get("carrier"):
        t = (inp.get("operator_task") or "") + "||" + (inp["carrier"].get("body") or "")
    else:
        parts = []
        if inp.get("system"):
            parts.append("[sys]" + inp["system"])
        for x in (inp.get("messages") or inp.get("turns") or []):
            parts.append(x.get("content") if isinstance(x, dict) else x)
        if inp.get("text"):
            parts.append(inp["text"])
        t = "\n".join(parts)
    return sha16(norm_text(t))


def content_sig(r):
    """CONTENT-only signature (system prompt excluded) — the qa L1 leak
    protocol: identical user-facing text must never straddle two splits even
    when one row carries a policy-pack system and the other is bare (e.g.
    m4-capfix pack rows vs reserve-cvalues bare rows share the same query)."""
    inp = r.get("input") or {}
    if inp.get("carrier"):
        t = inp["carrier"].get("body") or ""
    else:
        parts = []
        for x in (inp.get("messages") or inp.get("turns") or []):
            parts.append(x.get("content") if isinstance(x, dict) else x)
        if inp.get("text"):
            parts.append(inp["text"])
        t = "\n".join(parts)
    return sha16(norm_text(t))


def group_key(r):
    """Split-lock key: rows sharing input text must land in the same split
    (highest priority — prevents cross-task and same-task text leakage);
    then pair_id / dialog_id group locks."""
    meta = r.get("meta") or {}
    if meta.get("pair_id"):
        return ("pair", meta["pair_id"])
    if meta.get("dialog_id"):
        return ("dialog", meta["dialog_id"])
    return None


def assign_splits(rows, quotas, rng):
    """Split assignment with union-find locks:
    - text-sig lock: identical inputs (incl. system) always share a split —
      prevents same-text leakage across tasks and splits;
    - pair/dialog lock: minimal pairs and dialogue prefixes share a split.
    Locked components get train-dev-heldout ~75/13/12; singles fill quotas.
    """
    n = len(rows)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    sig_map = {}
    for i, r in enumerate(rows):
        s = row_sig(r)
        if s in sig_map:
            union(i, sig_map[s])
        else:
            sig_map[s] = i
    # content-only lock (qa L1 protocol): same user-facing text -> same split,
    # even across (query,pack) vs bare-query variants
    cs_map = {}
    for i, r in enumerate(rows):
        c = content_sig(r)
        if c in cs_map:
            union(i, cs_map[c])
        else:
            cs_map[c] = i
    g_map = {}
    for i, r in enumerate(rows):
        gk = group_key(r)
        if gk:
            if gk in g_map:
                union(i, g_map[gk])
            else:
                g_map[gk] = i

    comps = collections.defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)
    counts = collections.defaultdict(collections.Counter)
    locked = set()
    for comp in sorted(comps.values(), key=len, reverse=True):
        if len(comp) > 1:
            u = rng.random()
            sp = "train" if u < 0.75 else ("dev" if u < 0.88 else "heldout")
            for i in comp:
                rows[i]["split"] = sp
                locked.add(i)
                task = rows[i]["task"]
                counts[(task, rows[i]["labels"][task]["label"])][sp] += 1

    def lab_of(r):
        return r["labels"][r["task"]]["label"]

    def need(task, lab, sp):
        q = quotas.get(task, {}).get(lab)
        if not q:
            return False
        idx = {"train": 0, "dev": 1, "heldout": 2}[sp]
        return counts[(task, lab)][sp] < q[idx]

    singles = [rows[i] for i in range(n) if i not in locked]
    rng.shuffle(singles)
    # dev/heldout quotas first (train is the remainder): a small pool must not
    # be swallowed by the large train quota before dev/heldout are met
    order = ["dev", "heldout", "train"]
    for r in singles:
        task, lab = r["task"], lab_of(r)
        for sp in order:
            if need(task, lab, sp):
                r["split"] = sp
                counts[(task, lab)][sp] += 1
                break
        else:
            r["split"] = "train"
    return rows


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--out-dir", default="data/m6")
    args = ap.parse_args()
    rng = __import__("random").Random(args.seed)

    st = "data/m6/_staging"
    task_files = {
        "T1": ["t1-legacy.jsonl"],
        "T2": ["t2-legacy.jsonl", "t2-jailbreak.jsonl"],
        "T3": ["t3-legacy.jsonl", "t3-multiturn.jsonl", "t3-longctx.jsonl"],
        "T4": ["t4-pii-train.jsonl", "t4-pii-dev.jsonl", "t4-pii-heldout.jsonl"],
        "T5": ["t5-legacy.jsonl", "t5-indirect.jsonl"],
        "T6": ["t6-legacy.jsonl", "t6-instr.jsonl", "t6-instr-v2.jsonl"],
    }
    quotas = {
        "T1": {"pos": (3600, 250, 300), "neg": (3600, 600, 1200)},
        "T2": {"pos": (2400, 250, 300), "neg": (2400, 600, 1200)},
        "T3": {"pos": (2600, 250, 300), "neg": (2600, 600, 1200)},
        "T4": {"pos": (2400, 250, 300), "neg": (2400, 600, 1200)},
        "T5": {"pos": (2800, 250, 300), "neg": (2800, 600, 1200)},
        "T6": {"pos": (2200, 250, 300), "cond": (1600, 150, 150), "neg": (2200, 600, 1200)},
    }

    # 1) per-task rows (train/dev/heldout) — GLOBAL split assignment so that
    # text-sig locks hold across tasks (f5 T1 rows vs r9-paired T3 rows share
    # texts; they must never straddle splits)
    per_task = collections.defaultdict(list)
    all_rows = []
    t4_rows = []
    for task, files in task_files.items():
        pool = []
        for f in files:
            p = os.path.join(st, f)
            if os.path.exists(p):
                pool.extend(read_jsonl(p))
        if task == "T4":
            # scope files carry their split in split_hint (entity-pool
            # isolation is decided at generation time; qa L5 fix)
            for r in pool:
                row = staging_to_final(r, r.get("split_hint") or "train")
                if row["labels"]["T4"]["label"] == "cond":
                    row["labels"]["T4"]["label"] = "neg"
                row["split"] = r.get("split_hint") or "train"
                t4_rows.append(row)
            continue
        rows = [staging_to_final(r, "train") for r in pool]
        # label normalization: cond -> neg (T5/T6 GoldLabel is pos|neg only;
        # T6 keeps conditional semantics in t6_class — single source of truth;
        # T5 keeps m4 chosen-VERDICT provenance for D-12 attribution reads)
        for r in rows:
            t = r["task"]
            if t in ("T5", "T6") and r["labels"][t]["label"] == "cond":
                r["labels"][t]["label"] = "neg"
                if t == "T6":
                    r["labels"][t].setdefault("label_detail", {})["t6_class"] = "conditional"
                else:
                    r["labels"][t].setdefault("label_detail", {})["m4_verdict"] = "conditional"
            # forged-auth dual-key (t4_pos precedent): a forged authorization
            # is constructively a bypass attempt -> T2 pos (arch ruling #3)
            if (r["task"] == "T6"
                    and (r.get("meta") or {}).get("t2_pos")
                    and r["labels"]["T6"]["label"] == "pos"):
                r["labels"]["T2"] = {"label": "pos"}
        all_rows.extend(rows)
    assign_splits(all_rows, quotas, rng)

    # ---- qa L5 entity swap-out (arch P0-3: heldout stays, train side yields)
    # T4 heldout pos rows whose span entities leak into OTHER-task train texts
    # are exchanged 1:1 with clean T4 train pos rows — count-preserving, no
    # heldout row is ever edited, entity pools stay bucket-isolated.
    def _input_text(row):
        inp = row.get("input") or {}
        if inp.get("carrier"):
            return inp["carrier"].get("body") or ""
        parts = []
        if inp.get("text"):
            parts.append(inp["text"])
        for x in (inp.get("messages") or inp.get("turns") or []):
            parts.append(x.get("content") if isinstance(x, dict) else x)
        return "\n".join(parts)

    def _entities(row):
        out = []
        for tk, g in (row.get("labels") or {}).items():
            if tk == "T4" and g.get("label") == "pos":
                t = _input_text(row)
                for sp in (g.get("label_detail") or {}).get("spans", []):
                    if sp.get("end", 0) <= len(t):
                        out.append(t[sp["start"]:sp["end"]])
        return out

    other_train = [_input_text(r) for r in all_rows if r["split"] == "train"]
    other_blob = "\x00".join(other_train)
    t4_train_pos = [r for r in t4_rows
                    if r["split"] == "train" and r["labels"]["T4"]["label"] == "pos"]
    t4_held_pos = [r for r in t4_rows
                   if r["split"] == "heldout" and r["labels"]["T4"]["label"] == "pos"]
    leaking = [r for r in t4_held_pos if any(e and e in other_blob for e in _entities(r))]
    # T4 train side has legitimate intra-pool name reuse (~70% collision on
    # composed names); a swapped-in row must be name-unique against BOTH the
    # other-task train texts and the remaining T4 train rows
    t4_train_texts = {r["id"]: _input_text(r) for r in t4_train_pos}
    used = set()
    for lr in leaking:
        for tr in t4_train_pos:
            if tr["id"] in used:
                continue
            ents = _entities(tr)
            blob_excl = "\x00".join(t for tid, t in t4_train_texts.items()
                                    if tid != tr["id"])
            if any(e and (e in other_blob or e in blob_excl) for e in ents):
                continue
            used.add(tr["id"])
            tr["split"], lr["split"] = lr["split"], tr["split"]
            t4_train_texts[tr["id"]] = _input_text(lr)
            break
        else:
            raise SystemExit("no clean T4 train pos row available for entity swap")
    if leaking:
        print("t4 entity swap-out: %d heldout<->train rows exchanged" % len(leaking))

    all_rows.extend(t4_rows)
    for r in all_rows:
        per_task[r["task"]].append(r)
    for task in sorted(per_task):
        rows = per_task[task]
        cnt = collections.Counter((r["labels"][task]["label"], r["split"]) for r in rows)
        print(task, dict(cnt))

    # 2) benign base -> shared negatives (all six tasks)
    benign = read_jsonl(os.path.join(st, "benign-base.jsonl"))
    # 3) mirrors into dev
    ch_mirror = read_jsonl(os.path.join(st, "challenge-mirror.jsonl"))
    ood_mirror = read_jsonl(os.path.join(st, "ood-mirror.jsonl"))

    def shared_final(r, split, task_key):
        return staging_to_final(r, split, task_override=task_key, force_label="neg")

    # write per-task dirs; task view = own rows + shared-benign negatives
    # projected per task (train/dev), so every task's train neg gate >=2000
    # holds even when its in-domain negative pool is small (e.g. T2 near-miss)
    out = args.out_dir
    slug = {"T1": "t1-moderation", "T2": "t2-jailbreak", "T3": "t3-intent",
            "T4": "t4-pii", "T5": "t5-indirect", "T6": "t6-highrisk"}
    manifest_files = []

    def proj_benign(task, rows_b, split):
        """Per-task view projection of shared benign negatives (id suffixed)."""
        out_rows = []
        for r in rows_b:
            pr = staging_to_final(r, split, task_override=task, force_label="neg")
            pr["id"] = "%s-%s" % (pr["id"], task.lower())
            out_rows.append(pr)
        return out_rows

    benign_train_proj = benign[6000:8100]
    benign_dev_proj = benign[8100:8700]
    benign_held_proj = benign[3500:4500]
    for task, rows in per_task.items():
        d = os.path.join(out, slug[task])
        for sp in ["train", "dev", "heldout"]:
            sub = [r for r in rows if r["split"] == sp]
            if task != "T4":  # T4 negatives must be span-annotated domain rows
                if sp == "train":
                    sub = sub + proj_benign(task, benign_train_proj, "train")
                elif sp == "dev":
                    sub = sub + proj_benign(task, benign_dev_proj, "dev")
                elif sp == "heldout":
                    sub = sub + proj_benign(task, benign_held_proj, "heldout")
            write_jsonl(os.path.join(d, sp + ".jsonl"), sub)
            manifest_files.append((os.path.join(slug[task], sp + ".jsonl"), len(sub)))

    # shared negatives into dev + heldout of every task (cross-task pool)
    rng_b = __import__("random").Random(args.seed + 5)
    benign_dev = [shared_final(r, "dev", "pool") for r in benign[:3500]]
    benign_held = [shared_final(r, "heldout", "pool") for r in benign[3500:6000]]
    # mirrors carry their family flag so D8 OR-gate calibration and challenge
    # FPR stats can identify mirror rows inside pool/dev (deveng finding #1)
    chm_rows = [shared_final(r, "dev", "pool") for r in ch_mirror]
    for r in chm_rows:
        r["flags"] = {"ood": False, "challenge": True, "holdout_family": None,
                      "ambiguous": False}
        r.setdefault("meta", {})["eval_family"] = "challenge"
    oodm_rows = [shared_final(r, "dev", "pool") for r in ood_mirror]
    for r in oodm_rows:
        r["flags"] = {"ood": True, "challenge": False, "holdout_family": None,
                      "ambiguous": False}
        r.setdefault("meta", {})["eval_family"] = "ood"
    for r in benign_dev:
        r.setdefault("meta", {})["eval_family"] = "benign"

    # 4) challenge / ood eval dirs (six-key labels)
    challenge = read_jsonl(os.path.join(st, "challenge.jsonl"))
    ood = read_jsonl(os.path.join(st, "ood.jsonl"))

    def six_key_shared(r, split, flags):
        base = staging_to_final(r, split, task_override="pool", force_label="neg")
        base["flags"] = flags
        return base

    ch_rows = [six_key_shared(r, "challenge", {"ood": False, "challenge": True,
                                               "holdout_family": None, "ambiguous": False})
               for r in challenge]
    ood_rows = [six_key_shared(r, "ood", {"ood": True, "challenge": False,
                                          "holdout_family": None, "ambiguous": False})
                for r in ood]
    write_jsonl(os.path.join(out, "challenge", "all.jsonl"), ch_rows)
    write_jsonl(os.path.join(out, "ood", "all.jsonl"), ood_rows)
    manifest_files.append(("challenge/all.jsonl", len(ch_rows)))
    manifest_files.append(("ood/all.jsonl", len(ood_rows)))

    # dev mirrors file (lives in dev for threshold calibration, U4)
    write_jsonl(os.path.join(out, "dev-mirror", "challenge-mirror.jsonl"), chm_rows)
    write_jsonl(os.path.join(out, "dev-mirror", "ood-mirror.jsonl"), oodm_rows)
    write_jsonl(os.path.join(out, "dev-mirror", "benign-dev.jsonl"), benign_dev)
    manifest_files.append(("dev-mirror/challenge-mirror.jsonl", len(chm_rows)))
    manifest_files.append(("dev-mirror/ood-mirror.jsonl", len(oodm_rows)))
    manifest_files.append(("dev-mirror/benign-dev.jsonl", len(benign_dev)))

    # heldout shared negatives file
    write_jsonl(os.path.join(out, "heldout-shared", "benign-heldout.jsonl"), benign_held)
    manifest_files.append(("heldout-shared/benign-heldout.jsonl", len(benign_held)))

    # 5) pool/ joint view: per-task train/dev rows + shared benign (six-key)
    pool_rows = []
    for task, rows in per_task.items():
        for r in rows:
            if r["split"] in ("train", "dev"):
                pool_rows.append(r)
    # arch ruling (post-v1-2 saturation review, uniform-neg projection):
    # T6 synth-instr TRAIN rows carry cross-task neg labels in the pool view —
    # closes the zero-supervision gap that made the T2 head fire on
    # authorized-ops phrasing. DEV/HELDOUT rows stay single-key (calibration
    # tau guard: no projection enters the calibration pool or FPR denominators)
    _PROJ_DETAIL = {
        "T1": None, "T2": None, "T3": None,
        "T4": {"spans": []},
        "T5": {"carrier": "other", "mechanism": None, "carrier_site": ""},
    }
    # arch pre-condition (projection gate): T4/T5 are OBJECTIVE pattern
    # detectors — an authorized-ops narrative does not exempt real-shaped PII
    # or injection patterns from their gold. Blanket T4/T5-neg projection is
    # only valid on rows where both extractors score ZERO hits; any hit row
    # stays single-key (conservative — no wrong gold, arch rules on manual
    # pos+spans if a hit ever fires).
    _PROJ_GATE_PII = __import__("re").compile(
        r"(?<!\d)1[3-9]\d{9}(?!\d)"                      # zh mobile
        r"|(?<!\d)\d{17}[\dXx](?!\d)"                    # resident id
        r"|(?<!\d)62\d{14,17}(?!\d)"                     # bank card
        r"|(?<!\d)\d{3,4}-\d{7,8}(?!\d)"                 # landline
        # person-shaped email: ANY domain (example.* included — T4 gold marks
        # person-shaped example-domain emails as pos, 106/540 in current T4
        # views; the gate must stay CONSISTENT with that labeling practice).
        # Service-shaped locals (noreply/test/postmaster/admin/info) are the
        # placeholder form and stay exempt.
        r"|(?<![\w.+-])(?!noreply[\w.+-]*@|test[\w.+-]*@|postmaster[\w.+-]*@"
        r"|admin[\w.+-]*@|info[\w.+-]*@)[\w.+-]+@[\w.-]+")
    _PROJ_GATE_INJ = __import__("re").compile(
        r"忽略(?:之前|以上|前面)|无视(?:之前|以上)"
        r"|ignore (?:the )?(?:previous|above)|disregard (?:the )?(?:above|previous)"
        r"|system prompt|系统提示词", __import__("re").I)
    gate_blocked = []
    gate_hits = []
    gate_scope = collections.Counter()
    gate_pii_hits = gate_inj_hits = 0

    n_proj = 0
    for r in pool_rows:
        if (r["task"] == "T6" and r["split"] == "train"
                and (r.get("source") or {}).get("family") in ("synth-instr-v1",
                                                              "synth-instr-v2")):
            # arch tightening ruling: project ONLY conditional + safe rows
            # (verifiable-authorization => not-bypass/not-harmful is a
            # constructive implication). high-risk rows keep the T6-only key —
            # their cross-task polarity is undetermined and projection would
            # be guessing (the cvalues failure mode).
            if r["labels"]["T6"]["label"] != "neg":
                continue
            gate_scope[(r["labels"]["T6"].get("label_detail") or {}).get(
                "t6_class", "?")] += 1
            t = _input_text(r)
            pii_m = _PROJ_GATE_PII.search(t)
            inj_m = _PROJ_GATE_INJ.search(t)
            if pii_m or inj_m:
                gate_blocked.append(r["id"])
                gate_hits.append((r["id"], pii_m.group(0) if pii_m else None,
                                  inj_m.group(0) if inj_m else None))
                if pii_m:
                    gate_pii_hits += 1
                if inj_m:
                    gate_inj_hits += 1
                continue  # stay single-key — no blanket T4/T5-neg on pattern hits
            for tk, det in _PROJ_DETAIL.items():
                r["labels"][tk] = {"label": "neg"}
                if det is not None:
                    r["labels"][tk]["label_detail"] = det
            n_proj += 1
    # hard assertion: any projected row with a gate hit is a build failure
    # (same discipline as the cvalues purity assertion)
    leaked = [g for g in gate_hits
              if any(rr["id"] == g[0] and len(rr["labels"]) >= 6 for rr in pool_rows)]
    if leaked:
        print("PROJECTION GATE FAIL: %d rows projected despite pattern hits" % len(leaked))
        for g in leaked[:10]:
            print("  -", g)
        raise SystemExit(3)
    if gate_hits:
        print("projection gate: %d candidate rows withheld (pattern hits, kept single-key):"
              % len(gate_hits))
        for g in gate_hits[:10]:
            print("  -", g)
    print("cross-task neg projection (pool/train, T6 synth-instr cond+safe, gate-passed): %d rows" % n_proj)
    projection_gate = {
        "checked": n_proj + len(gate_blocked),
        "t4_hits": gate_pii_hits,
        "t5_hits": gate_inj_hits,
        "revoked_to_pos": 0,   # hit rows converted to T4 pos+spans (none — arch rules manually if ever)
        "revoked_exit": len(gate_blocked),  # hit rows kept single-key
        "assert": "PASS" if not leaked else "FAIL",
        "scope": {"classes_gated": dict(gate_scope)},
        "note": "gate extractors: real-shaped PII regex (RFC 5737 ranges + "
                "example.* treated as placeholder semantics) + injection "
                "marker regex; hits stay single-key (no blanket T4/T5-neg)",
    }
    # shared benign as six-key negatives in pool
    for r in benign[6000:9500]:
        base = staging_to_final(r, "train", task_override="pool", force_label="neg")
        pool_rows.append(base)
    # dedup by input hash
    seen = set()
    pool_final = []
    for r in pool_rows:
        h = sha16(norm_text(json.dumps(r["input"], ensure_ascii=False, sort_keys=True)))
        if h in seen:
            continue
        seen.add(h)
        pool_final.append(r)
    write_jsonl(os.path.join(out, "pool", "train.jsonl"),
                [r for r in pool_final if r["split"] == "train"])
    write_jsonl(os.path.join(out, "pool", "dev.jsonl"),
                [r for r in pool_final if r["split"] == "dev"] + chm_rows + oodm_rows + benign_dev)
    manifest_files.append(("pool/train.jsonl", sum(1 for r in pool_final if r["split"] == "train")))
    manifest_files.append(("pool/dev.jsonl", sum(1 for r in pool_final if r["split"] == "dev") + len(chm_rows) + len(oodm_rows) + len(benign_dev)))

    # 6) isolation check + manifest (v2 per schema v0.3.8)
    iso = isolation_report(out)

    # shape-mix / pair-integrity stats (manifest registration per sysdesign U5)
    def _stats(rows):
        t3 = collections.Counter()
        t5 = collections.Counter()
        pr5 = collections.defaultdict(set)
        pr3 = collections.defaultdict(set)
        prd = collections.defaultdict(set)
        for r in rows:
            t = r["task"]
            inp = r.get("input") or {}
            if t == "T3":
                if inp.get("messages"):
                    t3["messages_with_assistant"] += 1
                elif inp.get("turns"):
                    t3["user_only"] += 1
                else:
                    t3["text_longctx"] += 1
                did = (r.get("meta") or {}).get("dialog_id")
                if did:
                    prd[did].add(r["split"])
            if t == "T5":
                if inp.get("carrier"):
                    t5["carrier_structured:" + inp["carrier"].get("envelope_style", "std_tag")] += 1
                else:
                    t5["text_legacy"] += 1
                pid = (r.get("meta") or {}).get("pair_id")
                if pid:
                    pr5[pid].add(r["split"])
            if t in ("T1", "T6"):
                pid = (r.get("meta") or {}).get("pair_id")
                if pid:
                    pr3[pid].add(r["split"])
        return t3, t5, pr5, pr3, prd

    all_final = [r for rows in per_task.values() for r in rows]
    t3m, t5m, pr5, pr3, prd = _stats(all_final)

    def file_entry(rel_path, n):
        """v2 file entry: split/task inferred from path, sha256 + label_counts
        computed from the written file (schema v0.3.8)."""
        rel = rel_path.replace("\\", "/")
        sp = "challenge" if rel.startswith("challenge/") else \
             "ood" if rel.startswith("ood/") else \
             "heldout" if rel.startswith("heldout-shared/") else \
             "train" if rel.endswith("/train.jsonl") or rel == "pool/train.jsonl" else \
             "dev" if rel.endswith("/dev.jsonl") or rel == "pool/dev.jsonl" else \
             "heldout" if rel.endswith("/heldout.jsonl") else "dev"
        if rel.startswith("challenge/"):
            task = "pool"
        elif rel.startswith("ood/"):
            task = "pool"
        elif rel.startswith("heldout-shared/"):
            task = "shared-benign"
        else:
            task = {"t1-moderation": "T1", "t2-jailbreak": "T2", "t3-intent": "T3",
                    "t4-pii": "T4", "t5-indirect": "T5", "t6-highrisk": "T6",
                    "pool": "pool"}.get(rel.split("/")[0], "pool")
        import hashlib
        h = hashlib.sha256()
        lc = collections.defaultdict(collections.Counter)
        with open(os.path.join(out, rel), "rb") as fb:
            for chunk in iter(lambda: fb.read(1 << 20), b""):
                h.update(chunk)
        with open(os.path.join(out, rel), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                for tk, g in (r.get("labels") or {}).items():
                    lc[tk][g.get("label", "?")] += 1
        return {"path": rel, "n": n, "rows": n, "split": sp, "task": task,
                "sha256": h.hexdigest(),
                "label_counts": {tk: {"pos": c.get("pos", 0), "neg": c.get("neg", 0)}
                                 for tk, c in lc.items()}}

    # dev-mirror files are byte-identical subsets of pool/dev — registered once
    # via pool/dev; mirror files listed with subset_of marker only
    mirror_files = []
    files_v2 = []
    for p, n in manifest_files:
        if p.startswith("dev-mirror"):
            mirror_files.append(p.replace("\\", "/"))
            continue
        files_v2.append(file_entry(p, n))

    manifest = {
        "schema": "m6-manifest",
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "m6-data-v1",
        "created": "2026-10-21",
        "generator": {
            "script": "scripts/m6/build_all.py",
            "seed": args.seed,
            "staging_generators": [
                "gen_pii.py", "gen_indirect.py", "gen_multiturn.py", "gen_longctx.py",
                "gen_t2_jailbreak.py", "gen_t6.py", "gen_pools.py", "convert_legacy.py",
            ],
        },
        "files": files_v2,
        "dev_mirror_note": "dev-mirror/*.jsonl are byte-identical subsets of pool/dev.jsonl "
                           "(challenge-mirror flags.challenge=true, ood-mirror flags.ood=true); "
                           "kept as standalone files for qa/loader convenience: %s" % mirror_files,
        "scale_gates": {
            "heldout_pos_min_per_task": 200,
            "heldout_neg_min_per_task": 1000,
            "challenge_min": 1200,
            "ood_min": 300,
            "train_pos_min_per_task": 2000,
            "train_neg_min_per_task": 2000,
        },
        "risk_domain_enum": [d for d, _ in RISK_DOMAIN_RULES] + [RISK_DOMAIN_DEFAULT],
        "pii_type_table": {t: RISK_OF_TYPE[t] for t in RISK_OF_TYPE},
        "shape_mix": {
            "t3": dict(t3m),
            "t5": dict(t5m),
            "t5_note": "synth rows -> input.carrier + envelope_style (Option A, arch ruling); "
                       "legacy rows keep input.text as protocol-free coverage",
        },
        "pair_integrity": {
            "t5_pairs": len(pr5), "t5_pairs_cross_split": sum(1 for s in pr5.values() if len(s) > 1),
            "f5_policy_pairs": len(pr3), "f5_policy_cross_split": sum(1 for s in pr3.values() if len(s) > 1),
            "t3_dialog_groups": len(prd), "t3_dialogs_cross_split": sum(1 for s in prd.values() if len(s) > 1),
        },
        "frozen_suites": {
            "reference": "data/heldout/ (v0.2.3 / v0.3-gen / v0.4-toolout / v0.5-toolout-reg / "
                         "v0.5-topup-families / v0.6-document / v0.6-dilution / v0.7-jailbreak)",
            "leak_audit": "reports/m6/leak-audit.md (body-level zero overlap; 14 B1 hits "
                          "attributed to shared policy-pack template ancestry)",
        },
        "projection_gate": projection_gate,
        "disjointness": {
            **iso,
            "protocol": {
                "exact": "norm_text = NFKC -> lowercase -> whitespace-collapse; sha256[:16] of "
                         "full input text (system + content, carrier body fallback); "
                         "train side (t*/train + pool/train) vs eval side (t*/heldout, "
                         "challenge/, ood/)",
                "near_dup": "8-gram shingle containment >30% — see reports/m6/leak-audit.md "
                            "(heldout frozen suites vs training side, B1/B2 levels)",
                "entity": "T4 heldout span entity text vs ALL train-side row texts "
                          "(substring match, qa L5 leak-check protocol)",
                "nfkc": True,
                "schema_version": SCHEMA_VERSION,
            },
        },
        "notes": [
            "T4 pos spans are char offsets (end-exclusive), risk derived from type table.",
            "T6 labels: pos <=> t6_class=high-risk (single source of truth, adr-1b 6.2).",
            "T5 cond rows (753 in t5-indirect) are projected to neg per GoldLabel "
            "pos|neg enum (arch D-12 ruling); conditional semantics retained in "
            "label_detail.mechanism.",
            "T3 shape mix (arch H6 review): user_only=2239 (39%) / messages_with_assistant=3582 "
            "(61%, r9-paired seeds) / longctx=2900 — absolute coverage sufficient for v1; "
            "v0.7 eval-shape (user-only) generalization listed as task-10 watch item.",
            "T5 Option A (arch ruling): ALL synth carrier rows -> input.carrier + envelope_style "
            "(gold anchors on carrier.body raw text); legacy rows keep input.text as "
            "protocol-envelope-free coverage; label_detail.envelope mirrors carrier.envelope_style.",
            "challenge medical-PII subset: labels.T4=pos with real span gold, excluded from chFPR "
            "denominator; other five task keys remain hard negatives.",
            "Ethanol discipline: data/heldout/ never read for construction (README-only + task-6 "
            "read-only leak audit).",
        ],
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("manifest written; isolation:", json.dumps(iso, ensure_ascii=False))


def isolation_report(out):
    """A1-A4 disjointness: exact hash overlap between train and eval splits."""
    def load(p):
        rows = read_jsonl(p)
        return rows

    def sigs(rows):
        return set(row_sig(r) for r in rows)

    import glob
    train_rows, eval_rows = [], []
    for p in glob.glob(os.path.join(out, "*", "train.jsonl")):
        train_rows.extend(load(p))
    for sub in ["heldout", "challenge", "ood"]:
        for p in glob.glob(os.path.join(out, "*", sub + ".jsonl")) + \
                 glob.glob(os.path.join(out, sub, "*.jsonl")):
            eval_rows.extend(load(p))
    tr, ev = sigs(train_rows), sigs(eval_rows)
    inter = tr & ev
    # qa L1 protocol: content-only overlap (system prompt excluded) must be 0
    cs_tr = set(content_sig(r) for r in train_rows)
    cs_ev = set(content_sig(r) for r in eval_rows)
    content_overlap = len(cs_tr & cs_ev)

    # A3: dev-mirror (calibration) must be disjoint from challenge/ood eval sets
    mirror_rows = []
    for p in glob.glob(os.path.join(out, "dev-mirror", "*.jsonl")):
        mirror_rows.extend(load(p))
    mr = sigs(mirror_rows)
    mirror_overlap = len(mr & ev)

    # arch check #1: OOD set must be PII-free (no T4 pos rows)
    ood_t4_pos = 0
    for p in glob.glob(os.path.join(out, "ood", "*.jsonl")):
        for r in load(p):
            t4 = (r.get("labels") or {}).get("T4") or {}
            if t4.get("label") == "pos":
                ood_t4_pos += 1

    # qa L5: entity-level isolation — heldout T4 span entity texts must not
    # appear as substrings anywhere on the train side (per leak-check-h1)
    t4_held_entities = []
    for p in glob.glob(os.path.join(out, "t4-pii", "heldout.jsonl")):
        for r in load(p):
            inp = r.get("input") or {}
            t = inp.get("text") or ""
            for sp in ((r.get("labels") or {}).get("T4", {}).get("label_detail") or {}).get("spans", []):
                if sp.get("end", 0) <= len(t):
                    t4_held_entities.append(t[sp["start"]:sp["end"]])
    train_texts = []
    for p in glob.glob(os.path.join(out, "*", "train.jsonl")):
        for r in load(p):
            inp = r.get("input") or {}
            if inp.get("carrier"):
                train_texts.append(inp["carrier"].get("body") or "")
            else:
                parts = [inp.get("text") or ""]
                for x in (inp.get("messages") or inp.get("turns") or []):
                    parts.append(x.get("content") if isinstance(x, dict) else x)
                train_texts.append("\n".join(parts))
    train_blob = "\x00".join(train_texts)
    t4_ent_overlap = sum(1 for e in t4_held_entities if e and e in train_blob)

    ok = (not inter and not content_overlap and not mirror_overlap
          and ood_t4_pos == 0 and t4_ent_overlap == 0)
    return {
        "train_rows": len(train_rows), "eval_rows": len(eval_rows),
        "exact_overlap": len(inter),
        "content_overlap_qa_l1": content_overlap,
        "mirror_eval_overlap": mirror_overlap,
        "ood_t4_pos_rows": ood_t4_pos,
        "t4_entity_overlap": t4_ent_overlap,
        "t4_heldout_entities_checked": len(t4_held_entities),
        "assert": "PASS" if ok else "FAIL",
    }


if __name__ == "__main__":
    main()
