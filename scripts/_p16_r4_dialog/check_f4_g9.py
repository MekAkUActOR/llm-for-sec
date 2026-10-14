# -*- coding: utf-8 -*-
"""F4-dialog G9 同款 8-gram 污染检查（对 heldout 冻结件 + probes 全量样板）。

实现：monkeypatch 官方 checker 的文档侧全局 ROWS = 792 新行，直接调用
check_p16_calibration.gate_g9()——官方两段式全逻辑**零改动**复用：
- 样板 = data/heldout 全部 12 版本目录 + data/probes 全部（超集口径）
- 白名单双侧剥离：6 冻结模板全文 + VERDICT 行正则 + dsh-protocol 头骨架字面量
- 门禁层：union ≥57 字节窗 → 官方 doc_probe_hits(50) char-gram 游程 +
  verify_shared_substring(60) LCS 判真；诊断层（threshold=30）全景 + 交叉验证
- 被检对象 = parts/part-g01.jsonl + part-g02.jsonl 合并 792 行（一轮/二轮/三轮
  冻结行已过 G9 两次在案，非本轮被检对象）
用法：.venv\\Scripts\\python.exe scripts\\_p16_r4_dialog\\check_f4_g9.py
产物：parts/part-f4-g9.check.json（机读结论）+ stdout 留痕
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_p16_calibration as C  # noqa: E402  官方 checker 只读 import（加载一轮冻结件 + 模板 sha 断言，零改动）

rows = []
for part in sorted((HERE / "parts").glob("part-g*.jsonl")):
    for line in part.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
print(f"[f4-g9] new rows loaded: {len(rows)}")
assert len(rows) == 792, len(rows)
ids = [r["id"] for r in rows]
assert ids == sorted(ids) and len(set(ids)) == 792

t0 = time.time()
C.ROWS = rows  # 文档侧替换（gate_g9 只读 ROWS/TEMPLATES 两个模块全局；checker 本体零改动 ✗✓）
g = C.gate_g9()
report = {
    "gate": "G9-equivalent (official gate_g9 code path, docs=f4-dialog 792 rows)",
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
out = HERE / "parts" / "part-f4-g9.check.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"report -> {out}")
if not g.ok:
    print("F4-G9=FAIL")
    sys.exit(1)
print("F4-G9=PASS")
