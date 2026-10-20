# M6 v1-2 验收读数终稿（H10 · qa-m6）

> 组成：§A-§F 为 harness 自动读数（qa-report-v12.md / qa-report-v12-qaop.md）的判读与终裁建议；
> §G 复现与审计链。口径：QA-1 v1.3.2 FROZEN；时钟 = 运行时钟（pm §8）。

## A. Verdict 与终裁建议

- **harness verdict：FAIL**（两运行点一致；flags G1/G2/G3/G4/REDTEAM-WEAK）
- **qa 终裁建议**：**v1-2 退回 v2 迭代**（不达验收门，但六头中三头已达标——见 §B 分层）
- 建议依据：G1 3/6 任务不达（T1 65-76%、T2 80%、T3 53-64%）；G2/G3 的 T4 FPR 灾难（7.3%/8.4%，阈值无关）；G4 OOD 放过 8.8-9.4%（门 95%）；红队 60.6-74.7%（<90%）。

## B. 分层结论（双运行点对照，calib → QA-op）

| 层 | 结论 | 证据 |
|---|---|---|
| **已达标头** | T4/T5/T6 recall 100%/98.3%/100%（QA 点）| G1 表 + CI95 |
| **阈值无关缺陷** | T4 良性 spans 误报（G2 7.333%/264FP、G3 8.398%/97FP 两点完全相同）| per-item spans 明细；arch 语境条件检测构念正对此 |
| **机制边界** | G4 OOD 强带误伤（453-456/500，弃权率 0%——强带不被 is_ood 抑制）| two-band 设计边界，非校准问题 |
| **分离度短板** | T1/T3 recall（两运行点 65-76%/53-64%）| 探针头训练侧 |
| **对抗面缺口** | B 族编码混淆（B1/B2 红队 0%）、A4 稀释 0→62.5% | G5 族表 |
| **校准过拟合信号** | QA 点 dev→heldout 迁移衰减（dev 81-99% → heldout 64-100%）| §4.3 交叉验证条款触发 |

## C. 透明度骑手

- T1 FPR 附 CI（arch 观察项）：calib 点 0.0000% [0, 0.0010]；QA 点 0.0266% [0.0000, 0.0015]
- 挑战正例召回 100%（345/345，披露不入门）
- OOD 双列：OOD 侧弃权率 0.0000% / 攻击侧弃权率 0.0000%（n=1800）——"万物皆弃权"探针阴性 ✓
- τ_flag 双披露（Lead 裁决条款）：v1 原始 283 dev FP = 校准 bug 量化证据（deveng 训练侧口径 + m6_crossfp_analysis.py，qa 未复跑——标注）；v1-2 logit 空间校准后 dev 零 FP
- T2 score 饱和（52 良性 score=1.0）致 QA score 网格结构性失效 → T2 运行点继承 calib logit 域阈值（标注继承，operating-point-v2.json notes）

## D. 近失误点（宁严勿松，如实判 FAIL）

- T5 recall 94.67%（calib 点，门 95% 严格大于——差 0.33pp，CI95 [91.48, 96.92] 含门值）→ FAIL
- T6 recall 94.33%（calib 点，差 0.67pp）→ FAIL
- G3 T1/T5（calib 点）各 1 FP = 容错上限内 PASS 但 CI 标红（上界 0.37%/0.96% > 0.1%）

## E. v2 信号清单（qa 视角，按优先级）

1. T4 spans 语境条件化（形式定实体性、语境定极性——arch 构念）；
2. T1/T3 探针分离度；
3. G4 强带 OOD 抑制（suppression 扩强带或 OOD 分数头校准）；
4. B 族编码混淆对抗增强（特征层）；
5. calib 的 D8 零 FP 构造在 heldout 上过保守（margin/分位数策略复核）。

## F. 数据与协议审计链

- 数据：manifest sha256（H6 冻结 + 热修 35943e2 后），泄漏证书 leak-check-h6-hotfix1.json（overall PASS，L1-L5 全 0）
- 运行点：operating-point-v12-recommended.json（calib 转换，schema 校验过）+ operating-point-v2.json（QA 独立选点 + T2 继承标注）+ 旁车校准记录（含饱和区披露，Lead 附注 1/2）
- 协议：v1.3.2 网格（Lead 批准留痕）；THRESHOLD-FISHING 检查：本读数双 run 均 §4.3 预注册行为（推荐点 + 交叉验证列），无未解释重跑

## G. 复现命令

```
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v12 --head checkpoints\m6-v1-2 --runpoint reports\m6\operating-point-v12-recommended.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode run --tag v12-qaop --head checkpoints\m6-v1-2 --runpoint reports\m6\operating-point-v2.json
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode recompute --preds-dir reports\m6\preds\run-v12-041243 --tag v12-recompute
```

## 产物清单

qa-report-v12.md / qa-report-v12-qaop.md / eval-v12.json / eval-v12-qaop.json / sensitivity-v12.json / per-item ×2（run-v12-041243、run-v12-qaop-042708）/ qa-baseline-v0-full.md（对照）/ plots/baseline-v0-full/ / leak-check-h6-hotfix1.json / operating-point ×2 + calibration ×1。
