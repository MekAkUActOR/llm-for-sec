# -*- coding: utf-8 -*-
"""判定 doc_structure（document 载体）的行是否进入**活谱系**的训练文件。

为什么（2026-09-30 晚，由 staging 结账的发现触发）：
  * 载体本体论 D2 记"document 已入训（5,200 行，经 `configs/m3base-topup-e1.yaml:8` 绑定）"。
  * 但 C 路 top-up（`m3base-topup-e1/e2`）**已 FAIL 且权重被登记 `discarded`**。
  * staging 结账又实测：`doc_structure.jsonl` 与 `data/lf/sft_m25.jsonl` **零重叠**。
  ⇒ 必须查清 document 行到底进了哪些训练文件、其中哪些被**活的**模型消费过。
    这直接决定 document 门禁能声称"未见载体"还是只能声称"未见机理"。

用法：python scripts/trace_carrier_into_lineage.py [--carrier data/sft/m2.5-staging/doc_structure.jsonl]
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--carrier", default="data/sft/m2.5-staging/doc_structure.jsonl")
ap.add_argument("--limit", type=int, default=0, help="调试用：只读源文件前 N 行")
a = ap.parse_args()


def h(s):
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()


def norm(text):
    return " ".join(str(text).split())


def user_of(row):
    """取 user 内容：优先 messages 里 role==user，否则常见字段。"""
    msgs = row.get("messages") or row.get("conversations")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and str(m.get("role") or m.get("from")) in (
                    "user", "human"):
                return norm(m.get("content") or m.get("value") or "")
    for k in ("user", "prompt", "query", "instruction", "input"):
        if row.get(k):
            return norm(row[k])
    return ""


# ---- 1. 读载体源文件，建立 user 哈希集合 ----
src = ROOT / a.carrier
assert src.exists(), f"缺载体源文件 {src}"
src_h = {}
with src.open(encoding="utf-8") as f:
    for i, line in enumerate(f):
        if a.limit and i >= a.limit:
            break
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        u = user_of(r)
        if u:
            src_h.setdefault(h(u), 0)
            src_h[h(u)] += 1
print(f"载体源：{src.relative_to(ROOT)}  唯一 user = {len(src_h)}")

# ---- 2. 候选训练文件（data/lf 全部 jsonl）----
CAND = sorted((ROOT / "data" / "lf").glob("*.jsonl"))
print(f"\n{'候选训练文件':<44} {'行数':>9} {'命中载体行':>10} {'命中率':>8}")
print("-" * 78)
results = {}
for c in CAND:
    hit = set()
    n = 0
    with c.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            u = user_of(r)
            if not u:
                continue
            uu = h(u)
            if uu in src_h:
                hit.add(uu)
    if hit:
        results[c.name] = (n, len(hit))
        print(f"{c.name:<44} {n:>9,} {len(hit):>10} "
              f"{len(hit) / len(src_h) * 100:>7.1f}%")

if not results:
    print("（无任何候选文件命中）")
print(f"\n结论：载体 {src.name} 的 {len(src_h)} 条唯一 user 出现在 "
      f"{len(results)} 个训练文件里。")
print("\n下一步须人工图上：这些文件分别被哪个 config 消费、该 config 的产物是否在活谱系里：")
print("  sec_sft_m25       -> configs/m25-full.yaml        -> m25-full（活）")
print("  sec_sft_needlefix -> configs/m2calib-needlefix-e1 -> soup-a050 的一半（活）")
print("  sec_sft_topup     -> configs/m3base-topup-e1/e2   -> **已废弃（C 路 FAIL）**")
print("  sec_dpo_m3_final  -> configs/m3-dpo-final.yaml    -> M3（活，训练中）")
