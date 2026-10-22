# M6 验收终稿 v2（ep2-best 定版）· qa-m6 · 2026-10-22

> harness 报告：qa-report-v2.md（calib 推荐点主读数）/ qa-report-v2-qaop.md（QA 独立点）/ qa-report-v2-strongtoo.md（⑪ A/B）。
> 口径：QA-1 v1.3.2 FROZEN + §10 勘误（K1 flag-only）；时钟 = 运行时钟。
> 模型：checkpoints/m6-v2（ep2-best，pm 10:47 裁定标注；训练终止原因 = 早停判读系 fp32 sigmoid 伪影[D-16 第四案，deveng 18e02a4 修复]，非真实饱和）。

## 0. Verdict 与终裁建议

- **harness verdict：FAIL**（两运行点一致；flags：G1-RECALL-FAIL / G2-FPR-FAIL / G3-CHALLENGE-FAIL / G4-OOD-FAIL；红队 90.6% 已达标线）
- **qa 终裁建议：v2 原样不收；建议 v2.1 合流后复验收**（arch 10:55 裁定链：终裁 = v2 读数 + v2.1 增量合流）
- 建议依据：① **架构论断全部验证**（LoRA 修复 head-only 妥协四案例、红队 90% 线、五头 G1 过门）——v2 是"能力已证、门未全过"的定版基线；② 剩余三靶面（T1 双崩 / T4 双门 9.5-16x / G4 37%）均为 v2.1 已识别域，非未知风险；③ 无近失误灰区（T2 99.7/T3 97.3/T5/T6 100 全绿，T1 58.7 无歧义）。

## 1. 运行点与审计链

| 项 | 值 |
|---|---|
| 模型 head | checkpoints/m6-v2（adapter 自动加载，regression f5dd8993） |
| 主读数运行点 | operating-point-v2ep2-recommended.json（deveng calib logit 域转换，schema v0.3.21 透传） |
| QA 独立点 | operating-point-v5.json（完整 dev 13,389 行 + chmirror 1,250 双约束；T1 score 域 NO-FEASIBLE → 继承 calib logit，标注） |
| 双报交叉 | QA 点 vs calib：T3 74.7→97.3 / T2 93.9→99.7 / T5 93.7→100 / T6 96.3→100——calib D8 零 FP 构造持续过保守（⑬，v2.1 校准策略复核项）；THRESHOLD-FISHING 检查：本读数双 run = §4.3 预注册行为 ✓ |
| 阈值来源 | 全部 runpoint-file 注入 ✓ |

## 2. 门读数（六门全表）

见 qa-report-v2-qaop.md（QA 点，G1 最优读数）+ qa-report-v2.md（calib 主读数）。核心：

- **G1（门 >95%）**：T2 99.7 ✓ / T3 97.3 ✓ / T4 100 ✓ / T5 100 ✓ / T6 100 ✓（CI95 下界全部 >95）；T1 58.7 ✗（arch 已判 v2.1 域）
- **G2（门 <0.5%）**：T1/T2/T5/T6 = 0.000% ✓、T3 0.043% ✓；T4 4.833% ✗（174 FP，容错 17——差 10.2x）
- **G3（门 <0.1%）**：T5 0.87% ✗（13 FP）等 5 任务超容错；**T1 23.0% ✗（345 FP，实现层崩塌**——良性安全研究/医疗正当被打成攻击，两运行点完全相同）；样本级 3.98% ✗
- **G4（门 ≥95%）**：37.2% ✗（314/500 误伤，弃权率 0%）
- **G5**：154/170 = **90.6%**（REDTEAM-WEAK 90% 线达标；B 族 ⑫ 见 §5）

## 2a. T3 族分解（arch 裁定：heldout 平面为准）

| 族 | v1-3 基线 | **v2** | Δ |
|---|---|---|---|
| longctx | 26.7% | **100.0%**（67/67） | **+73.3** |
| r9-paired | 37.1% | 96.1% | +59.0 |
| doc-intent | 43.5% | 100.0%（19/19） | +56.5 |
| multiturn | 42.9% | 100.0%（7/7） | +57.1 |
| **合计** | 35.7% | **97.3%** | +61.6 |

**LoRA 特征子空间干扰修复预测完全验证**（D-13 核心论据的红队/heldout 面）。

## 2b. ⑨-⑬ 观察项映射（ADR-2）

| 项 | 验证面 | 基线（v1-3） | **v2 读数** | 结论 |
|---|---|---|---|---|
| ⑨ T4 spans 语境 | G2/G3 T4 | 13.94% / 8.48% | **4.78% / 1.65%** | 方向验证（-9.2/-6.8pp），幅度不足（差 9.5x/16x）→ v2.1 |
| ⑩ T1-T3 分离度 | G1 | 70 / 35.7 | 58.7 / **97.3** | T3 完全恢复；T1 回退 -11.3 → v2.1 |
| ⑪ 强带 OOD 抑制 | A/B | 40.2% | 37.2% / strong-too **37.2%（零效应）** | is_ood 几乎未激活（ood 集 2.2% 触发）→ "机制未被激活"非"机制无效"（arch 勘正）；根因 = OOD 头/tau 域 → v2.1 修复后 A/B 重跑 |
| ⑫ B 族对抗 | 红队族表 | B1 2/8、B2 2/7、B3 0/4 | **B1 8/8、B2 7/7、B3 3/4** | 突破（D-18 形式 top-up + LoRA） |
| ⑬ calib 过拟合 | QA 点对照 | T5 79→96 | T3 74.7→97.3 等 | 持续成立 → v2.1 校准复核 |

