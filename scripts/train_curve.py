# -*- coding: utf-8 -*-
r"""★★★★★ 读 M3 DPO 的**训练曲线**（trainer_state.json ✓）—— 判定是否过优化 ✓。

## 要看什么

| 指标 | 过优化的特征 |
|---|---|
| `rewards/accuracies` ✓ | 趋近 **1.0** ✗ ⇒ 训练集上偏好已被完全拟合 |
| `rewards/margins` ✓ | **单调发散** ✗ ⇒ 隐式奖励无界增长 |
| `loss` ✓ | 趋近 **0** ✗ |
| `logps/chosen` ✓ | 上升 ✓ |
| `logps/rejected` ✓ | **下降** ✗ —— DPO 的典型病态：压低 rejected 而非抬高 chosen ✓ |

**★ 若 `rewards/accuracies` 早早到 1.0 且 margin 持续发散** ⇒ **过优化** ✓✓
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CK = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
WANT = ("loss", "rewards/accuracies", "rewards/margins",
        "rewards/chosen", "rewards/rejected", "logps/chosen", "logps/rejected",
        "grad_norm", "learning_rate", "epoch")


def main() -> int:
    cands = sorted(CK.glob("checkpoint-*/trainer_state.json"),
                   key=lambda p: int(p.parent.name.split("-")[1]))
    if not cands:
        print("★找不到 trainer_state.json")
        return 1
    # 用最大步数的那个（= 最终档 ✓）
    st = json.loads(cands[-1].read_text(encoding="utf-8"))
    log = st.get("log_history") or []
    print(f"=== {cands[-1].parent.name}/trainer_state.json ===")
    print(f"  log 条目 = {len(log)}  全局步数 = {st.get('global_step')}  "
          f"epoch = {st.get('epoch')}")
    keys = sorted({k for e in log for k in e})
    print(f"  出现的指标 = {keys}")

    print(f"\n=== ★曲线（每 ~20 条抽一条 ✓）===")
    hdr = ["step"] + [w for w in WANT if w in keys]
    print("  " + "  ".join(f"{h:>16}" for h in hdr))
    shown = 0
    for i, e in enumerate(log):
        if "loss" not in e and "rewards/margins" not in e:
            continue
        if shown % 20 and i != len(log) - 1:
            shown += 1
            continue
        row = [str(e.get("step", "?"))]
        for w in hdr[1:]:
            v = e.get(w)
            row.append(f"{v:.4f}" if isinstance(v, (int, float)) else "-")
        print("  " + "  ".join(f"{c:>16}" for c in row))
        shown += 1

    print(f"\n=== ★首末对照（决定性 ✓）===")
    def first_last(k: str) -> None:
        vs = [(e.get("step"), e[k]) for e in log
              if isinstance(e.get(k), (int, float))]
        if not vs:
            return
        print(f"  {k:<22} 首 {vs[0][1]:>10.4f} @step{vs[0][0]:<6} "
              f"末 {vs[-1][1]:>10.4f} @step{vs[-1][0]}")
    for k in WANT:
        first_last(k)

    print(f"\n=== ★判读 ===")
    acc = [e["rewards/accuracies"] for e in log
           if isinstance(e.get("rewards/accuracies"), (int, float))]
    mar = [e["rewards/margins"] for e in log
           if isinstance(e.get("rewards/margins"), (int, float))]
    lc = [e["logps/chosen"] for e in log
          if isinstance(e.get("logps/chosen"), (int, float))]
    lr_ = [e["logps/rejected"] for e in log
           if isinstance(e.get("logps/rejected"), (int, float))]
    if acc:
        print(f"  rewards/accuracies: 首 {acc[0]:.4f} → 末 {acc[-1]:.4f}"
              f"  （最大 {max(acc):.4f}）")
        if max(acc) > 0.95:
            print("  ⇒ **训练集偏好准确率 >95%** ✗ ⇒ 已完全拟合 ⇒ 过优化风险高 ✓✓")
    if mar:
        print(f"  rewards/margins:    首 {mar[0]:.4f} → 末 {mar[-1]:.4f}"
              f"  （放大 {abs(mar[-1])/max(abs(mar[0]),1e-9):.1f}×）")
        if abs(mar[-1]) > 4 * max(abs(mar[0]), 1e-9):
            print("  ⇒ **margin 显著发散** ✗ ⇒ 隐式奖励无界 ✓")
    if lc and lr_:
        print(f"  logps/chosen:       {lc[0]:.4f} → {lc[-1]:.4f}  "
              f"(Δ {lc[-1]-lc[0]:+.4f})")
        print(f"  logps/rejected:     {lr_[0]:.4f} → {lr_[-1]:.4f}  "
              f"(Δ {lr_[-1]-lr_[0]:+.4f})")
        if abs(lr_[-1] - lr_[0]) > abs(lc[-1] - lc[0]):
            print("  ⇒ **压低 rejected 多于抬高 chosen** ✗ ⇒ DPO 典型病态 ✓✓")
    print("\nTRAIN-CURVE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
