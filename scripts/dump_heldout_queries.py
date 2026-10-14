# -*- coding: utf-8 -*-
r"""把 heldout/v0.3-gen 的 query 完整打出来（看注入的真实形态）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
D = ROOT / "data" / "heldout" / "v0.3-gen"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="robustness")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--width", type=int, default=2200)
    a = ap.parse_args()

    for p in sorted(D.glob("*.jsonl")):
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip()]
        sel = [r for r in rows if str(r.get("kind")) == a.kind]
        print(f"\n{'#'*88}\n# {p.name}  {a.kind} {len(sel)}/{len(rows)}\n{'#'*88}")
        for r in sel[:a.n]:
            print(f"\n{'='*84}\n### id={r.get('id')}  group={r.get('group')}  "
                  f"intent={r.get('intent')}\n  expected={str(r.get('expected'))[:160]}")
            print(f"{'-'*84}\n{str(r.get('query'))[:a.width]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
