# -*- coding: utf-8 -*-
"""判据统计工具（S0，2026-09-30）。

## 为什么
回顾（reports/review-2026-09-30.md §1.3）显示：本项目多处门禁基于 n=8 / n=12 的读数
做"通过/不通过"，而 Fisher 检验表明**多数阶段间差异在统计上不可区分**；同时缺少
置信区间与所需样本量的呈现。本模块提供统一实现，供判定器与审计脚本共用：

    wilson(k, n)                      → 比例的 95% Wilson 置信区间
    fisher_p(a, b, c, d)              → 双尾 Fisher 精确检验
    proportion_compare(k1, n1, k2, n2) → {p, significant, ci1, ci2, rates}
    required_n(p1, p2)                → 双比例检验所需每组样本量（α=.05, power=.80）
    power_adequate(n, p1, p2)         → 现有样本量是否足以分辨该效应

约定：**差异不可区分时，判定应写"未达可区分"，而不是"通过/不通过"**
（判定器的 evidence_strength 字段即为此设计）。
"""
from __future__ import annotations

import math

__all__ = ["axis_decision", "diff_ci", "fisher_p", "fisher_p_greater",
           "power_adequate", "proportion_compare", "required_n", "wilson"]

Z_ALPHA_2 = 1.959964   # alpha = 0.05 双尾
Z_BETA = 0.8416212     # power = 0.80


def wilson(k: int, n: int, z: float = Z_ALPHA_2) -> tuple[float, float]:
    """比例的 Wilson 得分区间（小样本优于正态近似）。"""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, mid - half), min(1.0, mid + half))


def fisher_p(a: int, b: int, c: int, d: int) -> float:
    """双尾 Fisher 精确检验，2×2 = [[a, b], [c, d]]。"""
    n = a + b + c + d
    if n == 0:
        return 1.0
    r1, r2 = a + b, c + d
    c1 = a + c
    if r1 == 0 or r2 == 0 or c1 == 0 or c1 == n:
        return 1.0

    def prob(x: int) -> float:
        return (math.comb(r1, x) * math.comb(r2, c1 - x)) / math.comb(n, c1)

    lo, hi = max(0, c1 - r2), min(r1, c1)
    p_obs = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                        if prob(x) <= p_obs + 1e-12))


def fisher_p_greater(a: int, b: int, c: int, d: int) -> float:
    """**单侧** Fisher 精确检验：P(X ≥ a)，2×2 = [[a, b], [c, d]]，第一行是"更差"组。

    为什么需要它（2026-09-30）：门禁命题一律是**单向**的——"变体不得**显著劣于**起点"、
    "不得**上升**超 X"。这类命题的正确检验是单侧；用双尾会把 p 大约翻倍，
    **使门禁偏宽（fail-open）**：实测未载体轴 k=15/168 vs 6/168 双尾 p=0.0716 ≥0.05
    会被放过，而单侧 p=0.0346 <0.05 应当判劣化。
    本项目冻结口径（`reports/criterion_b_table.py` 推 max_k=14）用的正是单侧。
    """
    n = a + b + c + d
    if n == 0:
        return 1.0
    r1, r2 = a + b, c + d
    c1 = a + c
    if r1 == 0 or r2 == 0 or c1 == 0 or c1 == n:
        return 1.0

    def prob(x: int) -> float:
        return (math.comb(r1, x) * math.comb(r2, c1 - x)) / math.comb(n, c1)

    lo, hi = max(0, c1 - r2), min(r1, c1)
    return min(1.0, sum(prob(x) for x in range(max(a, lo), hi + 1)))


def proportion_compare(k1: int, n1: int, k2: int, n2: int,
                       alpha: float = 0.05) -> dict:
    """两组比例对照：差异是否可区分（含 CI 与精确检验）。

    约定 k1/n1 为**参照系**（基线），k2/n2 为当前观测。
    """
    p = fisher_p(k1, n1 - k1, k2, n2 - k2)
    lo1, hi1 = wilson(k1, n1)
    lo2, hi2 = wilson(k2, n2)
    return {
        "base": {"k": k1, "n": n1, "rate": round(k1 / n1, 4) if n1 else None,
                 "ci95": [round(lo1, 4), round(hi1, 4)]},
        "cur": {"k": k2, "n": n2, "rate": round(k2 / n2, 4) if n2 else None,
                "ci95": [round(lo2, 4), round(hi2, 4)]},
        "fisher_p": round(p, 4),
        "significant": p < alpha,
        "verdict": ("可区分" if p < alpha else "★未达可区分（差异可能是抽样噪声）"),
    }


