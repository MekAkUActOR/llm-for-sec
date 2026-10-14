# -*- coding: utf-8 -*-
r"""对比 en / zh 条目的 intent 字段结构（我的解析对 en 全失效 ⇒ 结构不同 ✓）。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
D = ROOT / "data" / "heldout" / "v0.3-gen"


def main() -> int:
    rows = []
    for p in sorted(D.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) == "robustness":
                r["_file"] = p.name
                rows.append(r)
    print(f"=== robustness n={len(rows)} ===")
    for lg in ("en", "zh"):
        sel = [r for r in rows if str(r.get("language")) == lg]
        print(f"\n{'#'*84}\n# {lg}  n={len(sel)}   分文件 {dict(Counter(r['_file'] for r in sel))}\n{'#'*84}")
        for r in sel[:3]:
            print(f"\n--- id={r.get('id')}  file={r['_file']} ---")
            print(f"  intent   = {str(r.get('intent'))[:340]}")
            print(f"  group    = {str(r.get('group'))[:120]}")
            print(f"  forward  = {str(r.get('forward'))[:120]}")
            print(f"  expected = {str(r.get('expected'))[:120]}")
        print(f"\n  ★{lg} 的 intent 中位数长度 = "
              f"{sorted(len(str(r.get('intent') or '')) for r in sel)[len(sel)//2]}")
        print(f"  ★{lg} 的 group 取值 = {dict(Counter(str(r.get('group')) for r in sel))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
