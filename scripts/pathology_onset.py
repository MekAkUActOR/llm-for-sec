# -*- coding: utf-8 -*-
r"""★★★★★ 定位**病态起点**：chosen 的窗口均值首次跌破阈值的步 ✓。

## 为什么用"起点"而不是"末值"

第 25 轮实测：M3 与全长跑的曲线**逐点重合** ✗ ⇒ 逐点表格很长且看不出差别 ✓。
**★ 把整条轨迹压成**一个数字**（病态起点步 ✓）后，两次运行的差别一目了然** ✓✓。

**★ 判据（预先定好 ✓）**：窗口均值（W=10 个指标点 ✓）首次 **< +1.0** 的步 ✓。
**依据**：M3 在步 100 还是 **+4.890** ✓，到步 500 已是 **−1.657** ✗；
**+1.0 落在两者之间** ✓，且是第 24 轮就写下的健康下界 ✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
RUNS = [
    ("M3（毒 run ✗）",
     R / "checkpoints/qwen3-06b-sec-m3-dpo/checkpoint-1803/trainer_state.json"),
    ("探针（300 步 ✓）",
     R / "checkpoints/qwen3-06b-sec-m4-capfix-probe/trainer_state.json"),
    ("全长跑（在飞 ✓）",
     R / "checkpoints/qwen3-06b-sec-m4-capfix-full/checkpoint-200/trainer_state.json"),
]
W = 10
THR = 1.0


def latest_full() -> Path:
    ck = R / "checkpoints" / "qwen3-06b-sec-m4-capfix-full"
    ds = sorted((p for p in ck.glob("checkpoint-*") if p.is_dir()),
                key=lambda p: int(p.name.split("-")[-1]))
    return (ds[-1] / "trainer_state.json") if ds else RUNS[2][1]


def hist(p: Path) -> list[dict]:
    d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    return [x for x in (d.get("log_history") or []) if "rewards/chosen" in x]


def onset(h: list[dict]) -> tuple[int | None, list[tuple[int, float]]]:
    r"""返回（首个窗口均值 < THR 的**步** ✓，窗口序列 ✓）。步 = (start+W)*5 ✓。"""
    seq = []
    for s in range(0, len(h) - W + 1, W):
        m = sum(float(h[j]["rewards/chosen"]) for j in range(s, s + W)) / W
        seq.append(((s + W) * 5, m))
    for step, m in seq:
        if m < THR:
            return step, seq
    return None, seq


def main() -> int:
    print(f"=== ★病态起点（窗口均值首次 < {THR:+.1f} ✓，W={W} ✓）===")
    print(f"  {'运行':<22} {'指标点':>7} {'已跑步':>8} {'起点步':>8} {'末窗均值':>10}")
    out = {}
    for name, p in RUNS:
        if name.startswith("全长跑"):
            p = latest_full()
        if not p.exists():
            print(f"  {name:<22} ★缺 {p}")
            continue
        h = hist(p)
        st, seq = onset(h)
        last = seq[-1][1] if seq else float("nan")
        steps = len(h) * 5
        print(f"  {name:<22} {len(h):>7} {steps:>8} "
              f"{(str(st) if st else '尚未跌破 ✓'):>8} {last:>+10.3f}")
        out[name] = (st, last, steps, seq)

    # ★M3 vs 全长跑 的起点对照 ✓
    m3 = out.get("M3（毒 run ✗）")
    fu = out.get("全长跑（在飞 ✓）")
    if m3 and fu:
        print(f"\n=== ★起点对照 ===")
        print(f"  M3 起点步 = {m3[0]}，全长跑起点步 = {fu[0]}")
        if fu[0] is None:
            print("  ⇒ 全长跑**尚未跌破** ✓ —— 若它最终不跌破，则与 M3 **可分** ✓")
        elif fu[2] < 1803:
            print(f"  ⇒ 全长跑只跑到步 {fu[2]} ✓，**还不能**与 M3 的 {m3[0]} 对比定论 ✗")
        else:
            d = (fu[0] or 10**9) - (m3[0] or 10**9)
            print(f"  ⇒ 差 {d:+d} 步 ⇒ "
                  f"{'两者同量级 ⇒ **capfix 未改变病态起点** ✗（支持 H-B ✓）' if abs(d) < 200 else '起点明显不同 ✓'}")
    print(f"\n  ★窗口序列（M3 ✓ / 全长跑 ✓）")
    if m3 and fu:
        print(f"  {'步':>7} {'M3':>10} {'全长':>10}")
        for (s1, m1), (s2, m2) in zip(m3[3], fu[3]):
            print(f"  {s1:>7} {m1:>+10.3f} {m2:>+10.3f}")
    print("\nONSET=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
