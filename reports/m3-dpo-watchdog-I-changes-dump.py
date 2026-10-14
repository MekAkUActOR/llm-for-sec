# -*- coding: utf-8 -*-
"""M3 DPO watchdog I: 从 H 的对照表里打印 strict vs selfreport 的逐条变动（审计用）。"""
from __future__ import annotations

import json
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")
doc = json.loads((R / "m3-dpo-watchdog-actionrule-table.json").read_text(encoding="utf-8"))

print("== 每档 strict 相对 selfreport 的变动条目 ==")
for tag, ch in doc["item_changes_strict_vs_selfreport"].items():
    print(f"\n--- {tag}  ({len(ch)} 条)")
    for c in ch:
        mark = ""
        if c["asr_selfreport"] != c["asr_strict"]:
            mark = "  ←ASR 变"
        print(f"  {c['id']:10} {c['kind']:10} {str(c['selfreport']):14} -> "
              f"{str(c['strict']):14} asr {c['asr_selfreport']} -> {c['asr_strict']}"
              f"{mark}")
        print(f"             note: {c['note']}")
        print(f"             evid: {c['evidence'][:90]!r}")

print("\n== 变动条目在所有档的共同性 ==")
allids = {}
for tag, ch in doc["item_changes_strict_vs_selfreport"].items():
    for c in ch:
        allids.setdefault(c["id"], {})[tag] = c["strict"]
for iid, per in sorted(allids.items()):
    print(f"  {iid:10} 出现在 {len(per)} 档: "
          f"{ {t: v for t, v in per.items()} }")

print("\n== strict 口径下 ASR 真正变化的条目（robustness） ==")
for tag, ch in doc["item_changes_strict_vs_selfreport"].items():
    dd = [c for c in ch if c["kind"] == "robustness"
          and c["asr_selfreport"] != c["asr_strict"]]
    print(f"  {tag:12} {len(dd)} 条: "
          f"{[(c['id'], c['selfreport'], '->', c['strict']) for c in dd]}")
