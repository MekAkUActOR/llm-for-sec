# -*- coding: utf-8 -*-
"""临时检查脚本：dump 两臂 smoke 响应文本（不落正式产物）。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
for name in ["jb-resp-soup-needlefix-a050-v0.7-smoke.jsonl",
             "jb-resp-m4-capfix-probe-v0.7-smoke.jsonl"]:
    p = ROOT / "reports" / name
    print("=" * 30, name)
    for line in p.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        txt = r["text"].replace("\n", " | ")
        print(f"{r['dialogue_id']} t{r['turn_i']}/{r['n_turns']} "
              f"sr={r['label_selfreport']} st={r['label_strict']} "
              f"fin={r['finish_reason']}: {txt[:200]}")
    print()
