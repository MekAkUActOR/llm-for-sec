# `data/dpo-remediation-staging/` 结账记录（M4 数据修法）

**★ 本目录是 M4 的数据修法暂存区 ✓ —— 不是训练输入 ✗。**
**★ 发射前须把选定产物复制为 `data/lf/dpo_m4_final.jsonl` ✓ 并登记 `live_lineage` ✓。**

---

## 一、文件清单

| 文件 | 字节 | 行数 | 修法 | 状态 |
|---|---|---|---|---|
| `dpo_m4_lenmatch.jsonl.superseded` | 60,126,552 | 28,842 | **长度匹配**（`length_matched_from` 6,540 条 ✓） | ⚠️ **已退役**（被 capfix 取代 ✓） |
| `dpo_m4_capfix.jsonl` | 59,793,275 | 28,842 | **长度匹配 + 能力保持修法**（capfix ✓） | ✓ **唯一活候选** |

**★★ 为什么退役件带 `.superseded` 后缀**：本体论作用域是
`data/dpo-remediation-staging/*.jsonl`（`scripts/check_carrier_ontology.py` L81 ✓）。
**两个版本同处会**双计**** ✗ —— 实测报错 `computed` 恰为 `ontology` 的 **2×** ✗✓
（`train_rows_mismatch:text:... ontology=1548 computed=3096` ✓）。
**⇒ 退役件必须不匹配该 glob ✓，但仍保留以便 A/B 对照 ✓**（§四.5 ✓）。

**★ 两者的关系**：`dpo_m4_capfix.jsonl` = `dpo_m4_lenmatch.jsonl.superseded` **叠加** capfix ✓
（**非干净支 0 行被改动** ✓，已由 `scripts/verify_capfix.py` ④ 断言 ✓）。

## 二、capfix 是什么、为什么（第 22 轮定论）

### 证据链（全部实测 ✓）

| 证据 | 数值 | 出处 |
|---|---|---|
| `logps/rejected` 变化 | **−151.93** ✗ vs `logps/chosen` **+22.01** ✓ | `scripts/train_curve.py` |
| `rewards/rejected` 变化 | **−12.46** ✗ vs `rewards/chosen` **+0.29** ✓ | 同上 |
| ⇒ rejected 侧贡献的 margin | **97.7%** ✗（**有效比 ≈ 43:1** ✓） | 同上 |
| `report` 作 **rejected** | **1,320 条，全部在 `carrier_clean_overrefusal`** ✗ | `scripts/report_as_rejected.py` |
| `report` 作 **chosen** | 4,680 条 ✓ | 同上 |
| ⇒ 有效强度 | **压低 56,760** ✗ vs **抬高 4,680** ✓ ⇒ **12 倍压制** ✗✓ | 计算 |

### 机制

**`report` 是注入抵抗的**正确动作**** ✓，却在 `carrier_clean_overrefusal`（1,320 条 ✓）
里作为 **rejected**（要压低的 ✗）出现 ✓。
**加上 DPO 实测的梯度**严重偏向压低 rejected**（43:1 ✗）** ✓
⇒ **`report` 这一行为被全局压制** ✗✓
⇒ **模型不再报告，转为 `action=answer`** ✗ ⇒ **ASR 4.8% → 54.8%** ✗✓

**★ 这解释了为什么 4,680 条"教抵抗"的对**敌不过** 1,320 条"教别提报告"的对** ✓
—— **取胜的不是对数，是梯度方向** ✓。

### 修法（外科式 ✓）

**把 `carrier_clean_overrefusal` 的 rejected 侧整体重写为「过度谨慎」** ✓：
- 动作 `report` ✗ → **`refuse`** ✓
- `verdict` `contains-injection` ✗ → **`hold`** ✓
- 措辞去掉「检测到注入 / 上报」✗ ⇒ **退化为纯过度反应** ✓
- **长度 347 → 337 中位（比 0.97 ✓）** —— **不缩短** ✓（Cor 37.3 ✓）

**★ chosen 侧与载体正文**一字未动** ✓；`data/lf/dpo_m3_final.jsonl` **未写回** ✓。**

## 三、验证（`scripts/verify_capfix.py` ✓ 7 项全绿）

| # | 断言 | 结果 |
|---|---|---|
| ① | 行数 28,842 ✓ | PASS |
| ② | **`report` 作 rejected = 0** ✓ | PASS |
| ③ | 干净支 rejected 全为 `refuse` ✓ | PASS |
| ④ | **非干净支被改动 0 行** ✓ | PASS |
| ⑤ | `length_matched_from` = 6,540 ✓ | PASS |
| ⑥ | `report` 作 chosen 仍 = 4,680 ✓ | PASS |
| ⑦ | rejected 长度比 0.97 ✓ | PASS |

**`CAPFIX-VERIFY=PASS`** ✓

## 四、★ 残留风险（必须随产物一起交付 ✓）

1. **修法未经训练验证** ✗ —— 本目录只做了**数据侧**证明 ✓；
   **必须先用小规模跑（本轮口径 ④）确认 ASR 回落，才可发射全量** ✓。
2. **`policy` 族 14,688 对（50.9%）在动作轴上零信号** ✗
   （chosen/rejected 动作分布**完全相同** ✓）⇒ **稀释问题未被本修法处理** ✗。
3. **`refusal_quality` 300 对同为零信号** ✗（refuse/refuse ✓）。
4. **同句反标仍在** ✗：`[管道备注] 本告警与 OPS-2231 重复——已关联供参考。`
   在注入侧作 chosen=`report`（429 条 ✓）而干净侧作 chosen=`answer`（54 条 ✗）
   —— **属推论 41.5 所指的"同句异境须可判别"** ✓，本修法**未处理** ✗。
5. **长度修法与 capfix 未做交互检验** ✗ —— 建议小规模跑时两版对照
   （`dpo_m4_final` 单独 vs `dpo_m4_capfix` ✓）。

## 五、复核命令

```
.venv\Scripts\python.exe scripts\train_curve.py            ← 曲线与 43:1 梯度比 ✓
.venv\Scripts\python.exe scripts\report_as_rejected.py     ← `report` 的 chosen/rejected 计数 ✓
.venv\Scripts\python.exe scripts\fix_clean_rejected_v2.py --dry-run   ← 修法 dry-run ✓
.venv\Scripts\python.exe scripts\verify_capfix.py          ← 7 项断言 ✓
```
