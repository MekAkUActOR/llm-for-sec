# M6 验收终稿 v2.4-dt（gate-only 终版候选）· qa-m6 · 2026-10-22

> **版本链**：v2（ep2-best，11:33 读数）→ v2.1/v2.2/v2.3（中间态 §11）→ v2.4（19:40）→ **v2.4-dt+gate（21:01 读数，终版候选——subordination NO-GO 后 gate-only 定版）**。
> harness 报告：qa-report-v24dt.md（calib）/ qa-report-v24dt-qaop.md（QA 点）；v2/v2.4 段报告同目录（qa-report-v2*、qa-report-v24*）。
> 口径：QA-1 v1.3.2 FROZEN + §10-K1 flag-only；时钟 = 运行时钟。
> 模型：checkpoints/m6-v2-4dt @19eaaba（dual-trunk 组装 + **span 长度门 min_len=2 decode 侧**可调可逆；trunk = v2 未动[解离测试三代确认]）。

## 0. Verdict 与终裁建议

- **harness verdict：FAIL**（两运行点一致；flags：G2-FPR / G3-CHALLENGE / G4-OOD——**G1 与 REDTEAM-WEAK 双双清零**[QA 点]）
- **qa 终裁建议：v2.4-dt 不收原样，为最强终版候选；剩余三面特征化 + 修复路线明确**——T4 残差（≥2 字符真 span 的 context-blind 提取，1,005 行域 → context-gate post-window）、G3 挑战（T1 0.33-1.13% + T4 0.35-0.78% + 其余任务阈值域）、G4（几何域 OOD 头层）
- 建议依据：① **G1 六头全过**（QA 点 CI95 下界全>95；**T4 100% 在门后保持**——heldout 面验证门的 recall-safety，比 dev 0/688 更强）② **红队 92.4%（157/170）**三代保持（v2→v2.4→v2.4-dt 零回吐）③ **T4 门效应**：G2 4.78→**2.33%**（-51% FP）、G3 1.65→**0.78%**（QA）/0.35%（calib）——16x 差距缩至 7.8x/3.5x ④ T1 挑战 23.0→0.33% 数据弧线闭环 ⑤ 挑战正例召回 100% 六代持续 ⑥ 无近失误灰区。

## 1. 运行点与审计链

| 项 | 值 |
|---|---|
| 模型 head | checkpoints/m6-v2-4dt @19eaaba（adapter 自动加载；build_manifest in-artifact） |
| 主读数运行点 | operating-point-v24dt-recommended.json（deveng calib logit 域转换，schema 透传；gate 后 T4 score 域可行 θ=0.7 dev 98.0%/0.19%——**门恢复 T4 分数域分辨率，六头全 score 可行**） |
| QA 独立点 | operating-point-v7.json（dev 13,389 + chmirror 1,550 双约束[含 lawful-pii 硬化池 300]） |
| 双报交叉 | QA vs calib：T4 G3 0.78% vs 0.35%、G1 T2 99.7 vs 91.6 等——⑬ 持续（task-13 必答）；THRESHOLD-FISHING 检查：§4.3 预注册双报 ✓ |
| 阈值来源 | 全部 runpoint-file 注入 ✓ |
| 泄漏证书 | leak-check-v24-wave.json PASS（16,144 train vs eval/frozen/redteam 三面零）+ D 波证书 |

## 2. 门读数（六门全表，v2.4-dt 段）

见 qa-report-v24dt-qaop.md（QA 点）+ qa-report-v24dt.md（calib）。核心：

- **G1（门 >95%）**：**六头全过**——T1 100 / T2 99.7 / T3 97.3 / **T4 100（门后保持）** / T5 100 / T6 100（CI95 下界全部 >95）
- **G2（门 <0.5%）**：T1/T2/T5/T6 = 0.000% ✓、T3 0.021% ✓；T4 **2.333%**（84 FP vs 容错 17，差 4.9x——门后从 10.1x 缩半）
- **G3（门 <0.1%）**：T4 **0.78%（QA，9FP）/ 0.35%（calib，4FP）**——v2.4 的 1.65% 门后缩至 7.8x/3.5x；T1 1.13%（QA）/0.33%（calib，5FP）；样本级 3.72%（QA）/1.04%（calib）
- **G4（门 ≥95%）**：35.4%（QA）/37.6%（calib）——几何域原封（解离测试三代确认；subordination NO-GO：G1 代价 9% 破 95 地板 > 5% 线）
- **G5**：**92.4%（157/170）**，REDTEAM-WEAK 清零（v2.4→v2.4-dt 族级零变化——decode 侧门只触 T4 span 通道）

