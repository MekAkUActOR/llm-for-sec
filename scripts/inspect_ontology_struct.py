# -*- coding: utf-8 -*-
"""看 carriers.json 的三处结构，为 v0.6-document 登记做准备。"""
import json
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\data\ontology\carriers.json")
d = json.loads(P.read_text(encoding="utf-8"))
print(f"顶层键 = {list(d.keys())}")
print(f"\ninstruments 类型 = {type(d.get('instruments')).__name__}")
inst = d.get("instruments")
if isinstance(inst, dict):
    for k, v in inst.items():
        print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:200]}")
elif isinstance(inst, list):
    print(f"  列表长度 {len(inst)}；首项 = {json.dumps(inst[0], ensure_ascii=False)[:300]}")

cars = d.get("carriers")
print(f"\ncarriers 数 = {len(cars) if isinstance(cars, list) else '?'}")
if isinstance(cars, list) and cars:
    c0 = cars[0]
    print(f"  首载体键 = {sorted(c0.keys())}")
    print(f"  首载体 id = {c0.get('id')}")
    print(f"  gate_items = {json.dumps(c0.get('gate_items'), ensure_ascii=False)}")

cm = d.get("coverage_matrix")
print(f"\ncoverage_matrix 键 = {list(cm.keys()) if isinstance(cm, dict) else type(cm).__name__}")
if isinstance(cm, dict):
    cells = cm.get("cells")
    print(f"  cells 类型 = {type(cells).__name__}")
    if isinstance(cells, dict) and cells:
        k0 = next(iter(cells))
        print(f"  首个载体 {k0} 的格 = {json.dumps(cells[k0], ensure_ascii=False)[:400]}")
    for k in cm:
        if k != "cells":
            print(f"  {k} = {json.dumps(cm[k], ensure_ascii=False)[:200]}")
print("\nINSPECT-ONTOLOGY=DONE")
