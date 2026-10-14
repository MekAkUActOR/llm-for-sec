# -*- coding: utf-8 -*-
"""定位 M2.5 混料里的 t13（长文档检索）行，并给出按任务族的行数/长度统计。

用途：m2-calib 的 needle 缺口（0.609 vs m25full 0.875）若确由"未训 t13"造成，
则 needle 修复混料的主体就是 t13 切片 + 契约回放（data/sft/sft_v0.jsonl）。
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "lf" / "sft_m25.jsonl"
OUT = ROOT / "data" / "lf" / "needle_t13_slice.jsonl"
WANT = sys.argv[1] if len(sys.argv) > 1 else "t13"

PAT = re.compile(r"(t13|T13)", re.I)
fam = Counter()
keys = Counter()
n = 0
kept = 0
lens = defaultdict(list)
with SRC.open(encoding="utf-8") as f, OUT.open("w", encoding="utf-8") as g:
    for line in f:
        if not line.strip():
            continue
        n += 1
        r = json.loads(line)
        if n == 1:
            keys.update(r.keys())
        blob = json.dumps(r, ensure_ascii=False)
        tag = None
        for k in ("src_task", "task", "family", "tags", "id", "group"):
            v = r.get(k)
            if v:
                tag = f"{tag}|{k}={str(v)[:60]}" if tag else f"{k}={str(v)[:60]}"
        m = PAT.search(blob)
        famkey = "t13" if m else "other"
        fam[famkey] += 1
        if famkey == "t13":
            kept += 1
            g.write(line)
            txt = " ".join((x.get("value") or x.get("content") or "")
                           for x in (r.get("conversations") or r.get("messages") or []))
            lens["t13"].append(len(txt))
            if kept <= 2:
                print(f"--- t13 样例 id={r.get('id')} 字段={tag}")
                print("   ", txt[:400].replace("\n", " | "))
print(f"\n总行 = {n:,}  命中 t13 = {kept:,}  已写出 {OUT.name}")
print("首行字段 =", sorted(keys))
L = sorted(lens["t13"])
if L:
    print(f"t13 字符长度: min={L[0]} p50={L[len(L)//2]} p90={L[int(.9*len(L))]} max={L[-1]}")