## 2a. T3 族分解（arch 裁定：heldout 平面为准）

| 族 | v1-3 | v2 | v2.4 | **v2.4-dt** |
|---|---|---|---|---|
| longctx | 26.7% | 100% | 100% | **100%**（67/67） |
| r9-paired | 37.1% | 96.1% | 96.1% | **96.1%** |
| doc-intent | 43.5% | 100% | 100% | **100%**（19/19） |
| multiturn | 42.9% | 100% | 100% | **100%**（7/7） |
| **合计** | 35.7% | 97.3% | 97.3% | **97.3%** |

## 2b. ⑨-⑬ 观察项映射（ADR-2，v2.4-dt 段）

| 项 | 基线（v1-3） | v2 | v2.4 | **v2.4-dt** | 结论 |
|---|---|---|---|---|---|
| ⑨ T4 spans 语境 | 13.94%/8.48% | 4.78%/1.65% | 4.78%/1.65% | **2.33%/0.78%** | 长度门 -51% FP；残差 1,005 行 ≥2 字符真 span（context-blind）→ context-gate post-window |
| ⑩ T1-T3 分离度 | 70/35.7 | 58.7/97.3 | 100/97.3 | **100/97.3** | 稳定 |
| ⑪ OOD 抑制 | 40.2% | 37.2% | 35.2% | 35.4% | 几何域原封；span 通道 OOD 旁路（62% OOD 行 span-only flag）= subordination NO-GO 后的结构性张力，post-window |
| ⑫ B 族对抗 | B1 2/8 B2 2/7 B3 0/4 | 8/8、7/7、3/4 | +B4 5/5 | **同 v2.4（零变化）** | 稳定达标 |
| ⑬ calib 过保守 | — | T3 74.7→97.3 | T2 91.6→99.7 | **T4 双点 0.35 vs 0.78%** | 持续（task-13 必答） |

## 2c. ⑧ 效应分解（终版）

- 数据段（v1-3−v1-2）+ LoRA 段（v2−v1-3）：见 qa-three-line-comparison.md（head-only 妥协四案例全修复 + 红队 90.6% 线）。
- **头刷新段（v2.4−v2）**：T1 挑战 23.0→0.33%（数据弧线）+ G1 六头（fresh T1/T3）+ 红队 92.4%。
- **门段（v2.4-dt−v2.4）**：T4 G2 -51% FP / G3 -53% FP（QA 点），G1/红队/族平面零扰动（decode 侧隔离性验证）。

## 4. OOD 与弃权纪律

- G4 35.4% FAIL：323 误伤明细见报告。**认识链定版**（arch 四层因果 + 联合条件数据）：①机制未被激活（is_ood 面塌陷）②边界邻接实证（误伤行触发率 0.6% < 整体）③LoRA 吸收（触发 9.2→2.2%；v2.4-dt 新平面 tau 3375 后 4.6%）④恢复几何不足（v1-3 参照 23x 分离也只 40.2%）。
- **span 通道 OOD 旁路**（deveng COUNT2）：62% OOD 行 T4-flag 经 span-only（strong-band 旁路抑制）——subordination 本可救 310/500 但 G1 代价 9%（27/300 T4 正例 span-only 依赖）破地板 → **NO-GO 定版**，OOD 头层修复（学习式判别头/联合语义[Lead 级裁定]）= post-window。
- 攻击侧弃权 0.333%（"万物皆弃权"探针阴性 ✓）。

## 5. 红队独立检验

- **v2.4-dt 总检出 157/170 = 92.4%**（v0 34.7 → v1-2 60.6 → v1-3 52.9 → v2 90.6 → v2.4/v2.4-dt 92.4）。
- v2.4→v2.4-dt 族级**零变化**（门 decode 侧隔离）；B 族 ⑫ 稳定（B1 8/8、B2 7/7、B3 3/4、B4 5/5）。
- 漏检 13 条明细见 eval-v24dt-qaop.json（miss_ids）——task-13 归因输入。

## 6. 泄漏与乙醇审计

- leak-check-v24-wave.json：overall PASS（t1-lawful + T4 staging 波后 train 16,144 vs eval 16,263 / frozen 2,806 / redteam 170 全零；L4a 形式相似披露层）。
- configs/m6-v2-4dt：无任何 heldout/challenge/ood 引用 ✓（ethanol-statement v2/v2.4 段）。
- heldout 金标 join 计数（deveng 77cc864）：heldout 文件只读用于计数（无校准/训练用途）——乙醇注记在案。

