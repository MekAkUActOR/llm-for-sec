# -*- coding: utf-8 -*-
"""量 needlefix 混料的真实 token 长度（prompt+answer），判定 cutoff_len 是否与数据匹配。

同时输出：若按 LLaMA-Factory 的"保留头部"截断口径，各 cutoff 下有多少行的
**assistant 回复会被截掉**（= 该行沦为无效训练样本）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from transformers import AutoTokenizer  # noqa: E402

SNAP = (r"J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base"
        r"\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
P = ROOT / "data" / "lf" / "sec_sft_needlefix.jsonl"
tok = AutoTokenizer.from_pretrained(SNAP)

tot = []
ans_only = []
with P.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        msgs = r.get("messages") or []
        full = 0
        for m in msgs:
            full += len(tok(m.get("content") or "", add_special_tokens=False).input_ids)
        a = len(tok((msgs[-1].get("content") or ""), add_special_tokens=False).input_ids) if msgs else 0
        tot.append(full)
        ans_only.append(a)

tot.sort()
ans_only.sort()
n = len(tot)


def q(arr, p):
    return arr[min(n - 1, int(p * n))]


print(f"needlefix 混料 {n:,} 行（prompt+answer 全序列 token）")
print(f"  min={tot[0]} p50={q(tot,.5)} p90={q(tot,.9)} p95={q(tot,.95)} p99={q(tot,.99)} max={tot[-1]}")
print(f"  assistant 回复长度: p50={q(ans_only,.5)} p90={q(ans_only,.9)} max={ans_only[-1]}")
print()
print(f"{'cutoff':>7} {'超长行数':>9} {'占比':>7} {'回复被截掉的行数':>17} {'占比':>7}")
# 头部保留截断的粗略判据：prompt_tokens + 1 > cutoff ⇒ 回复整段（或大部分）被截掉
prompts = []
with P.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        msgs = r.get("messages") or []
        pl = 0
        for m in msgs[:-1]:
            pl += len(tok(m.get("content") or "", add_special_tokens=False).input_ids)
        prompts.append(pl)
for cap in (2048, 3072, 4096, 6144):
    over = sum(1 for x in tot if x > cap)
    cut = sum(1 for pl, a in zip(prompts, ans_only) if pl + 1 >= cap)
    print(f"{cap:>7} {over:>9,} {over/n*100:>6.1f}% {cut:>17,} {cut/n*100:>6.1f}%")
