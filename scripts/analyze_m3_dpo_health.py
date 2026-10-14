# -*- coding: utf-8 -*-
"""M3 DPO 健康度：`rewards/accuracies` 轨迹 vs 预注册的健康区间。

预注册 reports/m3-dpo-preregistration.md L85：
  「`rewards/accuracies`：健康区间约 **0.55–0.85**；若 **≥0.97 且维持** → **预警**
    （可能坍缩为空心拒答）。」
L81-83 说明 DPO 的典型崩塌不是 loss 上升，而是 accuracy 冲高 + margins 无界增大。

本脚本从训练 stdout 日志里抽取每个 logging 点的观测值并统计。
"""
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = [ROOT / "reports/logs/m3-dpo-resume-launch.log",
        ROOT / "reports/logs/m3-dpo-run.log",
        ROOT / "reports/logs/m3-dpo-launch.log"]

# 匹配形如 {'loss': '0.15', 'rewards/accuracies': '0.925', ...}
NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


def grab(text, key):
    return [float(m.group(1)) for m in
            re.finditer(rf"'{re.escape(key)}':\s*'({NUM})'", text)]


found = False
for lg in LOGS:
    if not lg.exists():
        continue
    t = lg.read_text(encoding="utf-8", errors="replace")
    acc = grab(t, "rewards/accuracies")
    if not acc:
        continue
    found = True
    mar = grab(t, "rewards/margins")
    ls = grab(t, "loss")
    print(f"=== {lg.name} ===")
    print(f"logging 点数（rewards/accuracies 观测）= {len(acc)}")
    print(f"  accuracies: min={min(acc):.4f} p50={st.median(acc):.4f} "
          f"mean={st.mean(acc):.4f} max={max(acc):.4f}")
    if mar:
        print(f"  margins   : min={min(mar):.4f} p50={st.median(mar):.4f} max={max(mar):.4f}")
    if ls:
        print(f"  loss      : min={min(ls):.4f} p50={st.median(ls):.4f} max={max(ls):.4f}")

    ge97 = sum(1 for a in acc if a >= 0.97)
    inband = sum(1 for a in acc if 0.55 <= a <= 0.85)
    above = sum(1 for a in acc if a > 0.85)
    print(f"\n  ★预注册判据（区间 0.55–0.85）")
    print(f"    落在健康区间内 = {inband}/{len(acc)} = {inband/len(acc)*100:.1f}%")
    print(f"    高于健康上界   = {above}/{len(acc)} = {above/len(acc)*100:.1f}%")
    print(f"    ≥0.97（预警线）= {ge97}/{len(acc)} = {ge97/len(acc)*100:.1f}%")

    # 「且维持」：最长连续 ≥0.97 的段
    run = best = 0
    for a in acc:
        run = run + 1 if a >= 0.97 else 0
        best = max(best, run)
    print(f"    最长连续 ≥0.97 = {best} 个 logging 点")
    print(f"    前 20 个观测 = {[round(x,3) for x in acc[:20]]}")
    print(f"    后 20 个观测 = {[round(x,3) for x in acc[-20:]]}")

    # 前半/后半趋势
    h = len(acc) // 2
    print(f"    前半 mean={st.mean(acc[:h]):.4f}  后半 mean={st.mean(acc[h:]):.4f}")
    print()
    break

if not found:
    print("未在日志中找到 rewards/accuracies 观测")
    sys.exit(1)
