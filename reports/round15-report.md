# 第 15 轮报告：根因第二次更正（长度）、token 预算实测、以及我自己的两个验证 bug

**时间**：2026-10-06 18:30–19:00。**状态**：512 口径重测跑批中（`pwsh-1990` 等待）。

---

## 一、★★★ 更正：契约共模**不是**缺陷，真根因是**长度**

### 1.1 我审错了文件

上一轮我用 `data/heldout/v0.5-topup-families/*.jsonl`（**27–30 条的评测集**）
当作"入训数据" ✗。**真正的入训文件是 `data/sft/m2.5-staging/*.jsonl`**
（`t2_mechanism` 1,200 行、`doc_structure` 1,200 行、`t9_phish_expand` 1,500 行）。

**复审真文件**（`scripts/audit_s1_training_files.py`）——**数字成立，机制不成立**：

| 族 | 行数 | 长度中位(字符) | 超预算 450 | 契约标记率 |
|---|---|---|---|---|
| `t2_mechanism` | 1,200 | **1,035** | 100.0% | 100.00% |
| `doc_structure` | 1,200 | **697** | 81.7% | 100.00% |
| `t9_phish_expand` | 1,500 | 394 | 41.6% | 100.00% |

### 1.2 决定性反证：prompt 侧本来就要求发契约

`scripts/check_prompt_contract_mandate.py`：

```
三族 prompt 侧要求发契约 = 100.00%，目标合规 = 100.00%
```

**⇒ 契约是 prompt 强制的**。目标 100% 合规是**正确行为** ✓，
不是"学不到何时该发" ✗。**我上一轮的处方（"补不含契约的负样本"）是有害的** ✗✗
——那会教模型**违反 prompt 的格式指令**，比现状更糟。

（T9 生成器自述的"负例 ≥30%"是**判断轴**的负例：干净站 vs 钓鱼站；
不是**契约轴**的负例。我把两根轴混为一谈了。）

### 1.3 更正后的规则 36（已落 `docs/01 §11.35`）

> 判"共模缺陷"**必须先判该行为是否被 prompt 强制**：
> - **prompt 强制** ⇒ 100% 合规是**正确** ✓，唯一的结构风险是**长度**（超出预算会在截断中丢失）；
> - **prompt 未强制** ⇒ 100% 含该行为才是**共模缺陷** ✗。
>
> **推论 36.3**：审计必须同时报 (a) prompt 要求率、(b) 目标合规率、(c) 长度/预算比。
> **推论 36.4**：真根因 = 目标长度超出部署预算。
> **推论 36.5**：审计对象必须是**训练配置真实引用的文件**，不得是同名/同族的**评测集**。

**已拆掉错误的门**：`scripts/audit_s1_families.py` → 弃用转发入口（备份在侧）；
runbook 步骤 2.0b 整段重写（命令、期望值、处方全改）；
`reports/s1-three-families-structural-audit.md` 顶部加**更正横幅**。
`verify_runbook_gates.py` 增加"旧引用必须零残留"检查 ⇒ `RUNBOOK-GATES=PASS` ✓

## 二、★★★ token 预算实测：96 下覆盖率是 **0.0%**

用真实 tokenizer 量（`scripts/measure_token_budgets.py`）——**此前所有讨论都用字符近似** ✗：

| 族 | p50 | p90 | max | 覆盖@96 | @256 | @512 |
|---|---|---|---|---|---|---|
| `t2_mechanism` | **380** | 469 | 576 | **0.0%** | **1.3%** | **97.2%** |
| `doc_structure` | 228 | 292 | 309 | **0.0%** | 70.0% | **100%** |
| `t9_phish_expand` | 146 | 221 | 276 | 35.0% | 98.3% | **100%** |

**⇒ 90% 覆盖率所需预算：`t2_mechanism` 512 / `doc_structure` 384 / `t9_phish_expand` 256。**

**★ 我因此推翻了自己半小时前的一个决定**：我按队列里的"96→256"直接发射了 256 ✗，
**没先量**——而 256 对 `t2_mechanism` 只覆盖 **1.3%** ✗✗。已停掉改跑 **512** ✓。

**★★ 字符↔token 比在同一批数据里就漂移 2 倍**（实测 302 字符/158 token = 1.9，
770 字符/203 token = 3.8）⇒ **用字符推断预算是不可靠的** ✓

## 三、★★★ 我自己的两个验证 bug（比上一条更重要）

### 3.1 **空洞通过**（vacuous pass）——规则 32 的活体演示

我的冒烟测试写的是：

```python
ok = True
for rec in records:      # ← 产物为空时循环不执行
    ok = ok and has_fields(rec)
print("PASS" if ok else "FAIL")   # ⇒ 空产物报 PASS ✗✗
```

**⇒ 我打印的 `SMOKE-FINISH-REASON=PASS` 一度是空洞的** ✗。
已加 `n_seen == 0 ⇒ FAIL`，并让 `dump_responses` 在写出 0 条时 **fail-closed** ✓
（`raise SystemExit("★写出 0 条记录 —— 拒绝产出空产物")`）。

**这正是 docs/01 §11.31 规则 32 说的「"没触发"不是观测结果」** ✓

### 3.2 **`dump_responses` 静默丢弃新字段**

