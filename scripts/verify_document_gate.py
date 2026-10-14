# -*- coding: utf-8 -*-
"""独立验证 document 门禁套件（不读它的自述，只算磁盘事实）。"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "heldout" / "v0.6-document"

doc = D / "document.jsonl"
if not doc.exists():
    print("套件尚未生成")
    raise SystemExit(0)

kind = Counter()
mech = Counter()
pos = Counter()
sevt = Counter()
n = 0
ids = []
with doc.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        n += 1
        ids.append(str(r.get("id")))
        kind[str(r.get("kind"))] += 1
        mech[str(r.get("mechanism") or r.get("mech") or "?")] += 1
        pos[str(r.get("position") or r.get("pos") or "?")] += 1
        for k in ("severity", "verdict", "policy_expected", "expected"):
            if r.get(k) is not None:
                sevt[f"{k}={r[k]}"] += 1

print(f"document.jsonl 条数 = {n}")
print(f"唯一 id = {len(set(ids))}  （重复 = {n - len(set(ids))}）")
print(f"\nkind 分布 = {dict(kind.most_common())}")
print(f"\nmechanism 数 = {len(mech)}；分布：")
for k, v in mech.most_common():
    print(f"   {k:<28} {v}")
print(f"\nposition 分布 = {dict(pos.most_common())}")
print(f"\n其它字段 = {dict(sevt.most_common())}")

print("\n--- 门禁阈值核对（docs/01 §11.2：鲁棒性 ≥34）---")
rob = kind.get("robustness", 0)
ali = kind.get("alignment", 0)
print(f"   robustness = {rob}  {'✓ 达阈值' if rob >= 40 else '✗'}")
print(f"   alignment  = {ali}  {'✓ 达阈值(≥20)' if ali >= 20 else '✗'}")

print("\n--- manifest.json 的 claims ---")
mf = D / "manifest.json"
if mf.exists():
    m = json.loads(mf.read_text(encoding="utf-8"))
    print("顶层键 =", list(m))
    cl = m.get("claims")
    print(json.dumps(cl, ensure_ascii=False, indent=1)[:1600])
