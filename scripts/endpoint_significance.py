# -*- coding: utf-8 -*-
r"""★★★★★ 终点裁决的**显著性**（第 36 轮 ✓，纯 CPU ✓）。

## 为什么必须做
`reports/m4-endpoint-verdict.md` 里，全长跑相对起点有**两处小代价** ✗：
- **ORR 16.2%（11/68）vs 起点 14.7%（10/68）**
- **`format_err` 1.8%（3/168）vs 起点 0.0%（0/168）**

**⇒ 裁决表要求「须判是否显著」** ✗ —— **不判就写进结论，等于把噪声当结论** ✗✓

**★ 方法**：Fisher 精确检验（双侧 ✓）+ 单侧（劣化方向 ✓）+ 风险差 + 95% CI（Wilson ✓）。
**★ 不用 scipy**（可能没装 ✗）⇒ 用 `math.comb` 直接算 ✓（本样本量下瞬间 ✓）。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
FILES = {
    "起点": "scored-chat-gen-soup-a050-v2-mnt512.json",
    "M3": "scored-chat-gen-m3-dpo-v2-mnt512.json",
    "探针": "scored-chat-gen-m4-capfix-probe-v2-mnt512.json",
    "★全长": "scored-chat-gen-m4-capfix-full-v2-mnt512.json",
}


def stats(name: str) -> dict:
    p = R / "reports" / FILES[name]
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items") or []
    by: dict[str, list] = {}
    for x in items:
        by.setdefault(str(x.get("kind")), []).append(x)
    rb = by.get("robustness", [])
    al = by.get("alignment", [])
    return {
        "asr_k": sum(1 for x in rb if str(x.get("label")) == "comply"),
        "asr_n": len(rb),
        "asr_fe": sum(1 for x in rb if str(x.get("label")) == "format_error"),
        "orr_k": sum(1 for x in al if (x.get("derived") or {}).get("over_refusal")),
        "orr_n": sum(1 for x in al if "over_refusal" in (x.get("derived") or {})),
    }


def fisher(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    r"""返回（双侧 p ✓，单侧 p（a/n1 > c/n2 方向 ✓））。表 = [[a,b],[c,d]] ✓。"""
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def pr(x: int) -> float:
        return (math.comb(r1, x) * math.comb(n - r1, c1 - x)
                / math.comb(n, c1))

    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    p_obs = pr(a)
    two = sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + 1e-9))
    one = sum(pr(x) for x in range(a, hi + 1))
    return min(1.0, two), min(1.0, one)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main() -> int:
    s = {k: stats(k) for k in FILES if (R / "reports" / FILES[k]).exists()}
    if "★全长" not in s or "起点" not in s:
        print("  ★缺关键产物")
        return 2
    fu, ba = s["★全长"], s["起点"]

    print("=== ★全长 vs 起点：三组显著性（Fisher 精确 ✓）===")
    print(f"  {'指标':<14} {'起点':>12} {'全长':>12} {'风险差':>10} "
          f"{'双侧p':>9} {'单侧p':>9} {'全长95%CI':>18}")
    rows = [
        ("ASR(rob)", ba["asr_k"], ba["asr_n"], fu["asr_k"], fu["asr_n"], True),
        ("ORR(align)", ba["orr_k"], ba["orr_n"], fu["orr_k"], fu["orr_n"], False),
        ("format_err", ba["asr_fe"], ba["asr_n"], fu["asr_fe"], fu["asr_n"], False),
    ]
    for name, k0, n0, k1, n1, lower_better in rows:
        two, one = fisher(k1, n1 - k1, k0, n0 - k0)
        rd = k1 / n1 - k0 / n0
        lo, hi = wilson(k1, n1)
        print(f"  {name:<14} {k0:>5}/{n0:<6} {k1:>5}/{n1:<6} {rd:>+10.4f} "
              f"{two:>9.4f} {one:>9.4f}   [{lo:.3f}, {hi:.3f}]")

    print(f"\n★判读（★阈值 p<0.05 ✓）：")
    for name, k0, n0, k1, n1, lower_better in rows:
        two, one = fisher(k1, n1 - k1, k0, n0 - k0)
        rd = k1 / n1 - k0 / n0
        dirn = "劣化 ✗" if (rd > 0) == lower_better and abs(rd) > 0 else ("改善 ✓" if rd < 0 else "无变化")
        sig = "**显著** ✓" if two < 0.05 else "**不显著**（噪声范围 ✓）"
        print(f"  · {name:<12} 风险差 {rd:+.4f}（{dirn}），双侧 p={two:.4f} ⇒ {sig}")
        if name == "ORR(align)":
            print(f"    ★ ORR 只有 {n0} 条 ⇒ **本检验的检出力很低** ✗ —— "
                  f"「不显著」≠「已证等价」✓（与第 23 轮同一条教训 ✓）")
    print("\nSIGNIFICANCE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
