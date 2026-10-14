# -*- coding: utf-8 -*-
"""取回 soup-a050 原裁定的比较口径，并用修复后的 ORR 复算其 MUST-C。"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"
d = json.loads((R / "verdict-backup-pre-orrfix" / "topup-verdict-soup-a050.json")
               .read_text(encoding="utf-8"))
print("=== 原裁定顶层键 ===")
print(list(d))
for k in ("variant", "baseline", "family_base", "needle_prompt_format", "decision",
          "must", "hard"):
    if k in d:
        print(f"  {k} = {json.dumps(d[k], ensure_ascii=False)[:300]}")
print("\n=== 全部 should 条目（原裁定）===")
for s in d.get("should", []):
    print(f"  [{s.get('verdict')}] {s.get('name')}  "
          f"base={s.get('baseline')} var={s.get('variant')} diff={s.get('diff')}")
print("\n=== 决策原文 ===")
print(" ", d.get("decision"))
