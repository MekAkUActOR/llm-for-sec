# -*- coding: utf-8 -*-
"""按 `<carrier>...</carrier>` 信封统计活谱系训练文件里的载体分布。

为什么：`scripts/trace_carrier_into_lineage.py` 证明 `doc_structure.jsonl` 的内容
**只**进了已废弃的 C 路 top-up（`sec_sft_topup.jsonl`），不在活谱系。
但"document 载体是否已入训"还取决于**其他**来源里有无 document 标记的行。
本脚本按信封标签直接数，给出权威答案。
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAT = re.compile(r"<carrier>\s*([A-Za-z_]+)\s*</carrier>", re.IGNORECASE)

FILES = [
    ("sft_m25.jsonl", "m25-full（活）"),
    ("sec_sft_needlefix.jsonl", "soup-a050 的一半（活）"),
    ("sec_sft_needlefix_carrier.jsonl", "R5 候选（未使用）"),
    ("carrier_sft_slice.jsonl", "载体切片（未使用？）"),
    ("sec_sft_topup.jsonl", "C 路 top-up（**已废弃**）"),
    ("dpo_m3_final.jsonl", "M3 DPO（活，训练中）"),
]

for name, role in FILES:
    p = ROOT / "data" / "lf" / name
    if not p.exists():
        print(f"{name:<36} 缺失")
        continue
    c = Counter()
    n = 0
    with p.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            if "<carrier>" not in line:
                continue
            for m in PAT.finditer(line):
                c[m.group(1).lower()] += 1
    tot = sum(c.values())
    top = " ".join(f"{k}={v}" for k, v in c.most_common(8))
    print(f"\n{name:<36} [{role}]")
    print(f"  行数={n:,}  带 carrier 信封的标签出现={tot:,}")
    print(f"  分布：{top if top else '（无 carrier 信封）'}")
    print(f"  ★document = {c.get('document', 0)}")
