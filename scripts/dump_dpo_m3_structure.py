# -*- coding: utf-8 -*-
"""查 data/lf/dpo_m3_final.jsonl 的真实结构（我的 chosen/rejected 解析假设不成立）。"""
import json
from collections import Counter
from pathlib import Path

p = Path(r"J:\Projects\llm_for_sec\data\lf\dpo_m3_final.jsonl")
keys = Counter()
first = None
n = 0
for line in p.open(encoding="utf-8"):
    if not line.strip():
        continue
    d = json.loads(line)
    n += 1
    keys[tuple(sorted(d.keys()))] += 1
    if first is None:
        first = d
    if n >= 4000:
        break

print(f"抽样行数 = {n}")
print("--- 顶层键组合分布 ---")
for k, v in keys.most_common():
    print(f"  {v:>6}  {k}")

print("\n--- 第一条原文字段（截断显示）---")
for k, v in first.items():
    if isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")
        for i, it in enumerate(v[:4]):
            if isinstance(it, dict):
                print(f"      [{i}] dict keys={list(it.keys())}")
                for kk, vv in it.items():
                    print(f"           {kk} = {str(vv)[:110]!r}")
            else:
                print(f"      [{i}] {str(it)[:130]!r}")
    else:
        print(f"  {k}: {str(v)[:200]!r}")
