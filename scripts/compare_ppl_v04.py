# -*- coding: utf-8 -*-
"""PPL 同口径（v0.4）对照表 —— 报告结构为 {..., "domains": {name: {ppl,...}}}。

用法：python scripts\\compare_ppl_v04.py [base_tag] [tag...]
默认：基准 m15，对照 m2calib / m2full / m25full。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
BASE = args[0] if args else "m15"
TAGS = args[1:] if len(args) > 1 else ["m2calib", "m2full", "m25full"]
DOMS = ["general_en", "general_zh", "sec_en", "sec_zh", "sec", "ais", "aisafety",
        "content", "privacy", "_raw_privacy_units", "malware"]


def load(tag):
    p = ROOT / "reports" / f"ppl-{tag}-v0.4.json"
    if not p.exists():
        print(f"（缺）{p.name}")
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("domains") or {}


rows = {t: load(t) for t in [BASE] + TAGS}
have = [t for t in [BASE] + TAGS if rows.get(t)]
print(f"{'domain':20}" + "".join(f"{t:>13}" for t in have))
for d in DOMS:
    if not any(d in (rows.get(t) or {}) for t in have):
        continue
    line = f"{d:20}"
    for t in have:
        v = (rows[t].get(d) or {}).get("ppl")
        line += f"{(f'{v:.4f}' if isinstance(v, (int, float)) else '—'):>13}"
    print(line)

print(f"\n相对基准 {BASE} 的变化率（G2 绝对轨上限：general_en ≤+18% / general_zh ≤+25%）")
for t in TAGS:
    if not rows.get(t) or not rows.get(BASE):
        continue
    line = f"  {t:14}"
    for d in ("general_en", "general_zh"):
        b = (rows[BASE].get(d) or {}).get("ppl")
        c = (rows[t].get(d) or {}).get("ppl")
        if isinstance(b, (int, float)) and isinstance(c, (int, float)) and b:
            pct = (c - b) / b * 100
            cap = 18 if d.endswith("en") else 25
            line += f"  {d}: {b:.3f}→{c:.3f} ({pct:+.2f}%) {'过' if pct <= cap else '★不过'}"
    print(line)
