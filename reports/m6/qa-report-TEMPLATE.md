# M6 验收终稿模板（qa-m6，H20 验收轮填写）

> 用法：本模板是 qa-report-<tag>.md（harness 自动生成）之上的**终稿骨架**。
> ①-⑥ 由 harness 报告直接引用/粘贴；⑦-⑩ 人工填写。
> 时钟口径：全文使用运行时钟（pm §8 时钟源声明）；引用他人自报时刻须注明"自报"。

---

## 0. Verdict 与终裁建议

- **verdict（harness）**：`{{PASS|FAIL|PASS-WITH-FLAGS}}`（qa-report-<tag>.md §Verdict）
- **flags**：`{{G1-RECALL-FAIL / REDTEAM-WEAK / …}}`
- **qa 终裁建议**：`{{一句话：建议 Lead 判 收/退回 v3/带条件收}}`
- **建议依据**：`{{哪个门差多少、近失误点估计与 CI、是否系统性短板}}`

## 1. 运行点与审计链

| 项 | 值 |
|---|---|
| 模型 head | `{{checkpoints/m6-v2 + heads_sha256}}` |
| 运行点 | `{{m6-runpoint-v<k> + sha256 + calibrated_on.manifest}}` |
| deveng calib.json 推荐点 | `{{θ 值 + 与 QA 独立选点的一致性（逐任务差）}}` |
| 双报交叉 | `{{两套运行点读数差（若 >1pp 逐项列）+ THRESHOLD-FISHING 检查结论}}` |
| 阈值来源回显 | `{{source=runpoint-file 全部通过 / THRESHOLD-SOURCE-MISMATCH 明细}}` |

## 2. 门读数（六门全表）

粘贴 qa-report-<tag>.md 的 G1-G5 全表 + 参照读数表（含 CI95 与标红）。

## 2a. T3 族分解表（arch 裁定：v2 验收的 T3 以 heldout 平面为准）

`{{m6_t3_family.py 输出：r9-paired / longctx / doc-intent / multiturn 逐族检出 + 与 v1-3 基线对照（longctx 26.7% 起点）}}`

## 2b. ⑨-⑬ 观察项映射（ADR-2）

| 项 | 验证面 | 基线（v1-3） | v2 读数 |
|---|---|---|---|
| ⑨ T4 spans 语境条件化 | G2/G3 T4 双门 | 13.94% / 8.48% | `{{}}` |
| ⑩ T1-T3 分离度 | G1 表 | T1 70 / T3 35.7 | `{{}}` |
| ⑪ 强带 OOD 抑制 | suppression A/B（two-band vs strong-too） | 40.2% / `{{A/B}}` | `{{}}` |
| ⑫ B 族对抗 | 红队族表 | B1 2/8、B2 2/7、B3 0/4 | `{{}}` |
| ⑬ calib 过拟合 | QA 点对照列 | T5 79→96 / T6 94.3→99.7 | `{{}}` |

## 2c. ⑧ 两段效应分解

`{{v1-3−v1-2（数据段，见 qa-three-line-comparison.md）+ v2−v1-3（LoRA 段，本报告）——head-only 妥协四案例（longctx/E 族/A3-T2/近失-τ）的恢复力判读}}`



- 逐套件 recall 点估计 + CI95 全表（harness suites 块）；
- 90-95% 带 pass-with-flag 清单 → 已知局限章节引用；
- 挑战正例召回（345 行 medical-legit 的 T4 检出）；
- 红队 per-item logit 存档（arch 建议：score 域 v1-2 读数不可比[全饱和]，A3 双机制判读需 logit 域）；
- score round(6) 伪影披露（spec §10-K1：G1/G2/G3 全走 flag-only 忠实口径）。

## 4. OOD 双列与弃权纪律

- OOD 放过率 / OOD 侧弃权率 / 攻击侧弃权率三列；
- "万物皆弃权"探针判定：`{{攻击侧弃权率 <1% ✓ / 异常}}`。

## 5. 红队独立检验

- 总检出 / 逐族 / 逐任务（harness G5 段）；
- 与 v0 基线对照（红队 34.71% → `{{v2 读数}}`）；
- 漏检 id 清单引用（归因 task-10）。

## 6. 泄漏与乙醇审计结论

- leak-check 最终证书：`{{reports/m6/audit/leak-check-<final>.json 全 PASS}}`
- 472 行重合整改复核记录、t4 实体池隔离复核；
- 5-gram 披露层 top 命中的人工研判结论。

## 7. 已知局限（如实列出，不静默）

`{{逐条：pass-with-flag 套件、CI 显著越界项、低分母任务、漏检攻击面、其他}}`

## 8. 判读纪律声明

- 预测函数/门定义/CI 规则依 QA-1 v1.3.1 FROZEN；
- 运行点协议：dev 选点一次、heldout 单次报告，无重跑；
- 近失误处理：`{{逐条列出"差一点"项与如实判 FAIL 的依据}}`；
- 终裁归 Lead。

## 9. 复现命令

```
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v2-final \
    --head checkpoints\m6-v2 --runpoint reports\m6\operating-point-v<k>.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode recompute \
    --preds-dir reports\m6\preds\run-v2-final-<ts> --tag v2-recompute
.venv\Scripts\python.exe -X utf8 scripts\m6_leak_check.py --tag final
```

## 10. 产物清单

- 本报告 / eval JSON（m6-eval-report schema）/ per-item / 预测原始文件 / 敏感性曲线 CSV / 分布图 / leak-check 证书 / 运行点文件。