def required_n(p1: float, p2: float, alpha: float = 0.05,
               power: float = 0.80) -> int:
    """双比例检验所需**每组**样本量（正态近似）。p1==p2 时返回 -1。"""
    if p1 == p2:
        return -1
    z = (Z_ALPHA_2 if alpha == 0.05 else 1.959964) + Z_BETA
    n = (z * z * (p1 * (1 - p1) + p2 * (1 - p2))) / ((p1 - p2) ** 2)
    return int(math.ceil(n))


def power_adequate(n: int, p1: float, p2: float, alpha: float = 0.05) -> dict:
    """现有样本量是否足以分辨 p1→p2 的效应（power=0.80）。"""
    need = required_n(p1, p2, alpha)
    return {"n": n, "needed": need, "adequate": need > 0 and n >= need,
            "effect": [p1, p2]}


def diff_ci(k1: int, n1: int, k2: int, n2: int,
            z: float = Z_ALPHA_2) -> tuple[float, float]:
    """两比例之差 (p2 - p1) 的 95% 置信区间（Newcombe 混合得分法）。"""
    if n1 <= 0 or n2 <= 0:
        return (float("nan"), float("nan"))
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    d = p2 - p1
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (lo, hi)


def mcnemar_p(b: int, c: int) -> float:
    """**配对** McNemar 精确检验（单侧）：P(X ≥ b)，X ~ Binom(b+c, 1/2)。

    为什么需要它（2026-09-30，看门狗提出）：本项目大量对照是**同一条目集上的配对**
    评测（例如 α 网格的 9 档**全部**在 `data/heldout/v0.4-toolout` 的同一批 46 条上跑），
    用非配对 Fisher 会丢掉配对信息。实测配对比非配对 p 小 **2.1–2.5 倍**：
    同一批数据下 a020/a065 由"不可区分"变成**可区分的劣化**（b=5,c=0 ⇒ p=0.03125）。
    **注意**：配对 H0 要求同一条目在不同臂之间可比；若条目语义在不同臂下失去可比性，
    该假设不成立（此风险已在 `reports/m3-dpo-watchdog.md` §3.9 登记）。

    参数：b = **单向不一致对数**（"更差"方向的翻转数），c = 反方向翻转数。
    """
    n = b + c
    if n <= 0:
        return 1.0
    if b <= 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(b, n + 1))
    return min(1.0, tail / (2 ** n))


