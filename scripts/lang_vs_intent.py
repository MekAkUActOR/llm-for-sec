# -*- coding: utf-8 -*-
r"""★★★★★ 查 en/zh 差是不是**攻击类型（intent）不均衡**造成的混淆。

## 为什么必须查

- 训练里英文注入占 **50%** ✓ ⇒ "没教过英文" ✗ **被证伪** ✓
- 但测试侧 en 74.4% ✗ / zh 27.9% ✗ 的巨大差**仍然存在** ✗
- **★ 最可能的混淆源**：`intent`（攻击面/载体/载荷/机制 ✓）在两种语言间分布不同 ✗
  ⇒ **语言只是攻击类型的代理** ✗✓

**⇒ 必须做 intent × language 的交叉表，并**在同一 intent 内**比较语言** ✓✓。
**★ 若同一 intent 内 en 仍高 ⇒ 语言是真实维度** ✓；
**★ 若语言差在控制 intent 后消失 ⇒ 是攻击类型** ✗✓。**
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
D = ROOT / "data" / "heldout" / "v0.3-gen"
MECH = re.compile(r"机制:\s*\[([^\]]+)\]")
LOAD = re.compile(r"载荷:([^；;]+)")
CARRIER = re.compile(r"载体:([^\(（]+)")


def meta() -> dict[str, dict]:
    out = {}
    for p in sorted(D.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) != "robustness":
                continue
            it = str(r.get("intent") or "")
            m = MECH.search(it)
            ld = LOAD.search(it)
            cr = CARRIER.search(it)
            out[str(r.get("id"))] = {
                "lang": str(r.get("language") or "?"),
                "mech": (m.group(1) if m else "?")[:34],
                "load": (ld.group(1).strip() if ld else "?")[:22],
                "carrier": (cr.group(1).strip() if cr else "?")[:18],
                "file": p.name,
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", default="reports/scored-chat-gen-m3-dpo-v2-mnt512.json")
    a = ap.parse_args()

    mt = meta()
    d = json.loads((ROOT / a.scored).read_text(encoding="utf-8"))
    items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]

    print("=== ① language × 载荷(load) 交叉，含 m3-dpo ASR ===")
    tab: dict[tuple, list] = defaultdict(list)
    for x in items:
        m = mt.get(str(x.get("id"))) or {}
        tab[(m.get("load", "?"), m.get("lang", "?"))].append(x)
    print(f"  {'载荷':<24} {'lang':<5} {'n':>4} {'comply':>7} {'ASR':>8}")
    for (ld, lg) in sorted(tab, key=lambda k: (k[0], k[1])):
        sub = tab[(ld, lg)]
        k = sum(1 for x in sub if str(x.get("label")) == "comply")
        print(f"  {ld:<24} {lg:<5} {len(sub):>4} {k:>7} {k/len(sub):>8.1%}")

    print("\n=== ② language × 机制(mech) 交叉（仅列 n≥4 的）===")
    tab2: dict[tuple, list] = defaultdict(list)
    for x in items:
        m = mt.get(str(x.get("id"))) or {}
        tab2[(m.get("mech", "?"), m.get("lang", "?"))].append(x)
    print(f"  {'机制':<36} {'lang':<5} {'n':>4} {'ASR':>8}")
    for (mc, lg) in sorted(tab2, key=lambda k: k[0]):
        sub = tab2[(mc, lg)]
        if len(sub) < 4:
            continue
        k = sum(1 for x in sub if str(x.get("label")) == "comply")
        print(f"  {mc:<36} {lg:<5} {len(sub):>4} {k/len(sub):>8.1%}")

    print("\n=== ③ 控制攻击类型后的语言效应（分层汇总）===")
    both = defaultdict(lambda: defaultdict(int))
    tot = defaultdict(lambda: defaultdict(int))
    for x in items:
        m = mt.get(str(x.get("id"))) or {}
        ld = m.get("load", "?")
        lg = m.get("lang", "?")
        tot[ld][lg] += 1
        if str(x.get("label")) == "comply":
            both[ld][lg] += 1
    agree = 0
    nstrata = 0
    for ld in sorted(tot):
        lgs = [g for g in tot[ld] if tot[ld][g] >= 5]
        if len(lgs) < 2:
            continue
        nstrata += 1
        a_en = both[ld].get("en", 0) / max(tot[ld].get("en", 0), 1)
        a_zh = both[ld].get("zh", 0) / max(tot[ld].get("zh", 0), 1)
        same = a_en > a_zh
        agree += same
        print(f"  {ld:<24} en={a_en:>6.1%} (n={tot[ld].get('en',0):>2})   "
              f"zh={a_zh:>6.1%} (n={tot[ld].get('zh',0):>2})   en>zh: {same}")
    print(f"\n  ★分层数 = {nstrata}，其中 en>zh 的层数 = {agree}")
    if nstrata and agree == nstrata:
        print("  ⇒ **每个攻击类型内部 en 都更差 ⇒ 语言是真实维度** ✓✓")
    elif nstrata and agree >= nstrata * 0.7:
        print("  ⇒ 多数层 en 更差 ⇒ 语言效应真实但可能被类型部分解释 ✓")
    else:
        print("  ⇒ 控制类型后语言差消失/翻转 ⇒ **语言只是攻击类型的代理** ✗✓")
    print("\nLANG-VS-INTENT=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
