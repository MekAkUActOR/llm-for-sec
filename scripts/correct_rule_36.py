# -*- coding: utf-8 -*-
"""把 docs/01 的 §11.35 规则 36 替换为**更正版**（2026-10-06 晚）。

原因：原规则 36 把"目标 100% 含 VERDICT"直接判为共模缺陷，并给出
"补不含契约的负样本"的处方 ✗。但 `scripts/check_prompt_contract_mandate.py`
证明：**三族的 prompt 侧 100% 要求"以 VERDICT 行结尾"** ⇒ 目标 100% 合规是
**正确行为**，不是缺陷。真根因是**目标长度（中位 697–1,035）远超部署预算 450** ✗。
若照原处方加负样本，会教模型**违反 prompt 的格式指令**，比现状更糟 ✗✗。
"""
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

HEAD_RE = re.compile(r"^### §11\.35 规则 36", re.M)

BLOCK = """### §11.35 规则 36（**更正版**：判"共模"必须先判"是否 prompt 强制"；长度 vs 部署预算）

> **★本节于 2026-10-06 晚更正。** 原版把"目标 100% 含契约标记"直接判为
> **共模缺陷**，并给出"补不含契约的负样本"的处方 ✗。
> `scripts/check_prompt_contract_mandate.py` 证明该诊断**是错的**：
> S1 三族的 **prompt 侧 100.00% 要求"以 VERDICT 行结尾"**，
> 目标 100.00% 合规 ⇒ **那是正确行为，不是缺陷**。
> **按原处方加负样本，会教模型违反 prompt 的格式指令，比现状更糟** ✗✗。
> 详见 `reports/rootcause-corrected-length-not-contract.md`。

**规则 36**：判"某行为是共模的、因而无判别梯度"时，
**必须先判定该行为是否被 prompt 强制**：

- **prompt 强制**（例："输出必须以 VERDICT 行结尾"）：
  目标 **100% 合规是正确的** ✓。此时**唯一**的结构风险是**长度**——
  目标若超出部署生成预算，该行为会在截断中被丢掉 ✗。
- **prompt 未强制**：目标却 100% 含该行为 ⇒ 才是**共模缺陷** ✗。

**只统计"标记出现率"而不看 prompt 侧，会把合规行为误判为缺陷** ✗。

**推论 36.3（结构审计的三件套）**：任何结构审计**必须同时报告**
**(a) prompt 侧要求率、(b) 目标侧合规率、(c) 目标长度与部署预算之比**。
三者缺一**不得**下"共模缺陷"结论。

**推论 36.4（真根因：长度）**：当 prompt 强制某尾部行为（契约行）时，
**目标长度超出部署预算 = 该行为必然在部署时丢失**。
本项目的实测：部署预算 **450 字符**（`max_new_tokens=96`），而
`t2_mechanism` 目标中位 **1,035**（2.3×）、`doc_structure` **697**（1.55×）✗。
**⇒ 修复方向是"把目标压进预算"，而不是"加负样本"** ✓。

**推论 36.5（审计对象必须是真正被消费的文件）**：结构审计的 `--data`
必须指向**训练配置里真实引用的文件**，**不得**指向同名或同族的**评测集**。
本条的来历：2026-10-06 我拿 `data/heldout/v0.5-topup-families/*.jsonl`
（27–30 条的**评测集**）当入训数据审 ✗，而真正的入训文件是
`data/sft/m2.5-staging/*.jsonl`（1,200–1,500 行）——
**审错对象会导致机制误判**（本次正是如此）。

**推论 36.6（"族改善"必须与结构审计联读）**：`eval_family_indistribution.py` 的
eval_loss 读数**不得单独**作为"族能力改善"的证据。在与训练目标同分布的数据上，
**eval_loss 下降可能只是"更像那个有缺陷的目标"**（可能是过长、可能是共模）。
⇒ 与规则 34 同源：**都是"指标在错误的量上改善"**。

**推论 36.7（交付 ≠ 可入训）**：一份数据"已交付 N 行"**不等于**"可入训"。
入训前必须过结构审计（prompt 要求率 / 合规率 / 长度-预算比）。
docs/01 L260 记的 A5 欠账（"T2 机制解释族已交付 1,200 行但未入训"）
的**结清条件是"压进长度预算"，不是"补足行数"**。

**★ 连带发现（2026-10-06）**：M3 起点 `soup-a050` 的契约保留率**本就只有
70/168 = 41.7%** ⇒ **契约问题早于 M3**；M3 把它打到 20/168 = 11.9%。
且 MUST-B 门限 **63/168 = 37.5%** 距起点水位只有 **7 条（4.2pp）余量**，
**违反推论 33.1（门限必须登记与起点的余量）**——
该门这次能抓到崩塌只因幅度大（−50 条），**不是因为它灵敏** ✗。
"""


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    m = HEAD_RE.search(src)
    if not m:
        print("RULE36-CORRECT=FAIL（找不到 §11.35 标题）")
        return 1
    new = src[:m.start()] + BLOCK
    DOC.write_text(new, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    checks = {
        "更正版": "更正版" in back,
        "三件套": "推论 36.3" in back,
        "长度根因": "推论 36.4" in back,
        "审计对象": "推论 36.5" in back,
        "无旧错句": "被模仿的对象本身是共模的" not in back,
        "无乱码": not any(t in back for t in ("\ufffd", "锟斤拷")),
    }
    ok = all(checks.values())
    print(f"RULE36-CORRECT={'PASS' if ok else 'FAIL'} 行数={len(back.splitlines())}")
    for k, v in checks.items():
        print(f"    {'OK ' if v else '★NG'} {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
