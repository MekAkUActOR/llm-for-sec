# -*- coding: utf-8 -*-
"""验证 `axis_decision` 的配对分辨率修复：①state 不变（决策不受影响）；
②配对宽度 vs 非配对宽度；③公差 0.05 在 46 / 256 / 600 条下**能否**被分辨。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from secfm.eval.stats import axis_decision  # noqa: E402

# 修正后（strict 口径）的 9 档读数：tag -> (k, b, c)
# b/c 为配对不一致格（b=变体顺从&基线防御 即变差；c=反之）
TABLE = {
    "m2calib":   (3, 0, 0),
    "soup-a020": (3, 2, 0),
    "soup-a035": (3, 2, 0),
    "soup-a038": (4, 3, 0),
    "soup-a040": (4, 3, 0),
    "soup-a042": (4, 3, 0),
    "soup-a045": (4, 3, 0),
    "soup-a050": (5, 4, 0),
    "soup-a065": (6, 5, 0),
}
BASE = (3, 46)

print("=== ① state 是否受本修复影响（应完全不变）===")
print(f"{'tag':<12} {'k/n':>7} {'state(unpaired)':>16} {'state(paired)':>15} {'一致':>5}")
for tag, (k, b, c) in TABLE.items():
    if k == BASE[0]:
        continue
    a = axis_decision(k, 46, BASE[0], 46, tolerance=0.05)
    p = axis_decision(k, 46, BASE[0], 46, tolerance=0.05, discordant=(b, c))
    print(f"{tag:<12} {f'{k}/46':>7} {a['state']:>16} {p['state']:>15} "
          f"{'✓' if a['state'] == p['state'] else '**不同**':>5}")

print("\n=== ② 宽度对比（tolerance=0.05）===")
print(f"{'tag':<12} {'非配对宽':>9} {'配对宽':>8} {'basis':>16} {'resolution_ok':>14}")
for tag, (k, b, c) in TABLE.items():
    if k == BASE[0]:
        continue
    p = axis_decision(k, 46, BASE[0], 46, tolerance=0.05, discordant=(b, c))
    u = p["diff_ci95"]
    pw = p["diff_ci95_paired"]
    print(f"{tag:<12} {u[1] - u[0]:>9.4f} {pw[1] - pw[0]:>8.4f} "
          f"{p['resolution_basis']:>16} {str(p['resolution_ok']):>14}")

print("\n=== ③ 公差 0.05 需要多大 n？（配对，按 a050 的翻转率外推）===")
print("  假设 b/n 与 c/n 保持 a050 的比例（b=5/46, c=0），看配对宽度随 n 变化：")
for n in (46, 100, 256, 600, 1100):
    b = round(5 / 46 * n)
    c = 0
    d = axis_decision(b, n, 0, n, tolerance=0.05, discordant=(b, c))
    pw = d["diff_ci95_paired"]
    print(f"    n={n:>5}  b={b:>3}  配对宽={pw[1] - pw[0]:.4f}  "
          f"resolution_ok={d['resolution_ok']}  state={d['state']}")
print("\n  ⇒ 若 gate 要求 resolution_ok(0.05)=True，即使配对也需 n≳600/臂；")
print("     256/臂 下 0.05 公差**原理上不可分辨**——这是设计事实，不是缺陷。")
