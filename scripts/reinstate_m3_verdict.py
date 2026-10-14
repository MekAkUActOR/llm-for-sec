# -*- coding: utf-8 -*-
r"""解除"挂起"，把 M3 的裁定**恢复为 FAIL** —— 但附上**正确口径**的证据。

## 时序（必须讲清楚，否则像是在"改口"✗）

1. **00:00 原裁决**：96 口径，MUST-B `70/168 → 20/168` ⇒ **FAIL** ✓
2. **第 18 轮前半**：发现 96 口径下**基线自己**只有 41.7%（余量 4.2pp）✗，
   且 96 口径下两模型响应中位都**恰好 96**（整批被切断 ✗）
   ⇒ 我判定"原比较被截断混杂污染" ✓ 并**挂起**裁定 ⏳
3. **第 18 轮后半（现在）**：把 **m3-dpo 也在 512 下重测** ✓：
   - 起点 **97.3%**（真实缺失仅 **1.6%** ✓）
   - `m3-dpo` **55.0%**（真实缺失 **32.6%** ✗✗）
   ⇒ **缺失 109 个 VERDICT，而截断最多只能解释 32 个** ✓
   ⇒ **"只是被截断"被证伪** ✗ ⇒ **契约退化是真实的** ✗

**⇒ 裁定恢复为 FAIL** ✓ —— **方向与原裁决相同 ✓，但证据第一次是干净的 ✓。**

**★ 同时**更正我前半段那句"契约从未被摧毁"** ✗**（见
`reports/round18-self-correction-caliber.md` ✓）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"

TARGETS = ("m3-final-verdict-20261006.md", "m3-verdict-mustb-fail.md",
           "m3-final-gate-picture.md", "m25-exit-verdict-m3dpo.md")
SUSPEND_MARK = "裁定挂起"
# ★校验标记必须与**横幅里真实出现的字符串**一致 ✗
#   （第一版我搜的是"512 口径复核：维持 FAIL" ✗，而横幅写的是"裁定维持 FAIL" ✓
#    ⇒ 4 份全报 ★NG，明明替换成功了 ✓。教训：校验串要**从横幅里取**，别另写一份 ✓）
FINAL_MARK = "裁定维持 FAIL"
# ★"旧横幅是否还在"要看它的**表头** ⏳⏳⏳ ✓，不能搜"裁定挂起" ✗ ——
#   因为**新横幅里合法地含有"裁定挂起"** ✓（那句解释了"我曾把裁定挂起" ✓）。
OLD_BANNER_HEAD = "⏳⏳⏳"

BANNER = """> # ✅✅✅ 512 部署口径复核完成：**裁定维持 FAIL** ✅✅✅
>
> **2026-10-06 第 18 轮**。本文原裁决（96 口径）的**方向是对的** ✓，
> 但它的**证据被截断混杂污染** ✗ —— 现已用**部署口径（512）**重测双方 ✓：
>
> | 512 口径 | 条目 | 有 `VERDICT` | 保留率 | tok 中位 | 截断缺 | **真实缺** | **真实缺失率** |
> |---|---|---|---|---|---|---|---|
> | 起点 `soup-a050` | 258 | 251 | **97.3%** ✓ | 148 | 3 | **4** | **1.6%** ✓ |
> | **`m3-dpo`** | 258 | 142 | **55.0%** ✗ | 179 | 32 | **84** | **32.6%** ✗✗ |
>
> **★"真实缺"= 生成已结束（`stop`）却仍无 `VERDICT`** ⇒ **契约退化** ✗
> （与"被预算切掉"的截断缺严格区分 ✓）。
>
> **⇒ `m3-dpo` 缺 109 个 `VERDICT`，而截断最多只能解释 32 个** ✓
> ⇒ **"契约只是被截断"的假设当场出局** ✗ ⇒ **契约退化是真实的、与口径无关** ✗✓。
>
> **⇒ MUST-B 在正确口径下依然 FAIL** ✗（起点 97.3% → M3 55.0%；
> 且门限按预注册规则"起点水位的 90%"重锚定为 **150/168** ✓）。
>
> **★★ 与原裁决的关系**：**方向不变（FAIL）✓，理由更正（真实退化，非截断混杂）✓。**
> 原裁决是"对的结论 + 被污染的证据" ✓；本次是"对的结论 + 干净的证据" ✓。
>
> **★★ 第 18 轮前半段我曾据"基线 512 读数变好"把裁定挂起 ⏳ —— 那是**过度外推** ✗**：
> **只测了基线、没测 M3 自己** ✓。详见 `reports/round18-self-correction-caliber.md` ✓。
>
> 详见 `reports/caliber-defect-m3-adjudication.md` ·
> `reports/round18-self-correction-caliber.md` · 规则 39（docs/01 §11.38）。
>
> **★原文一字未改地保留在下方** ✓。

---

"""


def main() -> int:
    ok_all = True
    for name in TARGETS:
        p = R / name
        if not p.exists():
            print(f"  ★缺 {name}")
            ok_all = False
            continue
        t = p.read_text(encoding="utf-8")
        if FINAL_MARK in t:
            print(f"  OK  已恢复（幂等） {name}")
            continue
        # 用新横幅**替换**旧挂起横幅（旧横幅以 "> # ⏳⏳⏳" 起到 "---\n\n" 止）
        if SUSPEND_MARK in t:
            start = t.find("> # ⏳⏳⏳")
            end = t.find("\n---\n", start)
            if start != -1 and end != -1:
                t = t[:start] + BANNER.rstrip("\n") + t[end + 4:]
            else:
                t = BANNER + t
        else:
            t = BANNER + t
        p.write_text(t, encoding="utf-8")
        back = p.read_text(encoding="utf-8")
        good = (FINAL_MARK in back and OLD_BANNER_HEAD not in back
                and not any(c in back for c in ("\ufffd", "锟斤拷")))
        print(f"  {'OK ' if good else '★NG'} {name}  ({len(back.splitlines())} 行)")
        ok_all = ok_all and good

    pre = R / "m3-dpo-preregistration.md"
    if pre.exists():
        untouched = FINAL_MARK not in pre.read_text(encoding="utf-8")
        print(f"  {'OK ' if untouched else '★NG'} 预注册仍未被改动")
        ok_all = ok_all and untouched

    print(f"\nM3-VERDICT-REINSTATED={'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
