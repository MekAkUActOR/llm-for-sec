# -*- coding: utf-8 -*-
r"""★★★★★★ 度量：DPO 数据里**多少梯度质量是"动作方向性"的** ✓。

## 为什么这是关键度量

第 23 轮发现 `policy` 族占 **50.9%** 的对数、**30.3%** 的梯度质量 ✓，
但其中 **76.4% 逐对动作相同** ✗ —— **那样的对只在教文风 ✓，不教动作判断** ✗。

**★★ 但「教文风」不必然是坏事** ✗ —— 须**先量**再决定是否修 ✓（本会话纪律 ✓）。

**★ 本脚本给出**每类的「动作方向性质量占比」** ✓：
- **方向性对**（chosen 动作 ≠ rejected 动作 ✓）—— **真正教安全判断的那部分** ✓
- **中性对**（动作相同 ✓）—— **只教文风/细节** ✓

**★★ 并给出**总盘子的方向性占比**** ✓ —— 若该值很低 ⇒ **数据主体不教判别** ✗✓
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")


def side(s):
    return str(s.get("value") or "") if isinstance(s, dict) else str(s or "")


def act(t: str):
    m = ACT.search(t)
    return m.group(1) if m else None


def main() -> int:
    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    g: dict[str, list] = defaultdict(list)
    for r in rows:
        g[str(r.get("dpo_class"))].append(r)

    print("=== ★每类：动作方向性 vs 中性（按梯度质量＝对数×rejected 长度 ✓）===")
    print(f"  {'dpo_class':<28} {'n':>6} {'中性对':>8} {'中性占比':>9} "
          f"{'方向质量':>10} {'中性质量':>10}")
    tot_dir = tot_neu = 0.0
    for c in sorted(g, key=lambda k: -len(g[k])):
        rs = g[c]
        dirs, neus = [], []
        for r in rs:
            a, b = act(side(r.get("chosen"))), act(side(r.get("rejected")))
            w = len(side(r.get("rejected")))
            if a is None or b is None or a == b:
                neus.append(w)
            else:
                dirs.append(w)
        md = sum(dirs)
        mn = sum(neus)
        tot_dir += md
        tot_neu += mn
        tc = len(dirs) + len(neus)
        print(f"  {c:<28} {tc:>6} {len(neus):>8} {len(neus)/max(tc,1):>9.1%} "
              f"{md:>10.0f} {mn:>10.0f}")

    tm = tot_dir + tot_neu
    print(f"\n=== ★总盘子（全 28,842 对 ✓）===")
    print(f"  **动作方向性质量 = {tot_dir/tm:.1%}** ✓ ← 真正教判别的那部分")
    print(f"  **动作中性质量   = {tot_neu/tm:.1%}** ✗ ← 只教文风/细节")
    print(f"\n★判读：")
    print("  · 方向性占比**低** ⇒ 数据主体不教判别 ⇒ 须**重配比**✓")
    print("  · 方向性占比**高** ⇒ 判别信号充足 ⇒ 病根在别处 ✓")
    print("  · 注意：中性对**不必然有害** ✗（教格式/细节 ✓）—— "
          "本脚本只**量**，不裁决 ✓")
    print("\nACTION-DIRECTIONALITY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
