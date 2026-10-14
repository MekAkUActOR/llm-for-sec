# -*- coding: utf-8 -*-
"""量 DPO 训练数据的真实长度分布，用于按数据设定 cutoff_len（docs/01 §11.7 规则 2）。

LLaMA-Factory 的 DPO 会把 chosen/rejected 与原 prompt 拼接，最长序列 ≈
max(len(prompt)+len(chosen), len(prompt)+len(rejected))（含模板槽位）。
这里直接对 **拼接后的 user+assistant 全文** 做 tokenizer 长度统计（保守上界）。
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transformers import AutoTokenizer  # noqa: E402

SNAP = (r"J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base"
        r"\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
tok = AutoTokenizer.from_pretrained(SNAP)

lanes: list[int] = []
with (ROOT / "data" / "lf" / "dpo_m3.jsonl").open(encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= N:
            break
        if not line.strip():
            continue
        r = json.loads(line)
        total = 0
        # LLaMA-Factory 的 sharegpt-DPO 行：conversations 为 prompt，chosen/rejected 为 {from,value}
        for m in r.get("conversations") or []:
            total += len(tok(m.get("value") or m.get("content") or "",
                             add_special_tokens=False).input_ids)
        for k in ("chosen", "rejected"):
            v = r.get(k)
            if isinstance(v, dict):
                v = v.get("value") or v.get("content") or ""
            total += len(tok(v or "", add_special_tokens=False).input_ids)
        lanes.append(total)

lanes.sort()
if lanes:
    def q(p):
        return lanes[min(len(lanes) - 1, int(p * len(lanes)))]
    print(f"样本 n={len(lanes)}（前 {N} 行）")
    print(f"  min={lanes[0]}  p50={q(.5)}  p90={q(.9)}  p95={q(.95)}  p99={q(.99)}  max={lanes[-1]}")
    print(f"  mean={sum(lanes)/len(lanes):.0f}")
    for cap in (512, 768, 1024, 1536, 2048):
        over = sum(1 for x in lanes if x > cap)
        print(f"  cutoff_len={cap:5d} → 截断 {over}/{len(lanes)} = {over/len(lanes)*100:.2f}%")
