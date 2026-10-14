# -*- coding: utf-8 -*-
"""核实 objective ③ 的"结构/行为层样本"：doc_structure.jsonl 的行数与层级构成。"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S = ROOT / "data/sft/m2.5-staging"

print("=== staging 各族真实行数 ===")
for f in sorted(S.glob("*.jsonl")):
    n = sum(1 for l in f.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip())
    print(f"  {f.name:<30} {n:>7,} 行  {f.stat().st_size/1e6:6.2f} MB")

p = S / "doc_structure.jsonl"
if p.exists():
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"\n=== {p.name}：{len(rows)} 行，{len(rows[0]) if rows else 0} 个顶层键 ===")
    print("顶层键 =", list(rows[0].keys()))
    for k in ("layer", "kind", "carrier", "mechanism", "type", "site", "axis", "tag"):
        vals = Counter(str(r.get(k)) for r in rows if k in r)
        if vals:
            print(f"  {k}: {dict(vals.most_common(12))}")

    # 结构层 / 行为层 的关键词判据
    import re
    text = p.read_text(encoding="utf-8", errors="replace")
    for pat in ("structure", "behavior", "behaviour", "结构", "行为"):
        print(f"  出现 '{pat}': {len(re.findall(pat, text))} 次")
else:
    print("✗ 缺 doc_structure.jsonl")
