# -*- coding: utf-8 -*-
"""临时调试：decisions.jsonl prompt 长度分布（用后即删）。"""
import json
from pathlib import Path

from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained(r"J:\Projects\llm_for_sec\checkpoints\soup-needlefix-a050")
ROLE = {"system": "system", "human": "user", "gpt": "assistant"}
lens = []
rows = [json.loads(l) for l in Path(r"J:\Projects\llm_for_sec\data\secjev\decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for r in rows:
    conv = [{"role": ROLE[m["from"]], "content": m["value"]} for m in r["conversations"]]
    text = tok.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
    lens.append(len(tok(text, add_special_tokens=False).input_ids))
lens.sort()
import statistics
n = len(lens)
print(f"n={n} min={lens[0]} p50={lens[n//2]} p90={lens[int(n*0.9)]} p99={lens[int(n*0.99)]} max={lens[-1]}")
print("超 4096:", sum(1 for x in lens if x > 4096), "| 超 8192:", sum(1 for x in lens if x > 8192), "| 超 16384:", sum(1 for x in lens if x > 16384))
