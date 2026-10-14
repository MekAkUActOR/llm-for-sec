# -*- coding: utf-8 -*-
"""冒烟：验证 baseline_eval.py 真的写出 finish_reason / new_tokens（换仪器前的 1 分钟门）。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
D = ROOT / "reports" / "logs" / "smoke-mnt"
D.mkdir(parents=True, exist_ok=True)

# 取 v0.3-gen 前 2 条，写进一个**目录**（★baseline_eval.py 的 --heldout 要目录，不是文件！
# 传文件会得到 n_items=0 ⇒ 空产物 ⇒ 若测试不 fail-closed 就会"空洞通过"）
rows = []
for f in sorted((ROOT / "data" / "heldout" / "v0.3-gen").glob("*.jsonl")):
    for ln in f.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rows.append(ln)
    if len(rows) >= 2:
        break
hold_dir = D / "heldout"
hold_dir.mkdir(parents=True, exist_ok=True)
(hold_dir / "smoke.jsonl").write_text("\n".join(rows[:2]) + "\n", encoding="utf-8")
print(f"smoke 条数 = {len(rows[:2])}（写在目录 {hold_dir.name}/ 下）")

cmd = [
    str(PY), str(ROOT / "scripts" / "baseline_eval.py"),
    # ★注意：真实目录名没有 `qwen3-06b-` 前缀（实测 Get-ChildItem checkpoints）
    "--model", str(ROOT / "checkpoints" / "soup-needlefix-a050"),
    "--heldout", str(hold_dir),
    "--prompt-format", "chat",
    "--max-new-tokens", "256",
    "--out", str(D / "out.json"),
    "--dump-responses", str(D / "resp.jsonl"),
]
r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
for ln in (r.stdout or "").splitlines():
    if any(k in ln for k in ("model loaded", "report ->", "Error", "error")):
        print(f"  {ln.strip()[:130]}")
if r.returncode != 0:
    print(f"★rc={r.returncode}；stderr 末尾：")
    for ln in (r.stderr or "").splitlines()[-6:]:
        print(f"    {ln.strip()[:130]}")

rp = D / "resp.jsonl"
if not rp.exists():
    print("SMOKE-FINISH-REASON=FAIL（无响应产物）")
    sys.exit(1)
ok = True
n_seen = 0
for i, ln in enumerate(rp.read_text(encoding="utf-8").splitlines(), 1):
    if not ln.strip():
        continue
    n_seen += 1
    rec = json.loads(ln)
    has = "finish_reason" in rec and "new_tokens" in rec
    ids = rec.get("new_token_ids")
    ids_ok = isinstance(ids, list) and len(ids) == rec.get("new_tokens")
    ok = ok and has and ids_ok
    print(f"  #{i} finish_reason={rec.get('finish_reason')!r} "
          f"new_tokens={rec.get('new_tokens')} max={rec.get('max_new_tokens')} "
          f"token_ids={len(ids) if isinstance(ids, list) else '缺'} "
          f"一致={ids_ok} len(text)={len(rec.get('text') or '')}")
# ★★2026-10-06：修**空洞通过**（vacuous pass）✗ ——
#   原版 `ok = True` 只在有记录时才更新 ⇒ **产物为空文件时循环不执行、ok 保持 True、报 PASS** ✗✗。
#   这正是 docs/01 §11.31 规则 32 说的「"没触发"不是观测结果」。
#   现加：n_seen 必须 > 0，且必须与预期条数一致。
if n_seen == 0:
    print("SMOKE-FINISH-REASON=FAIL（产物 0 条记录 —— 空洞通过已阻断）")
    print("SMOKE-TOKEN-IDS=FAIL（同上）")
    sys.exit(1)
print(f"  （实测记录数 = {n_seen}）")
print("SMOKE-FINISH-REASON=" + ("PASS" if ok else "FAIL"))
print("SMOKE-TOKEN-IDS=" + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
