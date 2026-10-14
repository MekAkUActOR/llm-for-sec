# -*- coding: utf-8 -*-
r"""★★★ 给 `reports/m3-asr-mechanism.md` 加**更正横幅** ✓。

## 为什么必须加

该报告（本轮早期）断言机制是「**词法化**」✗ —— 但同轮后续的测量证明：
1. 我的"无自称词汇"档**实际是"英文注入"档** ✗（关键词表只有中文 ✓）；
2. 而 `language` 字段**不是载荷语言** ✗（86 条 `zh` 里 64 条载荷是英文 ✓）；
3. 用整段正文定语言也失效 ✗（168 条全判 `en` ✓）。

**⇒ 该报告的机制结论**已被本轮的规则 42 判为**不可采信** ✗✓。
**★ 更正必须是**增补式**的 ✓（保留原文 ✓、留痕 ✓、不覆盖历史 ✓）。**
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TGT = ROOT / "reports" / "m3-asr-mechanism.md"
MARK = "> ⚠️⚠️⚠️ **更正（第 20 轮同日，必读）**"

BANNER = """> ⚠️⚠️⚠️ **更正（第 20 轮同日，必读）**

**本报告第三节的「词法化」机制结论**不可采信** ✗，请勿引用** ✗。

**★ 同轮后续测量推翻了它的口径**：
1. 本报告用来分档的「**无自称词汇**」档 ✓，其关键词表**只有中文** ✗
   ⇒ 它实际捕获的是「**英文载荷**」✗，**不是**「隐蔽载荷」✗✓。
2. 改用 `language` 字段复算得 en 74.4% / zh 27.9% ✗ ——
   但该字段是**条目语言**、**不是载荷语言** ✗：
   86 条 `language="zh"` 里 **64 条的载荷其实是英文** ✗（实例：`gen-av-a3` ✓）。
3. 改用整段载体正文定语言 ✗ ⇒ **168 条全判 `en`** ✗
   （结构化 ASCII `[box] ftyp offset=0 …` 淹没了注入文本 ✓）。

**⇒ 依据规则 42（`docs/01 §11.41`）**：抽取未在两侧验证 ⇒ 其统计量不得作结论依据 ✗。

**★ 本报告中**仍然成立**的部分** ✓（这些独立于语言分档 ✓）：
- §1 的**两档 ASR 数字本身**是真实的读数 ✓（起点 4.3%/5.1% ✓、m3-dpo 30.4%/64.6% ✓），
  **只是分档键的命名错了** ✗（应读作"载荷为英文 / 含中文"✓，而非"隐蔽 / 带词汇"✗）。
- §2 排除的三个替代假说 ✓（框架漂移 / 长度显著性 / 动作偏好 ✓）**仍然成立** ✓。
- §6 的复核路径 ✓。

**★★ 当前对机制的正确表述**：**尚未确立** ✗ ——
四个候选（框架 ✗、长度 ✗、动作偏好 ✗、模板多样性 ✗）**全部被实测排除** ✓；
样本层面观察到「训练注入多声称**虚假权威** ✓、测试注入多要求**伪造裁决/隐瞒证据** ✗」✓，
**但按规则 42.4 只作线索** ✓（未分类比例 93.9% ✗）。
**详见 `reports/round20-report.md`** ✓。

---

"""


def main() -> int:
    s = TGT.read_text(encoding="utf-8")
    if MARK in s:
        print("  更正横幅已存在（幂等）")
        print("MECH-REPORT-CORRECTED=PASS")
        return 0
    TGT.write_text(BANNER + s, encoding="utf-8")
    back = TGT.read_text(encoding="utf-8")
    ok = (MARK in back and back.startswith(BANNER[:30])
          and "词法化" in back)
    print(f"  报告行数 = {len(back.splitlines())}")
    print(f"  更正横幅在文件开头 = {back.startswith(BANNER[:30])}")
    print(f"  原文保留 = {'词法化' in back}")
    print(f"  已声明不可采信 = {'不可采信' in back}")
    print(f"MECH-REPORT-CORRECTED={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
