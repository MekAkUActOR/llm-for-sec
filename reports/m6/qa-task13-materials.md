# M6 task-13 QA 定向材料（三项）· qa-m6 · 2026-10-22 21:0x

> 候选锚点：**v2.4-dt @19eaaba**（gate-only 终版候选，arch 正式判定前推定）。QA 点读数为主口径（G1 最优），calib 点括注。
> 验收线：G1 recall >95%（严格 CI 点估计）/ G2 FPR <0.5% / G3 chFPR <0.1%（容错 = ⌈n×0.1%⌉ = 1 FP）+ 样本级双报 / G4 OOD 放过 ≥95%（目标 98%）。

## ① 差距表（v2.4-dt 终值 vs 验收线）

| 门 | 任务 | v2.4-dt | 验收线 | 差距倍数 | 六代轨迹（v0→v1-2→v1-3→v2→v2.4→v2.4-dt） |
|---|---|---|---|---|---|
| **G1** | T1-T6 | **六头全过**（100/99.7/97.3/100/100/100，CI 下界>95） | >95% | **0x（达标）** | T1: 13→65→70→58.7→100→100；T3: 37→53→35.7→97.3→97.3→97.3 |
| **G2** | T1/T2/T3/T5/T6 | 0.000/0.000/0.021/0.000/0.000% | <0.5% | **0x（达标）** | 五头三代零 FP |
| | **T4** | **2.333%**（84FP/容差 17） | <0.5% | **4.9x** | 8.86→7.33→13.94→4.78→4.78→**2.33** |
| **G3** | T4 | **0.78%（QA，9FP）/ 0.35%（calib，4FP）** | <0.1%（容差 1FP） | **7.8x / 3.5x** | 41.3→9.18→8.48→1.65→1.65→**0.78/0.35** |
| | T1 | 1.13%（QA，17FP）/ 0.33%（calib，5FP） | 同上 | 11.3x / 3.3x | 23.0（v2）→0.33（v2.4 数据弧线） |
| | T2/T3/T5/T6 | 0.87/2.13/0.73/0.67% | 同上 | 6.7-21x | 阈值域（QA 点松点代价；calib 点 0.53/0.47/0.07/0.47%） |
| | 样本级 | 3.72%（QA）/ 1.04%（calib） | 披露 | — | 41.3→9.18→8.74→3.98→2.34→**1.04**（calib 链） |
| **G4** | OOD 放过 | **35.4%（QA）/ 37.6%（calib）** | ≥95% | **2.7x 差额** | 70.4→9.4→40.2→37.2→37.0→**35.4** |
| G5 | 红队 | **92.4%（157/170）** | 90% 线 | **达标**（WEAK 清零） | 34.7→60.6→52.9→90.6→92.4→92.4 |
| 参照 | 挑战正例召回 | 100%（345/345） | 披露 | 达标 | 六代持续 100% |

**总结**：G1 + G2 五头 + G5 + 挑战召回 = **达标**；G2 T4（4.9x）+ G3 多任务（3.3-11x）+ G4（2.7x 差额）= 三个差距面。

## ② 修复路线排序（根因域 × 杠杆 × 预期收益 × 性价比）

| # | 差距面 | 根因域 | 修复杠杆 | 预期收益 | 成本/风险 | 性价比 |
|---|---|---|---|---|---|---|
| 1 | **T4 G2 残差**（2.33%，84FP） | 实现层：≥2 字符真 span 在 lawfully-benign 行的 context-blind 提取（1,005 行域，deveng TALLY） | **context-gate**（span 提取加语境条件——doc 头语境仲裁 span 通道） | G2 2.33→~0.1-0.3%（doc 通道基线）；G3 同步受益 | 中（架构域：dual-trunk 决策语义变更，需 sysdesign 契约 + 头级训练） | **高**（-84FP 的 90%+ 集中于此域；v2→v2.4-dt 已证 T4 可渐进：13.9→2.33） |
| 2 | **G3 阈值域**（T1 3.3-11x + T2/T3/T5/T6 6.7-21x） | 阈值/校准域：QA 点松点代价 + calib D8 零 FP 构造过保守（⑬ 三代证据） | **校准策略复核**（挑战镜像约束的选点协议 v2——chmirror 加权/两段式）；calib 构造改非零 FP 容忍 | G3 各任务 → 容差内（1-2FP）可能性高（T5 calib 点已 0.07% 过门） | 低（协议域，无训练成本；但 G1↔G3 权衡需重验——宁严勿松约束） | **高**（纯阈值动作；T5 已示范可行） |
| 3 | **G4**（35.4% vs 95%） | 几何域：OOD 头判定面塌陷（is_ood 4.6% 触发、边界邻接 0.6%、LoRA 吸收 4.2x）+ **span 通道 OOD 旁路**（62% OOD 行 span-only flag） | 三候选层（arch）：(a) 适配后特征重估 Mahalanobis（若 centers 未重算——deveng 确认判别树第一步）；(b) **学习式 OOD 判别头**（边界邻接覆盖）；(c) flagged-OOD 联合语义（Lead 级裁定，动 ADR-1 §8）+ context-gate 的 span 旁路收窄（与 #1 同杠杆） | (a) 视分支：若旧 centers → 便宜大收益；(b) 结构性覆盖边界区（v1-3 参照：23x 分离也只 40.2%——需 (b)/(c) 级动作）；(c) 语义级重构 | 高（训练 + 架构裁定） | **中**（差距最大但根因最深；#1 的 context-gate 顺带收窄 span 旁路 = 部分收益前置） |
| 4 | T4 G1 span 依赖结构 | 数据/架构域：heldout 9% T4 正例 span-only 依赖（27/300，subordination NO-GO 依据） | 正例池配额纪律（arch §6.15 镜像——dev 正例族覆盖 heldout 分布）+ doc 头长文 PII 教学 | 降低结构脆弱性（span 通道单点依赖） | 中（数据波 + 训练） | 中（防御性——当前 100% 达标，防未来回退） |

