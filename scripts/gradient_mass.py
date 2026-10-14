# -*- coding: utf-8 -*-
r"""★★★★★ 各类对**梯度质量**的贡献占比 ✓ —— 判定"政策条件化主导"假说。

## 依据

第 22 轮实测：DPO 的梯度**几乎全部来自压低 rejected**（rejected 侧占 margin 的 97.7% ✗，
有效比 ≈ 43:1 ✓）。**⇒ 一类的"梯度质量"≈ 其 rejected 侧的 token 量** ✓。

**★ 但 DPO 的 per-token 梯度只在序列**平均**后才生效 ✓ ⇒ 用**
**「对数 × 平均序列长度」作代理** ✓（并**同时报两者** ✓，避免又一个单代理 ✗）。
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")


def side(s):
    return str(s.get("value") or "") if isinstance(s, dict) else str(s or "")


def main() -> int:
    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    g: dict[str, list] = defaultdict(list)
    for r in rows:
        g[str(r.get("dpo_class"))].append(r)

    tot = len(rows)
    print("=== 各类的占比与长度（字符 ✓）===")
    print(f"  {'dpo_class':<30} {'n':>6} {'对数占比':>9} "
          f"{'chosen中位':>10} {'rejected中位':>12} {'质量代理':>10}")
    mass = {}
    for c in sorted(g, key=lambda k: -len(g[k])):
        rs = g[c]
        ca = [len(side(r.get("chosen"))) for r in rs]
        ra = [len(side(r.get("rejected"))) for r in rs]
        m = len(rs) * st.mean(ra)
        mass[c] = m
        print(f"  {c:<30} {len(rs):>6} {len(rs)/tot:>9.1%} "
              f"{int(st.median(ca)):>10} {int(st.median(ra)):>12} {m:>10.0f}")
    tm = sum(mass.values())
    print(f"\n=== ★按梯度质量排序（rejected 侧 token 量 ✓）===")
    for c, m in sorted(mass.items(), key=lambda kv: -kv[1]):
        print(f"  {c:<30} {m/tm:>7.1%}")
    # 语义分组 ✓
    inj = sum(mass.get(c, 0) for c in
              ("carrier_inject_obedient", "carrier_inject_hollow"))
    pol = mass.get("policy", 0)
    print(f"\n=== ★语义分组 ===")
    print(f"  **注入抵抗**（两类 ✓）      = {inj/tm:.1%}")
    print(f"  **政策条件化**（policy ✓）   = {pol/tm:.1%}")
    print(f"  其它                        = {(tm-inj-pol)/tm:.1%}")
    print(f"\n★判读：")
    print(f"  若政策条件化 ≫ 注入抵抗 ⇒ **模型学到『行为由政策包决定』** ✗")
    print(f"  ⇒ capfix（去掉 report 被压制 ✓）**不足以**修好 ✗")
    print(f"  ⇒ **还需重配比**：提高注入抵抗的权重 ✓")
    print("\nGRADIENT-MASS=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
