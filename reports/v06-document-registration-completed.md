# v0.6-document 本体登记完成（用户裁决：**选项 B —— 按模型分角色**）

**时间**：2026-10-06。**裁决**：用户在 A/B/C 中选 **B**。
**结果**：`CARRIER-ONTOLOGY-CHECK=PASS errors=0`，全套回归绿。

---

## 一、做了什么

| # | 改动 | 位置 |
|---|---|---|
| 1 | `GATE_SCOPES` 新增 `v0.6-document` → `data/heldout/v0.6-document/*.jsonl` | `scripts/check_carrier_ontology.py` |
| 2 | `INSTRUMENT_ROLES` 支持**按模型分角色**（值可为 `str` 或 `{模型: 角色}`） | 同上 |
| 3 | 新增 `role_of(instrument, model)` 帮助函数 | 同上 |
| 4 | `MATRIX_COLUMNS` 新增独立列 `document_gate` | 同上 |
| 5 | `instruments[name]` 输出新增 `role_by_model` / `role_merged` | 同上 |
| 6 | 本体 JSON 登记（外科式合并） | `data/ontology/carriers.json` |

**★ 为什么新增独立列而不并入 `unseen_gate`**：
① 它是**另一个仪器**，并进去会让该列 `basis` 混两种仪器 ⇒ 违反规则 21（不同口径不得混比）；
② 它的角色**按模型不同**，塞不进"按载体一行"的既有列语义。

## 二、登记结果（机器可读）

```json
"v0.6-document": {
  "role": {"soup-a050": "unseen_carrier_gate", "m3-dpo": "unseen_mechanism"},
  "role_by_model": {"soup-a050": "unseen_carrier_gate", "m3-dpo": "unseen_mechanism"},
  "role_merged": "unseen_carrier_gate|unseen_mechanism",
  "rows": 80,
  "kind": {"robustness": 52, "alignment": 28}
}
```

**角色查询**（规则 24 的操作化，**双角色不被压扁**）：

```
role_of('v0.6-document', 'soup-a050') = unseen_carrier_gate
role_of('v0.6-document', 'm3-dpo')    = unseen_mechanism
role_of('v0.6-document', 无模型)        = unseen_carrier_gate|unseen_mechanism   ← 无损合并
```

**条目数自洽**：80 = robustness **52**（46 未见机制 + 6 训练位点正例）+ alignment **28**（干净负例）✓

**覆盖矩阵**：每个载体新增 `document_gate: {n, basis: "v0.6-document"}` 格 ✓
**新列标签**：`"文档载体门（角色按模型）"` ✓

## 三、★登记过程中我自己引入并修回的一处退化

我的合并脚本第 4 步用 `MATRIX_COLUMNS[col]["label"]` 覆写了 `coverage_matrix.columns`，
把本体原有的**4 个描述性标签**（如
`"训练数据（data/lf/*.jsonl 全部，lf_total）"`、
`"未见载体门禁（…括号内为 kind==robustness 的行为门禁分母）"`）
替换成了 `MATRIX_COLUMNS` 里的短标签 ✗

**★关键点**：`run_check` **不比对** `coverage_matrix.columns` ⇒ 覆写后**检查依然 PASS** ✗
但我仍从备份恢复了原标签（`reports` 侧脚本 `scripts/restore_ontology_columns.py`，
`COLUMNS-RESTORE=PASS`）✓

**⇒ 登记为做法（与规则 25 同源）**：
> **不得以"检查器不看"为由留下信息退化。** 检查器的覆盖范围**不是**质量边界；
> 本次改动若只看 `CARRIER-ONTOLOGY-CHECK=PASS` 就会把 4 条真实的口径说明静默丢掉。

## 四、附带发现（未修，仅登记）

- `coverage_matrix.cell_caveat` 里 **"★2026-09-30 晚修正：`train.n` 原先用 basis=`lf_total`…"
  这段文字重复出现了两次** ✗ —— 说明历史上某次追加脚本被跑了两次。
  **纯文字冗余，不影响任何判定**；未在本轮改动（避免无关 churn），
  登记于此供后续清理。

## 五、回归状态（登记后全绿）

```
CARRIER-ONTOLOGY-CHECK=PASS errors=0     SYSPATH-HYGIENE=PASS 无违规
FIX-PS1-BOM=PASS                         STAGING-MANIFEST=PASS errors=0
DOCUMENT-GATE-CHECK=PASS errors=0        DPO-CARRIERS=ALL ASSERTIONS PASSED
TOOLOUT-REGRESSION rc=0                  unittest: Ran 862（2 个既有 pytest 缺件加载错误，与登记前相同）
```

**★ 备份**：`data/ontology/carriers.json.bak-before-v06-document`（改动前原样）✓
**★ 可复跑**：`scripts/register_v06_document.py` 幂等（再跑报 `SKIP`）✓

## 六、与本体自身判定的自洽性

本体 `claims` 段（本轮未改）现有：

```
unseen_carrier_gate_carriers = ["av_metadata", "image_metadata"]
no_unseen_gate_carriers      = ["code", "document", "email", "log", "text", "tool_output", "webpage"]
```

**⇒ `document` 不在"未见载体门"清单里** ✓ 这与双角色登记**自洽**：
document 对 `soup-a050` 暴露 0 次、对 `m3-dpo` 暴露 **1,000 次**
⇒ **不能对它做无绑定的"未见载体泛化"表述**（规则 24 要求未见载体必须绑定被评产物）✓
**⇒ 这也正是"按模型分角色"必须存在的原因**：若强行登记成单一角色，
本体要么错误宣称 document 未见、要么丢失 soup-a050 侧的未见载体结论 ✗