**排序依据**：#1/#2 无训练或协议级成本、直接命中当前 FAIL 面；#3 收益大但依赖 (b)/(c) 级投入且 #1 前置受益；#4 防御性。

## ③ 复现指南段（六代读数链）

**环境**：Windows + `.venv\Scripts\python.exe -X utf8`（repo 根）；GPU 单卡 24GB §9 串行纪律；运行时钟为准（报告机器戳 = 运行时钟）。种子：训练 seed=42（configs）；选点无随机性（网格枚举）；推理无随机性（determinism check 97f2860a [v2.4-dt]）。

**冻结行集**（评测输入，只读）：heldout（D 波后 16,263 行含 T2 +42）/ challenge 1,500 / ood 500 / redteam 170；dev gold 视图 13,389 + chmirror 1,550（v2.4 起，含 lawful-pii 300）。

```
# 通用：mode run = heldout/challenge/ood/redteam 四切分推理 + 六门计算 + 报告
# v0 基线（θ0.5 参考切）
m6_acceptance.py --mode run --tag baseline-v0 --head <m5a-r5 原样> --runpoint reports\m6\operating-point-baseline-v0.json
# v1-2（热修终态）
m6_acceptance.py --mode run --tag v12 --head checkpoints\m6-v1-2 --runpoint reports\m6\operating-point-v2.json   # QA 点
# v1-3（D 波 guard）
m6_acceptance.py --mode run --tag v13 --head checkpoints\m6-v1-3 --runpoint reports\m6\operating-point-v13-recommended.json
m6_acceptance.py --mode run --tag v13-qaop --head checkpoints\m6-v1-3 --runpoint reports\m6\operating-point-v4.json
# v2（LoRA ep2-best）
m6_acceptance.py --mode run --tag v2 --head checkpoints\m6-v2 --runpoint reports\m6\operating-point-v2ep2-recommended.json
m6_acceptance.py --mode run --tag v2-qaop --head checkpoints\m6-v2 --runpoint reports\m6\operating-point-v5.json
# v2.4（fresh 头）
m6_emit_dev.py --prefix v24 && m6_infer.py --head checkpoints\m6-v2-4 --input <v24-dev-in> --output <v24-dev-out>  # + chmirror
m6_acceptance.py --mode select-op --dev-preds reports\m6\preds --dev-preds-prefix v24- --dev-labels <v24-labels> --dev-manifest <sha> --calib-fallback <calib>
m6_acceptance.py --mode run --tag v24 / v24-qaop --head checkpoints\m6-v2-4 --runpoint <v24-recommended / v6>
# v2.4-dt（gate-only 终版候选）
m6_acceptance.py --mode run --tag v24dt / v24dt-qaop --head checkpoints\m6-v2-4dt --runpoint <v24dt-recommended / v7>
# 辅助验证
m6_t3_family.py <run-dir>                    # T3 族分解（flag-only 口径）
m6_leak_check.py --tag <wave>                 # 泄漏证书（D 波 + v2.4 波双证 PASS）
```

**完整命令记录**：各代终稿 §9（qa-report-v12-final / v24dt-final 等）；per-item 预测与标签快照在 reports/m6/preds/run-*/（可复算全部指标，无重跑依赖）；eval JSON（m6-eval-report schema）+ 敏感性曲线 JSON 落盘。

— qa-m6，2026-10-22 21:0x（运行时钟）；口径 QA-1 v1.3.2 FROZEN §10-K1 flag-only
