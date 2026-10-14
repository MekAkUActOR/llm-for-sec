# -*- coding: utf-8 -*-
"""★验证长度利用假设：DPO 的 chosen 是否系统性长于 rejected？

预测（先写后算）：
  若 DPO 学到"越长越好"，则 len(chosen) > len(rejected) 应在**绝大多数**对上成立，
  且在最"空心"的 carrier_inject_hollow 类上差距最大（chosen=长报告 vs rejected="无法协助。"）。
  果如此 ⇒ 96 token 预算被散文吃光、到不了 VERDICT 块，契约保留率崩塌是**必然**的。
"""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\data\lf\dpo_m3_final.jsonl")


def val(side) -> str:
    if isinstance(side, dict):
        return str(side.get("value", ""))
    if isinstance(side, str):
        return side
    if isinstance(side, list):
        return "\n".join(str(m.get("value", m)) if isinstance(m, dict) else str(m) for m in side)
    return ""


tot = 0
longer = 0
per = defaultdict(lambda: {"n": 0, "longer": 0, "lc": [], "lr": [], "ratio": []})

for line in P.open(encoding="utf-8"):
    if not line.strip():
        continue
    d = json.loads(line)
    ch, rj = val(d.get("chosen")), val(d.get("rejected"))
    if not ch or not rj:
        continue
    cls = d.get("dpo_class", "?")
    tot += 1
    islong = len(ch) > len(rj)
    longer += islong
    g = per[cls]
    g["n"] += 1
    g["longer"] += islong
    g["lc"].append(len(ch))
    g["lr"].append(len(rj))
    g["ratio"].append(len(ch) / max(len(rj), 1))

print(f"总有效对 = {tot}")
print(f"★chosen 长于 rejected 的比例 = {longer}/{tot} = {longer/tot*100:.1f}%\n")
print(f"{'dpo_class':<28} {'n':>6} {'chosen更长':>10} {'chosen中位':>10} "
      f"{'rejected中位':>12} {'中位长度比':>10}")
print("-" * 84)
for cls, g in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
    print(f"{cls:<28} {g['n']:>6} {g['longer']/g['n']*100:>9.1f}% "
          f"{st.median(g['lc']):>10.0f} {st.median(g['lr']):>12.0f} "
          f"{st.median(g['ratio']):>10.2f}")

allc = [x for g in per.values() for x in g["lc"]]
allr = [x for g in per.values() for x in g["lr"]]
print(f"\n全局：chosen 中位 {st.median(allc):.0f} 字符，"
      f"rejected 中位 {st.median(allr):.0f} 字符，"
      f"中位比 {st.median(allc)/st.median(allr):.2f}×")

# 与生成上限对齐：96 token 约 300+ 字符（中文约 1.5 字符/token，英文约 4）
print("\n对照：生成上限 max_new_tokens=96 ⇒ 中文观测上限约 450 字符"
      "（resp dump 实测 max=509）")
print(f"  chosen 中位 {st.median(allc):.0f} 字符 ⇒ "
      f"{'已超预算，必须被截断' if st.median(allc) > 400 else '大致在预算内'}")
print("\nDPO-LENGTH-BIAS=DONE")
