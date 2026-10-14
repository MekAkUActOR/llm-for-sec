# -*- coding: utf-8 -*-
r"""第 18 轮：补 docs/01 推论 39.3 —— **不得在测量中途更换仪器**。

★来历：我发现 `topup_verdict.py` 把 MUST-B 门限硬编码为 `63/168` ✗
（那是 96 口径的锚点算出来的 ✓），本想立刻改成"起点水位的 90%" ✓。
**但我没有改** ✓ —— 因为 `recaliber_mnt.ps1` 是**每个 tag 跑完后**才调用它 ✓，
中途改会让**先跑的 soup-a050** 与**后跑的 m3-dpo** 套用不同的判定逻辑 ✗✗，
而这两者正要**互相比较** ✓ ⇒ 比较就失去意义 ✗。

**⇒ 让跑批以同一套逻辑跑完** ✓（原始计数完全有效 ✓），
**判定在跑完后离线重锚定** ✓（`scripts/reanchor_mustb_threshold.py` ✓）。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

ADD = """
> **推论 39.3（不得在测量中途更换仪器）**：一次跑批内的**全部读数**必须由
> **同一份代码、同一套判据、同一档口径**产生 ✓。
> 若在一次跑批进行中发现判据/仪器有缺陷，**不得就地修改** ✗ ——
> 因为批内先跑的产物会用旧逻辑、后跑的用新逻辑，
> 而它们正要互相比对 ⇒ **比较失去意义** ✗✗。
>
> **正确处置**：让本批以**原逻辑跑完** ✓（**原始计数仍然有效** ✓，
> 判定可以事后重算 ✓）⇒ **离线按正确判据重算判定** ✓，
> 并把"判据已更正"显式标注在产物上 ✓。

**来历（2026-10-06 第 18 轮）**：我发现 `topup_verdict.py` 把 MUST-B 门限
**硬编码**为 `63/168` ✗（该值由 **96 口径**的起点水位 70 算出 ✓），
而预注册的**规则**其实是"**起点水位的 90%**" ✓。
512 口径下同一条规则给出 **150/168** ✓ —— **相差 87 条**，足以翻转结论 ✗✓。

**我当时正有一个跑批在途** ✓（`recaliber_mnt.ps1` 逐个 tag 调用该脚本 ✓），
**故没有就地修改** ✗ —— 而是让它跑完、**离线重锚定** ✓。
"""


def main() -> int:
    t = DOC.read_text(encoding="utf-8")
    if "推论 39.3" in t:
        print("推论 39.3 已存在（幂等）")
    else:
        DOC.write_text(t.rstrip("\n") + "\n" + ADD, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    ok = ("推论 39.3" in back and "不得在测量中途更换仪器" in back
          and not any(x in back for x in ("\ufffd", "锟斤拷")))
    print(f"DOCS-COR39.3={'PASS' if ok else 'FAIL'}  docs={len(back.splitlines())} 行")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
