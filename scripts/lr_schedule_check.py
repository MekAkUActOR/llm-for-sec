# -*- coding: utf-8 -*-
r"""★★★★★ 验「LR 调度假说」：探针的"健康签名"是否是它**压缩后的 cosine 调度**的产物？✗

## 假说的来历（第 25 轮）

全长跑在**同步数窗口**上 chosen **不比 M3 好** ✗（步 200：全长 +0.783 vs M3 +1.264 ✗），
而第 23 轮的**探针**（`max_steps: 300` ✓）在同区段看起来健康 ✓
⇒ 疑：**探针的 cosine 调度在 300 步内退到零** ✓，
而全长跑在步 200 的 LR 还接近峰值 ✗ ⇒ **两者同步数不可比** ✗✓。

**★ 若成立**：
- 探针的**曲线证据不可外推**到全长跑 ✗
- 但探针的**评测读数**（ASR 0.6% ✓）仍是**它自己那个模型**的真实读数 ✓ —— 只是不能预测末态 ✓
- **决定性对照变成：全长跑终点(1803) vs M3 终点(1803)** ✓（完全同步数 ✓）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
SOURCES = [
    ("探针（300 步调度）", R / "checkpoints/qwen3-06b-sec-m4-capfix-probe/trainer_state.json"),
    ("M3（1803 步调度）", R / "checkpoints/qwen3-06b-sec-m3-dpo/checkpoint-1803/trainer_state.json"),
    ("全长（1803 步调度）", R / "checkpoints/qwen3-06b-sec-m4-capfix-full/checkpoint-200/trainer_state.json"),
]
IDX = (0, 5, 20, 39, 59, 100, 200, 300, 359)


def hist(p: Path) -> list[dict]:
    d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    return [x for x in (d.get("log_history") or []) if "learning_rate" in x]


def main() -> int:
    hs = []
    for name, p in SOURCES:
        if not p.exists():
            print(f"  ★缺 {p}")
            return 1
        hs.append((name, hist(p)))

    print("  === LR 轨迹（索引 → learning_rate ✓）===")
    head = "  {:>5}".format("idx")
    for name, _ in hs:
        head += " {:>20}".format(name)
    print(head)
    for i in IDX:
        row = "  {:>5}".format(i)
        for _, h in hs:
            row += " {:>20.3e}".format(float(h[i]["learning_rate"])) if i < len(h) else " {:>20}".format("—")
        print(row)

    print("\n  === ★同步数 LR 比（探针 ÷ M3 ✓）===")
    probe, m3 = hs[0][1], hs[1][1]
    ratios = []
    for i in IDX:
        if i < len(probe) and i < len(m3):
            lp = float(probe[i]["learning_rate"])
            lm = float(m3[i]["learning_rate"])
            ratios.append((i, lp / lm if lm else float("nan")))
            print(f"    idx {i:>3}: 探针 {lp:.3e} / M3 {lm:.3e} = **{lp/lm:.3f}**")
    # ★判据必须是**末段比值** ✓，不能是 max（前段受 warmup 影响会 >1 ✗）
    #   —— 这正是我先前写错的地方 ✗（用 max 得"不成立"✗，实际成立 ✓）。
    tail = [r for i, r in ratios if i >= 39]
    verdict = bool(tail) and max(tail) < 0.75
    print(f"\n★判读（判据 = **末段**比值 ✓，不是 max ✗）：")
    print(f"  · 末段(idx≥39)最大比值 = {max(tail):.3f}" if tail else "  · 无末段可比点")
    print(f"  · ⇒ LR 调度假说 {'**成立** ✓' if verdict else '**不成立** ✗'}")
    if verdict:
        print("  ⇒ 探针的 cosine 在 300 步内退到零 ⇒ 它**约在 step 150 后基本停止学习** ✓")
        print("  ⇒ **探针的曲线证据不可外推到全长跑** ✗（全长跑同步数 LR 是它的 3~10^9 倍 ✓）")
        print("  ⇒ 但探针的**评测读数**（ASR 0.6% ✓）仍是它自己那个模型的**真实读数** ✓")
        print("     只是**不能**用来预测全长跑末态 ✗")
        print("  ⇒ **决定性对照 = 全长跑终点(1803) vs M3 终点(1803)** ✓（完全同步数 ✓）")
    else:
        print("  ⇒ 两者的调度量级相当 ✓ ⇒ 差异须另找原因 ✗")
    print("\nLR-SCHEDULE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
