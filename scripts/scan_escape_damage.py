# -*- coding: utf-8 -*-
r"""修复并扫描"Python 转义吃掉路径字符"造成的静默损坏。

★事故（2026-10-06 第 17 轮）：
  我在一个普通（非 raw）字符串里写 PowerShell 路径 `scripts\audit_...`，
  Python 把 `\a` 当成 **BEL（\x07）** 吃掉 ✗ ⇒ 写进 runbook 的成了
  `scriptsudit_dpo_nonlength_signal.py` ✗✗ —— **用户照抄会直接失败**。
  同类危险转义：`\a`(BEL) `\b`(BS) `\f`(FF) `\n`(LF) `\r`(CR) `\t`(TAB) `\v`(VT)；
  `\P`/`\S` 等**不是**合法转义 ⇒ Python 保留原样（只发 SyntaxWarning）⇒ 相对无害 ✗✓。

  ⇒ **教训**：凡含 Windows 路径的字符串一律用 **raw 字符串（r"..."）**；
    并且 **SyntaxWarning 必须当真** —— 这次它就在警告我 ✗。

本脚本做两件事：
  1. 修复 runbook 里已损坏的那一行（用 raw 字符串重写）；
  2. 全仓扫描**控制字符**出现在路径样 token 里的情形，报告可疑点。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
RUNBOOK = ROOT / "reports" / "m3-launch-runbook.md"

BAD = {"\x07": "BEL(\\a)", "\x08": "BS(\\b)", "\x0b": "VT(\\v)", "\x0c": "FF(\\f)"}
SCAN_EXT = {".md", ".py", ".ps1", ".json", ".jsonl", ".yaml", ".yml", ".txt", ".cfg"}
SKIP = (".venv", ".git", ".cache", "checkpoints", "node_modules", "__pycache__")


def fix_runbook() -> list[str]:
    t = RUNBOOK.read_text(encoding="utf-8")
    notes = []
    # ★通用还原：控制字符本来只可能来自对应的转义序列被吃掉
    #   ⇒ BEL(\x07) 还原成 `\a`、BS(\x08)→`\b`、VT(\x0b)→`\v`、FF(\x0c)→`\f`
    #   这正好把 `scripts\x07udit_...` 复原成 `scripts\audit_...` ✓
    #   （合法文件里几乎不会真出现这些裸控制字符 ⇒ 误修风险极低）
    restore = {"\x07": r"\a", "\x08": r"\b", "\x0b": r"\v", "\x0c": r"\f"}
    n_fix = 0
    for ch, lit in restore.items():
        c = t.count(ch)
        if c:
            t = t.replace(ch, lit)
            n_fix += c
            notes.append(f"还原 {c} 处 {BAD[ch]} → {lit!r}")
    if n_fix:
        RUNBOOK.write_text(t, encoding="utf-8")
    else:
        notes.append("runbook 无控制字符损坏")

    # 再查 `scripts` 后紧跟小写字母（分隔符被吃但控制字符已不在的形态）
    damaged = re.findall(r"scripts(?=[a-z])", t)
    if damaged:
        notes.append(f"★runbook 另有 {len(damaged)} 处 `scripts` 后缺分隔符（需人工看）")
    for ch, name in BAD.items():
        if ch in t:
            notes.append(f"★runbook 仍含控制字符 {name}")
    return notes


def scan() -> list[str]:
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SCAN_EXT:
            continue
        if any(s in p.parts for s in SKIP):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for ch, name in BAD.items():
            if ch in txt:
                rel = p.relative_to(ROOT)
                n = txt.count(ch)
                hits.append(f"{rel}  含 {name} ×{n}")
    return hits


def main() -> int:
    print("=== 1. 修复 runbook ===")
    for n in fix_runbook():
        print(f"    {n}")

    print("\n=== 2. 全仓扫描控制字符（BEL/BS/VT/FF）===")
    hits = scan()
    if hits:
        for h in hits:
            print(f"    ★ {h}")
    else:
        print("    未发现控制字符损坏 ✓")

    print("\n=== 3. 复验 runbook 关键路径可照抄 ===")
    t = RUNBOOK.read_text(encoding="utf-8")
    for cmd in ("scripts\\audit_dpo_nonlength_signal.py",
                "scripts\\audit_dpo_length_confounding.py",
                "scripts\\audit_dpo_discriminative_axes.py",
                "scripts\\audit_s1_training_files.py"):
        ok = cmd in t
        print(f"    {'OK ' if ok else '★缺'} {cmd}")
    print("\nESCAPE-DAMAGE-CHECK=" +
          ("PASS" if not hits and not re.search(r"scripts(?=[a-z])", t) else "FAIL"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
