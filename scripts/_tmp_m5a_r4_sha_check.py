# -*- coding: utf-8 -*-
"""M5A-R4 门禁链启动前仪器 sha 复验（gates runner Step 0 调用；fail-closed）。"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    (r"scripts\probe_jailbreak.py", "6cd4390f7848", "0a6881b"),
    (r"scripts\score_heldout_v2.py", "83d50c8bfb8a", "52bcb1da"),
    (r"data\heldout\v0.7-jailbreak\jailbreak.jsonl", "cbad0fed25d3", "20f816cb"),
    (r"data\heldout\v0.6-dilution\risk_payloads.jsonl", "c6eabcee", ""),
    (r"configs\m5a-dpo-r4.yaml", "47eb8b616fe47f45", "e09c84d5"),
]
bad = []
for rel, pre, suf in CHECKS:
    h = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    ok = h.startswith(pre) and (not suf or h.endswith(suf))
    print(f"  [{'OK' if ok else 'FAIL'}] {rel}: {h[:16]}…{h[-8:]}")
    if not ok:
        bad.append(rel)
if bad:
    print(f"INSTRUMENT-SHA=FAIL: {bad}")
    sys.exit(1)
print("INSTRUMENT-SHA=PASS (jb scorer / heldout scorer / jb suite / dilution pool / r4 config)")
