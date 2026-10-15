# -*- coding: utf-8 -*-
"""M5A-R6 门禁链启动前仪器 sha 复验（gates runner Step 0 调用；fail-closed）。

=r5 版（_tmp_m5a_r5_sha_check.py）逐条复制，仅 config 行换 r6（2026-10-15 b086bda 落盘实测）。"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    (r"scripts\probe_jailbreak.py", "6cd4390f7848", "0a6881b"),
    (r"scripts\score_heldout_v2.py", "83d50c8bfb8a", "52bcb1da"),
    (r"data\heldout\v0.7-jailbreak\jailbreak.jsonl", "cbad0fed25d3", "20f816cb"),
    (r"data\heldout\v0.6-dilution\risk_payloads.jsonl", "c6eabcee", ""),
    (r"configs\m5a-dpo-r6.yaml", "62b0e3c04f274fd3", "c0e195dc"),
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
print("INSTRUMENT-SHA=PASS (jb scorer / heldout scorer / jb suite / dilution pool / r6 config)")
