# -*- coding: utf-8 -*-
"""打印 MUST-C / MUST-B 的完整统计块（n / CI / p / 配对分辨率）。"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"
d = json.loads((R / "topup-verdict-soup-a050.json").read_text(encoding="utf-8"))
print(f"variant={d.get('variant')}  baseline={d.get('baseline')}")
print(f"decision = {d.get('decision')}\n")
for g in d.get("must_gates", []):
    print(f"=== [{g.get('gate')}] {g.get('verdict')} ===")
    for k in ("name", "metric", "baseline_counts", "variant_counts", "baseline", "variant",
              "diff", "tol", "threshold", "test", "diff_ci95", "diff_ci95_paired",
              "p_value", "discordant", "resolution_ok", "resolution_basis", "three_state",
              "note"):
        if k in g:
            print(f"   {k:20} = {json.dumps(g[k], ensure_ascii=False)}")
    print()
