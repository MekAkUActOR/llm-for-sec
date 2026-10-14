# -*- coding: utf-8 -*-
"""未见载体门禁的单侧 Fisher 精确检验（MUST-3 判定用）。

口径：v0.3-gen 的 168 条鲁棒性条目，攻击成功数 / 168。
单侧（greater）= 检验"该档是否显著劣于对照档"。
"""
from math import comb

ROWS = [("m2calib", 6, 168), ("m2calib-needlefix-e1", 24, 168), ("m25full", 36, 168),
        ("m3base-topup-e1", 101, 168), ("m3base-topup-e2", 108, 168)]


def fisher_greater(a: int, b: int, c: int, d: int) -> float:
    """P(X >= a)，其中 X ~ Hypergeom，用于检验 a/b 显著大于 c/d。"""
    n = a + b + c + d
    p = 0.0
    for k in range(a, min(a + b, a + c) + 1):
        p += comb(a + c, k) * comb(b + d, a + b - k) / comb(n, a + b)
    return p


def newcombe(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """第二档相对第一档的风险差 (p2-p1) 的 Newcombe 混合区间。"""
    import math

    def wilson(k, n, z=1.959963985):
        if n == 0:
            return (0.0, 1.0)
        p = k / n
        den = 1 + z * z / n
        c = (p + z * z / (2 * n)) / den
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
        return (max(0.0, c - h), min(1.0, c + h))

    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    diff = p2 - p1
    lo = diff - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    hi = diff + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)
    return (lo, hi)


base = ("m2calib", 6, 168)
kb, nb = base[1], base[2]
print(f"对照档 = {base[0]}  {kb}/{nb} = {kb/nb:.4f}\n")
print(f"{'档':24} {'ASR':>12} {'风险差(2-1)':>12} {'Newcombe 95%CI':>24} {'单侧 Fisher p(劣化)':>20}")
for name, k, n in ROWS:
    if name == base[0]:
        continue
    lo, hi = newcombe(kb, nb, k, n)
    p = fisher_greater(k, n - k, kb, nb - kb)
    print(f"{name:24} {k:>4}/{n} {k/n:>6.3f} {k/n-kb/nb:>+12.3f} "
          f"[{lo:+.3f}, {hi:+.3f}]{'':>4} {p:>20.3g}")

# needle 的对照（同法）
print("\n--- needle（64 次试验，单侧 Fisher 检验提升）---")
NK = [("m2calib", 39, 64), ("m2calib-needlefix-e1", 60, 64), ("m25full", 56, 64), ("m15", 43, 64)]
for name, k, n in NK[1:]:
    p = fisher_greater(k, n - k, 39, 64 - 39)
    print(f"  {name:24} {k}/64={k/n:.3f}  vs m2calib 39/64  单侧 p={p:.3g}")
