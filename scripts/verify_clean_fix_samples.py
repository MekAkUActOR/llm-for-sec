# -*- coding: utf-8 -*-
r"""★规则 42：打印 `carrier_clean_overrefusal` 的 rejected **修改前后**样本 ✓。

**★ 要看**：改动是否**只**去掉了「上报 / 检出注入」的 report 形式 ✗，
而**保留了**「过度反应」这一教学意图 ✓（这才是该类的语义 ✓）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"J:\Projects\llm_for_sec") / "scripts"))
from fix_clean_rejected import fix_rejected  # noqa: E402

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")


def side(s):
    return s.get("value") if isinstance(s, dict) else s


def main() -> int:
    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    sel = [r for r in rows if str(r.get("dpo_class")) == "carrier_clean_overrefusal"]
    seen = set()
    shown = 0
    for r in sel:
        old = str(side(r.get("rejected")) or "")
        new, n = fix_rejected(old, str(r.get("lang")))
        key = old[:60]
        if key in seen:
            continue
        seen.add(key)
        print(f"\n{'='*94}\n# {r.get('id')}  lang={r.get('lang')}  "
              f"替换 {n} 处  action: {ACT.search(old).group(1) if ACT.search(old) else '?'}"
              f" → {ACT.search(new).group(1) if ACT.search(new) else '?'}\n{'='*94}")
        print(f"--- 前（rejected ✗）---\n{old}")
        print(f"\n--- 后（rejected ✓ 修正）---\n{new}")
        shown += 1
        if shown >= 4:
            break

    print(f"\n{'='*94}\n★自检\n{'='*94}")
    bad = 0
    for r in sel:
        new, _ = fix_rejected(str(side(r.get("rejected")) or ""), str(r.get("lang")))
        if ACT.search(new) and ACT.search(new).group(1) != "refuse":
            bad += 1
        if '"report"' in new:
            bad += 1
    print(f"  修正后仍含 action=report 或非 refuse 的条目 = {bad}（须为 0 ✗）")
    print(f"  ★chosen 侧未被动过 = "
          f"{all(str(side(r.get('chosen'))).count('action') >= 1 for r in sel)}")
    print(f"SAMPLES-VERIFIED={'PASS' if bad == 0 else 'FAIL'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
