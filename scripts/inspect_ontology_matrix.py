# -*- coding: utf-8 -*-
"""定位并打印本体论 coverage_matrix 里 document 的条目（含 5200 的两处）。"""
import json
from pathlib import Path

p = Path("data/ontology/carriers.json")
d = json.loads(p.read_text(encoding="utf-8"))
cm = d.get("coverage_matrix")
print("coverage_matrix 类型 =", type(cm).__name__)
if isinstance(cm, dict):
    print("键 =", list(cm)[:12])
    for k, v in cm.items():
        s = json.dumps(v, ensure_ascii=False)
        if "5200" in s or "document" in s:
            print(f"\n--- coverage_matrix[{k}] ---")
            print(s[:900])
elif isinstance(cm, list):
    for i, v in enumerate(cm):
        s = json.dumps(v, ensure_ascii=False)
        if "5200" in s:
            print(f"\n--- coverage_matrix[{i}] ---")
            print(s[:900])
print("\n--- claims ---")
print(json.dumps(d.get("claims"), ensure_ascii=False)[:800])
