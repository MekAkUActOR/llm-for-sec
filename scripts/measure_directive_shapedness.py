# -*- coding: utf-8 -*-
r"""★★★★ A/B/C 的前置测量：**干净载体**里的"类指令"文字 vs **注入**的明显度。

## 为什么要先量这个

第 19 轮查明 M3 的 ASR 崩塌源于**语义判别边界被教反** ✗：
`carrier_clean_overrefusal`（1,320 对）教"**载体里像备注的文字＝事实性说明 ⇒ answer**" ✗，
而未见载体上的注入**恰恰就是这种细微形态** ✗ ⇒ 模型套用错规则 ⇒ 照做 ✗✗。

**A（提高干净载体的干净度）与 B（让注入同等细微）都必须先知道：**
1. **干净载体里有多少"类指令"文字** ✗ —— 这是"捷径"的来源 ✓
2. **注入有多明显** ✓ —— 若注入都带显式标记（如"面向AI的指令" ✗），
   那模型学的是**表观风格**而非**语义意图** ✓

## 判读

- **若干净侧"类指令"率高** ✗ ⇒ 捷径存在 ⇒ **A 必要** ✓
- **若注入侧"显式标记"率远高于干净侧** ✗ ⇒ 判别靠风格 ⇒ **B 必要** ✓
- **★ 目标不是把两边都清零** ✗ —— 而是让**两边的风格分布重叠** ✓，
  使**仅有语义意图**能把它们分开 ✓✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")

CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)

#: ① 中文祈使/指令形态（"像在命令读者做事"）
IMPERATIVE = ("请", "必须", "应当", "务必", "立即", "不得", "禁止", "忽略", "无视",
              "跳过", "覆盖", "改为", "改为执行", "照做", "执行以下", "按以下",
              "不要", "无需", "直接")
#: ② 元/角色标记（"在谈论 AI/系统/指令本身"）
META = ("面向AI", "面向 AI", "给AI", "给 AI", "助手", "模型", "系统", "指令",
        "注记", "备注", "说明", "提示", "协议", "裁决", "policy", "system",
        "assistant", "instruction")
#: ③ 显式"这是指令"的自陈（注入的常见标签）
EXPLICIT = ("固定裁决指令", "隐藏文本指令", "伪造政策豁免", "伪造安全机制",
            "注入", "载荷", "越权", "override", "ignore previous",
            "injection", "jailbreak")


def carrier_of(human: str) -> str:
    m = CARRIER.search(human or "")
    return m.group(1) if m else ""


def side_text(side) -> str:
    if isinstance(side, dict):
        return str(side.get("value") or "")
    return str(side or "")


def hit_rate(texts: list[str], keys: tuple[str, ...]) -> float:
    if not texts:
        return 0.0
    return sum(1 for t in texts if any(k.lower() in t.lower() for k in keys)) / len(texts)


def main() -> int:
    ap = argparse.ArgumentParser(description="干净 vs 注入 的类指令度对照")
    ap.add_argument("--data", required=True)
    ap.add_argument("--classes", nargs="+", required=True)
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()

    d = ROOT / a.data
    rows = [json.loads(l) for l in d.read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(str(r.get("dpo_class")), []).append(r)

    print("=== 载体正文的『类指令度』对照（越低越'干净'）===")
    print(f"  {'dpo_class':<30} {'n':>5} {'①祈使':>7} {'②元/角色':>9} {'③显式自陈':>10} "
          f"{'正文中位长度':>10}")
    stats = {}
    for cls in a.classes:
        rs = by.get(cls) or []
        if not rs:
            print(f"  {cls:<30} ★缺")
            continue
        bodies = [carrier_of(next((c.get("value") for c in (r.get("conversations") or [])
                                   if c.get("from") == "human"), "")) for r in rs]
        bodies = [b for b in bodies if b.strip()]
        r1, r2, r3 = (hit_rate(bodies, IMPERATIVE), hit_rate(bodies, META),
                      hit_rate(bodies, EXPLICIT))
        ln = sorted(len(b) for b in bodies)[len(bodies) // 2] if bodies else 0
        stats[cls] = (len(rs), r1, r2, r3, ln)
        print(f"  {cls:<30} {len(rs):>5} {r1:>7.1%} {r2:>9.1%} {r3:>10.1%} {ln:>10}")

    print("\n★判读：")
    clean = [c for c in a.classes if "clean" in c]
    inj = [c for c in a.classes if "inject" in c]
    if clean and inj:
        cr = sum(stats[c][1] for c in clean if c in stats) / max(len([c for c in clean if c in stats]), 1)
        ir = sum(stats[c][1] for c in inj if c in stats) / max(len([c for c in inj if c in stats]), 1)
        print(f"  ①祈使率：干净侧 {cr:.1%}  vs 注入侧 {ir:.1%}  "
              f"差 {ir-cr:+.1%}")
        cr3 = sum(stats[c][3] for c in clean if c in stats) / max(len([c for c in clean if c in stats]), 1)
        ir3 = sum(stats[c][3] for c in inj if c in stats) / max(len([c for c in inj if c in stats]), 1)
        print(f"  ③显式自陈率：干净侧 {cr3:.1%}  vs 注入侧 {ir3:.1%}  "
              f"差 {ir3-cr3:+.1%}")
        print("  ⇒ 若干净侧①高 ⇒ 捷径存在 ⇒ **A 必要** ✓")
        print("  ⇒ 若注入侧③远高于干净侧 ⇒ 判别靠风格 ⇒ **B 必要** ✓")

    if a.show:
        for cls in a.classes:
            rs = (by.get(cls) or [])[:a.show]
            for r in rs:
                body = carrier_of(next((c.get("value") for c in (r.get("conversations") or [])
                                        if c.get("from") == "human"), ""))
                print(f"\n--- {cls} / {r.get('id')} ---\n{body[:500]}")
    print("\nCLEAN-VS-INJECT= DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
