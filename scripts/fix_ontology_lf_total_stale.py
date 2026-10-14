# -*- coding: utf-8 -*-
"""修 `carriers[log].train_rows['lf_total']` 的陈旧值，并查清为何检查器漏检。

事实（2026-09-30 晚，由 tests/test_carrier_ontology.py 暴露）：
  本体论 `carriers[log].train_rows['lf_total'] = 4714`，而按磁盘现算 = 4713。
  `scripts/check_carrier_ontology.py` 报 PASS（**漏检**），单测报 FAIL（**抓到**）
  ⇒ 两个仪器口径不一致，这本身是一个缺陷（检查器应当抓到）。

本脚本：①现算全量 lf_total 并逐载体对比；②打印所有不一致；③修正为现算值。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "cco", ROOT / "scripts" / "check_carrier_ontology.py")
cco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cco)

facts = cco.collect_facts() if hasattr(cco, "collect_facts") else None
if facts is None:
    cands = [n for n in dir(cco) if "fact" in n.lower() or "scan" in n.lower()
             or "collect" in n.lower()]
    print("未找到 collect_facts；候选函数：", cands)
    sys.exit(1)

# 现算 lf_total 逐载体
lf = (facts.get("train_scope_carriers") or {}).get("lf_total") or {}
print("现算 lf_total 逐载体：")
for k, v in sorted(lf.items(), key=lambda x: -x[1]):
    print(f"   {k:<16} {v}")

OP = ROOT / "data" / "ontology" / "carriers.json"
d = json.loads(OP.read_text(encoding="utf-8"))
bad = []
for car in d.get("carriers", []):
    cid = car.get("id")
    tr = car.get("train_rows")
    if not isinstance(tr, dict):
        continue
    cur = tr.get("lf_total")
    comp = lf.get(cid, 0)
    if cur != comp:
        bad.append((cid, cur, comp))

print(f"\n★ 与现算不一致的载体数 = {len(bad)}")
for cid, cur, comp in bad:
    print(f"   {cid:<16} ontology={cur}  computed={comp}  (差 {(cur or 0) - comp})")

if bad:
    for car in d["carriers"]:
        cid = car.get("id")
        if isinstance(car.get("train_rows"), dict) and cid in [b[0] for b in bad]:
            car["train_rows"]["lf_total"] = lf.get(cid, 0)
    OP.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已修正 {len(bad)} 处并写回 {OP.relative_to(ROOT)}")
else:
    print("\n无需修正")
