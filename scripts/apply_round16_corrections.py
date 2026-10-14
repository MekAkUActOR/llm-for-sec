# -*- coding: utf-8 -*-
"""第 16 轮的两处 docs/01 更正：

A. **更正推论 36.4**：原文说"修复方向是把目标压进预算" ✗。
   第 16 轮的 token 实测表明正确方向是**把预算对齐到数据分布**（预算 512），
   因为 SFT 长度分布是**刻意生成的设计意图**，而 96 只是评测脚本的 CLI 默认值。
   （数据侧仍有真缺陷，但那是 `carrier_inject_hollow` 的**语义**，不是长度。）

B. **新增 §11.36 规则 37**：偏好数据（DPO/偏好对）发射前，必须
   **逐 dpo_class** 报告 token 长度的 (a) chosen/rejected 中位与比、
   (b) chosen 更长比例；任一类比值 >1.2 且更长比例 >80% ⇒ 该类必须长度匹配。
   **字符口径不得用于此项判定**（本案字符↔token 比在同一批数据里漂移 2 倍）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

OLD_364 = """**推论 36.4（真根因：长度）**：当 prompt 强制某尾部行为（契约行）时，
**目标长度超出部署预算 = 该行为必然在部署时丢失**。
本项目的实测：部署预算 **450 字符**（`max_new_tokens=96`），而
`t2_mechanism` 目标中位 **1,035**（2.3×）、`doc_structure` **697**（1.55×）✗。
**⇒ 修复方向是"把目标压进预算"，而不是"加负样本"** ✓。"""

NEW_364 = """**推论 36.4（真根因：长度；★2026-10-06 二次更正）**：当 prompt 强制某尾部行为
（契约行）时，**目标长度超出部署预算 = 该行为必然在部署时丢失** ✓。

**★但"往哪边对齐"要说清**：原版本条写"修复方向是把目标压进预算" ✗ ——
token 实测后更正为 **把预算对齐到数据分布**：

- SFT 三族目标长度（token）：`t2_mechanism` p50=**380**/max=576、
  `doc_structure` p50=228/max=309、`t9_phish_expand` p50=146/max=276。
- 部署预算 **96** 下的覆盖率：**0.0% / 0.0% / 35.0%** ✗✗
  ⇒ 历史门禁读数全部产自"训练目标**一条都装不下**"的预算。
- **512** 下：**97.2% / 100% / 100%** ✓；DPO chosen（p50=67/max=987）在 512 下 **100%** ✓。

**为什么是"改预算"而不是"压数据"**：SFT 的长度分布由生成器**刻意定义**
（粒度带 + "长散文 + 尾部裁决"结构），是**设计意图**；而 96 只是
`scripts/baseline_eval.py:73` 的一个 **CLI 默认值**，从未与数据对齐过 ✗。
**⇒ 对齐方向是把预算提到数据分布内。**

**★ 但"改预算"不能解决全部问题**：偏好数据侧另有**长度混杂**缺陷（见规则 37），
以及 `carrier_inject_hollow` 的**语义**缺陷——二者都必须改**数据**。
**长度不是唯一的长度问题；"改预算"也不是万能的。**"""

BLOCK_37 = """
### §11.36 规则 37（偏好数据发射前必须逐类报告**token**长度；字符口径禁用）

**规则 37**：任何偏好数据（DPO / 偏好对 / 任何 chosen-rejected 对）在发射前，
**必须逐 `dpo_class` 报告**：

1. `chosen` 与 `rejected` 的 **token** 长度中位（及 p90/max）；
2. 两者中位**比值**；
3. **chosen 更长的比例**。

**判据**：任一类同时满足「中位比 **>1.2**」且「chosen 更长比例 **>80%**」
⇒ 该类的偏好梯度**主要来自长度而非内容** ⇒ **必须长度匹配后才可入训** ✗。

**推论 37.1（字符口径禁用）**：本项判定**不得**使用字符数。
实测同一批数据里字符↔token 比漂移 **2 倍**（302 字符/158 token = 1.9；
770 字符/203 token = 3.8）⇒ 字符口径会给出**方向都可能相反**的结论 ✗。
（与规则 36 的 (c) 项合读：凡"长度/预算比"一律用 token。）

**来历（2026-10-06）**：`scripts/measure_dpo_tokens.py` 对
`data/lf/dpo_m3_final.jsonl`（28,842 对）逐类实测：

| dpo_class | n | chosen中位 | rej中位 | 比 | chosen更长 | 判定 |
|---|---|---|---|---|---|---|
| `policy` | 14,688 | 66 | 66 | 1.00 | 47.4% | 干净 |
| `reserve` | 5,710 | 120 | 121 | 0.99 | 46.7% | 干净 |
| `carrier_inject_obedient` | 2,360 | **210** | 51 | **4.12** | **100.0%** | ★混杂 |
| `carrier_inject_hollow` | 2,320 | **210** | 43 | **4.88** | **100.0%** | ★混杂 |
| `bt330_refusal` | 1,904 | 78 | 110 | 0.71 | 21.5% | 干净 |
| `carrier_clean_overrefusal` | 1,320 | 160 | 110 | **1.45** | **100.0%** | ★混杂 |
| `refusal_quality` | 300 | 57 | 45 | **1.27** | 98.7% | ★混杂 |
| `calibration` | 240 | 71 | 45 | **1.58** | **100.0%** | ★混杂 |

**⇒ 5 类 / 6,540 对（22.7%）触发**，且**全部是行为关键类** ✗ ——
其中 `carrier_inject_obedient` + `carrier_inject_hollow` 共 **4,680 对**
正是"教模型拒绝被注入载体"的类，其梯度**几乎纯粹来自"写得更长"** ✗✗。

**⇒ 这就是 M3 契约崩塌（70/168 → 20/168）的机制**：4,680 对在教
"被注入时要写长报告"，而部署预算装不下长报告 ⇒ 模型学会"长"，
代价是尾部契约行被截断。

**推论 37.2（`carrier_inject_hollow` 的语义缺陷）**：该类当时的 `rejected` 是
**简短且格式正确**的拒绝（含合法 VERDICT）⇒ 这一对实际教的是"**短 = 坏**"，
而不是"**空洞 = 坏**" ✗✗。修复须改**语义**：rejected 应是
"空洞/敷衍"的拒绝，且**长度与 chosen 相当**。
（与长度匹配是**两件事**，必须都做。）
"""


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    checks = {}

    # --- A. 更正推论 36.4 ---
    if OLD_364 in src:
        src = src.replace(OLD_364, NEW_364)
        checks["36.4 已更正"] = True
    elif "二次更正" in src:
        checks["36.4 已更正"] = True      # 幂等
    else:
        checks["36.4 已更正"] = False

    # --- B. 追加规则 37 ---
    marker = "### §11.36 规则 37"
    if marker in src:
        checks["规则 37 已落"] = True
    else:
        src = src.rstrip("\n") + "\n" + BLOCK_37
        checks["规则 37 已落"] = True

    DOC.write_text(src, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    checks["无乱码"] = not any(t in back for t in ("\ufffd", "锟斤拷"))
    checks["旧错句已消失"] = "修复方向是\"把目标压进预算\"" not in back
    ok = all(checks.values())
    print(f"DOCS-ROUND16-CORRECTION={'PASS' if ok else 'FAIL'} 行数={len(back.splitlines())}")
    for k, v in checks.items():
        print(f"    {'OK ' if v else '★NG'} {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
