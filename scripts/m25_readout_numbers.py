# -*- coding: utf-8 -*-
"""M2.5 读数汇总：把出口判定所需的全部数字一次打全（供 14:00 读数与决策）。

只读 reports/ 下已产出的 json，不做任何测量、不写任何文件（除 stdout）。
用法：
  python scripts/m25_readout_numbers.py                      # 历史 raw 口径
  python scripts/m25_readout_numbers.py --suffix chat- \
      --verdict m25-exit-verdict-chat                        # 部署格式口径
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"


def load(n):
    p = R / n
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", default="",
                    help="判分文件名前缀后缀（如 chat-），用于部署格式口径")
    ap.add_argument("--verdict", default="m25-exit-verdict",
                    help="出口判定文件名（不含 -{tag}.json）")
    args = ap.parse_args()
    suf = args.suffix
    print(f"[readout] suffix={suf!r} verdict-file={args.verdict}")
    print("=" * 72)
    print("A. 32k 锚（longctx PPL：同长度同文档，跨阶段可比）")
    print("=" * 72)
    a = load("m25-anchor-decision.json") or {}
    anc = a.get("anchor", {})
    if anc.get("m25full"):
        for lens in ("16384", "32768"):
            for lang in ("en", "zh"):
                m15 = anc["m15"][lens][lang]
                m2 = anc["m2full"][lens][lang]
                cu = anc["m25full"][lens][lang]
                d15 = anc.get(f"delta_{lens}_{lang}_pct")
                print(f"  {lens}/{lang}: m15={m15:8.3f}  m2full={m2:8.3f}  "
                      f"m25={cu:8.3f} | vs m15 {d15:+7.2f}%  vs m2 "
                      f"{100 * (cu / m2 - 1):+6.2f}%")
    print(f"  needle: m15={a.get('needle', {}).get('m15')} "
          f"m2full={a.get('needle', {}).get('m2full')} "
          f"m25full={a.get('needle', {}).get('m25full')} (水位线 9)")

    print()
    print("=" * 72)
    print("B. 通用 PPL（v0.3 门禁口径 / v0.4 干净口径）")
    print("=" * 72)
    gp = a.get("general_ppl", {})
    for ver in ("v0.3", "v0.4"):
        blk = gp.get(ver) or {}
        print(f"  [{ver}]")
        for k in ("general_en", "general_zh", "privacy"):
            if k in blk:
                v = blk[k]
                print(f"    {k:12} m15={v['m15']:8.4f} -> m25={v['cur']:8.4f}  "
                      f"{v['delta_pct']:+7.2f}%")
    print("  → v0.3 与 v0.4 的 general_en 幅度几乎相同 = 漂移真实（非探针污染）")

    print()
    print("=" * 72)
    print("C. 行为读数（heldout v0.2.1, judge v2）")
    print("=" * 72)
    rows = [("c1full", "c1-full"), ("m15", "m15"), ("m2calib", "m2-calib"),
            ("m2full", "m2-full"), ("m25full", "m25-full")]
    print(f"  {'模型':10} {'asr':>7} {'fwd':>7} {'nonfwd':>7} {'ORR':>7} "
          f"{'fmt':>7}  labels(report/refuse/deflect/comply/fmt)")
    for tag, label in rows:
        d = load(f"scored-{suf}{tag}-v2.json")
        if not d:
            continue
        m, ld = d["metrics"], d["label_distribution"]
        nf = m.get("asr_nonforward")
        print(f"  {label:10} {m['asr']:7.4f} {m['asr_forward']:7.3f} "
              f"{(nf if nf is not None else float('nan')):7.3f} "
              f"{m['over_refusal_rate']:7.4f} {m['format_error_rate']:7.4f}  "
              f"{ld['report_finding']}/{ld['refuse']}/{ld['deflect']}/"
              f"{ld['comply']}/{ld['format_error']}")

    print()
    print("=" * 72)
    print("D. tool_output 8 条未见载体（**M2.5 主读数**）")
    print("=" * 72)
    for tag in ("m2calib", "m2full", "m25full"):
        d = load(f"scored-{suf}{tag}-tooloutput-v2.json")
        if not d:
            continue
        ld = d["label_distribution"]
        defended = (ld["report_finding"] + ld["refuse"] + ld["deflect"])
        print(f"  {tag:8} n={d['n']} asr={d['metrics']['asr']:.2f} | "
              f"defended={defended}/{d['n']} | "
              f"report={ld['report_finding']} refuse={ld['refuse']} "
              f"comply={ld['comply']} fmt={ld['format_error']}")

    print()
    print("=" * 72)
    print("E. 出口判定（m25-exit-verdict.json）")
    print("=" * 72)
    v = load(f"{args.verdict}-m25full.json") or load(f"{args.verdict}-m3dpo.json") or {}
    print(f"  VERDICT={v.get('verdict')}  gate_version={v.get('gate_version')}  "
          f"passed={v.get('passed')}  failed={v.get('failed')}  "
          f"missing={v.get('missing', v.get('missing_inputs'))}  "
          f"undecided={len(v.get('undecided') or [])}")
    for w in (v.get("warnings") or []):
        print(f"  [warn] {w}")
    # 键名按前缀查找（I6：不要再硬编码 _vs_m15 / _vs_25full 之类）
    g2k = next((k for k in (v.get("gates") or {}) if k.startswith("G2_")), None)
    g2 = (v.get("gates") or {}).get(g2k, {}) if g2k else {}
    if g2.get("v0.4_clean_note"):
        print("  G2 的 v0.4 附注：",
              json.dumps(g2["v0.4_clean_note"], ensure_ascii=False))
    if g2.get("present") and not g2.get("legacy"):
        for k, cell in (g2.get("domains") or {}).items():
            print(f"  G2 {k}: 增量 vs {g2.get('prev_tag')}="
                  f"{cell.get('delta_pct_vs_prev')}% (cap 10) | 绝对 vs "
                  f"{g2.get('base_tag')}={cell.get('delta_pct_vs_base')}% "
                  f"(上限 {cell.get('ceiling_pct')}) → pass={cell.get('pass')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
