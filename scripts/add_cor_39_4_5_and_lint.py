# -*- coding: utf-8 -*-
r"""① 落 docs/01 推论 39.4 / 39.5（自我更正后的两条方法论）
   ② 建一个**嵌套引号 lint** —— 本会话我已**连犯三次** ✗，必须机械拦住 ✓。

## 我自己反复犯的错（三次）

```python
print("    则"契约只是被截断"的论证被**证伪** ✗")   # ✗ SyntaxError
```
中文引号 `"` 与 Python 字符串定界符 `"` 混用 ✗。
三次都靠 `py_compile` 抓到 ✓，但每次都要**多跑一轮** ✓ ⇒ 值得机械化 ✓。

**★ 规则**：`print("...")` 这类**双引号定界的字符串里不得出现裸的 `"`** ✓；
中文引用一律用 `『』` 或 `「」` ✓。

## 推论 39.4 / 39.5（来自本轮真实的自我更正）

**39.4**：发现**基线**在正确口径下的读数与旧读数显著不同时，
**不得据此直接判定"原比较无效"** ✗ —— 那只说明**基线那一侧**不可信 ✓。
判定比较是否有效，必须**把双方都用正确口径重测** ✓✓。

**39.5**：先算**异常的总量**，再看**候选解释能覆盖多少** ✓。
本例缺 109 个 `VERDICT`，而"截断"最多解释 **32** 个 ✓
⇒ **"只是被截断"当场出局** ✓✓。**不要凭一处读数就宣布机制 ✓；要拿机制去配平总量 ✓。**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

ADD = """
> **推论 39.4（证伪比较必须测两侧）**：当发现**基线**在正确口径下的读数与旧读数
> 显著不同时，**不得据此直接判定"原比较无效"** ✗ ——
> 那只说明**基线那一侧**不可信 ✓。
> **判定比较是否有效，必须把**比较的双方**都用正确口径重测** ✓✓。
>
> **推论 39.5（拿机制去配平总量，而不是凭一处读数宣布机制）**：
> 先算**异常的总量**，再看**候选解释能覆盖多少** ✓。
> 若候选解释只能覆盖其中一部分，它**当场出局** ✗，无需再争论 ✓。
>
> **来历（2026-10-06 第 18 轮，我自己的错）**：
> 我看到起点在 512 下是 **166/168** ✓（96 下 70/168 ✗），
> 就用"奥卡姆剃刀"断言"**契约从未被摧毁，只是被截断了**"✗，
> 并据此把 M3 的裁定**挂起** ⏳ —— **那是过度外推** ✗
> （**只测了基线，没测 M3 自己** ✓）。
>
> 把 m3-dpo 也在 512 下重测后：
>
> | 512 口径 | 有 `VERDICT` | 保留率 | 截断缺 | **真实缺** | **真实缺失率** |
> |---|---|---|---|---|---|
> | 起点 | 251/258 | **97.3%** ✓ | 3 | **4** | **1.6%** ✓ |
> | `m3-dpo` | 142/258 | **55.0%** ✗ | 32 | **84** | **32.6%** ✗✗ |
>
> 缺 **109** 个，截断最多解释 **32** 个 ⇒ **39.5 当场判"只是被截断"出局** ✓✓
> ⇒ **契约退化是真实的、与口径无关** ✗ ⇒ **M3 裁定恢复为 FAIL**（方向不变、证据转干净 ✓）。
"""

QUOTE_LINT = '''# -*- coding: utf-8 -*-
r"""lint：双引号定界的字符串里不得出现裸的 `"`（中文引用请用 『』/「」）。

★来历：本会话我**连犯三次** —— `print("...则"契约只是被截断"的论证...")` ✗。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"J:\\Projects\\llm_for_sec")
# 双引号定界的字符串，里面又出现一个裸的 ASCII 双引号 ⇒ 可疑
PAT = re.compile(r'"[^"\\n]*"[^"\\n,)*\\]:]*"')


def main() -> int:
    bad = []
    for p in sorted((ROOT / "scripts").glob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('r"""') or s.startswith('"""'):
                continue
            # 只看 print( / f-string 里的可疑形态
            if "print(" not in line and 'f"' not in line and "f'" not in line:
                continue
            if PAT.search(line):
                bad.append(f"{p.name}:{i}: {s[:90]}")
    if bad:
        print("NESTED-QUOTE-LINT=FAIL")
        for b in bad:
            print(f"  ★ {b}")
        return 1
    print(f"NESTED-QUOTE-LINT=PASS（检查 {len(list((ROOT / 'scripts').glob('*.py')))} 个脚本，0 处可疑）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main() -> int:
    t = DOC.read_text(encoding="utf-8")
    if "推论 39.4" in t:
        print("推论 39.4/39.5 已存在（幂等）")
    else:
        DOC.write_text(t.rstrip("\n") + "\n" + ADD, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    ok_doc = ("推论 39.4" in back and "推论 39.5" in back
              and not any(x in back for x in ("\ufffd", "锟斤拷")))
    print(f"DOCS-COR39.4-5={'PASS' if ok_doc else 'FAIL'}  docs={len(back.splitlines())} 行")

    lint = ROOT / "scripts" / "lint_nested_quotes.py"
    if lint.exists():
        print("lint 已存在（幂等）")
    else:
        lint.write_text(QUOTE_LINT, encoding="utf-8")
        print(f"  已建 {lint.name}")
    return 0 if ok_doc else 1


if __name__ == "__main__":
    sys.exit(main())
