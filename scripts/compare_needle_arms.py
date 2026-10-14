# -*- coding: utf-8 -*-
"""直接用新格式的 needle_success / needle_counts 汇总，对比各臂（raw 口径）。"""
import json
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")

print(f"{'臂':<20} {'口径':<6} {'总':>8}   {'en16k':>10} {'en32k':>10} {'zh16k':>10} {'zh32k':>10}")
print("-" * 92)
for f in sorted(R.glob("longctx-*.json")):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        continue
    # ★真实结构：needle_counts.<lens>.<lang>.{k,n}；needle_success.<lens>.<lang> = 比率
    nc = d.get("needle_counts")
    if not isinstance(nc, dict):
        continue
    tag = f.stem.replace("longctx-", "")
    fmt = d.get("prompt_format", "raw")

    def cell(lens: str, lang: str):
        v = nc.get(lens, {})
        if not isinstance(v, dict):
            return None
        w = v.get(lang)
        if isinstance(w, dict) and "k" in w and "n" in w:
            return (w["k"], w["n"])
        return None

    cells = {}
    tot_k = tot_n = 0
    for lens in ("16384", "32768"):
        for lang in ("en", "zh"):
            c = cell(lens, lang)
            cells[(lens, lang)] = c
            if c:
                tot_k += c[0]
                tot_n += c[1]
    rate = f"{tot_k}/{tot_n}={tot_k/tot_n*100:.1f}%" if tot_n else "?"
    def s(lens, lang):
        c = cells.get((lens, lang))
        return f"{c[0]}/{c[1]}" if c and c[0] is not None else "-"
    print(f"{tag:<20} {fmt:<6} {rate:>8}   {s('16384','en'):>10} {s('32768','en'):>10} "
          f"{s('16384','zh'):>10} {s('32768','zh'):>10}")

print("\n（m3-dpo 的 chat 读数从运行日志统计为 11/64，见 count_needle_hits.py；")
print("  其 chat 报告 longctx-m3-dpo-chat.json 尚未落盘，故未出现在上表。）")
print("\nNEEDLE-SUMMARY=DONE")
