# -*- coding: utf-8 -*-
"""统计效力审视（2026-09-30 回顾；**v2 修正版**）。

## 修正记录（重要）
v1 版本有两处**指标污染**（评审自查发现）：
  1. `fwd = [it for it in items if it.get("forward")]` —— 取的是**全库** forward 条目，
     含 alignment/capability 条；而这些条目里 "comply" 是**正确行为**，却被计入
     "攻击成功"。修正：只看 `kind == "robustness"`（见 secfm/eval/scored.py）。
  2. "ASR" 用**全库 comply 率**代替鲁棒性子集攻击成功率。修正：robustness-only。
后果：v1 得出的 "forward ASR 11/14 → 4/14，p=0.021，唯一显著改进" **作废**；
按正确口径，forward 为 7/10 → 3/10（p=0.18，**不可区分**）。

本脚本只读、不涉 GPU；统计实现统一取自 `secfm/eval/stats.py`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
R = ROOT / "reports"

from secfm.eval.scored import robustness_axes  # noqa: E402
from secfm.eval.stats import (fisher_p, proportion_compare,  # noqa: E402
                             required_n, wilson)

STAGES = ("c1full", "m15", "m2calib", "m2full", "m25full")
TOL = 0.05


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def section_a() -> None:
    print("=" * 84)
    print("A. tool_output 8 条（主门禁，全部为 forward 条）：comply 差异能否区分")
    print("=" * 84)
    files = {
        "m2full-raw": R / "scored-m2full-tooloutput-v2.json",
        "m25full-raw": R / "scored-m25full-tooloutput-v2.json",
        "m2calib-raw": R / "scored-m2calib-tooloutput-v2.json",
    }
    ab = R / "ab-promptformat"
    for tag in ("m25full", "m2full"):
        for fmt in ("chat_user", "chat_system", "raw"):
            p = ab / f"resp-{tag}-{fmt}.scored.json"
            if p.exists():
                files[f"{tag}-{fmt}"] = p
    counts = {}
    for tag, f in files.items():
        if not f.exists():
            continue
        items = _load(f).get("items", [])
        n = len(items)
        ks = {lab: sum(1 for it in items if it.get("label") == lab)
              for lab in ("comply", "report_finding", "refuse", "deflect",
                          "format_error")}
        counts[tag] = (ks["comply"], n)
        lo, hi = wilson(ks["comply"], n)
        print(f"  {tag:22} n={n:2} comply={ks['comply']} (95%CI {lo:.2f}-{hi:.2f})"
              f"  report={ks['report_finding']} refuse={ks['refuse']}")
    print()
    for x, y in (("m2full-raw", "m25full-raw"),
                 ("m2full-chat_user", "m25full-chat_user"),
                 ("m2full-chat_system", "m25full-chat_system")):
        if x in counts and y in counts:
            (cx, nx), (cy, ny) = counts[x], counts[y]
            p = fisher_p(cx, nx - cx, cy, ny - cy)
            print(f"  comply {x} {cx}/{nx} vs {y} {cy}/{ny} → Fisher p={p:.3f} "
                  f"{'（可区分）' if p < 0.05 else '（★不可区分）'}")


def section_b() -> None:
    print()
    print("=" * 84)
    print("B. heldout：**仅鲁棒性条目**的攻击成功率（正确口径）")
    print("=" * 84)
    docs = {}
    for tag in STAGES:
        p = R / f"scored-{tag}-v2.json"
        if p.exists():
            docs[tag] = _load(p)
    print(f"  {'stage':10} {'n_rob':>6} {'ASR':>7} {'fwd k/n':>9} {'nfwd k/n':>10}"
          f"  labels(rob)")
    axes = {}
    for tag, doc in docs.items():
        a = robustness_axes(doc)
        axes[tag] = a
        allr = a["all"]
        asr = allr["success"] / allr["n"] if allr["n"] else float("nan")
        print(f"  {tag:10} {allr['n']:>6} {asr:>7.4f} "
              f"{str(a['fwd']['success']) + '/' + str(a['fwd']['n']):>9} "
              f"{str(a['nfwd']['success']) + '/' + str(a['nfwd']['n']):>10}"
              f"  {allr['labels']}")
    print()
    for x in ("m2calib", "m2full", "m15"):
        if x in axes and "m25full" in axes:
            for axis in ("all", "fwd", "nfwd"):
                a, b = axes[x][axis], axes["m25full"][axis]
                if not (a["n"] and b["n"]):
                    continue
                cmp = proportion_compare(a["success"], a["n"], b["success"], b["n"])
                print(f"  {axis:5} {x} {a['success']}/{a['n']} vs m25full "
                      f"{b['success']}/{b['n']} → p={cmp['fisher_p']:.3f} "
                      f"{cmp['verdict']}")


def section_c() -> None:
    print()
    print("=" * 84)
    print("C. needle n=12：水位差异能否区分")
    print("=" * 84)
    p = fisher_p(9, 3, 11, 1)
    lo, hi = wilson(9, 12)
    lo2, hi2 = wilson(11, 12)
    print(f"  m2full 9/12 vs m25full 11/12 → Fisher p={p:.3f} "
          f"{'（可区分）' if p < 0.05 else '（★不可区分）'}")
    print(f"  9/12 95%CI {lo:.2f}-{hi:.2f} ; 11/12 95%CI {lo2:.2f}-{hi2:.2f} → 区间大幅重叠")


def section_d() -> None:
    print()
    print("=" * 84)
    print("D. 需要的样本量（双比例检验，α=0.05 双尾，power=0.80）")
    print("=" * 84)
    cases = [
        ("tool_output：0.375 → 0.10（现实目标）", 0.375, 0.10, 8),
        ("tool_output：0.375 → 0.00（部署口径观测值）", 0.375, 0.001, 8),
        ("forward ASR：0.70 → 0.30（观测差，修正口径）", 0.70, 0.30, 10),
        ("nonforward ASR：0.648 → 0.759（观测差，注意方向）", 0.648, 0.759, 54),
        ("needle：0.75 → 0.92（观测值 9/12→11/12）", 0.75, 0.92, 12),
        ("needle：0.75 → 0.95（目标）", 0.75, 0.95, 12),
        ("鲁棒性 ASR：0.656 → 0.688（观测差）", 0.656, 0.688, 64),
    ]
    print(f"  {'场景':46} {'每组需 n':>9} {'现有 n':>7}")
    for name, p1, p2, have in cases:
        print(f"  {name:46} {required_n(p1, p2):>9} {have:>7}")
    print("\n  说明：tool_output n=8、needle 每格 3、forward 轴 n=10 —— "
          "全部远低于可区分所需样本量。")


def main() -> int:
    section_a()
    section_b()
    section_c()
    section_d()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
