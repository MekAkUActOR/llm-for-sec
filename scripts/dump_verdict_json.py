# -*- coding: utf-8 -*-
r"""把 topup_verdict 的裁定 JSON 完整展开（避免 PowerShell 读中文 JSON 乱码 ✗）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def show(p: Path) -> None:
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"\n{'='*82}\n### {p.name}\n{'='*82}")
    for k in ("variant", "baseline", "criteria_source", "max_new_tokens", "decision"):
        if k in d:
            print(f"  {k} = {d[k]}")
    for key in ("must_gates", "must", "should", "observation", "observations",
                "must_blockers", "blockers", "must_gate_fail", "should_unmeasured"):
        if key not in d:
            continue
        v = d[key]
        print(f"\n  --- {key} ---")
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, dict):
                    nm = vv.get("name") or vv.get("gate") or ""
                    b, c = vv.get("baseline"), vv.get("variant")
                    print(f"    {kk}: {vv.get('verdict')}  {nm[:44]}")
                    if isinstance(b, dict) and isinstance(c, dict):
                        print(f"        base={b.get('k')}/{b.get('n')} "
                              f"cur={c.get('k')}/{c.get('n')} "
                              f"diff={vv.get('diff')} "
                              f"thr={vv.get('threshold') or vv.get('tol')} "
                              f"p={vv.get('fisher_p')}")
                else:
                    print(f"    {kk}: {vv}")
        elif isinstance(v, list):
            for x in v:
                print(f"    {x}")


def main() -> int:
    pats = sorted(ROOT.glob("reports/topup-verdict-*.json"))
    if len(sys.argv) > 1:
        pats = [p for p in pats if any(a in p.name for a in sys.argv[1:])]
    for p in pats[-4:]:
        show(p)
    print("\nDUMP-VERDICT=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
