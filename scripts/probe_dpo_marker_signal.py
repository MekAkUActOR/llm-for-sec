# -*- coding: utf-8 -*-
"""★决定性：DPO 训练对的 **chosen/rejected 两侧是否都含 VERDICT**？

若两侧都含 ⇒ **`VERDICT` 标记在偏好对上零判别信号** ⇒ DPO 无梯度压力保留它
⇒ 结构标记随训练衰减，而这是**数据设计缺陷，不是超参问题**。
"""
import json
from collections import Counter
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\data\lf\dpo_m3_final.jsonl")


def val(side) -> str:
    """chosen/rejected 是 dict {'from','value'}；也容忍 str / list。"""
    if isinstance(side, dict):
        return str(side.get("value", ""))
    if isinstance(side, str):
        return side
    if isinstance(side, list):
        return "\n".join(str(m.get("value", m)) if isinstance(m, dict) else str(m) for m in side)
    return ""


n = 0
c = Counter()
by_class = Counter()
cls_marker = Counter()
examples = {}
for line in P.open(encoding="utf-8"):
    if not line.strip():
        continue
    d = json.loads(line)
    n += 1
    ch, rj = val(d.get("chosen")), val(d.get("rejected"))
    chv, rjv = "VERDICT" in ch, "VERDICT" in rj
    key = ("chosen有" if chv else "chosen无") + " / " + ("rejected有" if rjv else "rejected无")
    c[key] += 1
    if not chv:
        cls_marker[d.get("dpo_class", "?")] += 1
        if d.get("dpo_class") not in examples:
            examples[d.get("dpo_class")] = (d.get("id"), ch[:260], rj[:160])
    by_class[d.get("dpo_class", "?")] += 1

print(f"总对数 = {n}\n")
print("=== chosen / rejected 两侧含 VERDICT 的交叉表 ===")
for k, v in c.most_common():
    print(f"  {k:<28} {v:>7}  ({v/n*100:5.1f}%)")

both = sum(v for k, v in c.items() if k == "chosen有 / rejected有")
only_c = sum(v for k, v in c.items() if k == "chosen有 / rejected无")
only_r = sum(v for k, v in c.items() if k == "chosen无 / rejected有")
neither = sum(v for k, v in c.items() if k == "chosen无 / rejected无")

print(f"\n  ★两侧都有（零判别信号） = {both:>7} = {both/n*100:.1f}%")
print(f"    仅 chosen 有（有信号）   = {only_c:>7} = {only_c/n*100:.1f}%")
print(f"    仅 rejected 有           = {only_r:>7} = {only_r/n*100:.1f}%")
print(f"    两侧都无                 = {neither:>7} = {neither/n*100:.1f}%")

print(f"\n=== 按 dpo_class 分布 ===（共 {len(by_class)} 类）")
for k, v in by_class.most_common():
    miss = cls_marker.get(k, 0)
    print(f"  {k:<26} {v:>7}   chosen 缺 VERDICT = {miss:>6} ({miss/v*100:5.1f}%)")

if examples:
    print("\n=== chosen 缺 VERDICT 的样例 ===")
    for cls, (i, ch, rj) in examples.items():
        print(f"\n  [class={cls} id={i}]")
        print("    chosen  : " + ch.replace("\n", " / ")[:230])
        print("    rejected: " + rj.replace("\n", " / ")[:150])

print("\nDPO-PAIR-MARKER-SIGNAL=DONE")
