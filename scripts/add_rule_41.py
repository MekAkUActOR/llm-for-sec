# -*- coding: utf-8 -*-
r"""把本轮的核心结论落成 **规则 41**（docs/01 §11.40）。

规则 41：**安全判别器的"词法化"是一种训练事故，且它只在**隐蔽样本**上暴露**
⇒ 评测必须**按显式度分档**，只看总体 ASR 会漏掉它 ✗✓。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"
MARK = "### 11.40 规则 41"

TEXT = """
### 11.40 规则 41 —— 安全判别器的「词法化」与**分档评测**

**规则 41**：**当一个安全判别器从"语义意图"退化成"表观词汇匹配"时，
总体 ASR 可能只显示中度恶化，而**隐蔽样本**上的 ASR 会显示灾难** ✗。
⇒ **任何安全评测都必须按样本的"显式度"分档报告** ✓，
只报总体数字会**系统性掩盖**这类事故 ✗✓。

**推论 41.1（分档口径）**：分档键必须是**载体正文中是否存在自称性词汇**
（指令/裁决/说明/备注/政策/条款/policy/§… ✓），
以及**是否存在把该文本宣示为对读者有效的措辞** ✓。
**不得**按长度分档（实测证明长度平坦 ✗，见推论 41.3）。

**推论 41.2（隐蔽档必须与总体并列报出）**：
若 **隐蔽档 ASR ≥ 总体 ASR 的 1.5 倍** ⇒ 判为**词法化事故** ✗✓，
**即使总体 ASR 仍在容差内** ✗。

**推论 41.3（长度与显著性先排除掉）**：
在归因"隐蔽档为何失败"之前，必须先排除：
①**载体长度**（按长度分箱，若 ASR 平坦 ⇒ 出局 ✓）、
②**动作偏好**（统计训练数据在动作轴上的净方向 ✓，若与观测相反 ⇒ 出局 ✓）、
③**框架漂移**（比较训练/测试的自称词汇分布 ✓，若差异 <10pp ⇒ 出局 ✓）。
**★ 本轮三条全部被实测排除** ✓（`reports/m3-asr-mechanism.md` §2）
—— **排除替代解释本身就是证据** ✓。

**推论 41.4（根因在数据构型，不在长度）**：
**★ 佐证**：起点（SFT 产物）在隐蔽档 **5.1%** ✓ 与带词汇档 **4.3%** ✓ **一样好**
⇒ **隐蔽注入并不天然更难** ✗ ⇒ **任务可解** ✓
⇒ 缺口是 **DPO 训出来的** ✗✓ ⇒ **修法是补隐蔽正样本与成对硬负样本** ✓，
**不是**长度匹配 ✗。

**推论 41.5（发射前的对称性检查）**：
构造隐蔽注入正样本时，**干净侧的元文本必须**同样使用**那些词汇** ✓
（由**上下文**表明其正当性 ✓），否则模型只会换一条新捷径 ✗✓。
**必须**做**同句、不同上下文**的成对硬负样本 ✓ —— 只差语义、不差词面 ✓✓。
"""


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    if MARK in src:
        print("  规则 41 已存在（幂等）")
        print("DOCS-RULE41=PASS")
        return 0
    anchor = "\n## 12"
    idx = src.find(anchor)
    if idx < 0:
        # 退回到文件末尾追加
        new = src.rstrip() + "\n" + TEXT
    else:
        new = src[:idx] + TEXT + src[idx:]
    DOC.write_text(new, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    n = len(back.splitlines())
    ok = MARK in back and "推论 41.5" in back and "推论 41.1" in back
    print(f"  docs/01 行数 = {n}")
    print(f"  含规则 41 = {MARK in back}  含 41.1/41.5 = "
          f"{'推论 41.1' in back}/{'推论 41.5' in back}")
    print(f"DOCS-RULE41={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
