"""对比两份 probe PPL 报告，输出 M1 出口门禁判定（docs/05 §7）。

用法：
    python scripts/compare_ppl.py reports/ppl-base.json reports/ppl-stage1-202m.json

门禁（默认，可用 --sec-drop/--general-rise 覆盖）：
- sec 域 PPL 相对 base 下降 ≥25%
- general_en / general_zh PPL 回升 ≤10%
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def compare(base: dict, other: dict, sec_drop: float, general_rise: float) -> dict:
    """纯函数：两份报告 dict → 对比结构（供单测）。"""
    out = {}
    all_doms = list(other["domains"]) + [d for d in base["domains"]
                                         if d not in other["domains"]]
    for dom in all_doms:
        o = other["domains"].get(dom)
        b = base["domains"].get(dom)
        if not b or not o or not b.get("ppl") or not o.get("ppl"):
            out[dom] = {"ok": None, "reason": "missing"}
            continue
        delta = (o["ppl"] - b["ppl"]) / b["ppl"]  # 正=变差(升)，负=变好(降)
        if dom == "sec":
            ok = delta <= -sec_drop
            gate = f"下降 ≥{sec_drop:.0%}"
        elif dom.startswith("general"):
            ok = delta <= general_rise
            gate = f"回升 ≤{general_rise:.0%}"
        else:  # privacy/ais 等副域：只报告，不设门禁
            ok = None
            gate = "观察项"
        out[dom] = {"base_ppl": b["ppl"], "other_ppl": o["ppl"],
                    "delta": delta, "ok": ok, "gate": gate}
    return out


def main():
    ap = argparse.ArgumentParser(description="PPL 报告对比门禁")
    ap.add_argument("base")
    ap.add_argument("other")
    ap.add_argument("--sec-drop", type=float, default=0.25)
    ap.add_argument("--general-rise", type=float, default=0.10)
    args = ap.parse_args()

    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    other = json.loads(Path(args.other).read_text(encoding="utf-8"))
    res = compare(base, other, args.sec_drop, args.general_rise)

    print(f"base: {base['model']}\nother: {other['model']}\n")
    verdict = True
    for dom, r in res.items():
        if r["ok"] is None and r.get("reason") == "missing":
            print(f"  {dom:12} {'—':>10} -> {'—':>10}  [缺失] {r['gate']}")
            continue
        delta_s = f"{r['delta']:+.1%}" if "delta" in r else "N/A"
        if r["ok"] is None:
            print(f"  {dom:12} {r['base_ppl']:>10.3f} -> {r['other_ppl']:>10.3f}"
                  f"  {delta_s:>8}  [观察] {r['gate']}")
        else:
            v = "PASS" if r["ok"] else "FAIL"
            verdict = verdict and r["ok"]
            print(f"  {dom:12} {r['base_ppl']:>10.3f} -> {r['other_ppl']:>10.3f}"
                  f"  {delta_s:>8}  [{v}] {r['gate']}")

    print(f"\n门禁总判定: {'通过 ✓' if verdict else '未通过 ✗'}")
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