def axis_decision(cur_k: int, cur_n: int, base_k: int, base_n: int,
                  tolerance: float = 0.05, alpha: float = 0.05,
                  direction: str = "lower_is_better",
                  discordant: tuple[int, int] | None = None) -> dict:
    """单轴三态判定：ok / worse / **undecidable**（不可区分）。

    设计原则（reports/review-2026-09-30.md §1.3）：
      * 差异**方向不利且统计可区分** → `worse`（可判失败）；
      * 差异方向不利但**统计不可区分** → `undecidable`（**不得写成失败，也不得
        写成通过**；必须报出所需样本量）；
      * 其余 → `ok`。
    另标 `resolution_ok`：差值 CI 宽度是否小于公差（否则该公差在本样本量下**原理上
    不可判定**，需要扩容而不是反复重测）。

    ★2026-09-30 修复（与 `topup_verdict.py` MUST-A 同类 fail-open，看门狗发现）：
    本函数原先用**双尾** `fisher_p` 判定 `state="worse"`，而门禁命题是**单向**的
    （"不得显著劣于 / 不得上升超 X"）。双尾约把 p 翻倍 ⇒ **偏宽（fail-open）**：
    实测把 a020/a065 由 `worse` 误降为 `undecidable`。现改为单侧 `fisher_p_greater`
    （"更差"组放第一行）。

    `discordant=(b, c)`：若受测各臂跑在**同一条目集**上（本项目的常规做法），
    应传**单向不一致对数** b 与反向翻转数 c，此时改用**配对** `mcnemar_p`
    （功效显著更高；配对比非配对 p 小 2.1–2.5 倍）。不传则退回非配对单侧 Fisher。
    """
    if min(cur_n, base_n) <= 0:
        return {"state": "missing", "tolerance": tolerance}
    sign = 1.0 if direction == "lower_is_better" else -1.0
    p_cur, p_base = cur_k / cur_n, base_k / base_n
    d = sign * (p_cur - p_base)          # >0 表示"更差"
    lo, hi = diff_ci(base_k, base_n, cur_k, cur_n)
    lo_s, hi_s = (sign * lo, sign * hi)
    # ★2026-09-30 晚修（潜在缺陷，由 MUST-B 首次暴露；见 docs/01 §11.27）：
    #   原实现只做符号翻转而不重排端点。`sign = -1`（direction="higher_is_better"）
    #   时必然得到 lo_s > hi_s —— **区间端点反序**。此前所有调用都用默认的
    #   "lower_is_better"（sign=+1）故从未暴露；MUST-B（契约保留率，越高越好）首次触发。
    if lo_s > hi_s:
        lo_s, hi_s = hi_s, lo_s
    # 例如 direction="lower_is_better" 且"当前更差" ⇒ [[cur_k, cur_n-cur_k],[base_k, base_n-base_k]]
    if discordant is not None:
        b, c = int(discordant[0]), int(discordant[1])
        test = "mcnemar(paired,one-sided)"
        raw_p = mcnemar_p(max(b, 0), max(c, 0))
    else:
        test = "fisher(one-sided)"
        raw_p = fisher_p_greater(cur_k, cur_n - cur_k, base_k, base_n - base_k)
    p = raw_p
    if d <= tolerance:
        state = "ok"
    elif p < alpha:
        state = "worse"
    else:
        state = "undecidable"
    need = required_n(p_base, p_cur)
    width = hi_s - lo_s
    # ★2026-09-30 晚修（配对盲点，由 v0.5-toolout-reg 校验器指出）：
    #   传入 discordant 时，检验已改用 McNemar（配对），但 resolution_ok 原先仍取
    #   **非配对** diff_ci 的宽度 ⇒ 高估所需样本量，会让配对扩容被"分辨率不足"白判。
    #   现补配对 Wald 区间（McNemar）：d=(b-c)/n，Var=((b+c)-(b-c)²/n)/n²。
    #   两种宽度**同时暴露**（diff_ci95 / diff_ci95_paired + resolution_basis），
    #   不静默改变既有字段的含义；resolution_ok 在有 discordant 时以**配对**口径为准。
    paired_basis = False
    lo_p = hi_p = None
    if discordant is not None:
        b_, c_ = int(discordant[0]), int(discordant[1])
        n_pair = max(cur_n, base_n, 1)
        d_pair = (b_ - c_) / n_pair
        var_pair = max((b_ + c_) - (b_ - c_) ** 2 / n_pair, 0.0) / (n_pair ** 2)
        se_pair = var_pair ** 0.5
        z = 1.959963984540054
        lo_p, hi_p = sign * (d_pair - z * se_pair), sign * (d_pair + z * se_pair)
        # ★同上：先重排端点再算宽度。否则 sign=-1 时 width 为**负数** ⇒
        #   `resolution_ok = width <= tolerance` 假为 True ⇒ 又一个 fail-open。
        if lo_p > hi_p:
            lo_p, hi_p = hi_p, lo_p
        width = hi_p - lo_p
        paired_basis = True
    return {
        "cur": {"k": cur_k, "n": cur_n, "rate": round(p_cur, 4)},
        "base": {"k": base_k, "n": base_n, "rate": round(p_base, 4)},
        "diff": round(sign * (p_cur - p_base), 4),
        "diff_ci95": [round(lo_s, 4), round(hi_s, 4)],
        "diff_ci95_paired": ([round(lo_p, 4), round(hi_p, 4)]
                             if lo_p is not None else None),
        "resolution_basis": ("paired(mcnemar)" if paired_basis else "unpaired"),
        "tolerance": tolerance,
        "test": test,
        "discordant": (list(discordant) if discordant is not None else None),
        "fisher_p": round(p, 4),
        "state": state,
        "required_n_per_group": need,
        "resolution_ok": width <= tolerance,
        "note": ("公差小于本样本量的分辨率 → 需扩容" if width > tolerance
                 else "分辨率足够"),
    }
