# -*- coding: utf-8 -*-
r"""★★★★★ 实时读全长跑的曲线（`trainer_log.jsonl` 由训练器直写 ✓ 不受 Tee 锁 ✓）。

## 为什么这是本轮的关键

第 24 轮写下**可证伪预测** ✓：
- `rewards/chosen` 应**全程守住 +1 以上** ✓（M3 只有 **+0.34** ✗）
- 若末段 chosen 掉回 ~0 且 rejected 独降 ✗ ⇒ **过优化重现** ✗ ⇒ capfix **不足** ✓

**★ 本脚本让这个判断**在跑完之前**就能看出趋势** ✓ ——
不必等 90 分钟，也不必等评测 ✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CKPT = ROOT / "checkpoints" / "qwen3-06b-sec-m4-capfix-full"
M3 = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo" / "checkpoint-1803" / "trainer_state.json"
KEYS = ("rewards/chosen", "rewards/rejected", "rewards/accuracies",
        "rewards/margins", "loss")


def rows_from_state() -> list[dict]:
    r"""★真源：最新 checkpoint 的 `trainer_state.json` 的 `log_history` ✓。

    ★ 为什么不读 `trainer_log.jsonl`：它的 schema 是
      `['accuracy','current_steps','elapsed_time','epoch','loss','lr',
        'percentage','remaining_time','total_steps']`
      ⇒ **没有 `rewards/chosen` / `rewards/rejected`** ✗ ——
      而第 23 轮已证：**只看 accuracy 分辨不出病态** ✗（M3 在 0.94 时 chosen 卡在 +0.34 ✗）。
    ★ 为什么不读 `reports/logs/m4-capfix-full.log`：它被 `Tee-Object` 以**无读共享**方式独占 ✗
      （`ReadAllText` 抛 IOException ⇒ 连 `Copy-Item` 也读不了 ✗）。
    """
    cks = sorted(
        (p for p in CKPT.glob("checkpoint-*") if p.is_dir()),
        key=lambda p: int(p.name.split("-")[-1]),
    )
    if not cks:
        return []
    st = cks[-1] / "trainer_state.json"
    if not st.exists():
        return []
    d = json.loads(st.read_text(encoding="utf-8", errors="replace"))
    return [x for x in (d.get("log_history") or []) if "rewards/chosen" in x], cks[-1].name


def main() -> int:
    got = rows_from_state()
    if not got:
        print(f"  ★尚无 checkpoint 的 trainer_state.json（{CKPT}）")
        return 1
    rows, ckname = got
    print(f"=== 全长跑：最新 checkpoint = {ckname} ✓，指标点 {len(rows)} 个 ===")
    if not rows:
        print("  ★该 checkpoint 的 log_history 里还没有奖励指标")
        return 0

    n = len(rows)
    pick = sorted({0, n // 8, n // 4, n // 2, (3 * n) // 4,
                   (7 * n) // 8, n - 1})
    print(f"  {'步':>6} {'epoch':>8} {'loss':>7} {'chosen':>8} "
          f"{'rejected':>9} {'margin':>8} {'acc':>7}")
    for i in pick:
        d = rows[i]
        print(f"  {i+1:>6} {float(d.get('epoch', 0)):>8.3f} "
              f"{float(d.get('loss', 0)):>7.4f} "
              f"{float(d.get('rewards/chosen', 0)):>8.3f} "
              f"{float(d.get('rewards/rejected', 0)):>9.3f} "
              f"{float(d.get('rewards/margins', 0)):>8.3f} "
              f"{float(d.get('rewards/accuracies', 0)):>7.4f}")

    last = rows[-1]
    c = float(last.get("rewards/chosen", 0))
    r = float(last.get("rewards/rejected", 0))
    print(f"\n=== ★当前末点（第 {n} 个指标点 ✓，epoch {float(last.get('epoch',0)):.3f} ✓）===")
    print(f"  rewards/chosen   = {c:+.3f}   ← **唯一的关键量** ✓")
    print(f"  rewards/rejected = {r:+.3f}")
    print(f"  比（抬高 : 压低）= 1 : {abs(r)/max(abs(c), 1e-6):.2f}")

    # ★M3 的末态作参照 ✓
    if M3.exists():
        st = json.loads(M3.read_text(encoding="utf-8"))
        hist = [x for x in (st.get("log_history") or []) if "rewards/chosen" in x]
        if hist:
            m3c = float(hist[-1]["rewards/chosen"])
            m3r = float(hist[-1]["rewards/rejected"])
            print(f"\n  M3 末态（参照 ✓）：chosen {m3c:+.3f}  rejected {m3r:+.3f} "
                  f"⇒ 比 1 : {abs(m3r)/max(abs(m3c),1e-6):.0f} ✗")

            # ★★★窗口均值对照（唯一的稳健对照 ✓）★★★
            #   ★教训：M3 的单点 chosen 剧烈震荡（idx20 +4.89 ✓ / idx100 −1.66 ✗）✗
            #     ⇒ **单点对照不可靠** ✗ ⇒ 必须用**窗口均值** ✓
            #   ★教训二：本脚本先前的「步」列印的是**索引** ✗ 不是训练步 ✗
            #     ⇒ 训练步 = 索引 × 5 ✓（两边的 logging_steps 都是 5 ✓）
            W = 10
            n_now = len(rows)
            print(f"\n=== ★窗口均值对照（每 {W} 个指标点的均值 ✓，步 = 索引×5 ✓）===")
            print(f"  {'步(全长)':>9} {'步(M3)':>8} {'全长chosen ✓':>13} "
                  f"{'M3chosen ✗':>12} {'差(全长−M3)':>12}")
            for start in range(0, min(n_now, len(hist)) - W + 1, W):
                fc = [float(rows[j]["rewards/chosen"]) for j in range(start, start + W)]
                mc = [float(hist[j]["rewards/chosen"]) for j in range(start, start + W)]
                fa, ma = sum(fc) / W, sum(mc) / W
                print(f"  {(start+W)*5:>9} {(start+W)*5:>8} {fa:>13.3f} "
                      f"{ma:>12.3f} {fa-ma:>12.3f}")
            i_last = min(n_now, len(hist))
            s0 = max(0, i_last - W)
            fa = sum(float(rows[j]["rewards/chosen"]) for j in range(s0, i_last)) / (i_last - s0)
            ma = sum(float(hist[j]["rewards/chosen"]) for j in range(s0, i_last)) / (i_last - s0)
            print(f"\n  ★最末窗口均值：全长 {fa:+.3f} vs M3 {ma:+.3f} ⇒ "
                  f"**差 {fa-ma:+.3f}** "
                  f"{'✓ capfix 明显更好' if fa - ma > 0.5 else ('✗ 未拉开 —— 需警惕' if fa - ma > -0.5 else '✗✗ capfix 反而更差')}")
            print(f"  ★M3 的病态形态：chosen **晚期单调塌陷** "
                  f"（idx20 +4.89 → idx100 −1.66 → idx300 +0.84 → 末态 +0.34 ✗）")
            print(f"  ★⇒ 判据是**末段是否塌陷** ✓，不是单点是否 >+1 ✗")

    print(f"\n★判读：")
    if c >= 1.0:
        print(f"  chosen {c:+.3f} ≥ +1 ⇒ **目前守住** ✓ —— 病态尚未出现 ✓")
    elif c >= 0.3:
        print(f"  chosen {c:+.3f} 在 0.3~1 之间 ⇒ **警戒** ✗ —— 接近 M3 的 +0.34 ✗")
    else:
        print(f"  chosen {c:+.3f} < 0.3 ⇒ **病态已出现** ✗✗ —— "
              f"与 M3（+0.34 ✗）同量级 ✓ ⇒ capfix 不足，须改配比 ✓")
    print("\nFULLCURVE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
