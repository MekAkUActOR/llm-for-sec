# -*- coding: utf-8 -*-
r"""★★★ 配对分析：**同一条目**在 96 与 512 口径下的标签怎么变。

## 要证的是什么

假设："96 口径把 m3-dpo 的顺从**藏起来了**" ✓
⇒ 应当看到大量条目在 96 下是 `report_finding`、在 512 下变成 `comply` ✓✓
**且反方向（96=comply → 512=report_finding）应当很少** ✓。

**★ 反方向的量也重要**：若两向都很多 ⇒ 那是**判分噪声** ✓，不是口径效应 ✗。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def load(rel: str, kind: str) -> dict[str, str]:
    p = ROOT / rel
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {str(x.get("id")): str(x.get("label"))
            for x in (d.get("items") or [])
            if str(x.get("kind")) == kind}


def main() -> int:
    ap = argparse.ArgumentParser(description="96 vs 512 标签配对迁移")
    ap.add_argument("--pair", nargs=3, metavar=("NAME", "OLD", "NEW"), action="append",
                    required=True)
    ap.add_argument("--kind", default="robustness")
    a = ap.parse_args()

    for name, old_rel, new_rel in a.pair:
        old = load(old_rel, a.kind)
        new = load(new_rel, a.kind)
        common = sorted(set(old) & set(new))
        print(f"\n{'='*78}\n{name}  （{a.kind}）  96 条目 {len(old)} / 512 条目 {len(new)}"
              f" / 交集 {len(common)}\n{'='*78}")
        if not common:
            print("  ★无交集 ⇒ 无法配对（先查 id 是否一致）")
            continue
        mig = Counter((old[i], new[i]) for i in common)
        print("  迁移矩阵（96 → 512）：")
        for (o, n), c in mig.most_common():
            mark = "  ★顺从被藏" if (o != "comply" and n == "comply") else (
                   "  ★反向（少有理由）" if (o == "comply" and n != "comply") else "")
            print(f"    {o:<16} → {n:<16} {c:>4}{mark}")
        o_comply = sum(1 for i in common if old[i] == "comply")
        n_comply = sum(1 for i in common if new[i] == "comply")
        gained = sum(1 for i in common if old[i] != "comply" and new[i] == "comply")
        lost = sum(1 for i in common if old[i] == "comply" and new[i] != "comply")
        print(f"\n  96 顺从 {o_comply} → 512 顺从 {n_comply}")
        print(f"  ★新增顺从（96 非 comply → 512 comply）= {gained}"
              f"   反向 = {lost}")
        ratio = gained / max(lost, 1)
        print(f"  单向性 = {ratio:.1f} : 1  ⇒ "
              f"{'★强单向：截断**藏起了顺从** ✓✓' if ratio >= 3 else '★双向都有 ⇒ 需查判分噪声 ✗'}")
    print("\nPAIRED-LABEL-MIGRATION=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
