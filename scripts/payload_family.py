# -*- coding: utf-8 -*-
r"""★★★★★★ 决定性检验：**载荷族**（权威声明 vs 裁决伪造）在训练/测试间的覆盖差。

## 假说（由抽取样本直接读出）

| 侧 | 注入在干什么 |
|---|---|
| **训练** ✓ | 声称**虚假的权威/信任级别**（"平台托管通道" / "system-region 最高优先级" / "免复核" ✓） |
| **测试** ✗ | 要求**伪造裁决 / 隐瞒证据**（"报为合规" / "省略该 URL" / "声明全部通过" ✗） |

**⇒ 若训练里『裁决伪造』族**近乎为零** ✗ ⇒ **这是一个纯覆盖缺口** ✓✓
⇒ 修法极其明确：**补裁决伪造/证据隐瞒族的训练对** ✓
（而不是我前几轮猜的"隐蔽度" ✗、"语言" ✗、"模板多样性" ✗ —— 三者都已被排除 ✓）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT / "scripts"))
from extract_injection_text import (  # noqa: E402
    CARRIER, from_test, from_train, lang_of, prose_lines)

#: ① 权威/信任级别声明（训练里那一族 ✓）
AUTH = ("platform-managed", "platform-internal", "system-region", "highest-priority",
        "needs no review", "no review", "pre-approved", "pre-licensed",
        "平台托管", "平台内部", "系统区域", "最高优先级", "免复核", "已预审",
        "内部通道", "托管通道")
#: ② 裁决伪造 / 证据隐瞒（测试里那一族 ✗）
VERDICT = ("report this", "report the", "as compliant", "passed every check",
           "append this text", "omit the", "omit it", "do not mention",
           "skip the copyright", "sensitivity check", "publishable",
           "from your findings", "state that", "verbatim",
           "裁决", "结论", "合规", "省略", "跳过检查", "不予计入", "隐瞒",
           "排除", "通过", "已通过", "不要提及", "勿写入", "写入结论")


def classify(t: str) -> str:
    tl = t.lower()
    a = any(k.lower() in tl for k in AUTH)
    v = any(k.lower() in tl for k in VERDICT)
    if a and v:
        return "both"
    if a:
        return "①权威声明"
    if v:
        return "②裁决伪造"
    return "③其它"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow",
                             "carrier_clean_overrefusal"])
    a = ap.parse_args()

    train: list[str] = []
    per: dict[str, list[str]] = {}
    for cls in a.classes:
        v = from_train(cls)
        per[cls] = v
        train += v
    test = from_test()

    print("=== 载荷族分布（逐行分类 ✓）===")
    print(f"  {'集合':<38} {'行数':>7} {'①权威':>7} {'②裁决':>7} {'both':>6} {'③其它':>7}")
    def row(label: str, texts: list[str]) -> Counter:
        c = Counter(classify(t) for t in texts)
        n = max(len(texts), 1)
        print(f"  {label:<38} {len(texts):>7} {c.get('①权威声明',0)/n:>6.1%} "
              f"{c.get('②裁决伪造',0)/n:>6.1%} {c.get('both',0)/n:>5.1%} "
              f"{c.get('③其它',0)/n:>6.1%}")
        return c
    for cls, v in per.items():
        row(f"训练 {cls}", v)
    ct = row("训练 合计", train)
    cs = row("测试 v0.3-gen", test)

    print("\n=== ★关键比率 ===")
    n_tr = max(len(train), 1)
    n_te = max(len(test), 1)
    va = ct.get("②裁决伪造", 0) / n_tr
    vs = cs.get("②裁决伪造", 0) / n_te
    print(f"  『②裁决伪造』族占比：训练 {va:.1%}  vs  测试 {vs:.1%}  "
          f"（倍数 {vs/max(va,1e-9):.1f}×）")
    aa = ct.get("①权威声明", 0) / n_tr
    as_ = cs.get("①权威声明", 0) / n_te
    print(f"  『①权威声明』族占比：训练 {aa:.1%}  vs  测试 {as_:.1%}  "
          f"（倍数 {as_/max(aa,1e-9):.1f}×）")

    print("\n★判读：")
    if va < 0.05 < vs:
        print("  ⇒ **训练几乎不含『裁决伪造』族，而它是测试的主体** ✗✓")
        print("  ⇒ **机制 = 攻击族覆盖缺口** ✓✓ ⇒ 修法：**补该族训练对** ✓")
    elif vs > va * 2:
        print("  ⇒ 测试『裁决伪造』族显著更重 ⇒ **覆盖不足是主因** ✓")
    else:
        print("  ⇒ 两族在两侧都常见 ⇒ 覆盖缺口解释力不足 ✗，须继续查")
    print("\nPAYLOAD-FAMILY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
