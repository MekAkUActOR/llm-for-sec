# -*- coding: utf-8 -*-
"""M5 门禁辅助：needle 逐格 + 32768 PPL 对比（起点 vs 新臂）。"""
import json
import sys

for tag in sys.argv[1:]:
    d = json.load(open(f"reports/longctx-{tag}-chat.json", encoding="utf-8"))
    cells = {L: {lg: f"{c['k']}/{c['n']}" for lg, c in langs.items()}
             for L, langs in d["needle_counts"].items()}
    tot_k = sum(c["k"] for langs in d["needle_counts"].values() for c in langs.values())
    tot_n = sum(c["n"] for langs in d["needle_counts"].values() for c in langs.values())
    ppl = {lg: round(v["ppl"], 3) for lg, v in d["ppl"]["32768"].items()}
    print(f"{tag}: needle {tot_k}/{tot_n} = {tot_k/tot_n:.4f} cells={cells} ppl32768={ppl}")
