# -*- coding: utf-8 -*-
r"""规整 docs/01 的规则章节：把 §11.40 移到 §11.39 之后，并修标题层级。

## 修什么

1. **§11.40（规则 41）位置孤立** ✗ —— 我插在 §12 之前（L1074），
   而 §11.26–§11.39 全部在 §12 **之后** ⇒ 移到末尾与它们相邻 ✓。
2. **`## 11.39 规则 40` 用的是二级标题** ✗ —— 同级规则都是 `###` ⇒ 改 `###` ✓。
3. **★ 不做**大重排** ✗**：§11.26–§11.39 整体位于 §12 之后是既成事实 ✓，
   本次**只**消除我新引入的不一致 ✓（改动最小化 ✓，留痕 ✓）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

START = "### 11.40 规则 41"
END = "## 12. 未决问题"
BAD_H = "## 11.39 规则 40"
GOOD_H = "### 11.39 规则 40"


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    orig_len = len(src.splitlines())

    # ① 修正标题层级
    hfix = 0
    if BAD_H in src:
        src = src.replace(BAD_H, GOOD_H, 1)
        hfix = 1

    # ② 抽出 §11.40 块
    i = src.find(START)
    j = src.find(END)
    moved = 0
    if i >= 0 and j > i:
        block = src[i:j].rstrip() + "\n"
        src = src[:i] + src[j:]
        if not src.endswith("\n"):
            src += "\n"
        src = src.rstrip() + "\n\n" + block
        moved = 1

    DOC.write_text(src, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")

    import re
    heads = [(m.start(), m.group(0))
             for m in re.finditer(r"^#{2,3} 1?1?\.?\d+(?:\.\d+)?[^\n]*", back, re.M)]
    order = [h for _, h in heads if "11." in h or "## 12" in h]
    # 定位 §11.40 与 §11.39 的先后
    p40 = back.find(START)
    p39 = back.find(GOOD_H)
    p12 = back.find(END)
    ok = (p40 > p39 > 0 and p12 > 0 and BAD_H not in back)
    print(f"  docs/01 行数 {orig_len} → {len(back.splitlines())}")
    print(f"  标题层级修正 = {hfix}   §11.40 位移 = {moved}")
    print(f"  §11.39 位置 = {p39}   §11.40 位置 = {p40}   §12 位置 = {p12}")
    print(f"  §11.40 在 §11.39 之后 = {p40 > p39}")
    print(f"  旧二级标题已消除 = {BAD_H not in back}")
    print(f"DOCS-RULE41-ORDER={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
