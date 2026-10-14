# -*- coding: utf-8 -*-
"""Sanity linter for the watchdog report. Two failure modes it must catch:

1. f-string brace blow-ups -- a whole Python list inlined into prose.
2. ragged markdown tables -- counting only UNESCAPED pipes (a `\\|` inside a cell
   is an escaped pipe and must not be counted; but a bare `|` inside a code span
   in a GFM table DOES split the cell, which silently mis-renders the row).

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-lint.txt
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")
t = (R / "m3-dpo-resume-watchdog.md").read_text(encoding="utf-8")
lines = t.split("\n")
out: list[str] = []


def w(s: str = "") -> None:
    out.append(s)


w(f"total lines: {len(lines)}  chars: {len(t)}")
w(f"longest line: {max(len(l) for l in lines)}")
longs = [(i + 1, len(l)) for i, l in enumerate(lines) if len(l) > 700]
w(f"lines >700 chars: {longs or 'none'}  (a legit long line is the below-zero step list)")

w("\n-- f-string blow-up pattern (a float list inlined in prose) --")
pat = re.compile(r"\[\s*-?\d\.\d{6,}(\s*,\s*-?\d\.\d{6,}){8,}")
hits = [i + 1 for i, l in enumerate(lines) if pat.search(l)]
w(f"  {'CLEAN' if not hits else 'FOUND at ' + str(hits)}")


def unescaped_pipes(s: str) -> int:
    """Count pipes that actually split GFM table cells."""
    return len(re.findall(r"(?<!\\)\|", s))


w("\n-- ragged tables (unescaped-pipe count) --")
i, ntab, nbad = 0, 0, 0
while i < len(lines):
    if lines[i].lstrip().startswith("|"):
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        widths = [unescaped_pipes(lines[k]) for k in range(i, j)]
        ntab += 1
        if len(set(widths)) > 1:
            nbad += 1
            w(f"  !! table starting line {i + 1}: widths {sorted(set(widths))}")
            for k in range(i, min(j, i + 3)):
                w(f"       {k + 1}: {lines[k][:100]}")
        i = j
    else:
        i += 1
w(f"  tables scanned: {ntab};  ragged: {nbad}")

w("\n-- stale narrative references --")
for name, p in {
    "literal rewards/{chosen,rejected}": r"rewards/\{chosen,rejected\}",
    "'事件段 B' (renamed to 最长段)": r"事件段 B",
    "'仍在进行' (no episode is in progress now)": r"仍在进行",
    "'至今没有出现过'": r"至今没有出现过",
    "'从未出现'": r"从未出现",
}.items():
    h = [i + 1 for i, l in enumerate(lines) if re.search(p, l)]
    w(f"  {name}: {'absent OK' if not h else 'FOUND at ' + str(h[:6])}")

w("\n-- required sections present --")
for sec in ["## §0", "## §1", "## §2", "## §3", "## §4", "## §5", "## §6", "## §7",
            "## §8", "## §9", "## §10", "附录 A"]:
    w(f"  {sec}: {'yes' if any(sec in l for l in lines) else '** MISSING **'}")

(R / "m3-dpo-resume-watchdog-lint.txt").write_text("\n".join(out), encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print("\n".join(out))
sys.exit(0)
