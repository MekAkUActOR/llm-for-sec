# -*- coding: utf-8 -*-
"""M5B-R5 门禁链/训练发射前仪器 sha 复验（沿 _tmp_m5a_r4_sha_check.py 同构；fail-closed）。

冻结值来源：m5b-r4-gates.md 头部（jb scorer / heldout scorer / jb suite / 稀释载荷池）
+ p2rl-round2-preregistration L185（训练池全量 sha，launch-audit-m5-launch.json 冻结登记）。
R5 唯一变量 = p2rl_reward.py H 门控（df89902）；仪器链五件全部不在变量面 ⇒ 必须逐位一致。
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    (r"scripts\probe_jailbreak.py", "6cd4390f7848", "0a6881b"),
    (r"scripts\score_heldout_v2.py", "83d50c8bfb8a", "52bcb1da"),
    (r"data\heldout\v0.7-jailbreak\jailbreak.jsonl", "cbad0fed25d3", "20f816cb"),
    (r"data\heldout\v0.6-dilution\risk_payloads.jsonl", "c6eabcee", ""),
    (r"data\rlvr\p2rl-pool-v01.jsonl", "77ff6cf1d05c0d5cbd93e7be48cc8104bd396fdc3627f3d4ea4bd09528851dd0", ""),
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
print("INSTRUMENT-SHA=PASS (jb scorer / heldout scorer / jb suite / dilution pool / rlvr pool)")
