# -*- coding: utf-8 -*-
"""按 dpo_class 拆契约覆盖率，并抽样看 chosen/rejected 形态（判断是否为数据缺陷）。"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "lf" / "dpo_m3.jsonl"
N_SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2

tot = Counter()
withv = Counter()
samples = defaultdict(list)
lench = defaultdict(list)
with P.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        c = r.get("dpo_class")
        tot[c] += 1
        ch = (r.get("chosen") or {}).get("value") or ""
        rj = (r.get("rejected") or {}).get("value") or ""
        if "VERDICT" in ch:
            withv[c] += 1
        lench[c].append(len(ch))
        if len(samples[c]) < N_SAMPLE:
            samples[c].append((r.get("id"), ch, rj))

print(f"{'dpo_class':18} {'行数':>7} {'chosen含VERDICT':>16} {'占比':>7} {'chosen长度中位数':>16}")
for c, n in tot.most_common():
    L = sorted(lench[c])
    med = L[len(L) // 2]
    print(f"{c:18} {n:>7,} {withv[c]:>16,} {withv[c]/n*100:>6.1f}% {med:>16,}")

for c in tot:
    print(f"\n===== dpo_class={c} 样例 =====")
    for i, ch, rj in samples[c]:
        print(f"--- id={i}")
        print(f"  chosen   ({len(ch):>5} 字符): {ch[:260]!r}")
        print(f"  rejected ({len(rj):>5} 字符): {rj[:200]!r}")
