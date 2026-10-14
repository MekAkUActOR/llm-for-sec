# -*- coding: utf-8 -*-
"""读 alignment 审计的结论部分。"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"
md = R / "alignment-recovery-audit.md"
t = md.read_text(encoding="utf-8").splitlines()
print(f"alignment-recovery-audit.md 行数 = {len(t)}")
print("\n=== 含 VERDICT / 结论 / 判读 的行 ===")
for i, ln in enumerate(t, 1):
    if any(k in ln for k in ("ALIGNMENT-AUDIT=", "VERDICT", "结论", "判读", "裁决", "末行")):
        s = ln.strip()
        if s:
            print(f"{i}: {s[:190]}")

print("\n=== 最后 55 行 ===")
for i, ln in enumerate(t[-55:], len(t) - 54):
    print(f"{i}: {ln[:190]}")

j = R / "alignment-recovery-audit.json"
if j.exists():
    d = json.loads(j.read_text(encoding="utf-8"))
    print(f"\n=== JSON 顶层键 ({len(list(d))}) ===")
    print(list(d))
    for k in ("verdict", "summary", "conclusion", "headline", "l3", "layers"):
        if k in d:
            print(f"\n--- {k} ---")
            print(json.dumps(d[k], ensure_ascii=False)[:900])
