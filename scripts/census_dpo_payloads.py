# -*- coding: utf-8 -*-
"""DPO 提示里是否真含载体载荷（不只看 `<carrier>` 标记）。

用于判断 M3 DPO 混料能否提供跨载体训练信号。
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "lf" / "dpo_m3.jsonl"
PAT = re.compile(
    r"<(?:\s*)(carrier|cord|document|doc|log|email|webpage|web|code|tool_output|tool|image|av|video|audio)\b[^>]{0,60}>"
    r"|<载体|<\s*payload\b|\[carrier", re.I)

n = 0
hit = 0
kinds = Counter()
samples = []
with P.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        n += 1
        t = " ".join((m.get("value") or "") for m in (r.get("conversations") or []))
        m = PAT.search(t)
        if m:
            hit += 1
            kinds[(m.group(0).strip().lower(), r.get("dpo_class"))] += 1
            if len(samples) < 3:
                samples.append((r.get("id"), r.get("dpo_class"),
                                t[max(0, m.start() - 100):m.start() + 200]))
print(f"含载体式标记的行 = {hit:,}/{n:,} = {hit / n * 100:.2f}%")
print("\n标记 × dpo_class 分布（前 12）:")
for (k, c), v in kinds.most_common(12):
    print(f"  {k:22} {c:16} {v:>6,}")
for i, c, s in samples:
    print(f"\n--- {i} class={c}\n    {s.replace(chr(10), ' | ')[:340]}")
