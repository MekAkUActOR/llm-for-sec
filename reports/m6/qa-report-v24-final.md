# M6 验收终稿 v2.4（终版候选）· qa-m6 · 2026-10-22

> **版本链**：v2（ep2-best，11:33 读数）→ v2.1/v2.2/v2.3（中间态，见 §11 增量链）→ **v2.4（19:40 读数，终版候选）**。本稿 = v2.4 段主文 + v2 段对照保留。
> harness 报告：qa-report-v24.md（calib）/ qa-report-v24-qaop.md（QA 点）；v2 段：qa-report-v2{,-qaop,-strongtoo}.md。
> 口径：QA-1 v1.3.2 FROZEN + §10-K1 flag-only；时钟 = 运行时钟。
> 模型：checkpoints/m6-v2-4（fresh T1 头 26k 监督 + fresh T3 头 + T4 lawful-pii mirror 硬化池校准 300 + T6 结构分离；trunk = v2 未动[解离测试]）。

## 0. Verdict 与终裁建议

- **harness verdict：FAIL**（两运行点一致；flags：G2-FPR / G3-CHALLENGE / G4-OOD——**G1 与 REDTEAM-WEAK 双双清零**[QA 点]）
- **qa 终裁建议：不收原样；v2.4 为迄今最强候选，剩余三面修复路线全部特征化**——T4 双门（实现层/dual-trunk 评审）、G3 挑战（阈值域，0.33-1.13% vs 0.1%）、G4（几何域，OOD 头层 post-window）
- 建议依据：① **G1 六头全过**（QA 点 CI95 下界全>95）② **红队 92.4%**（157/170，WEAK 线持续达标 + v2 增益零回吐）③ **T1 挑战崩塌修复**（23.0%→0.33%，数据弧线验收面成功）④ T3 族平面保持 97.3%（longctx 100%×2 代）⑤ 挑战正例召回 100% 四代持续 ⑥ 无近失误灰区。

## 1. 运行点与审计链

| 项 | 值 |
|---|---|
| 模型 head | checkpoints/m6-v2（adapter 自动加载，regression f5dd8993） |
| 主读数运行点 | operating-point-v2ep2-recommended.json（deveng calib logit 域转换，schema v0.3.21 透传） |
| QA 独立点 | operating-point-v5.json（完整 dev 13,389 行 + chmirror 1,250 双约束；T1 score 域 NO-FEASIBLE → 继承 calib logit，标注） |
| 双报交叉 | QA 点 vs calib：T3 74.7→97.3 / T2 93.9→99.7 / T5 93.7→100 / T6 96.3→100——calib D8 零 FP 构造持续过保守（⑬，v2.1 校准策略复核项）；THRESHOLD-FISHING 检查：本读数双 run = §4.3 预注册行为 ✓ |
| 阈值来源 | 全部 runpoint-file 注入 ✓ |

## 2. 门读数（六门全表，v2.4 段）

见 qa-report-v24-qaop.md（QA 点）+ qa-report-v24.md（calib）。核心：

- **G1（门 >95%）**：**六头全过**——T1 100 / T2 99.7 / T3 97.3 / T4 100 / T5 100 / T6 100（CI95 下界全部 >95；v2 的 T1 58.7 → 100 = fresh 头 + t1-lawful 波）
- **G2（门 <0.5%）**：T1/T2/T5/T6 = 0.000% ✓、T3 0.021% ✓（1FP）；T4 4.778% ✗（172 FP vs 容错 17，差 10.1x）
- **G3（门 <0.1%）**：T1 1.13%（QA）/ 0.33%（calib，5FP）——**23.0%→0.33% 崩塌修复**但差 3.3-11x；T4 1.65% 差 16x；样本级 4.59%（QA）/ 2.34%（calib）
- **G4（门 ≥95%）**：35.2%（QA）/ 37.0%（calib）——**解离测试确认**（trunk 未动 → 几何赤字原封；tau 3375 新平面落位不改读数；v2 37.2% 为旧平面读数，同平面对照 deveng 侧跑）
- **G5**：**92.4%（157/170）**，REDTEAM-WEAK 清零（v2→v2.4 仅 A5 5→6、B4 3→5 微升，fresh 头零回吐）

## 2a. T3 族分解（arch 裁定：heldout 平面为准）

| 族 | v1-3 | v2 | **v2.4** |
|---|---|---|---|
| longctx | 26.7% | 100% | **100%**（67/67） |
| r9-paired | 37.1% | 96.1% | **96.1%** |
| doc-intent | 43.5% | 100% | **100%**（19/19） |
| multiturn | 42.9% | 100% | **100%**（7/7） |
| **合计** | 35.7% | 97.3% | **97.3%** |

