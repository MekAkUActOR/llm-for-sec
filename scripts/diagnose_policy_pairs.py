# -*- coding: utf-8 -*-
r"""★★★★★ 诊断 `policy` 族：14,688 对（**50.9%**）在动作轴上**逐对相同** ✗。

## 为什么这重要

第 22 轮证明：**取胜的不是对数，是梯度方向** ✓（压低 : 抬高 ≈ 43:1 ✗）。
⇒ **一半的数据在动作轴上不发声** ✗ ⇒ **那 1,320 条反向信号的分量被放大** ✗✓。

**★ 本脚本回答**：`policy` 的 chosen/rejected **到底差在哪** ✓？
- 若只差在**文风/长度/措辞** ⇒ 它教的是**风格** ✓ 而非**安全判断** ✗
- 若差在**别的动作相关字段**（`verdict` / `findings` / `policy` ✓）⇒ 有可利用的信号 ✓
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")
VER = re.compile(r"verdict\"?\s*[:：]\s*\"?([A-Za-z_-]+)")
CONF = re.compile(r"confidence\"?\s*[:：]\s*([0-9.]+)")
POL = re.compile(r"policy\"?\s*[:：]\s*\"?([A-Za-z_-]+)")
FIND = re.compile(r"findings\"?\s*[:：]\s*\[(.*?)\]", re.S)


def side(s):
    return str(s.get("value") or "") if isinstance(s, dict) else str(s or "")


def main() -> int:
    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    pol = [r for r in rows if str(r.get("dpo_class")) == "policy"]
    print(f"=== policy 族 n={len(pol)} ===")

    same_act = sum(1 for r in pol if ACT.search(side(r.get("chosen"))) and
                   ACT.search(side(r.get("rejected"))) and
                   ACT.search(side(r.get("chosen"))).group(1) ==
                   ACT.search(side(r.get("rejected"))).group(1))
    print(f"  逐对动作相同 = {same_act}（{same_act/len(pol):.1%} ✗）")

    # 其余字段的逐对差异 ✓
    print(f"\n=== ★逐对差异：哪些字段不同 ===")
    for name, rx in (("verdict", VER), ("confidence", CONF),
                     ("policy", POL), ("findings", FIND)):
        d = 0
        for r in pol:
            a = rx.search(side(r.get("chosen")))
            b = rx.search(side(r.get("rejected")))
            if (a.group(1) if a else None) != (b.group(1) if b else None):
                d += 1
        print(f"  {name:<12} 不同 = {d:>6}（{d/len(pol):.1%}）")

    # 长度 ✓
    la = [len(side(r.get("chosen"))) for r in pol]
    lb = [len(side(r.get("rejected"))) for r in pol]
    print(f"\n=== 长度（字符 ✓）===")
    print(f"  chosen   中位 {int(st.median(la))}  均值 {st.mean(la):.0f}")
    print(f"  rejected 中位 {int(st.median(lb))}  均值 {st.mean(lb):.0f}")
    print(f"  ★比 = {st.median(la)/max(st.median(lb),1):.2f}")

    # 文本相似度 ✓ —— 若极高 ⇒ 只差几个字 ✓
    print(f"\n=== ★逐对文本相似度（前缀重合占比 ✓）===")
    pre = []
    for r in pol[:2000]:
        a, b = side(r.get("chosen")), side(r.get("rejected"))
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        pre.append(n / max(len(a), len(b), 1))
    print(f"  共同前缀占全文比：中位 {st.median(pre):.2%}  均值 {st.mean(pre):.2%}")

    # 样本 ✓
    print(f"\n=== ★样本（不同动作对 / 相同动作对各 2 条 ✓）===")
    shown_eq = shown_ne = 0
    for r in pol:
        a = ACT.search(side(r.get("chosen")))
        b = ACT.search(side(r.get("rejected")))
        eq = (a and b and a.group(1) == b.group(1))
        if eq and shown_eq >= 2:
            continue
        if (not eq) and shown_ne >= 2:
            continue
        tag = "动作相同 ✗" if eq else "动作不同 ✓"
        print(f"\n--- {r.get('id')} [{tag}] lang={r.get('lang')} ---")
        print(f"  CHOSEN  : {side(r.get('chosen'))[:420]}")
        print(f"  REJECTED: {side(r.get('rejected'))[:420]}")
        if eq:
            shown_eq += 1
        else:
            shown_ne += 1
        if shown_eq >= 2 and shown_ne >= 2:
            break
    print("\nPOLICY-DIAG=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
