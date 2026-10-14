# -*- coding: utf-8 -*-
"""按 task 字段前缀对 M2.5 混料做族普查，并用"文档长度"找出长上下文/检索类族。

判定长上下文族的依据（任一）：row 的 user 内容里出现长文档结构标记
（<document> / <carrier type="document" ...> / 长 body），或行的字符长度 p50 很大。
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "lf" / "sft_m25.jsonl"

fam = Counter()
lens = defaultdict(list)
n = 0
with SRC.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        n += 1
        r = json.loads(line)
        t = str(r.get("task") or "")
        pre = t.split(":")[0].strip() or "<空>"
        fam[pre] += 1
        txt = " ".join((m.get("content") or m.get("value") or "")
                       for m in (r.get("messages") or r.get("conversations") or []))
        lens[pre].append(len(txt))

print(f"总行 = {n:,}\n")
print(f"{'族前缀':26} {'行数':>8} {'字符p50':>9} {'字符p90':>9} {'字符max':>9}")
for k, v in fam.most_common(40):
    L = sorted(lens[k])
    p50 = L[len(L) // 2]
    p90 = L[int(0.9 * len(L))]
    print(f"{k:26} {v:>8,} {p50:>9,} {p90:>9,} {L[-1]:>9,}")
