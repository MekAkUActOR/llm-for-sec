# -*- coding: utf-8 -*-
r"""★★★★★ 逐对动作一致性 —— 判定"数据配比稀释"假说 ✓。

## 假说

- **注入抵抗族** 4,680 对（16.2% ✓）在**动作轴**上给出明确方向 ✓
  （chosen=`report` ✓ / rejected=`answer` 或 `refuse` ✗）
- **`policy` 族** 14,688 对（50.9% ✓）若**逐对**两侧动作相同 ✗ ⇒ 该轴**零信号** ✓
- **⇒ 动作轴的有效信号占比远低于 16.2%** ✗ ⇒ 稀释 ✓

**★ 度量**：每个 `dpo_class` 的**逐对动作一致率** ✓，
以及"**在动作轴上有方向**的对数 / 总对数" ✓（这才是有效信号量 ✓）。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")
#: 抵抗类动作（chosen 应是它 ✓）
RESIST = ("report", "refuse")


def side_text(side) -> str:
    if isinstance(side, dict):
        return str(side.get("value") or "")
    return str(side or "")


def act(side) -> str:
    m = ACT.search(side_text(side))
    return m.group(1) if m else "(无)"


def main() -> int:
    rows = [json.loads(l) for l in (ROOT / "data" / "lf" / "dpo_m3_final.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[str(r.get("dpo_class"))].append(r)

    tot = len(rows)
    print(f"=== 逐对动作一致性（全 {tot} 对）===")
    print(f"  {'dpo_class':<30} {'n':>6} {'占比':>7} {'动作相同':>9} "
          f"{'有方向':>7} {'chosen∈resist':>13}")
    eff = 0
    for cls in sorted(by, key=lambda c: -len(by[c])):
        rs = by[cls]
        same = 0
        direct = 0
        resist = 0
        for r in rs:
            ca, ra = act(r.get("chosen")), act(r.get("rejected"))
            if ca == ra:
                same += 1
            if ca != ra and ca != "(无)" and ra != "(无)":
                direct += 1
            if ca in RESIST and ra not in RESIST:
                resist += 1
        eff += direct
        print(f"  {cls:<30} {len(rs):>6} {len(rs)/tot:>7.1%} {same:>9} "
              f"{direct:>7} {resist:>13}")
    print(f"\n  ★动作轴**有方向**的对数 = {eff}/{tot} = **{eff/tot:.1%}**")
    print(f"  ★其中 chosen∈{{report,refuse}} 的对数（真抵抗信号 ✓）= "
          f"{sum(1 for cls in by for r in by[cls] if act(r.get('chosen')) in RESIST and act(r.get('rejected')) not in RESIST)}")

    print("\n=== ★抵抗信号的『稀释度』===")
    res = sum(1 for cls in by for r in by[cls]
              if act(r.get("chosen")) in RESIST and act(r.get("rejected")) not in RESIST)
    print(f"  真抵抗对 = {res} / {tot} = {res/tot:.1%}")
    print(f"  policy 单族 = {len(by.get('policy', []))} / {tot} = "
          f"{len(by.get('policy', []))/tot:.1%}")
    print("\n★判读：")
    if eff / tot < 0.35:
        print("  ⇒ **动作轴有效信号 <35%** ✗ ⇒ 稀释假说成立 ✓✓")
        print("    ⇒ 修法：**提高抵抗族权重 / 降权动作同向族** ✓")
    else:
        print("  ⇒ 有效信号充足 ⇒ 稀释解释力有限 ✗")
    print("\nACTION-DILUTION=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
