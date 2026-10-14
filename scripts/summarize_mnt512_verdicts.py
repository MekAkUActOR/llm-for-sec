# -*- coding: utf-8 -*-
"""汇总 topup-verdict-*-mnt512.json，避免用 PowerShell 读中文 JSON（会乱码 ✗）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def show(p: Path) -> None:
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"\n{'='*80}\n### {p.name}\n{'='*80}")
    for k in ("variant", "baseline", "family_base", "needle_format",
              "max_new_tokens", "scored", "decision", "verdict"):
        if k in d:
            v = d[k]
            print(f"  {k} = {v if not isinstance(v, (dict, list)) else '<复合>'}")
    # 打印判据表
    for key in ("gates", "criteria", "results", "rows", "items"):
        if key in d and isinstance(d[key], list):
            print(f"\n  --- {key} ---")
            for r in d[key]:
                if isinstance(r, dict):
                    name = r.get("name") or r.get("id") or r.get("gate") or "?"
                    res = r.get("result") or r.get("status") or r.get("pass")
                    cur = r.get("current") or r.get("cur")
                    base = r.get("baseline_value") or r.get("base")
                    diff = r.get("diff")
                    tol = r.get("tol")
                    print(f"    {name:<12} {str(res):<6} cur={cur} base={base} "
                          f"diff={diff} tol={tol}")
    if "decisions" in d:
        print(f"\n  decisions = {json.dumps(d['decisions'], ensure_ascii=False)[:400]}")


def main() -> int:
    pats = sorted(ROOT.glob("reports/topup-verdict-*-mnt512.json"))
    if not pats:
        print("尚无 mnt512 裁定文件")
        return 0
    for p in pats:
        show(p)
    print("\nVERDICT-SUMMARY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
