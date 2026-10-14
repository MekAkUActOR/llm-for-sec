# -*- coding: utf-8 -*-
"""有界打印 document 门禁 manifest 的关键结论块。"""
import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data" / "heldout" / "v0.6-document"
m = json.loads((D / "manifest.json").read_text(encoding="utf-8"))

print("=== 计数 ===")
for k in ("n_items", "n_robustness", "n_robustness_unseen_mechanism",
          "n_control_trained_site", "n_alignment", "robustness_n", "control_n",
          "by_language", "by_domain"):
    print(f"  {k} = {json.dumps(m.get(k), ensure_ascii=False)[:200]}")

print("\n=== claims ===")
print(json.dumps(m.get("claims"), ensure_ascii=False, indent=1))

print("\n=== train_side（前 700 字）===")
print(json.dumps(m.get("train_side"), ensure_ascii=False)[:700])

print("\n=== gate_side（前 500 字）===")
print(json.dumps(m.get("gate_side"), ensure_ascii=False)[:500])

print("\n=== overlap（前 500 字）===")
print(json.dumps(m.get("overlap"), ensure_ascii=False)[:500])

print("\n=== robustness_by_mechanism ===")
print(json.dumps(m.get("robustness_by_mechanism"), ensure_ascii=False)[:600])
