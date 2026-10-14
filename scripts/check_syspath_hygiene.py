# -*- coding: utf-8 -*-
"""规则 29 的**机械合规扫描**：脚本定义了 ROOT 却没有把它插进 sys.path。

★为什么需要它：2026-09-30 晚，`probe_longctx.py` 因缺这一行而**chat 口径从未跑通**；
  同日我在**新写的** `compute_toolout_significance.py` 里**又犯了一次**。
  ⇒ 光靠"知道规则"不够，必须机械检查（规则 29 要求"写下规则时同时产出合规扫描"）。

判定：脚本中同时出现
  (a) 顶层定义 ROOT（如 `ROOT = Path(...)` / `ROOT = ...resolve()...`）—— 不是函数内局部变量；
  (b) 导入本项目包（`import secfm` / `from secfm...`）；
  (c) **没有** `sys.path.insert(..., str(ROOT))` 或等价的 `sys.path.append`。
则报违规。

退出码：0 = 无违规；1 = 有违规。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RE_ROOT = re.compile(r"^ROOT\s*[:=]", re.M)
RE_SECFM = re.compile(r"^\s*(?:from|import)\s+secfm\b", re.M)
RE_INSERT = re.compile(r"sys\.path\.(?:insert|append)\s*\(\s*[^)]*str\(\s*ROOT\s*\)")
RE_INSERT_VAR = re.compile(r"sys\.path\.(?:insert|append)\s*\([^)]*\bROOT\b")

#: 显式豁免标记（故意不插 ROOT 的验证器用，例如 precheck_probe_longctx_chat.py）
RE_SKIP = re.compile(r"syspath-hygiene:\s*skip", re.I)


def main() -> int:
    violations = []
    skipped = []
    scanned = 0
    for d in ("scripts", "secfm", "tests", "tools"):
        p = ROOT / d
        if not p.exists():
            continue
        for f in sorted(p.rglob("*.py")):
            scanned += 1
            # ★包内模块（secfm/**）用包内相对导入，无需把 ROOT 插进 sys.path
            if d == "secfm":
                continue
            try:
                src = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not RE_ROOT.search(src):
                continue
            if not RE_SECFM.search(src):
                continue
            if RE_INSERT.search(src) or RE_INSERT_VAR.search(src):
                continue
            if RE_SKIP.search(src):
                skipped.append(f.relative_to(ROOT))
                continue
            violations.append(f.relative_to(ROOT))

    print(f"扫描 {scanned} 个 .py（secfm 包内模块按包内导入规则跳过）；"
          f"同时定义 ROOT 且导入 secfm 的脚本中：")
    if skipped:
        print(f"  显式豁免 {len(skipped)} 个：")
        for v in skipped:
            print(f"    {v}")
    if violations:
        print(f"★SYSPATH-HYGIENE=FAIL 违规 {len(violations)} 个：")
        for v in violations:
            print(f"    {v}")
        print("\n  修法：在使用 ROOT 之后、导入 secfm 之前加：")
        print("      if str(ROOT) not in sys.path:")
        print("          sys.path.insert(0, str(ROOT))")
        return 1
    print("SYSPATH-HYGIENE=PASS 无违规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
