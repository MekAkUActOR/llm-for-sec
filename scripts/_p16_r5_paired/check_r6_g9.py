# -*- coding: utf-8 -*-
"""R6 G9 同款 8-gram 污染检查（对 heldout 冻结件 + probes 全量样板）。

r5 checker（check_f5_g9.py）逻辑适配：被检对象 = data/dpo/p16-calibration-r6/
p16_r6_paired.jsonl 的 6,000 行。官方 gate_g9 代码路径 monkeypatch 复用。
用法：.venv\\Scripts\\python.exe scripts\\_p16_r5_paired\\check_r6_g9.py
产物：data/dpo/p16-calibration-r6/parts-r6-g9.check.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_p16_calibration as C  # noqa: E402  官方 checker 只读 import（零改动）

DATA = ROOT / "data" / "dpo" / "p16-calibration-r6"
rows = [json.loads(line) for line in (DATA / "p16_r6_paired.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
print(f"[r6-g9] new rows loaded: {len(rows)}")
assert len(rows) == 6000, len(rows)
ids = [r["id"] for r in rows]
assert len(set(ids)) == 6000

t0 = time.time()
C.ROWS = rows  # 文档侧替换（gate_g9 只读 ROWS/TEMPLATES 模块全局；checker 本体零改动）
g = C.gate_g9()
report = {
    "gate": "G9-equivalent (official gate_g9 code path, docs=r6-paired 6000 rows)",
    "rows": len(rows),
    "ok": g.ok,
    "fails": g.fails,
    "info": [[k, v] for k, v in g.info],
    "notes": g.notes,
    "elapsed_s": round(time.time() - t0, 1),
}
for k, v in g.info:
    print(f"  {k}: {v}")
for note in g.notes:
    print(f"  [note] {note}")
if g.fails:
    for f in g.fails:
        print("FAIL:", f)
out = DATA / "parts-r6-g9.check.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"report -> {out}")
if not g.ok:
    print("R6-G9=FAIL")
    sys.exit(1)
print("R6-G9=PASS")
