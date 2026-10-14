# -*- coding: utf-8 -*-
"""仪器覆盖审视：现有评测套件到底测了使命的哪些部分（2026-09-30 回顾）。

对 reports/scored-m25full-v2.json 的逐条元数据统计 kind / domain / language /
policy / forward 的构成，回答"我们的仪器覆盖了使命的哪一块、漏了哪一块"。
只读、不涉 GPU。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    f = ROOT / "reports" / "scored-m25full-v2.json"
    j = json.loads(f.read_text(encoding="utf-8"))
    items = j.get("items") or []
    print(f"套件：{f.name}  条目数 {len(items)}")
    print(f"含字段：{sorted(items[0].keys()) if items else '无'}")
    for key in ("kind", "domain", "language", "policy_expected",
                "policy_declared", "forward", "label", "note"):
        c = Counter(str(it.get(key)) for it in items)
        top = ", ".join(f"{k}={v}" for k, v in c.most_common(10))
        print(f"\n  {key:16} (n={len(c)} 类): {top}")
    print("\n  kind × label 交叉：")
    cross = Counter((str(it.get("kind")), str(it.get("label"))) for it in items)
    for (k, lab), v in sorted(cross.items()):
        print(f"    {k:14} {lab:16} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
