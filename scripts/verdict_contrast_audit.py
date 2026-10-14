# -*- coding: utf-8 -*-
r"""★★★★★ 回顾审计（第 41 轮 ✓，纯 CPU ✓）：训练混料里 `VERDICT:` 标记的**对比度**。

## 为什么这是决定性问题
第 37 轮已定位：M4-full 丢了 `VERDICT:` 前缀标记（62/168 ✗）但保住了安全行为 ✓。
机制假说：**绝对对数概率塌缩** ✗ ⇒ 最脆弱的 token（格式标记）先丢 ✗。

**★ 但还有一个数据级的问题从未被问过**：
**训练对里 chosen 和 rejected 是否都带 `VERDICT:`？**
- **若两侧都带** ✓ ⇒ 标记在训练中**零对比度** ⇒ DPO 对标记**没有任何梯度信号** ⇒
  模型可以在总体似然下降时**自由丢弃它** ✗✓ —— 这将是机制的数据级确认 ✓✓
- **若 rejected 常缺标记** ✓ ⇒ 标记有对比度 ⇒ 理论上应被强化 ⇒ 丢失另有原因 ✗

## 已核实的 schema（本会话第 30 轮 dump 过 ✓，不猜 ✓）
顶层键 = ['chosen','conversations','dpo_class','id','lang','length_matched_from','pack','rejected','src_task']
chosen/rejected = {'from': 'gpt', 'value': <响应文本>}
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
SRC = R / "data" / "m4-run" / "dpo_m4_capfix.jsonl"
VRE = re.compile(r"VERDICT\s*:", re.I)
FIELD = re.compile(r'"([a-z_]+)"\s*:\s*("([^"]*)"|(-?[\d.]+)|(\[[^\]]*\]))')


def parse_verdict(t: str) -> dict:
    m = re.search(r"VERDICT\s*:\s*(\{.*\})", t or "", re.S)
    if not m:
        return {}
    s = m.group(1)
    k = s.rfind("}")
    s = s[:k + 1] if k >= 0 else s
    try:
        return json.loads(s)
    except Exception:
        out = {}
        for mm in FIELD.finditer(s):
            out[mm.group(1)] = (mm.group(3) if mm.group(3) is not None
                                else (mm.group(4) if mm.group(4) is not None
                                      else mm.group(5)))
        return out


def classify(row: dict) -> str:
    ct = (row.get("chosen") or {}).get("value") or ""
    rt = (row.get("rejected") or {}).get("value") or ""
    cv, rv = parse_verdict(ct), parse_verdict(rt)
    ca, ra = cv.get("action"), rv.get("action")
    if not ca or ca != ra:
        return "S"
    diffs = any(str(cv.get(x)) != str(rv.get(x))
                for x in ("verdict", "findings", "confidence"))
    return "C" if diffs else "F"


def main() -> int:
    if not SRC.exists():
        print(f"  ★缺 {SRC}")
        return 2
    # cell = (类, chosen有V, rejected有V)
    cells: Counter = Counter()
    cls_n: Counter = Counter()
    dpo_class_cells: Counter = Counter()
    n = 0
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            ct = (row.get("chosen") or {}).get("value") or ""
            rt = (row.get("rejected") or {}).get("value") or ""
            k = classify(row)
            cls_n[k] += 1
            cv, rv = bool(VRE.search(ct)), bool(VRE.search(rt))
            cells[(k, cv, rv)] += 1
            dpo_class_cells[(str(row.get("dpo_class")), cv, rv)] += 1

    print(f"=== ★`VERDICT:` 标记对比度审计（n={n:,} 对 ✓）===")
    print(f"\n  按 S/C/F 类 × (chosen 有V, rejected 有V)：")
    for k, name in (("S", "S 方向对"), ("C", "C 契约对"), ("F", "F 风格对")):
        tot = cls_n[k] or 1
        b = cells[(k, True, True)]
        only_c = cells[(k, True, False)]
        only_r = cells[(k, False, True)]
        neither = cells[(k, False, False)]
        print(f"  {name}（n={cls_n[k]:,}）:")
        print(f"    两侧都有 V ：{b:>6,}（{b/tot:>6.1%}）  ← ★标记零对比 ✓")
        print(f"    仅 chosen  ：{only_c:>6,}（{only_c/tot:>6.1%}）  ← ★标记有对比（正）")
        print(f"    仅 rejected：{only_r:>6,}（{only_r/tot:>6.1%}）  ← ★标记有对比（反）")
        print(f"    两侧都无  ：{neither:>6,}（{neither/tot:>6.1%}）")

    tb = sum(v for (k, c, r), v in cells.items() if c and r)
    to = sum(v for (k, c, r), v in cells.items() if c != r)
    tn = sum(v for (k, c, r), v in cells.items() if not c and not r)
    print(f"\n  ★全量汇总（n={n:,}）：")
    print(f"    两侧都有 V ：{tb:>6,}（{tb/n:>6.1%}）")
    print(f"    有对比（任一侧独有）：{to:>6,}（{to/n:>6.1%}）")
    print(f"    两侧都无 V ：{tn:>6,}（{tn/n:>6.1%}）")

    print(f"\n  ★按 dpo_class 的对比度（仅列有对比的类 ✓）：")
    any_contrast = False
    for (dc, c, r), v in sorted(dpo_class_cells.items()):
        if c != r:
            any_contrast = True
            print(f"    {dc:<28} 仅chosen={v:,}" if c else f"    {dc:<28} 仅rejected={v:,}")
    if not any_contrast:
        print(f"    ★★★ **没有任何一个 dpo_class 存在标记对比** ✗✗✓")

    print(f"\n★判读：")
    print(f"  · 全量标记对比率 = {to/n:.2%}")
    if to / n < 0.01:
        print(f"  · **<1%** ⇒ `VERDICT:` 在训练中**几乎零对比度** ✗✓")
        print(f"    ⇒ DPO 对标记**没有梯度信号** ⇒ 模型可在似然下降时自由丢弃它 ✓✓")
        print(f"    ⇒ **第 37 轮的机制假说在数据级得到确认** ✓✓✓")
    print("\nVERDICT-CONTRAST=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