## 2b. ⑨-⑬ 观察项映射（ADR-2，v2.4 段）

| 项 | 基线（v1-3） | v2 | **v2.4** | 结论 |
|---|---|---|---|---|
| ⑨ T4 spans 语境 | 13.94%/8.48% | 4.78%/1.65% | **4.78%/1.65%** | lawful-pii mirror 硬化池校准未移 score 域可行点（NO-FEASIBLE 继承）；dual-trunk 架构评审输入 |
| ⑩ T1-T3 分离度 | 70/35.7 | 58.7/97.3 | **100/97.3** | T1 fresh 头全修复（score 域可行 θ0.8）|
| ⑪ OOD 抑制 | 40.2% | 37.2%（A/B 零效） | 35.2%/37.0%（解离确认） | 几何域，OOD 头层 post-window |
| ⑫ B 族对抗 | B1 2/8 B2 2/7 B3 0/4 | 8/8、7/7、3/4 | **8/8、7/7、3/4 + B4 5/5** | 稳定达标 |
| ⑬ calib 过保守 | T3 35.7→? | 74.7→97.3 | **88.3→97.3** | 持续（task-13 必答） |

## 11. 版本增量链（v2 → v2.4，读数档存）

- v2（11:33）：LoRA 主验证轮——五头 G1 + 红队 90.6% + T4 减半；T1 双崩 + G4。
- v2.1 attempt-3（16:32 产物，未验收读数）：T1 权重 2.0 致 T2 侵蚀 + T6 头退化——诊断弃（m6_infer 编辑窗口撞车）。
- v2.2（16:52 发射，四增量：T1 1.4 修侵蚀 / T6 结构分离 / T4 staging / T2 后置刷新）：ep2 dev T1 0.882。
- v2.4（18:56 产物，19:40 读数）：fresh T1/T3 头 + lawful-pii mirror——**本稿主体**。
- 同平面对照（deveng 侧 v2-新平面重校准）：G4 章合并材料，见 §4。

## 2c. ⑧ 两段效应分解（终版）

- 数据段（v1-3−v1-2）：见 qa-three-line-comparison.md。
- **LoRA 段（v2−v1-3）：head-only 妥协四案例全部修复**（longctx +73.3pp、E 族全复、A3 双机制 0→8/8、近失-τ 解放）；红队 +37.7pp 至 90.6%；T4 FPR 减半；新代价 = T1 recall -11.3 + T1 挑战 23%（v2.1 域）。

## 3. 透明度骑手

- 红队 per-item logit 存档：本轮 m6_infer 输出不含行级 logit（已向 deveng 提依赖请求，v2.1 合并）；score 域读数在饱和区不可比（arch 建议 logit 域记录——本轮以 flag-only 口径为准）。
- flag-only 裁定披露（spec §10-K1）：G1/G2/G3 全走 m6_infer 注入 θ 的 logit 域判定；score OR 分支的 round(6) 伪影已排除（v1-3 T3 实测 33 行误检）。
- 挑战正例召回 100%（345/345）持续五代 ✓。
- OOD 双列（v2.4 QA 点）：OOD 侧弃权 0.2% / 攻击侧弃权 0.333%（"万物皆弃权"探针阴性 ✓）。

## 4. OOD 与弃权纪律

- G4 37.2% FAIL：314 误伤明细见报告；strong-too A/B 零效应（186/500 不变）——**is_ood 判定几乎未被激活**（ood 集 500 行仅 11 行触发[2.2%]、heldout 0.2%；两 run 触发集完全相同）→ **结论 = "机制未被激活"而非"机制无效"**（arch 11:36 勘正）：314 误伤中判入 is_ood 的 ≤11 行，即使全抑制也救不了。
  **三代触发率对照（arch 判别树数据）**：v1-2 2.6%/0.7%（~3.7x 分离）→ v1-3 **9.2%**/0.4%（~23x，D 波 ood-mirror 修复）→ v2 **2.2%**/0.2%（~11x）——**LoRA 吸收 OOD 分离度**（-4.2x）。**联合条件精算**：v2 误伤 314 行中 is_ood 触发仅 **2（0.6%）**（v1-3 对照 10/299 = 3.3%）——边界邻接行恰是 Mahalanobis 最难覆盖（arch 门槛论证实证：即使恢复吸收前几何也远不过门）。
  **前提缺口（arch 12:0x 标注）**：吸收结论（分支③）依赖"v2 的 centers/tau 已在适配后 trunk 上重算"——若沿用 v1-3 几何则兼容"空间旋转后旧 centers 失准"（分支①，便宜修复：适配后重算重测）。**deveng 确认为判别树第一步闭环要件**（已请求）。修复三候选层（arch）：(a) 适配后特征重估几何 (b) 学习式 OOD 判别头（边界邻接覆盖）(c) flagged-OOD 联合语义（动 ADR-1 §8，Lead 级裁定）——**G4 定位为 task-13 差距归因 + 修复路线章节主角，非本窗修完项**。strong-too 的 A/B 在修复后需重跑才有信息量。

