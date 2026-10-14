# -*- coding: utf-8 -*-
"""M3 失效模式诊断（CPU）：DPO 到底把行为改成了什么？

不猜机制，直接看文本。对同一批条目（v0.3-gen 鲁棒性 168 条）：
  1. 找出"A 臂有 VERDICT 而 B 臂没有"的条目，把两侧原文并排打印；
  2. 把 B 臂的无 VERDICT 响应归类（空/极短拒答/长但无裁决行/其它）。
目的：为"重开 M3 决策"提供**现象层**的事实，而不是先换超参再试。
"""
import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")


def load(name: str):
    p = R / name
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            rows[d["id"]] = d
    return rows


a = load("resp-chat-gen-soup-a050.jsonl")   # 起点
b = load("resp-chat-gen-m3-dpo.jsonl")     # M3 产物
common = sorted(set(a) & set(b))
print(f"soup-a050 n={len(a)}，m3-dpo n={len(b)}，共同 id = {len(common)}")


def has_verdict(t: str) -> bool:
    return "VERDICT" in t


def verdict_lines(t: str):
    return [l.strip() for l in t.splitlines() if "VERDICT" in l]


only_a = [i for i in common if has_verdict(a[i]["text"]) and not has_verdict(b[i]["text"])]
only_b = [i for i in common if has_verdict(b[i]["text"]) and not has_verdict(a[i]["text"])]
both = [i for i in common if has_verdict(a[i]["text"]) and has_verdict(b[i]["text"])]
neither = [i for i in common if not has_verdict(a[i]["text"]) and not has_verdict(b[i]["text"])]
print(f"\n2×2（含 VERDICT）：both={len(both)}  only_soup={len(only_a)}  "
      f"only_m3={len(only_b)}  neither={len(neither)}")

# --- B 臂无 VERDICT 响应的归类 ---
print("\n=== m3-dpo 无 VERDICT 响应的形态归类 ===")
cat = Counter()
samples = {}
for i in common:
    if has_verdict(b[i]["text"]):
        continue
    t = b[i]["text"].strip()
    c = len(t)
    if c == 0:
        k = "空响应"
    elif c < 40:
        k = "极短（<40 字符）"
    elif c < 120:
        k = "短（40–120）"
    else:
        k = "长（≥120）但无 VERDICT 行"
    cat[k] += 1
    samples.setdefault(k, []).append((i, t, c))
for k, v in cat.most_common():
    print(f"  {k:<24} {v:>4} 条")

# --- 并排样例（A 有、B 无）---
print("\n=== 并排样例：起点有 VERDICT、M3 没有（前 4 条）===")
for i in only_a[:4]:
    print(f"\n----- id={i}  kind={a[i].get('kind')} lang={a[i].get('language')} -----")
    ta, tb = a[i]["text"].strip(), b[i]["text"].strip()
    print(f"  [起点 soup-a050] {len(ta)} 字符：")
    print("    " + ta[:420].replace("\n", "\n    "))
    print(f"  [M3 m3-dpo] {len(tb)} 字符：")
    print("    " + (tb[:420] if tb else "<空>").replace("\n", "\n    "))

# --- m3-dpo 里那些"长但无 VERDICT"的样例 ---
for k in ("长（≥120）但无 VERDICT 行", "短（40–120）", "极短（<40 字符）", "空响应"):
    if samples.get(k):
        i, t, c = samples[k][0]
        print(f"\n=== m3-dpo [{k}] 样例 id={i}（{c} 字符）===")
        print("    " + (t[:400] if t else "<空>").replace("\n", "\n    "))

# --- 长度对照 ---
la = [len(a[i]["text"]) for i in common]
lb = [len(b[i]["text"]) for i in common]
print(f"\n=== 长度（字符）===\n  soup-a050 p50={st.median(la):.0f} mean={st.mean(la):.0f} max={max(la)}")
print(f"  m3-dpo    p50={st.median(lb):.0f} mean={st.mean(lb):.0f} max={max(lb)}")
print("\nM3-FAILUREMODE=DONE")
