# -*- coding: utf-8 -*-
"""校验 MUST-A 的 Fisher 修复：把边界逐格列出来。

修复内容（2026-09-30）：
  原 `topup_verdict.py` 调 `fisher_p(vk, vn, bk, bn)`——而 `fisher_p` 的签名是 2×2
  单元格 `[[a,b],[c,d]]`，正确应为 `[[k, n-k],[k_b, n_b-k_b]]`；且门禁命题单向，
  应用单侧。两个错误叠加＝**fail-open**。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from secfm.eval.stats import fisher_p, fisher_p_greater  # noqa: E402

BASE_K, BASE_N = 6, 168
print(f"起点（基线）= {BASE_K}/{BASE_N}；MUST-A 命题：变体不得**显著劣于**起点")
print(f"{'变体':>8} {'率':>7} {'单侧(修复后)':>13} {'双尾(修复后)':>13} "
      f"{'旧误用实现':>11} {'修复后判':>9} {'旧实现判':>9}")
for k in (6, 10, 13, 14, 15, 16, 18, 24):
    one = fisher_p_greater(k, BASE_N - k, BASE_K, BASE_N - BASE_K)
    two = fisher_p(k, BASE_N - k, BASE_K, BASE_N - BASE_K)
    old = fisher_p(k, BASE_N, BASE_K, BASE_N)      # 旧的签名误用
    print(f"{k:>5}/168 {k/BASE_N:>7.1%} {one:>13.4f} {two:>13.4f} {old:>11.4f} "
          f"{('FAIL' if one < 0.05 else 'PASS'):>9} {('FAIL' if old < 0.05 else 'PASS'):>9}")

print("\n结论：")
print("  * 修复后，k=15/168 即判 FAIL（单侧 p=%.4f < 0.05）；旧实现要到 k=16 才 FAIL。" %
      fisher_p_greater(15, 153, 6, 162))
print("    ⇒ 修复收紧了门禁 1 次试验，与冻结口径 max_k=14 一致（criterion_b_table.py）。")
print("  * 对既有已记录判定：所有已发布的 p 值来自旧路径，需按本修复重算后方可引用；")
print("    已核对的方向不变（各档 p 仍 <<0.05），但**边界情形**必须用新值。")
