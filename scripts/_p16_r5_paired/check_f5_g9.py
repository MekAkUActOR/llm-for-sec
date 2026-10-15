# -*- coding: utf-8 -*-
"""F5-paired G9 同款 8-gram 污染检查（对 heldout 冻结件 + probes 全量样板）。

r4 checker（scripts/_p16_r4_dialog/check_f4_g9.py）零改动适配：被检对象 =
data/dpo/p16-calibration-r5/p16_f5_paired.jsonl 的 2000 行（一轮~四轮冻结行
已过 G9 在案，非本轮被检对象）。官方 gate_g9 代码路径 monkeypatch 复用。
用法：.venv\\Scripts\\python.exe scripts\\_p16_r5_paired\\check_f5_g9.py
产物：data/dpo/p16-calibration-r5/parts-f5-g9.check.json（机读结论）+ stdout 留痕
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

DATA = ROOT / "data" / "dpo" / "p16-calibration-r5"
rows = [json.loads(line) for line in (DATA / "p16_f5_paired.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
print(f"[f5-g9] new rows loaded: {len(rows)}")
assert len(rows) == 2000, len(rows)
ids = [r["id"] for r in rows]
assert len(set(ids)) == 2000

t0 = time.time()
C.ROWS = rows  # 文档侧替换（gate_g9 只读 ROWS/TEMPLATES 两个模块全局；checker 本体零改动 ✗✓）
g = C.gate_g9()
report = {
    "gate": "G9-equivalent (official gate_g9 code path, docs=f5-paired 2000 rows)",
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
out = DATA / "parts-f5-g9.check.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"report -> {out}")
if not g.ok:
    print("F5-G9=FAIL")
    sys.exit(1)
print("F5-G9=PASS")
