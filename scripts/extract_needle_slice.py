# -*- coding: utf-8 -*-
"""抽取 needle 修复用的长上下文切片，并核对契约回放集 schema。

- 长上下文切片：sft_m25.jsonl 中 task 前缀 ∈ {T13-retrieval, T10-multiturn}
- 契约回放集：data/sft/sft_v0.jsonl（m2-calib 的契约来源）
两处 schema 必须一致，否则不能直接拼进同一个 LLaMA-Factory 数据集。
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SFT = ROOT / "data" / "lf" / "sft_m25.jsonl"
V0 = ROOT / "data" / "lf" / "sft_v0.jsonl"
OUT = ROOT / "data" / "lf" / "needle_longctx_slice.jsonl"
FAMS = ("T13-retrieval", "T10-multiturn")

n = kept = 0
schemas = Counter()
with SFT.open(encoding="utf-8") as f, OUT.open("w", encoding="utf-8") as g:
    for line in f:
        if not line.strip():
            continue
        n += 1
        r = json.loads(line)
        if str(r.get("task") or "").split(":")[0].strip() in FAMS:
            kept += 1
            g.write(line)
            for m in (r.get("messages") or r.get("conversations") or []):
                schemas[tuple(sorted(m.keys()))] += 1
print(f"sft_m25 总行 = {n:,}；长上下文切片写出 = {kept:,} → {OUT.name}")
print("切片内 message 字段形态:", dict(schemas))

with V0.open(encoding="utf-8") as f:
    first = json.loads(f.readline())
    v0n = sum(1 for line in f if line.strip()) + 1
print(f"\nsft_v0.jsonl 行数 = {v0n:,}")
print("sft_v0 顶层字段 =", sorted(first.keys()))
msgs = first.get("messages") or first.get("conversations") or []
print("sft_v0 message 字段形态 =", sorted(msgs[0].keys()) if msgs else "—")
print("sft_v0 首行样例:", json.dumps(first, ensure_ascii=False)[:300])
