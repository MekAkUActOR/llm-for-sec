# -*- coding: utf-8 -*-
"""幂等追加 §11.35 / 规则 36 到 docs/01-engineering-definition.md。

规则 36 来历（2026-10-06）：审计 S1 三族（doc_structure / t2_mechanism / t9_phish）
发现它们与 M3 的 DPO 数据**结构同型**：
  A/C 类：三族**各 100% 含 VERDICT、负样本为 0** ⇒ 契约共模 ⇒ 学不到"何时不发"；
  B 类：doc_structure 中位 499、t2_mechanism 中位 569 > 部署预算 450 ⇒ 必被截断。
而 M3 的 family-indistribution 却显示 2/3 族"改善"（t2 −0.2521、doc −0.2158），
同一模型契约却崩塌（70→20）——⇒ **在共模族上，eval_loss 改善只证明模仿更像，
不证明能力更强**。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

MARKER = "### §11.35 规则 36"

BLOCK = """
### §11.35 规则 36（"族改善"必须与结构审计联读；交付 ≠ 可入训）

**规则 36**：`scripts/eval_family_indistribution.py` 的 eval_loss 读数
**不得单独作为"族能力改善"的证据**。任何"族改善"结论必须与该族的
**结构审计结果**（`scripts/audit_s1_families.py` 的 A/B/C 类）**联读**。
**在契约共模的族上，"改善"只证明模型模仿得更像，不证明能力更强或更安全。**

**推论 36.1（交付 ≠ 可入训）**：一份数据"已交付 N 行"**不等于**"可入训"。
入训前必须通过结构审计：**契约标记必须有对照（既有含、也有不含的样本）**，
且**目标长度必须落在部署预算内**。docs/01 L260 记的 A5 欠账
（"T2 机制解释族 S1 已交付 1,200 行但**未入训**"）正属此类——
本次审计给出了"为什么不可"的机械证据，故**该欠账的结清条件是"修好结构"而非"补足行数"**。

**来历（2026-10-06）**：审计 `data/heldout/v0.5-topup-families/` 三族：
- **A/C 类**：`doc_structure` 27 条、`t2_mechanism` 28 条、`t9_phish` 30 条，
  **三族的契约标记出现率均为 100.0%，不含标记的负样本均为 0**
  ⇒ 契约是**共模行为**，SFT/DPO 都产生不了判别梯度。
  这与 M3 的 DPO 数据 D1 缺陷（两侧 100% 都含 `VERDICT`）**同一机制**——
  我此前只审了 DPO 侧，**漏了 SFT 侧**。
- **B 类**：`doc_structure` 长度中位 **499**、`t2_mechanism` 中位 **569**
  （最大 1214），部署预算 = **450 字符**（`max_new_tokens=96`）
  ⇒ **即使完美模仿也会在契约行出现前被截断**。与 M3 DPO 的 D3 同型。
- **★ 交叉印证**：同一模型的 `family-indistribution` 显示 2/3 族**改善**
  （`t2_mechanism` −0.2521、`doc_structure` −0.2158），而契约**崩塌**（70/168 → 20/168）。
  **不矛盾**：三族的 targets 本就是"长散文 + 固定尾部裁决"，
  **eval_loss 下降 = 更好地模仿了这个有缺陷的结构**。

**与规则 34 同源**：两条都是"**指标在错误的量上改善**"——
规则 34 是分母（覆盖率）塌了，规则 36 是**被模仿的对象本身是共模的**。

**推论 36.2（同批修）**：SFT 侧与 DPO 侧的判别轴修复**必须同批进行**。
只修一侧会让另一侧继续注入共模梯度，两侧互相抵消（docs/01 L452 已要求
三族"必须与契约回放同批混合"，本条把该要求**机械化为审计门**）。
"""


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    if MARKER in src:
        print("RULE36-APPEND=SKIP（已存在，幂等）")
        return 0
    new = src.rstrip("\n") + "\n" + BLOCK
    DOC.write_text(new, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    ok_marker = MARKER in back
    bad = [t for t in ("\ufffd", "锟斤拷") if t in back]
    print(f"RULE36-APPEND={'PASS' if ok_marker and not bad else 'FAIL'} "
          f"marker={ok_marker} mojibake={bad} 行数={len(back.splitlines())}")
    return 0 if ok_marker and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
