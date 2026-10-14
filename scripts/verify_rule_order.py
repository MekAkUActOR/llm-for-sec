# -*- coding: utf-8 -*-
r"""★复核 docs/01 的规则章节顺序 —— 用**行首锚定**，不用子串包含 ✗。

## 教训（本会话第五次同型）

`"### 11.39 规则 40"` **包含** `"## 11.39 规则 40"` ✗
⇒ `BAD_H in back` 永远为 True ⇒ 检查永远 FAIL ✗。
**凡"某字符串是否作为独立标题存在"，必须锚定行首** ✓。

**★ 更一般地：幂等键/校验串必须是**结构性的**（行首、独立标题、表情表头 ✓），
**绝不能是**散文子串** ✗ —— 子串检查还会被自己的前缀、以及自己的纠正性引用误伤 ✓。**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

#: 只匹配**恰好二级**的标题（行首 ## + 空格，后面不能再跟 #）
BAD_H2 = re.compile(r"^## 11\.39", re.M)
#: 恰好三级的标题
H3_39 = re.compile(r"^### 11\.39 规则 40", re.M)
H3_40 = re.compile(r"^### 11\.40 规则 41", re.M)
SEC12 = re.compile(r"^## 12\.", re.M)


def main() -> int:
    s = DOC.read_text(encoding="utf-8")
    bad = BAD_H2.search(s)
    p39 = H3_39.search(s)
    p40 = H3_40.search(s)
    p12 = SEC12.search(s)
    print(f"  docs/01 行数 = {len(s.splitlines())}")
    print(f"  恰好二级的『## 11.39』残留 = {bool(bad)}"
          + (f"（L{s[:bad.start()].count(chr(10))+1}）" if bad else " ✓"))
    print(f"  ### 11.39 规则 40 位置 = {p39.start() if p39 else None}")
    print(f"  ### 11.40 规则 41 位置 = {p40.start() if p40 else None}")
    print(f"  ##  12           位置 = {p12.start() if p12 else None}")
    ok = (bad is None and p39 and p40 and p12
          and p40.start() > p39.start())
    print(f"\n  规则 39 → 40 → 41 相邻且有序 = "
          f"{bool(p40 and p39 and p40.start() > p39.start())}")
    print(f"DOCS-RULE41-ORDER={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
