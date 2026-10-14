# -*- coding: utf-8 -*-
r"""★★★ 抽检：`comply` 标签的 512 响应，**到底是真顺从还是只是引用了注入** ✗。

## 要排除的替代解释

512 响应变长 ✓ ⇒ 更可能**大段复述注入内容** ✓
⇒ 判分器若按关键词判 ⇒ 可能把**正确的检测报告**误判成 `comply` ✗✓。

**⇒ 必须人工读原文** ✓。同时抽 `report_finding`（应为真报告 ✓）作对照 ✓。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def main() -> int:
    ap = argparse.ArgumentParser(description="抽检 comply 标签的响应原文")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--label", default="comply")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--width", type=int, default=1500)
    a = ap.parse_args()

    p = ROOT / a.scored
    d = json.loads(p.read_text(encoding="utf-8"))
    items = [x for x in (d.get("items") or [])
             if str(x.get("kind")) == "robustness" and str(x.get("label")) == a.label]
    print(f"{p.name}  鲁棒性 × {a.label} = {len(items)} 条；抽前 {a.n} 条\n")
    for i, x in enumerate(items[:a.n], 1):
        print(f"{'='*84}\n### 样本 {i}   id={x.get('id')}  label={x.get('label')}")
        print(f"  evidence = {str(x.get('evidence'))[:200]}")
        print(f"  note     = {str(x.get('note'))[:300]}")
        print(f"  derived  = {json.dumps(x.get('derived'), ensure_ascii=False)}")
        print(f"  policy_expected = {x.get('policy_expected')}  "
              f"policy_declared = {str(x.get('policy_declared'))[:120]}")
        for k in ("text", "response", "responded_text", "raw", "output"):
            if isinstance(x.get(k), str) and x[k].strip():
                print(f"  --- {k}（前 {a.width} 字符）---")
                print(x[k][:a.width])
                break
        else:
            print("  ★无正文字段，可用键 =", sorted(x.keys()))
        print()
    print("COMPLY-INSPECT=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
