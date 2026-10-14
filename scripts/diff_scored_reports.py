# -*- coding: utf-8 -*-
"""比较两份判分报告：到底哪些条目/字段变了（而非只看哈希）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(arg):
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / p
    return json.loads(p.read_text(encoding="utf-8")), p


a, pa = load(sys.argv[1])
b, pb = load(sys.argv[2])
print(f"A = {pa.name}\nB = {pb.name}\n")

# 顶层键差异（可能只是版本字符串/notes）
ka, kb = set(a), set(b)
if ka != kb:
    print(f"顶层键差异：仅A={ka-kb}  仅B={kb-ka}")
for k in sorted(ka & kb):
    if isinstance(a[k], (str, int, float, bool)) or a[k] is None:
        if a[k] != b[k]:
            print(f"  顶层标量 {k}: A={a[k]!r}  B={b[k]!r}")

# metrics
ma, mb = a.get("metrics") or {}, b.get("metrics") or {}
if ma != mb:
    print(f"\nmetrics 差异：")
    for k in sorted(set(ma) | set(mb)):
        if ma.get(k) != mb.get(k):
            print(f"   {k}: A={ma.get(k)}  B={mb.get(k)}")
else:
    print("\nmetrics 完全相同 ✓")

# 逐条 derived 差异
ia = {r.get("id"): r for r in a.get("items", [])}
ib = {r.get("id"): r for r in b.get("items", [])}
print(f"\n条目数 A={len(ia)} B={len(ib)}")
only_a, only_b = set(ia) - set(ib), set(ib) - set(ia)
if only_a or only_b:
    print(f"  仅A={sorted(only_a)}  仅B={sorted(only_b)}")
n = 0
for i in sorted(set(ia) & set(ib)):
    ra, rb = ia[i], ib[i]
    da, db = ra.get("derived") or {}, rb.get("derived") or {}
    keys = set(da) | set(db)
    diff = {k: (da.get(k), db.get(k)) for k in keys if da.get(k) != db.get(k)}
    if diff or ra.get("label") != rb.get("label"):
        n += 1
        print(f"  {i}: label {ra.get('label')!r} -> {rb.get('label')!r}  derived {diff}")
        if n >= 25:
            print("  …（截断）")
            break
print(f"\n有差异的条目数 = {n}（≥25 时截断显示）")
