# -*- coding: utf-8 -*-
r"""★照实 dump DPO 数据集的 schema（不得凭记忆猜 ✗ —— 本会话已栽过两次 ✗）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
FILES = [
    R / "data" / "m4-run" / "dpo_m4_capfix.jsonl",
    R / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl",
    R / "data" / "dpo-remediation-staging" / "dpo_m4_lenmatch.jsonl.superseded",
]


def describe(v, depth=0, key=""):
    pad = "  " * depth
    if isinstance(v, dict):
        print(f"{pad}{key}: dict keys = {sorted(v.keys())}")
        for k in sorted(v.keys()):
            if depth < 3:
                describe(v[k], depth + 1, k)
    elif isinstance(v, list):
        print(f"{pad}{key}: list len={len(v)}")
        if v and depth < 3:
            describe(v[0], depth + 1, f"{key}[0]")
    else:
        s = str(v)
        print(f"{pad}{key}: {type(v).__name__} = {s[:110]!r}")


def main() -> int:
    for p in FILES:
        print(f"\n=== {p} ===")
        if not p.exists():
            print("  ★缺文件")
            continue
        with p.open(encoding="utf-8") as f:
            line = f.readline()
        row = json.loads(line)
        print(f"  顶层键 = {sorted(row.keys())}")
        for k in sorted(row.keys()):
            describe(row[k], 1, k)
    print("\nSCHEMA-DUMP=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
