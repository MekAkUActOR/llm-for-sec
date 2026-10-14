# -*- coding: utf-8 -*-
"""M2.5 双轴诊断：forward（间接注入/多轮前瞻）vs nonforward（直接攻击）。

背景：v2 判定器的 G4 分轴门禁发现 **nonforward 轴相对 m2-full 劣化**，
而 v1 只看总体 asr（0.6562→0.6875，恰好被 forward 轴的巨大改进掩盖）。
本脚本给出精确计数、标签构成与统计可区分性，回答两个问题：
  Q1 劣化是真的吗（Fisher）？
  Q2 劣化是"更顺从"还是"格式崩坏"？

用法：python scripts/diag_m25_axes.py [--suffix chat-]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
R = ROOT / "reports"

from secfm.eval.stats import proportion_compare  # noqa: E402

STAGES = ("c1-full", "m15", "m2calib", "m2full", "m25full")


def axis_counts(doc: dict) -> dict:
    """→ {"fwd": {"n","success","labels"}, "nfwd": {...}, "all": {...}}"""
    out = {}
    for key, want_fwd in (("fwd", True), ("nfwd", False), ("all", None)):
        sel = [r for r in doc.get("items", [])
               if r.get("kind") == "robustness" and r.get("responded")
               and (want_fwd is None or bool(r.get("forward")) is want_fwd)]
        labels: dict[str, int] = {}
        for r in sel:
            labels[r.get("label")] = labels.get(r.get("label"), 0) + 1
        out[key] = {
            "n": len(sel),
            "success": sum(1 for r in sel if r["derived"].get("attack_success")),
            "labels": dict(sorted(labels.items(), key=lambda kv: -kv[1])),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", default="")
    ap.add_argument("--out", default="reports/m25-axes-diagnosis.json")
    args = ap.parse_args()

    docs = {}
    for tag in STAGES:
        p = R / f"scored-{args.suffix}{tag}-v2.json"
        if p.exists():
            docs[tag] = json.loads(p.read_text(encoding="utf-8"))
    if not docs:
        print("no scored files found")
        return 2

    table, rep = {}, {"suffix": args.suffix, "stages": {}}
    print(f"{'stage':10} {'axis':6} {'asr':>7} {'k/n':>9}  labels")
    for tag, doc in docs.items():
        c = axis_counts(doc)
        rep["stages"][tag] = c
        for axis in ("all", "fwd", "nfwd"):
            d = c[axis]
            rate = d["success"] / d["n"] if d["n"] else None
            print(f"{tag:10} {axis:6} "
                  f"{('%.4f' % rate) if rate is not None else '   -  ':>7} "
                  f"{str(d['success']) + '/' + str(d['n']):>9}  {d['labels']}")
        table[tag] = {a: c[a]["success"] / c[a]["n"] if c[a]["n"] else None
                      for a in ("all", "fwd", "nfwd")}
    print()
    comparisons = {}
    if "m2full" in docs and "m25full" in docs:
        for axis in ("fwd", "nfwd", "all"):
            a = rep["stages"]["m2full"][axis]
            b = rep["stages"]["m25full"][axis]
            if a["n"] and b["n"]:
                cmp = proportion_compare(a["success"], a["n"], b["success"], b["n"])
                comparisons[f"m2full_vs_m25full_{axis}"] = cmp
                print(f"[{axis}] m2full {a['success']}/{a['n']} → "
                      f"m25full {b['success']}/{b['n']}: "
                      f"p={cmp['fisher_p']} {cmp['verdict']}")
                print(f"       m2full labels {a['labels']}")
                print(f"       m25    labels {b['labels']}")
    if "m15" in docs and "m25full" in docs:
        for axis in ("fwd", "nfwd"):
            a = rep["stages"]["m15"][axis]
            b = rep["stages"]["m25full"][axis]
            if a["n"] and b["n"]:
                comparisons[f"m15_vs_m25full_{axis}"] = proportion_compare(
                    a["success"], a["n"], b["success"], b["n"])
    rep["comparisons"] = comparisons
    rep["rate_table"] = table
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\nreport -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
