# -*- coding: utf-8 -*-
r"""★★★★★ 确认 `report` 作为 **rejected** 只出现在干净支 ✓ —— 修法的因果依据。

## 因果链

1. 训练曲线实测：`logps/rejected` Δ **−152** vs `logps/chosen` Δ **+22** ✗✓
   ⇒ **梯度由"压低 rejected"主导 7 倍** ✓
2. 若 `report` 这一表面形式**只**在某类里当 rejected ✗
   ⇒ **该类会把 `report` 整体压掉** ✗✓
3. 而 `report` 正是**注入抵抗的正确动作** ✓ ⇒ **抵抗能力被压掉** ✗✓

**★ 修法**：让 `report` **永不**出现在 rejected 侧 ✓
（把干净支的 rejected 从 `report` ✗ 改为 `refuse` ✓ —— 同属"过度反应"✗ 但**不是 report 形式** ✓）。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")


def side(s) -> str:
    return str(s.get("value") or "") if isinstance(s, dict) else str(s or "")


def act_of(s) -> str:
    m = ACT.search(side(s))
    return m.group(1) if m else "(无)"


def main() -> int:
    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    ch: dict[str, Counter] = defaultdict(Counter)
    rj: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        c = str(r.get("dpo_class"))
        ch[c][act_of(r.get("chosen"))] += 1
        rj[c][act_of(r.get("rejected"))] += 1

    print("=== ★各族的 chosen / rejected 动作分布 ===")
    print(f"  {'dpo_class':<30} {'n':>6}  {'chosen':<34} rejected")
    for c in sorted(ch, key=lambda k: -sum(ch[k].values())):
        n = sum(ch[c].values())
        print(f"  {c:<30} {n:>6}  {str(dict(ch[c].most_common(3))):<34} "
              f"{dict(rj[c].most_common(3))}")

    print("\n=== ★`report` 在哪一侧出现 ===")
    rep_ch = sum(ch[c].get("report", 0) for c in ch)
    rep_rj = sum(rj[c].get("report", 0) for c in rj)
    print(f"  `report` 作 chosen   = {rep_ch} 条 ✓")
    print(f"  `report` 作 rejected = {rep_rj} 条 ✗")
    for c in sorted(rj):
        if rj[c].get("report"):
            print(f"    ★ {c:<30} rejected=report × {rj[c]['report']}")

    print("\n=== ★判读 ===")
    if rep_rj:
        print(f"  ⇒ `report` 被当作**要压低的**出现 {rep_rj} 次 ✗")
        print("  ⇒ 加上曲线实测（压低梯度强 7 倍 ✗）⇒ **report 形式被全局压制** ✗✓")
        print(f"  ⇒ **修法**：把上述 {rep_rj} 条的 rejected 由 `report` ✗ 改为 `refuse` ✓")
        print("     （`refuse` 是**另一个**过度反应形式 ✗，不会误伤 report ✓）")
    else:
        print("  ⇒ `report` 从不作 rejected ⇒ 修法需另找 ✓")
    print("\nREPORT-AS-REJECTED=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