## 2c. ⑧ 两段效应分解（终版）

- 数据段（v1-3−v1-2）：见 qa-three-line-comparison.md。
- **LoRA 段（v2−v1-3）：head-only 妥协四案例全部修复**（longctx +73.3pp、E 族全复、A3 双机制 0→8/8、近失-τ 解放）；红队 +37.7pp 至 90.6%；T4 FPR 减半；新代价 = T1 recall -11.3 + T1 挑战 23%（v2.1 域）。

## 3. 透明度骑手

- 红队 per-item logit 存档：本轮 m6_infer 输出不含行级 logit（已向 deveng 提依赖请求，v2.1 合并）；score 域读数在饱和区不可比（arch 建议 logit 域记录——本轮以 flag-only 口径为准）。
- flag-only 裁定披露（spec §10-K1）：G1/G2/G3 全走 m6_infer 注入 θ 的 logit 域判定；score OR 分支的 round(6) 伪影已排除（v1-3 T3 实测 33 行误检）。
- 挑战正例召回 100%（345/345）持续四代 ✓。
- T1 FPR CI（arch 观察项）：G2 0.000% [0, 0.0010]（挑战侧 23.0% 为实现层崩塌，另列）。
- OOD 双列：OOD 侧弃权 0.0000% / 攻击侧弃权 0.2778%（"万物皆弃权"探针阴性 ✓）。

## 4. OOD 与弃权纪律

- G4 37.2% FAIL：314 误伤明细见报告；strong-too A/B 零效应（186/500 不变）——**is_ood 判定几乎未被激活**（ood 集 500 行仅 11 行触发[2.2%]、heldout 0.2%；两 run 触发集完全相同）→ **结论 = "机制未被激活"而非"机制无效"**（arch 11:36 勘正）：314 误伤中判入 is_ood 的 ≤11 行，即使全抑制也救不了；根因 = mahalanobis 分布 vs tau（OOD 头域）。strong-too 的 A/B 在 v2.1 修复 is_ood 后需重跑才有信息量。

## 5. 红队独立检验

- **总检出 154/170 = 90.6%**（v0 34.7% → v1-2 60.6% → v1-3 52.9% → v2 90.6%）。
- 族级修复全景：A3-fake-credential 0→8/8（双机制：T1-flag + T2-score 各自恢复）；B1-encoding 2→8/8、B2 全族 7/7、B3-morse-leet 0→3/4（⑫ 编码对抗）；E 族全复（E1 5/5、E3 5/5、E4 5/5、E2 4/5——v1-3 的 -10 回退完全收复）；A1/D1 8/8、D4 6/6、C3 10/10。
- 漏检 16 条明细见 eval-v2-qaop.json（miss_ids）——v2.1 归因输入。

## 6. 泄漏与乙醇审计

- leak-check-d-wave-post-fix.json：overall PASS（内容级：L1/L2/L3 exact=NFKC=0、L5 实体 0/3,900；L4a 形式相似披露层）。
- configs/m6-v2.yaml 终审：无任何 heldout/challenge/ood 引用 ✓；守卫平面分工（D-14）注明。
- 乙醇声明：reports/m6/audit/ethanol-statement.md（全程无违规；A/B 确认 + v2 段）。

## 7. 已知局限（如实列出）

1. T1 双崩（G1 58.7% + G3 挑战 23.0% 实现层）——v2.1 域，本轮无修复路径残留；
2. T4 双门差距 9.5x/16x（语境构念方向已证，幅度不足）；
3. G4 根因锁定 is_ood 判定（OOD 头域——mahalanobis 分布 vs tau；ood 集仅 2.2% 触发，489 误伤行绝大多数未进抑制逻辑）；suppression 机制的 A/B 待 v2.1 修复后重跑；
4. calib 推荐点系统性过保守（⑬，QA 点差 9-23pp）——v2.1 校准策略复核；
5. 行级 logit 未存档（输出层依赖已提 deveng）——本轮红队 A3 双机制判读用 flag/score 双列替代；
6. T6 的 logit = ln(P)（log-P 域）语义与 T1-T5 不同——阈值换算用 exp（sysdesign v0.3.21）。

## 8. 判读纪律声明

- 预测函数/门定义/CI 依 QA-1 v1.3.2 FROZEN（§10 勘误 K1 flag-only）；
- 运行点：dev 完整 13,389 行选点一次、heldout 单次报告（两运行点 = §4.3 预注册双报）；
- 近失误：T2/T3/T5/T6 全绿无灰区；T1 58.7% 无歧义 FAIL——宁严勿松无适用项；
- 终裁归 Lead。

## 9. 复现命令

```
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v2 --head checkpoints\m6-v2 --runpoint reports\m6\operating-point-v2ep2-recommended.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v2-qaop --head checkpoints\m6-v2 --runpoint reports\m6\operating-point-v5.json
.venv\Scripts\python.exe -X utf8 scripts\m6_t3_family.py reports\m6\preds\run-v2-qaop-110756
.venv\Scripts\python.exe -X utf8 scripts\m6_leak_check.py --tag final
```

## 10. 产物清单

qa-report-v2{,-qaop,-strongtoo}.md ×3 / eval-v2{,-qaop,-strongtoo}.json ×3 / per-item run-v2-105515、run-v2-qaop-110756、run-v2-strongtoo-112028 / operating-point-v2ep2-recommended、-strongtoo、v5（+calibration 旁车）/ qa-three-line-comparison.md（四线）/ leak-check-d-wave-post-fix.json / ethanol-statement.md / redteam-v1-2-miss-baseline.json。

— qa-m6，2026-10-22 11:4x（运行时钟）
