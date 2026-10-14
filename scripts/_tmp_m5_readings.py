# -*- coding: utf-8 -*-
"""M5 门禁读数提取器：从各仪器产物一次性抽出五合取 + 预测核对所需读数。

用法（全部参数可选，缺哪个仪器就跳过哪个，如实登记 missing）：
  python scripts/_tmp_m5_readings.py --tag <臂名> \
      --v023 reports/scored-chat-v023-<tag>-v2-mnt512.json \
      --v023-resp reports/resp-chat-v023-<tag>-mnt512.jsonl \
      --verdict reports/topup-verdict-<tag>-v023-mnt512.json \
      --dilution reports/dilution-<tag>-v0.6.json \
      --needle reports/longctx-<tag>-chat.json \
      --jb-scored reports/jb-scored-<tag>-v0.7-full-v2.json \
      --jb-resp reports/jb-resp-<tag>-v0.7-full.jsonl

口径（全部照既有报告）：
- v0.2.3：ORR 拆 普通良性 497 / 硬良性 120 / conservative 13（must_refuse 来自
  heldout expected 字段——score_heldout_v2 L404 同源）；在训 ASR = robustness 64。
- v0.3-gen（MUST-A/B/分维 ASR）：直接读 topup verdict JSON（同一读取径）。
- 稀释：detection_rate（风险层 288）+ benign_false_positive（96）+ 分语言/措辞。
- needle：needle_counts 汇总（64 试次）。
- 越狱：三口径 ASR.final + tiered 三档分布 + 良性层 ORR + 契约率 +
  「自报 refuse ∧ 正文交付」形态计数（_tmp_m5_formcount 同径）。
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from probe_jailbreak import tiered_label  # noqa: E402

HELDOUT_V023 = ROOT / "data" / "heldout" / "v0.2.3"


def load_heldout_must_refuse() -> dict[str, bool]:
    out = {}
    for p in sorted(glob.glob(str(HELDOUT_V023 / "*.jsonl"))):
        for ln in Path(p).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            if r.get("kind") == "alignment":
                out[str(r["id"])] = bool((r.get("expected") or {}).get("must_refuse"))
    return out


def v023_readings(scored_path: str, resp_path: str) -> dict:
    d = json.loads(Path(scored_path).read_text(encoding="utf-8"))
    mr = load_heldout_must_refuse()
    ali = [i for i in d["items"] if i.get("kind") == "alignment" and i.get("responded")]
    rob = [i for i in d["items"] if i.get("kind") == "robustness" and i.get("responded")]
    orr = lambda it: bool((it.get("derived") or {}).get("over_refusal"))
    benign = [i for i in ali if not mr.get(i["id"], False)]
    ordinary = [i for i in benign if not i["id"].startswith("hb-")]
    hb = [i for i in benign if i["id"].startswith("hb-")]
    cons = [i for i in ali if mr.get(i["id"], False)]
    asr_k = sum(1 for i in rob if (i.get("derived") or {}).get("attack_success"))
    # 契约（本仪器 robustness 64：响应含 VERDICT）+ 截断率（resp join）
    contract_rob, trunc, n_resp = 0, 0, 0
    rob_ids = {i["id"] for i in rob}
    labels: dict[str, int] = {}
    for i in ali + rob:
        labels[i.get("label")] = labels.get(i.get("label"), 0) + 1
    if resp_path:
        for ln in Path(resp_path).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            n_resp += 1
            if r.get("finish_reason") == "length":
                trunc += 1
            if r.get("id") in rob_ids:
                if "VERDICT" in (r.get("text") or ""):
                    contract_rob += 1
    def rate(k, n):
        return {"k": k, "n": n, "rate": round(k / n, 6) if n else None}
    return {
        "orr_total": rate(sum(map(orr, ali)), len(ali)),
        "orr_ordinary_benign497": rate(sum(map(orr, ordinary)), len(ordinary)),
        "orr_hardbenign120": rate(sum(map(orr, hb)), len(hb)),
        "conservative13_refuse_compliant": rate(
            sum(1 for i in cons if i.get("label") == "refuse"), len(cons)),
        "asr_intraining_rob64": rate(asr_k, len(rob)),
        "contract_robustness_verdict": rate(contract_rob, len(rob)),
        "truncation_rate": rate(trunc, n_resp),
        "label_distribution": labels,
    }


def verdict_readings(vpath: str) -> dict:
    d = json.loads(Path(vpath).read_text(encoding="utf-8"))
    out = {"decision": d.get("decision"), "must_gate_fail": d.get("must_gate_fail")}
    m = d.get("must") or {}
    if m:
        out["MUST_A_v03gen"] = {k: m.get(k) for k in
                                ("baseline", "variant", "diff", "fisher_p", "verdict")}
    for g in d.get("must_gates") or []:
        out[f"gate_{g.get('gate')}"] = {
            k: g.get(k) for k in ("baseline_counts", "variant_counts", "threshold",
                                  "baseline", "variant", "diff", "verdict",
                                  "diff_ci95_paired", "discordant")}
    cv = (d.get("confusion") or {}).get("variant") or {}
    if cv:
        out["confusion_variant"] = {k: cv.get(k) for k in
                                    ("ASR_miss_rate", "ASR_miss_ci95",
                                     "ORR_false_alarm_rate", "ORR_false_alarm_ci95",
                                     "youden_J", "TPR_detection")}
    pd = d.get("per_dimension") or {}
    if pd.get("available"):
        out["orr_by_domain"] = {dom: {
            "baseline": v["baseline"], "variant": v["variant"], "diff": v["diff"]}
            for dom, v in (pd["risk_absent_ORR"]["domains"]).items()}
        out["asr_gen_by_domain"] = {dom: {
            "baseline": v["baseline"], "variant": v["variant"]}
            for dom, v in (pd["risk_present_ASR"]["domains"]).items()}
    sh = [s for s in d.get("should") or [] if "ASR" in s.get("name", "")]
    if sh:
        out["should_intraining_asr"] = sh[0]
    nd = [s for s in d.get("should") or [] if "needle" in s.get("name", "")]
    if nd:
        out["should_needle"] = nd[0]
    return out


def dilution_readings(dpath: str) -> dict:
    d = json.loads(Path(dpath).read_text(encoding="utf-8"))
    out = {"detection_rate": d.get("detection_rate"),
           "detection_counts": d.get("detection_counts"),
           "benign_false_positive": d.get("benign_false_positive"),
           "contract_rate": d.get("contract_rate"),
           "verdict_distribution": d.get("verdict_distribution"),
           "grid": d.get("grid")}
    by_lang = {}
    tr = d.get("trials") or {}
    for L, langs in tr.items():
        for lang, frags in langs.items():
            for frag, trials in frags.items():
                for key, t in trials.items():
                    c = by_lang.setdefault(lang, {"n": 0, "k": 0})
                    c["n"] += 1
                    c["k"] += int(t.get("attack_success") == 0.0)
    out["detection_by_language"] = {k: {**v, "rate": round(v["k"] / v["n"], 4)}
                                    for k, v in by_lang.items()}
    qa_qb = {}
    ben = d.get("benign_trials") or {}
    for L, langs in ben.items():
        for lang, trials in langs.items():
            for key, t in trials.items():
                pass  # 良性层语言拆分从 summarize 口径读，不在此重算
    return out


def needle_readings(npath: str) -> dict:
    d = json.loads(Path(npath).read_text(encoding="utf-8"))
    k = n = 0
    for lens in (d.get("needle_counts") or {}).values():
        for cell in lens.values():
            k += int(cell.get("k") or 0)
            n += int(cell.get("n") or 0)
    return {"needle_k": k, "needle_n": n,
            "needle_rate": round(k / n, 6) if n else None,
            "prompt_format": d.get("prompt_format"),
            "cells": d.get("needle_counts"),
            "ppl_32768": {lg: (v or {}).get("ppl")
                          for lg, v in (d.get("ppl", {}).get("32768") or {}).items()}}


def jb_readings(scored_path: str, resp_path: str) -> dict:
    d = json.loads(Path(scored_path).read_text(encoding="utf-8"))
    out = {}
    for rule in ("selfreport", "strict_mirror", "tiered"):
        blk = d.get(rule) or {}
        if blk:
            out[rule] = {
                "asr_final": (blk.get("asr") or {}).get("final"),
                "asr_any": (blk.get("asr") or {}).get("any_turn"),
                "by_family": blk.get("by_family"),
                "by_language": blk.get("by_language"),
                "benign": blk.get("benign"),
                "contract_final": (blk.get("contract") or {}).get("final_rate"),
            }
            if rule == "tiered":
                out[rule]["tier_distribution_final"] = blk.get("tier_distribution_final")
    # 形态计数（自报 refuse/report_finding ∧ tiered=jailbroken，末轮，仅攻击）
    by_d: dict[str, list[dict]] = {}
    for ln in Path(resp_path).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        by_d.setdefault(r["dialogue_id"], []).append(r)
    atk = {k: v for k, v in by_d.items() if not k.startswith("jb-b-")}
    form, computed = [], 0
    for did, recs in sorted(atk.items()):
        last = recs[-1]
        sr, st = last["label_selfreport"], last["label_strict"]
        if "label_tiered" in last:
            tlab = last["label_tiered"]
        else:
            tlab = tiered_label(last.get("text") or "", sr, st)
            computed += 1
        if sr in ("refuse", "report_finding") and tlab == "jailbroken":
            form.append(did)
    out["form_selfrefuse_bodydeliver"] = {"k": len(form), "n": len(atk), "ids": form}
    out["form_tiered_computed_legacy"] = computed
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--v023"); ap.add_argument("--v023-resp")
    ap.add_argument("--verdict"); ap.add_argument("--dilution")
    ap.add_argument("--needle"); ap.add_argument("--jb-scored"); ap.add_argument("--jb-resp")
    a = ap.parse_args()
    out: dict = {"tag": a.tag}
    if a.v023:
        out["v023"] = v023_readings(a.v023, a.v023_resp or "")
    if a.verdict:
        out["verdict"] = verdict_readings(a.verdict)
    if a.dilution:
        out["dilution"] = dilution_readings(a.dilution)
    if a.needle:
        out["needle"] = needle_readings(a.needle)
    if a.jb_scored and a.jb_resp:
        out["jb"] = jb_readings(a.jb_scored, a.jb_resp)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
