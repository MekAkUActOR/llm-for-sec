# -*- coding: utf-8 -*-
"""量 DPO 混料的真实 token 长度，为 cutoff_len 提供实测依据（docs/01 §11.7 规则 2）。

用法：python scripts/measure_dpo_lengths2.py <jsonl> [<jsonl> ...]
对每个文件报 prompt+chosen / prompt+rejected 的 p50/p90/p95/p99/max，
以及各候选 cutoff 下的截断比例（DPO 截断会同时伤到 chosen 与 rejected 的对比）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from transformers import AutoTokenizer  # noqa: E402

SNAP = (r"J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base"
        r"\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
tok = AutoTokenizer.from_pretrained(SNAP)
CUTS = (768, 1024, 1536, 2048)


def q(a, p):
    return a[min(len(a) - 1, int(p * len(a)))]


for arg in sys.argv[1:]:
    p = ROOT / arg if not Path(arg).is_absolute() else Path(arg)
    lens = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            prompt = sum(len(tok((m.get("value") or m.get("content") or ""),
                                 add_special_tokens=False).input_ids)
                         for m in (r.get("conversations") or r.get("messages") or []))
            ch = len(tok((r.get("chosen") or {}).get("value") or "", add_special_tokens=False).input_ids)
            rj = len(tok((r.get("rejected") or {}).get("value") or "", add_special_tokens=False).input_ids)
            lens.append(prompt + max(ch, rj))
    lens.sort()
    n = len(lens)
    print(f"\n=== {p.name}  ({n:,} 行) ===")
    print(f"  prompt+max(chosen,rejected): p50={q(lens,.5)} p90={q(lens,.9)} "
          f"p95={q(lens,.95)} p99={q(lens,.99)} max={lens[-1]}")
    for c in CUTS:
        over = sum(1 for x in lens if x > c)
        print(f"    cutoff {c:>5}: 超长 {over:>6,} ({over/n*100:5.2f}%)")
