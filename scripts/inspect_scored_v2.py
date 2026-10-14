# -*- coding: utf-8 -*-
r"""看清 scored-*-v2 的条目结构：响应正文在哪、kind 怎么分、标签怎么判。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def main() -> int:
    p = ROOT / "reports" / "scored-chat-gen-m3-dpo-v2-mnt512.json"
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items") or d.get("rows") or []
    print(f"{p.name}: 条目 {len(items)}  顶层键 {list(d.keys())[:12]}")
    if not items:
        return 1
    it = items[0]
    print("\n=== 首条逐字段 ===")
    for k, v in it.items():
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        print(f"  {k} ({type(v).__name__}) = {s[:190]}")

    print("\n=== 各字段在多少条上有值 / 非空 ===")
    for k in it:
        n = sum(1 for x in items if x.get(k) not in (None, "", [], {}))
        print(f"  {k:<18} 非空 {n}/{len(items)}")

    print("\n=== kind 分布 ===")
    print(" ", dict(Counter(str(x.get("kind")) for x in items)))
    print("\n=== kind × label ===")
    cross: dict[str, Counter] = {}
    for x in items:
        cross.setdefault(str(x.get("kind")), Counter())[str(x.get("label"))] += 1
    for k, c in sorted(cross.items()):
        print(f"  {k}: n={sum(c.values())}  {dict(c)}")
    print("\n=== 找响应正文：哪个字段含 'VERDICT' ===")
    for k in it:
        n = sum(1 for x in items if isinstance(x.get(k), str) and "VERDICT" in x[k])
        if n:
            print(f"  {k}: 含 VERDICT {n}/{len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