## 5. 红队独立检验

- **v2.4 总检出 157/170 = 92.4%**（v0 34.7 → v1-2 60.6 → v1-3 52.9 → v2 90.6 → **v2.4 92.4**）。
- v2 → v2.4 仅两族变化（A5 5→6、B4 3/5→5/5）——fresh 头零回吐；B 族 ⑫ 稳定（B1 8/8、B2 7/7、B3 3/4、B4 5/5）。
- 漏检 13 条明细见 eval-v24-qaop.json（miss_ids）——task-13 归因输入。

## 6. 泄漏与乙醇审计

- leak-check-d-wave-post-fix.json：overall PASS（内容级：L1/L2/L3 exact=NFKC=0、L5 实体 0/3,900；L4a 形式相似披露层）。
- configs/m6-v2.yaml 终审：无任何 heldout/challenge/ood 引用 ✓；守卫平面分工（D-14）注明。
- 乙醇声明：reports/m6/audit/ethanol-statement.md（全程无违规；A/B 确认 + v2 段）。

## 7. 已知局限（如实列出，v2.4 段）

1. T4 双门差距 10.1x/16x（G2 4.78%/G3 1.65% vs 0.5%/0.1%——score 域 NO-FEASIBLE 继承 calib logit；dual-trunk 架构评审域）；
2. G3 挑战阈值域：T1 0.33%（calib）/1.13%（QA）等全任务超 0.1% 容错——差 3-16x（门语义 vs 挑战集难负例构造的张力，task-13 必答）；
3. G4 几何域 35-37%（解离测试确认；OOD 头层修复 post-window，三候选层含 Lead 级裁定项）；
4. calib 推荐点系统性过保守（⑬，v2.4 双点差 3-11pp——校准策略复核项）；
5. 行级 logit 输出字段已就位（deveng 验证 0.3.3 含 per-task logit）——下一轮读数起 A3 类双机制判读可用 logit 域存档；
6. T6 的 logit = ln(P) 语义（sysdesign v0.3.21 band-level threshold_space）；
7. v2.1 attempt-3 中间态未验收读数（T2 侵蚀 + T6 退化——版本链 §11 存档）。

## 8. 判读纪律声明

- 预测函数/门定义/CI 依 QA-1 v1.3.2 FROZEN（§10 勘误 K1 flag-only）；
- 运行点：dev 完整 13,389 行选点一次、heldout 单次报告（两运行点 = §4.3 预注册双报）；
- 近失误：T2/T3/T5/T6 全绿无灰区；T1 58.7% 无歧义 FAIL——宁严勿松无适用项；
- 终裁归 Lead。

## 9. 复现命令

```
.venv\Scripts\python.exe -X utf8 scripts\m6_emit_dev.py --prefix v24
.venv\Scripts\python.exe -X utf8 scripts\m6_infer.py --head checkpoints\m6-v2-4 --input reports\m6\preds\v24-dev-in.jsonl --output reports\m6\preds\v24-dev-out.jsonl
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v24 --head checkpoints\m6-v2-4 --runpoint reports\m6\operating-point-v24-recommended.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v24-qaop --head checkpoints\m6-v2-4 --runpoint reports\m6\operating-point-v6.json
.venv\Scripts\python.exe -X utf8 scripts\m6_t3_family.py reports\m6\preds\run-v24-qaop-192743
```

## 10. 产物清单

v2.4 段：qa-report-v24{,-qaop}.md / eval-v24{,-qaop}.json / run-v24-191512、run-v24-qaop-192743 per-item / operating-point-v24-recommended、v6（+calibration 旁车）/ v24 emit 三件套。
v2 段：qa-report-v2{,-qaop,-strongtoo}.md / eval ×3 / run-v2-105515 等 / operating-point-v2ep2-*、v5。
公共：qa-three-line-comparison.md（五代对照）/ leak-check-d-wave-post-fix.json（v2.4 数据波复核见 task-15 补段）/ ethanol-statement.md / redteam-v1-2-miss-baseline.json。

— qa-m6，2026-10-22 19:4x（运行时钟）
