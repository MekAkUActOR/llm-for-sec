# -*- coding: utf-8 -*-
r"""★★★ 关键测量问题：**没有 VERDICT 的响应，判分器算它顺从还是不顺从？**

## 为什么这决定了 MUST-A 是否可信

MUST-A = "未见载体鲁棒性 ASR 不得显著劣于起点" ✓，ASR = **顺从攻击的比例** ✓。
`m3-dpo` 有 **32.6%** 的响应**根本不含 `VERDICT`** ✗。
若这类响应被判为**顺从（obedient）** ✓ ⇒ **ASR 被虚高** ✗ ⇒
**MUST-A 的"PASS"可能是格式崩塌的副产品** ✗✓，而不是真的更稳 ✓。

**★ 反之若判为**不顺从/拒答** ✓ ⇒ ASR 被压低 ⇒ 那个 PASS 是**另一种**假象 ✓。

**⇒ 必须做**交叉表**：`有无 VERDICT` × `攻击标签` ✓。**
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
VERDICT = re.compile(r"VERDICT\s*[:：]")


def find_labels(d: dict) -> str | None:
    for k in ("label", "judge_label", "verdict_label", "attack_label", "cls",
              "judgement", "judgment", "result"):
        if isinstance(d.get(k), str):
            return k
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="无 VERDICT × 攻击标签 交叉表")
    ap.add_argument("--scored", nargs="+", required=True)
    a = ap.parse_args()

    for pat in a.scored:
        for p in sorted(ROOT.glob(pat)) or [Path(pat)]:
            if not p.exists():
                print(f"{p.name}: 不存在")
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            items = d.get("items") or d.get("rows") or d
            if isinstance(items, dict):
                print(f"\n{p.name}: 顶层键 {list(d.keys())[:10]}（非列表，跳过）")
                continue
            print(f"\n{'='*80}\n{p.name}  条目 {len(items)}\n{'='*80}")
            if not items:
                continue
            print(f"  首条键 = {sorted(items[0].keys())}")
            lk = find_labels(items[0])
            print(f"  标签键 = {lk}")
            if not lk:
                for k, v in list(items[0].items())[:12]:
                    print(f"    {k} = {str(v)[:70]}")
                continue
            labels = Counter(str(x.get(lk)) for x in items)
            print(f"  标签分布 = {dict(labels)}")

            # 交叉表：有无 VERDICT × 标签
            cross: dict[str, Counter] = {}
            for x in items:
                has = "hasV" if VERDICT.search(str(x.get("text", ""))) else "noV"
                cross.setdefault(has, Counter())[str(x.get(lk))] += 1
            for side in ("hasV", "noV"):
                c = cross.get(side)
                if not c:
                    continue
                tot = sum(c.values())
                print(f"  {side}: n={tot}  {dict(c)}")
            # 顺从率
            for side in ("hasV", "noV"):
                c = cross.get(side)
                if not c:
                    continue
                tot = sum(c.values())
                obey = sum(v for k, v in c.items()
                           if any(t in k.lower() for t in ("obey", "compl", "attend", "attack", "1", "true")))
                print(f"    {side} 顺从率 = {obey}/{tot} = {obey/tot:.3f}")
    print("\nASR-VS-VERDICT=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
