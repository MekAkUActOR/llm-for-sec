# -*- coding: utf-8 -*-
"""统计 needle 探针的命中/未命中（按语言、按 lens 分层）。

★编码：PS 5.1 的 `Tee-Object` 默认写 **UTF-16LE**（不是 UTF-8），
  故本脚本对多种编码逐一尝试，并报告哪一种能匹配（这是本会话第三次踩
  "PowerShell 管道/重定向的编码与 UTF-8 不一致"）。
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
tag = sys.argv[1] if len(sys.argv) > 1 else "m3-dpo-chat"
p = ROOT / f"reports/logs/nf-eval-needle-{tag}.log"
if not p.exists():
    raise SystemExit(f"✗ 无 {p}")

PAT = re.compile(r"needle\s+(\d+)/(\w+)\s+d=([\d.]+)#(\d+):\s*(\S+)")

best = None
for enc in ("utf-8", "utf-16", "utf-16-le", "cp936", "latin-1"):
    try:
        raw = p.read_bytes()
    except OSError as e:
        print(f"读盘失败（可能被 Tee 持有）：{e}")
        break
    try:
        txt = raw.decode(enc)
    except (UnicodeDecodeError, LookupError):
        continue
    rows = PAT.findall(txt)
    print(f"  编码 {enc:<10} 字节 {len(raw):>7} 匹配 {len(rows):>3} 条")
    if rows and (best is None or len(rows) > len(best[1])):
        best = (enc, rows)

if not best:
    raise SystemExit("✗ 所有编码均无匹配")

enc, rows = best
print(f"\n=== 采用编码 {enc}：共 {len(rows)} 次（满分 64）===")


def is_hit(s: str) -> bool:
    return ("命中" in s and "未" not in s) or s.lower() == "hit"


hit = sum(1 for r in rows if is_hit(r[4]))
print(f"★总命中 = {hit}/{len(rows)} = {hit/len(rows)*100:.1f}%\n")

by = defaultdict(lambda: [0, 0])
bl = defaultdict(lambda: [0, 0])
for lens, lang, d, v, verdict in rows:
    k = (lang, int(lens))
    by[k][0] += 1
    bl[lang][0] += 1
    if is_hit(verdict):
        by[k][1] += 1
        bl[lang][1] += 1

print("按 (语言, lens) 分层：")
for k in sorted(by):
    n, k2 = by[k]
    print(f"    {k[0]:<3} {k[1]:>6}  {k2:>2}/{n:<3} = {k2/n*100:5.1f}%")
print("按语言合计：")
for lang in sorted(bl):
    n, k2 = bl[lang]
    print(f"    {lang:<3} {k2:>2}/{n:<3} = {k2/n*100:5.1f}%")

print("\n逐条（全部）：")
for r in rows:
    print(f"    {r[1]:<3} {r[0]:>6} d={r[2]:<5} # {r[3]} -> {r[4]}")
print("\nNEEDLE-COUNT=DONE")
