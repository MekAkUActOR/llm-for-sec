# -*- coding: utf-8 -*-
"""M3 DPO 混料的载体构成：直接决定 DPO 会不会再次侵蚀跨载体泛化。

载体判定复用 secfm.carriers.meta_ser 的标记口径（<carrier ...> / <carrier=...>），
并统计 dpo_class / pack / lang 分布与"拒绝率方向"（chosen 是否为 refuse/report）。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "lf" / "dpo_m3.jsonl"

CAR = re.compile(r"<\s*carrier(?:\s*=\s*|\s+)([A-Za-z_]+)")
VERD = re.compile(r"VERDICT:\s*(\{.*?\})")

cls = Counter()
lang = Counter()
pack = Counter()
carriers = Counter()
n = 0
has_v = 0
with P.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        n += 1
        cls[r.get("dpo_class")] += 1
        lang[r.get("lang")] += 1
        pack[r.get("pack")] += 1
        text = " ".join((m.get("value") or "") for m in (r.get("conversations") or []))
        found = CAR.findall(text)
        if found:
            for c in set(found):
                carriers[c] += 1
        else:
            carriers["<无载体标记>"] += 1
        ch = (r.get("chosen") or {}).get("value") or ""
        if "VERDICT" in ch:
            has_v += 1

print(f"总行数 = {n:,}")
print(f"chosen 含 VERDICT 的行 = {has_v:,} ({has_v/n*100:.1f}%)  ← 契约回放")
print("\n载体构成（按 prompt 文本里的标记计；一行可含多标记）")
for k, v in carriers.most_common():
    print(f"  {k:20} {v:>7,}  {v/n*100:5.1f}%")
print("\ndpo_class:", dict(cls.most_common()))
print("lang:", dict(lang.most_common()))
print("pack:", dict(pack.most_common()))
