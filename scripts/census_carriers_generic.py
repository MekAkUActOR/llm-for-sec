# -*- coding: utf-8 -*-
"""通用载体普查：对给定 jsonl 逐文件统计 `<carrier type=\"X\">` 分布与 kind 分布。

用法：python scripts/census_carriers_generic.py <path1> [path2 ...]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

PAT = re.compile(r'<carrier\s+type=\\"([^\\"]+)\\"')


def census(p: Path):
    car = Counter()
    kind = Counter()
    ck = Counter()          # (载体, kind) 交叉
    n = 0
    with p.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            ms = PAT.findall(line)
            ctype = ms[0].lower() if ms else "UNTAGGED"
            for m in ms:
                car[m.lower()] += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            k = str(r.get("kind") or r.get("category") or "?")
            kind[k] += 1
            ck[(ctype, k)] += 1
    return n, car, kind, ck


for arg in sys.argv[1:]:
    p = Path(arg)
    if not p.exists():
        print(f"缺失：{p}")
        continue
    n, car, kind, ck = census(p)
    print(f"\n{p}")
    print(f"  行数 = {n}")
    print(f"  kind 分布 = {dict(kind.most_common())}")
    print(f"  carrier 分布 = {dict(car.most_common()) if car else '（无信封）'}")
    print(f"  ★ 不同载体类数 = {len(car)}")
    print(f"  ★ 载体 × kind 交叉（**鲁棒性分母 ≥34 才够门禁阈值**，docs/01 §11.2）：")
    carriers = sorted({c for c, _ in ck})
    for c in carriers:
        rob = ck.get((c, "robustness"), 0)
        ali = ck.get((c, "alignment"), 0)
        flag = "✓ 达门禁阈值" if rob >= 34 else ("△ 不足" if rob else "—")
        print(f"      {c:<16} robustness={rob:>4}  alignment={ali:>4}   {flag}")
