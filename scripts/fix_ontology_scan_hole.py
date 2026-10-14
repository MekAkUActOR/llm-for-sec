# -*- coding: utf-8 -*-
r"""补两个洞：
 ① `data/dpo-remediation-staging/*.jsonl` 未在 `scan_globs` 里 ⇒ 暂存候选永不被扫 ✗
 ② **更重要的**：scope 的 glob 在磁盘上有匹配、却在 `files` 里取不到时，
    校验器**静默计为 0** ✗✗ —— 这是**测量层的静默失败路径**（规则 32 的反面 ✗）。

## 为什么 ② 必须修（不只是为了 m4）

`collect_facts()` 里：
```python
scan_globs = ["data/lf/*.jsonl", "data/sft/**/*.jsonl", "data/dpo/**/*.jsonl",
              "data/heldout/**/*.jsonl"]
...
blk = files.get(key)
if blk:                       # ← 取不到就静默跳过 ✗
    c.update(blk["carrier_rows"])
```
⇒ 任何人新增一个 scope、却忘了同步 `scan_globs`，
  该 scope 就会**安静地显示 0 行** ✓ —— 而 0 行看起来像"还没数据" ✓，
  于是**没有人会去查** ✗✗。这正是"空洞通过"的同类缺陷 ✓。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CHECKER = ROOT / "scripts" / "check_carrier_ontology.py"

OLD_SCAN = '''    scan_globs = ["data/lf/*.jsonl", "data/sft/**/*.jsonl", "data/dpo/**/*.jsonl",
                  "data/heldout/**/*.jsonl"]'''
NEW_SCAN = '''    # ★2026-10-06 第 18 轮：暂存/候选区也必须被扫描 ✓
    #   （此前漏了它 ⇒ 新增的 dpo_remediation_staging scope 静默计为 0 ✗）
    scan_globs = ["data/lf/*.jsonl", "data/sft/**/*.jsonl", "data/dpo/**/*.jsonl",
                  "data/dpo-remediation-staging/*.jsonl",
                  "data/heldout/**/*.jsonl"]'''

OLD_LOOP = '''        scope_carriers[scope] = c
        for label, n in c.items():
            train_rows.setdefault(label, {})[scope] = n'''
NEW_LOOP = '''        # ★2026-10-06 第 18 轮（规则 32 fail-closed）：
        #   若某 scope 的 glob 在**磁盘上确有匹配**，却在 `files` 里取不到，
        #   那是"scan_globs 与 TRAIN_SCOPES 不同步"的**缺陷** ✗，
        #   不得静默计为 0 ✓ —— 0 行看起来像"还没数据"，没人会去查 ✗✗。
        if not c:
            on_disk = 0
            for _p in pats:
                on_disk += len(_expand(_p))
            if on_disk > 0:
                raise SystemExit(
                    f"[fail-closed] scope `{scope}` 的模式 {pats} 在磁盘上匹配到 "
                    f"{on_disk} 个文件，但扫描集 `files` 里一个都没有 ⇒ "
                    f"`scan_globs` 与 `TRAIN_SCOPES` 不同步 ✗。"
                    f"请把该路径加入 collect_facts() 的 scan_globs ✓。")
        scope_carriers[scope] = c
        for label, n in c.items():
            train_rows.setdefault(label, {})[scope] = n'''


def main() -> int:
    t = CHECKER.read_text(encoding="utf-8")
    ok = True

    if "dpo-remediation-staging/*.jsonl" in t:
        print("  OK  ① scan_globs 已含暂存区（幂等）")
    elif OLD_SCAN in t:
        t = t.replace(OLD_SCAN, NEW_SCAN, 1)
        CHECKER.write_text(t, encoding="utf-8")
        t = CHECKER.read_text(encoding="utf-8")
        print(f"  {'OK ' if 'dpo-remediation-staging' in t else '★NG'} ① 已补 scan_globs")
        ok = ok and "dpo-remediation-staging" in t
    else:
        print("  ★NG ① 未找到 scan_globs 锚点")
        ok = False

    if "scan_globs 与 TRAIN_SCOPES 不同步" in t:
        print("  OK  ② fail-closed 检查已存在（幂等）")
    elif OLD_LOOP in t:
        t = t.replace(OLD_LOOP, NEW_LOOP, 1)
        CHECKER.write_text(t, encoding="utf-8")
        t = CHECKER.read_text(encoding="utf-8")
        good = "scan_globs 与 TRAIN_SCOPES 不同步" in t
        print(f"  {'OK ' if good else '★NG'} ② 已加 fail-closed 检查")
        ok = ok and good
    else:
        print("  ★NG ② 未找到 scope 循环锚点")
        ok = False

    print("\n=== 复验 ===")
    r = subprocess.run([str(PY), str(CHECKER)], capture_output=True, text=True,
                       encoding="utf-8", cwd=str(ROOT))
    out = (r.stdout or "") + (r.stderr or "")
    tail = [l for l in out.splitlines() if "CARRIER-ONTOLOGY-CHECK" in l]
    print("  " + (tail[-1] if tail else "(无终判行)"))
    for l in out.splitlines()[:12]:
        if l.strip():
            print("    " + l)
    print(f"\nONTOLOGY-HOLEFIX={'PASS' if r.returncode == 0 else 'FAIL'}")
    return 0 if (ok and r.returncode == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
