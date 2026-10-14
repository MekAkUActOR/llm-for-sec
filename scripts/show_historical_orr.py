# -*- coding: utf-8 -*-
"""查历史裁定里 MUST-C/ORR 条目，确认 fail-open 缺陷的历史波及范围。"""
import glob
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"
print("=== 历史裁定（备份副本）里的 ORR / SHOULD 条目 ===")
for f in sorted(glob.glob(str(R / "verdict-backup-pre-orrfix" / "topup-verdict-*.json"))):
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    print(f"\n--- {Path(f).name}  decision={d.get('decision')} ---")
    for s in d.get("should", []):
        nm = str(s.get("name", ""))
        if "ORR" in nm or "误拒" in nm or "ASR" in nm:
            print(f"    {nm}: base={s.get('baseline')} var={s.get('variant')} "
                  f"diff={s.get('diff')} verdict={s.get('verdict')} "
                  f"counts={s.get('baseline_counts')}/{s.get('variant_counts')}")
    if not any("ORR" in str(s.get("name", "")) for s in d.get("should", [])):
        print("    （无 ORR 条目）")
    print(f"    should 条目数={len(d.get('should', []))}, blockers={len(d.get('blockers', []))}")
