# -*- coding: utf-8 -*-
"""打印某份 longctx 报告的 needle_success / needle_counts 原文结构。"""
import json
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")
name = sys.argv[1] if len(sys.argv) > 1 else "longctx-soup-a050.json"
d = json.loads((R / name).read_text(encoding="utf-8"))
for k in ("name", "prompt_format", "max_new", "n_docs", "elapsed_s",
          "needle_trials_per_cell"):
    if k in d:
        print(f"{k} = {d[k]!r}")
for k in ("needle_success", "needle_counts"):
    print(f"\n--- {k} ---")
    print(json.dumps(d.get(k), ensure_ascii=False, indent=2)[:1800])
