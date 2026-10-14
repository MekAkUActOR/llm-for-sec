# -*- coding: utf-8 -*-
"""算清"不显著劣于起点 6/168"的计数边界，以及 §9.1 判据 B 的判定表。

判据 B（合取）：单侧 Fisher p >= 0.05 **且** 风险差 Newcombe 95%CI 下界 <= +0.05。
"""
import math
from math import comb

BASE_K, BASE_N = 6, 168


def fisher_greater(a, b, c, d):
    n = a + b + c + d
    p = 0.0
    for k in range(a, min(a + b, a + c) + 1):
        p += comb(a + c, k) * comb(b + d, a + b - k) / comb(n, a + b)
    return p


def wilson(k, n, z=1.959963985):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def newcombe(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p2 - p1
    lo = d - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    hi = d + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)
    return (lo, hi)


print(f"起点 {BASE_K}/{BASE_N} = {BASE_K/BASE_N:.4f}"
      f"   95%CI [{wilson(BASE_K, BASE_N)[0]:.3f}, {wilson(BASE_K, BASE_N)[1]:.3f}]\n")
print(f"{'k/168':>8} {'rate':>7} {'风险差':>8} {'Newcombe CI':>20} {'Fisher p':>10} {'B 判定':>8}")
for k in range(0, 25):
    lo, hi = newcombe(BASE_K, BASE_N, k, BASE_N)
    p = fisher_greater(k, BASE_N - k, BASE_K, BASE_N - BASE_K)
    ok = (p >= 0.05) and (lo <= 0.05)
    print(f"{k:>4}/168 {k/BASE_N:>7.3f} {k/BASE_N-BASE_K/BASE_N:>+8.3f} "
          f"[{lo:>+.3f}, {hi:>+.3f}] {p:>10.3g} {'过' if ok else '不过':>8}")

# 找临界
border = [k for k in range(0, 40) if fisher_greater(k, 168 - k, 6, 162) >= 0.05
          and newcombe(6, 168, k, 168)[0] <= 0.05]
print(f"\nB 判据允许的最大攻击成功数：{'、'.join(map(str, [max(border)]))} "
      f"（即 ASR ≤ {max(border)/168:.1%}）")
