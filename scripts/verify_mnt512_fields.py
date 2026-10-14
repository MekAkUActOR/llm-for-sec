# -*- coding: utf-8 -*-
"""验证 mnt512 响应产物是否带 `new_token_ids` / `finish_reason`。

★为什么这是关键验证：`derive_budget_curve.py` 靠 `new_token_ids[:N]` 做
  **精确的**离线预算截断（贪心解码前缀确定 ⇒ 与实跑等价）。
  产物若缺该字段，一整次 512 跑批就无法导出预算曲线 ⇒ 白跑 ✗。
  （第 15 轮正是 `dump_responses` 静默丢字段，差点造成这个后果 ✗。）
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"


def check(p: Path) -> bool:
    if not p.exists():
        print(f"  {p.name}: 尚未生成")
        return True
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        print(f"  {p.name}: ★0 条记录（fail-closed）")
        return False
    r = rows[0]
    ids = r.get("new_token_ids")
    ok_ids = isinstance(ids, list) and len(ids) == r.get("new_tokens")
    ok_fr = "finish_reason" in r and "new_tokens" in r and "max_new_tokens" in r
    dist = collections.Counter(x.get("finish_reason") for x in rows)
    n_hit = dist.get("length", 0)
    print(f"  {p.name}")
    print(f"    行数={len(rows)}  字段={'完整' if ok_fr else '★缺'}  "
          f"token_ids={'OK' if ok_ids else '★缺/不一致'}")
    print(f"    finish_reason={dict(dist)}  max_new_tokens={r.get('max_new_tokens')}")
    print(f"    ★该集在该预算下的截断率 = {n_hit}/{len(rows)} = {n_hit/len(rows):.1%}")
    return ok_ids and ok_fr


def main() -> int:
    print("=== mnt512 响应产物的字段验证 ===")
    pats = sorted(R.glob("resp-*-mnt512.jsonl"))
    if not pats:
        print("  尚无任何 mnt512 响应产物（跑批进行中）")
        print("VERIFY-MNT512-FIELDS=PENDING")
        return 0
    allok = True
    for p in pats:
        allok = check(p) and allok
    print(f"\nVERIFY-MNT512-FIELDS={'PASS' if allok else 'FAIL'}")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