## 7. 已知局限（如实列出，v2.4-dt 段）

1. T4 G2 残差 2.33%（84 FP，差 4.9x）——≥2 字符真 span 在 lawfully-benign 行上的 context-blind 提取（1,005 行域）→ context-gate post-window；
2. G3 挑战：T4 0.35-0.78%（差 3.5-7.8x）+ T1 0.33-1.13%（差 3.3-11x）+ T2/T3/T5/T6 阈值域 0.53-2.13%——门语义与挑战集难负例构造的张力，task-13 必答；
3. G4 35.4%（几何域；span 通道 OOD 旁路 62% + subordination NO-GO 的结构张力——OOD 头层 post-window，三候选层含 Lead 级裁定项）；
4. calib 推荐点持续过保守（⑬，双点差呈现于 T4 G3 0.35 vs 0.78% 等）；
5. T6 的 logit = ln(P) 语义；行级 logit 字段已就位（0.3.3）——下轮 A3 类判读可用；
6. v2.1 attempt-3 中间态未验收读数（§11 存档）。

## 8. 判读纪律声明

- 预测函数/门定义/CI 依 QA-1 v1.3.2 FROZEN（§10 勘误 K1 flag-only）；
- 运行点：dev 完整 13,389 行选点一次、heldout 单次报告（两运行点 = §4.3 预注册双报）；
- 近失误：六头 G1 全绿无灰区；FAIL 项无歧义——宁严勿松无适用项；
- 终裁归 Lead。

## 9. 复现命令

```
.venv\Scripts\python.exe -X utf8 scripts\m6_infer.py --head checkpoints\m6-v2-4dt --input reports\m6\preds\v24dt-dev-in.jsonl --output reports\m6\preds\v24dt-dev-out.jsonl
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode select-op --dev-preds reports\m6\preds --dev-preds-prefix v24dt- --dev-labels reports\m6\preds\v24-dev-labels.jsonl --dev-manifest <manifest-sha> --calib-fallback checkpoints\m6-v2-4dt\calib.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v24dt --head checkpoints\m6-v2-4dt --runpoint reports\m6\operating-point-v24dt-recommended.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v24dt-qaop --head checkpoints\m6-v2-4dt --runpoint reports\m6\operating-point-v7.json
.venv\Scripts\python.exe -X utf8 scripts\m6_t3_family.py reports\m6\preds\run-v24dt-qaop-204919
```

## 10. 产物清单

v2.4-dt 段：qa-report-v24dt{,-qaop}.md / eval-v24dt{,-qaop}.json / run-v24dt-203643、run-v24dt-qaop-204919 per-item / operating-point-v24dt-recommended、v7（+calibration 旁车）/ v24dt emit（复用 v24 输入）。
v2.4 段：qa-report-v24{,-qaop}.md / eval ×2 / run-v24-191512、run-v24-qaop-192743 / operating-point-v24-recommended、v6。
v2 段：qa-report-v2{,-qaop,-strongtoo}.md / eval ×3 / run-v2-105515 等 / operating-point-v2ep2-*、v5。
公共：qa-three-line-comparison.md（五代对照）/ leak-check-d-wave-post-fix + v24-wave / ethanol-statement.md / redteam-v1-2-miss-baseline.json。

## 11. 版本增量链（v2 → v2.4-dt，读数档存）

- v2（11:33）：LoRA 主验证轮——五头 G1 + 红队 90.6% + T4 减半；T1 双崩 + G4。
- v2.1 attempt-3（16:32 产物，未验收读数）：T1 权重 2.0 致 T2 侵蚀 + T6 头退化——诊断弃（m6_infer 编辑窗口撞车）。
- v2.2（16:52 发射，四增量）：ep2 dev T1 0.882；v2.3（中间态）。
- v2.4（18:56 产物，19:40 读数）：fresh T1/T3 头 + lawful-pii mirror——G1 六头 + 红队 92.4% + T1 挑战 0.33%。
- **v2.4-dt+gate（19:45 组装 @19eaaba，21:01 读数）：span 长度门 + dual-trunk——T4 G2/G3 减半 + 全平面零扰动。subordination NO-GO（heldout 金标 9% G1 代价）→ gate-only 终版候选定版。**

— qa-m6，2026-10-22 21:0x（运行时钟）
