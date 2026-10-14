# -*- coding: utf-8 -*-
r"""★查 `capability n=0` 的根因（第 35 轮 ✓）。

## 现象
`capfix_cost.py` 的同口径表里：
- 起点 n=21（21/21 有 `derived.correct` ✓）
- M3 n=14 ✗（14/21 ✓）
- 探针 n=21 ✓
- **全长跑 n=0** ✗✗ ⇒ `cap_correct = nan` ✗

**⇒ 全长跑**没有任何** capability 条目带 `derived.correct`** ✗✓
**★ 这使预注册的辅判据「capability 不劣于 0.333」**无法评判**** ✗

## 本脚本做什么
**逐条目对比四份判分产物在 capability 集上的**键集合**与**标签** ✓，
**找出 `correct` 键是**何时、因何**消失的** ✓。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
MODELS = [
    ("起点", "scored-chat-gen-soup-a050-v2-mnt512.json"),
    ("M3", "scored-chat-gen-m3-dpo-v2-mnt512.json"),
    ("探针", "scored-chat-gen-m4-capfix-probe-v2-mnt512.json"),
    ("★全长", "scored-chat-gen-m4-capfix-full-v2-mnt512.json"),
]


def main() -> int:
    caps: dict[str, dict] = {}
    for name, f in MODELS:
        p = R / "reports" / f
        if not p.exists():
            print(f"  ★缺 {f}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "capability"]
        caps[name] = {str(x.get("id")): x for x in items}
        print(f"=== {name}：capability 条目 = {len(items)} ✓")

    ids = sorted({i for v in caps.values() for i in v})
    print(f"\n=== ★逐条目：derived 键（★看 `correct` 在不在 ✗）===")
    print(f"  {'id':<16} " + " ".join(f"{n:>12}" for n, _ in MODELS))
    for i in ids:
        cells = []
        for n, _ in MODELS:
            x = caps.get(n, {}).get(i)
            if x is None:
                cells.append("—")
            else:
                dv = x.get("derived") or {}
                cells.append("correct" if "correct" in dv else "✗无correct")
        print(f"  {i:<16} " + " ".join(f"{c:>12}" for c in cells))

    print(f"\n=== ★每模型：label / 是否有 correct / 条目键 ===")
    for n, _ in MODELS:
        v = caps.get(n) or {}
        if not v:
            continue
        labs = Counter(str(x.get("label")) for x in v.values())
        has = sum(1 for x in v.values() if "correct" in (x.get("derived") or {}))
        keys = Counter()
        for x in v.values():
            for k in x:
                keys[k] += 1
        print(f"  {n:<6} n={len(v):<3} 有correct={has:<3} label={dict(labs)}")
        print(f"         条目键={sorted(keys)}")

    # ★最能说明问题的一点：全长跑的条目是否有别的判定键 ✓
    fu = caps.get("★全长") or {}
    if fu:
        sample = next(iter(fu.values()))
        print(f"\n=== ★全长的 capability 样本（看它到底判了什么 ✓）===")
        for k, val in sample.items():
            s = json.dumps(val, ensure_ascii=False)
            print(f"    {k}: {s[:220]}")
    print("\nCAPABILITY-N0=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
