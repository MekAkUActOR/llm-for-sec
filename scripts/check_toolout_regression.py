# -*- coding: utf-8 -*-
"""核对 v0.4-toolout 回归集（70 条 / 17 机理）能否承担 G1 的 tool_output 轴。

背景（S0.4 遗留）：裁决 `scripts/topup_verdict.py` 的 G1 只由 v0.2.1 的 tool_output
子集承担（n≈4，严重欠功效）；而 70 条的 v0.4-toolout 已评测却未被使用。

诚实标注：该套件**已被同族训练数据污染**（M3 载体批的 tool_output 机理与其同族），
按 docs/01 §10.3 **只能作回归集**，不得作为"未见载体"证据。
"""
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "reports"
TAGS = ["m2calib", "soup-a035", "soup-a050", "m2calib-needlefix-e1", "m25full"]
print(f"{'tag':24} {'toolout 条数':>12} {'顺从':>6} {'报告+拒绝':>10} {'顺从率':>8} {'拒绝率':>8}")
for tag in TAGS:
    p = R / f"scored-chat-to-{tag}-v2.json"
    if not p.exists():
        print(f"{tag:24} {'缺':>12}")
        continue
    d = json.load(open(p, encoding="utf-8"))
    items = d.get("items") or []
    n = len(items)
    comp = rep = 0
    for i in items:
        dv = i.get("derived") or {}
        ax = i.get("axes") or {}
        # 复用裁定脚本的轴口径：暴力遍历可能的键名，找不到就退回 attack_success
        s = dv.get("attack_success")
        if s is None:
            s = ax.get("attack_success")
        try:
            s = float(s)
        except (TypeError, ValueError):
            s = None
        if s == 1.0:
            comp += 1
        elif s == 0.0:
            rep += 1
    print(f"{tag:24} {n:>12} {comp:>6} {rep:>10} {comp/max(1,n):>8.3f} {rep/max(1,n):>8.3f}")

# 打印一条样例的可用键，确认仪器口径
p = R / "scored-chat-to-soup-a050-v2.json"
if p.exists():
    d = json.load(open(p, encoding="utf-8"))
    it = (d.get("items") or [{}])[0]
    print("\n样例条目顶层键:", sorted(it.keys()))
    print("axes:", json.dumps(it.get("axes"), ensure_ascii=False))
    print("derived:", json.dumps(it.get("derived"), ensure_ascii=False))
