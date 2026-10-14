# -*- coding: utf-8 -*-
"""Probe 6 (micro2): t6 rec1 lines 12+ to see Fix diff / Files changed format."""
import json

f = open('data/corpora/clean/t6_cvefixes.jsonl', encoding='utf-8')
t = json.loads(f.readline())['text']
lines = t.split('\n')
idx = {m: i for i, m in enumerate(lines) if m.startswith(('Fix diff:', 'Files changed:', 'Commit message:'))}
print(f"marker_line_idx={idx}")
for i in range(12, min(len(lines), 52)):
    print(f" L{i} ({len(lines[i])}ch): {lines[i][:110]!r}")
