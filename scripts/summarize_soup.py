# -*- coding: utf-8 -*-
"""汇总权重插值扫描：needle（及可选的门禁）随 α 的变化。"""
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
reports = sorted(glob.glob(str(ROOT / "reports" / "longctx-*.json")))
want = ["m2calib", "soup-a020", "soup-a035", "soup-a050", "soup-a065", "soup-a080",
        "m2calib-needlefix-e1", "m25full", "m15"]
table = []
for p in reports:
    tag = Path(p).stem.replace("longctx-", "")
    d = json.load(open(p, encoding="utf-8"))
    nc = d.get("needle_counts") or {}
    k = sum(v.get("k", 0) for L in nc.values() for v in L.values())
    n = sum(v.get("n", 0) for L in nc.values() for v in L.values())
    if n:
        table.append((tag, k, n))
order = {t: i for i, t in enumerate(want)}
table.sort(key=lambda x: order.get(x[0], 99))
print(f"{'tag':26} {'needle':>10} {'rate':>7}  {'≥0.75?':>7}")
for tag, k, n in table:
    print(f"{tag:26} {k:>4}/{n:<5} {k/n:>7.3f}  {'YES' if k/n >= 0.75 else 'no':>7}")

# 与 v0.3-gen ASR 并列（若已有读数）
print("\n--- 与未见载体 ASR 并列（若该档已测 v0.3-gen）---")
import re
for tag, k, n in table:
    sp = ROOT / "reports" / f"scored-chat-gen-{tag}-v2.json"
    if not sp.exists():
        continue
    d = json.load(open(sp, encoding="utf-8"))
    items = d.get("items") or []
    rob = [i for i in items if (i.get("axes") or {}).get("kind") == "robustness"] or \
          [i for i in items if i.get("kind") == "robustness"]
    succ = sum(1 for i in rob if float((i.get("derived") or {}).get("attack_success") or 0) == 1.0)
    print(f"  {tag:26} needle {k}/{n} = {k/n:.3f}   ASR {succ}/{len(rob)}"
          f" = {succ/max(1,len(rob)):.3f}")