我给 `baseline_eval.py` 的 `__call__` 加了 `finish_reason` / `new_tokens` /
`new_token_ids`，**但 `dump_responses()` 只写固定字段，把它们全丢了** ✗✗。
若不修，一次 60 分钟的 512 跑批会产出**无法派生预算曲线的废数据** ✗。
已改为**透传 response 的全部键** ✓ ⇒ 结构上杜绝静默丢字段。

### 3.3 连带：**模型目录名我凭记忆写错**

`checkpoints\qwen3-06b-soup-needlefix-a050` **不存在** ✗；
真实名是 **`soup-needlefix-a050`**（无 `qwen3-06b-` 前缀）✓。
不存在的路径被 HF 当成 repo id ⇒ `HFValidationError`。
**⇒ 冒烟测试因此拦截了一次 30 分钟的空跑** ✓（这是它唯一一次立刻回本）。

**★ 已加"开跑前路径预检"**：`CALIBER-PRECHECK` 校验
`config.json` + `model.safetensors` 存在，否则 `exit 2` ✓ ——
把"路径笔误"从"等完 GPU 才暴露"提前到"秒级失败" ✓

### 3.4 再次踩到规则 19 的自匹配

我用 `CommandLine -match 'baseline_eval|...'` 停进程时，**把我自己也杀了** ✗
（我的命令行文本里就含这些模式串）。已产出
`scripts/stop_eval_procs.ps1`：**排除自身 + 12 层祖先**，并支持 `-WhatIfOnly` 先 dry-run ✓

## 四、本轮的工程改动

| 改动 | 文件 | 状态 |
|---|---|---|
| 部署预算参数化（默认 96 逐字节等价） | `scripts/eval_needlefix.ps1` | `-MaxNewTokens N`，产物名带 `-mntN` 后缀 ✓ |
| 口径后缀接线 | `scripts/topup_verdict.py` | `--max-new-tokens N` ✓ |
| finish_reason / token id 落盘 | `scripts/baseline_eval.py` | 已修 + 透传全部键 ✓ |
| 预算曲线离线导出 | `scripts/derive_budget_curve.py` | 已写，待跑批完成 ✓ |
| token 预算实测 | `scripts/measure_token_budgets.py` | `TOKEN-BUDGET-MEASURE=DONE` ✓ |
| 真入训文件审计 | `scripts/audit_s1_training_files.py` | `AUDIT-S1-TRAINING=FAIL`（长度）✓ |
| prompt 强制判定 | `scripts/check_prompt_contract_mandate.py` | 三族均 100% ✓ |
| 路径预检 + 口径重测 | `scripts/recaliber_mnt.ps1` | 跑批中 ✓ |
| 安全停进程 | `scripts/stop_eval_procs.ps1` | 新增 ✓ |

**★ 96 口径零回归已验证**：
`VERDICT-96-REGRESSION=PASS 逐字段一致`（重跑 `topup_verdict.py` 与既有
`topup-verdict-m3-dpo-chatneedle.json` 比对，**每一个字段都相同**）✓

## 五、为什么"一次 512 跑批"就能给出整条曲线

`do_sample=False`（贪心）⇒ 解码**前缀确定**：
512 下生成的 token 序列，其**前 N 个 token 逐位等于**直接以 N 实跑的结果 ✓
⇒ `new_token_ids[:N]` 解码后重打分 = **实跑 N 的文本** ✓
⇒ 96/128/192/256/384/512 各点**互相可比**，也**可比实跑** ✓

**★ 这不是近似，但仍是派生产物**：`derive_budget_curve.py` 会写
`reports/derived-caliber-provenance.json`，逐文件记录
"派生自哪次实跑、截了多少 token、该预算下的截断率" ✓（规则 2：留痕）✓

## 六、不改变的部分（M3 裁定仍然成立）

**256 或 512 会不会翻转 M3 的裁定？——不会** ✓：

M3 的 MUST-B 失败在**两个层**里都成立（早先的分层分析）：

| 层 | 起点 soup-a050 | m3-dpo |
|---|---|---|
| 命中上限（被截断） | 49.6% | 22.4% |
| **自然停笔（未被截断）** | **45.9%** | **7.5%** |

**⇒ 在"根本没被截断"的响应里，m3-dpo 的契约率也是 7.5% vs 起点 45.9%** ✓
⇒ **契约崩塌是真实的行为损失，不只是截断伪影** ✓
提高预算会把**两侧的水位都抬高**，**配对差依然显著为负** ✓

**★ 但它会改变另一个读数**：起点的契约水位 **70/168 = 41.7%** 本就偏低，
且 MUST-B 门限 **63/168 = 37.5%** 只留 7 条余量（**违反推论 33.1**）✗。
提高预算后这两者都应重新登记 ✓。

## 七、下一步

1. **等 `pwsh-1990`**（512 跑批 + 两份 `-mnt512` 裁定）。
2. 跑 `derive_budget_curve.py` ⇒ 得到 96…512 的**完整预算曲线**与**截断率**。
3. 读曲线决定**正式部署预算**，并按推论 36.3 重新登记三件套。
4. **然后才重开 M3 决策**：按更正后的处方——**首要项是"把目标压进预算"**（D0），
   **不是**加契约负样本 ✗；DPO 侧仍是 D2/D3（长度匹配 + chosen 压入预算）。
5. 两道强制门（`audit_dpo_discriminative_axes.py`、`audit_s1_training_files.py`）
   都 PASS 后才可发射。
