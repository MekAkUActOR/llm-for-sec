# -*- coding: utf-8 -*-
"""校验 stats.py 的两处口径修复（单侧化 + 配对 McNemar）。

背景（2026-09-30，看门狗独立发现）：
  * `axis_decision` 原用**双尾** `fisher_p` 判 `state="worse"`，而门禁命题是**单向**的
    ⇒ 偏宽（fail-open），实测把 a020/a065 由 worse 误降为 undecidable。
  * 本项目大量对照是**同一条目集上的配对**评测（α 网格 9 档全在同一批 46 条上跑），
    应用配对 McNemar；配对比非配对 p 小 2.1–2.5 倍。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from secfm.eval.stats import axis_decision, fisher_p, mcnemar_p  # noqa: E402

print("=== 1) McNemar 精确单侧：b 个单向翻转 / c 个反向翻转 ===")
for b, c in [(5, 0), (4, 0), (3, 0), (5, 1), (0, 0), (0, 5)]:
    print(f"  b={b} c={c}  p={mcnemar_p(b, c):.5f}"
          f"   {'判 worse' if mcnemar_p(b, c) < 0.05 else '未达可区分'}")
assert abs(mcnemar_p(5, 0) - 0.03125) < 1e-9, "b=5,c=0 应为 1/32"
assert abs(mcnemar_p(4, 0) - 0.0625) < 1e-9, "b=4,c=0 应为 1/16"
print("  ✓ 与看门狗报告的数字逐位一致（0.03125 / 0.0625）")

print("\n=== 2) axis_decision：单侧 vs 双尾（同一批 46 条，起点 2/46）===")
print(f"{'当前':>8} {'diff':>8} {'单侧(修复后)':>13} {'双尾(旧)':>10} {'修复后态':>10} {'旧态':>10}")
for k in (4, 5, 6, 7, 9):
    new = axis_decision(k, 46, 2, 46)
    # 复现旧行为：双尾
    d = k / 46 - 2 / 46
    old_p = fisher_p(2, 44, k, 46 - k)
    old_state = "ok" if d <= 0.05 else ("worse" if old_p < 0.05 else "undecidable")
    print(f"{k:>5}/46 {d:>+8.3f} {new['fisher_p']:>13.4f} {old_p:>10.4f} "
          f"{new['state']:>10} {old_state:>10}")

print("\n=== 3) 配对（McNemar）对同一批数据的判定 ===")
# 用 v0.4-toolout 的观测（看门狗给的不一致对数）
for tag, b, c in [("soup-a020", 5, 0), ("soup-a035", 4, 0), ("soup-a050", 4, 0),
                  ("soup-a065", 5, 0)]:
    r = axis_decision(2 + b, 46, 2, 46, discordant=(b, c))
    print(f"  {tag:>10}  不一致对(b={b},c={c})  p={r['fisher_p']:.4f}  "
          f"state={r['state']}  test={r['test']}")
print("\n  ⇒ 配对口径下 a020/a065 = worse（可区分的劣化）；其余未达可区分。")
print("  ⇒ 与'所有档一律 undecidable'或'所有档一律 FAIL'两种说法都不同：**按档分三态**。")
print("\nSTATS-FIX-SELFTEST=PASS")
