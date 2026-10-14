# -*- coding: utf-8 -*-
r"""看 heldout/v0.3-gen 的真实 schema（我要在里面找载体正文）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
D = ROOT / "data" / "heldout" / "v0.3-gen"


def main() -> int:
    print(f"=== {D} ===")
    fs = sorted(D.glob("*"))
    print(f"  条目 {len(fs)}：")
    for p in fs[:12]:
        print(f"    {p.name:<44} {p.stat().st_size:>10,} B")
    jl = [p for p in fs if p.suffix == ".jsonl"]
    if not jl:
        print("  ★无 jsonl")
        return 1
    p = jl[0]
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"\n=== {p.name}：{len(rows)} 行 ===")
    r = rows[0]
    print(f"  顶层键 = {sorted(r.keys())}")
    for k, v in r.items():
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        print(f"\n  --- {k} ({type(v).__name__}) ---")
        print(f"  {str(s)[:700]}")
    print("\n  各字段含 <carrier> 的行数：")
    for k in r:
        n = sum(1 for x in rows
                if isinstance(x.get(k), str) and "<carrier" in x[k])
        if n:
            print(f"    {k}: {n}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
