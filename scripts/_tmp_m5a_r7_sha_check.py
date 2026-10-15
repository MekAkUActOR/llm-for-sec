# -*- coding: utf-8 -*-
"""M5A-R7 门禁链启动前仪器 sha 复验（gates runner Step 0 调用；fail-closed）。

=r6 版（_tmp_m5a_r6_sha_check.py）逐条复制，仅 config 行换 r7（2026-10-16 落盘实测
sha256=2845b6b36c52b1b1215de23a1f9dcf3ef594ab2a4c84f27463373900c5b3e61d）。
冻结仪器四件（jb scorer / heldout scorer / jb suite / dilution pool）与 r6 逐字节
相同——r7 为纯容量对照轮（0.6B→8B + 全参→LoRA），仪器零改动；config 行 = r7
LoRA 适配件（configs/m5a-dpo-r7.yaml 头部登记的 LoRA 适配组）新 sha。"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    (r"scripts\probe_jailbreak.py", "6cd4390f7848", "0a6881b"),
    (r"scripts\score_heldout_v2.py", "83d50c8bfb8a", "52bcb1da"),
    (r"data\heldout\v0.7-jailbreak\jailbreak.jsonl", "cbad0fed25d3", "20f816cb"),
    (r"data\heldout\v0.6-dilution\risk_payloads.jsonl", "c6eabcee", ""),
    (r"configs\m5a-dpo-r7.yaml", "2845b6b36c52b1b1", "c5b3e61d"),
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
print("INSTRUMENT-SHA=PASS (jb scorer / heldout scorer / jb suite / dilution pool / r7 config)")
