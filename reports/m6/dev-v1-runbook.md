# M6 v1 训练 Runbook（deveng-m6，task-8 执行单）

> 前置：task-4/6 过门（数据冻结 + manifest 审计）→ 本单执行。
> GPU 纪律：每步前 `nvidia-smi`；串行占用；预计总 GPU 时长 ~35-50min。

## 0. 冻结确认（H6 07:00）
```powershell
# 板上 task-4、task-6 状态 completed？
# data/m6/manifest.json 为 schema 版（含 split/task/n/sha256/label_counts/manifest_id）？
# dataeng 修复项落地？(mirror 标记 / T3 dev 正例)
.venv\Scripts\python.exe -X utf8 scripts\m6_preflight_data.py   # 期望 train/dev 双 OK
```
- manifest 若与 pool 目录读法冲突：以 manifest 的 files[]（split=train/dev）为准，configs/m6-v1.yaml 不需要改（data.manifest 已指向 data/m6/manifest.json）。
- 若 mirror 行改用其他标记字段：单点改 `m6_train.derive_labels` 的 mirror 判定（现读 flags.challenge）。

## 1. 开跑（H7 窗口）
```powershell
nvidia-smi   # 确认空闲
.venv\Scripts\python.exe -X utf8 scripts\m6_train.py --config configs\m6-v1.yaml 2>&1 | Tee-Object logs\m6_v1_train_console.log
```
预期（预检外推）：
- Stage A train：45k 行 × p50 78 tok，batch 16 → **~15-25min**；PII 9,250 行 tokfeats 扁平缓存 ~2-4GB
- Stage A dev：9k 行 → ~3-5min
- Stage B：缓存上训练 6 头，bs 256 → **<2min/epoch**，≤3 epoch + 早停
- Stage C：校准 + Mahalanobis → <1min
- 产物：checkpoints/m6-v1/{probe-heads.pt, calib.json(tau_ood), ood_centers.json, head_structure.json, metrics.json, train_log.jsonl, config.json, feat_cache/}

## 2. 健康检查（训练中/后）
- train_log.jsonl：loss 单调下降无 NaN；macroR@zeroFP 每 epoch 报告
- metrics.json：六任务 dev recall@zeroFP + FP 计数（目标方向：FP=0 基线）
- 早停触发即正常（patience 1）

## 3. 推理验证 + qa 交接口径
```powershell
.venv\Scripts\python.exe -X utf8 scripts\m6_infer.py --head checkpoints\m6-v1 --input outputs\m6\infer_smoke_in.jsonl --output outputs\m6\v1_infer_smoke.jsonl --determinism-check
.venv\Scripts\python.exe -X utf8 scripts\m6_infer.py --head checkpoints\m6-v1 --input reports\m6\regression\m6_regression_inputs.jsonl --output outputs\m6\v1_regression.jsonl --determinism-check
```
- 输出 v0.3.1 契约（tasks/decision/ood.score 原始距离/T4 spans 一等/tau_ood 回显）
- 11k 行评测预算：~7ms/row warm → qa harness 直接可用；--thresholds-json 注入优先级已实现

## 4. 消融副产（可选，不阻塞）
```powershell
# T3 前缀消融：copy m6-v1.yaml 改 data.prefix_rows: include + output_dir: checkpoints\m6-v1-prefixinc
.venv\Scripts\python.exe -X utf8 scripts\m6_train.py --config configs\m6-v1-prefixinc.yaml --reuse-cache
```
（feature cache 复用：头重训 0.3s CPU 级——v1→v2 迭代引擎）

## 5. 异常处置
| 症状 | 处置 |
|------|------|
| manifest sha256 mismatch | 数据漂移——停，找 dataeng 重发 manifest |
| OOM | extract_batch_rows 16→8；bio_max_tokens 1024→512（记录改动） |
| Stage B loss NaN | grad_clip 已 1.0；降 lr 1e-3→5e-4 重跑（记录） |
| dev recall 异常低（<0.5 某任务） | 查该任务标签覆盖（预检表）；数据问题回 dataeng，不盲调参 |
| GPU 被占 | 等 + 板上登记；不并行 |

## 6. 完成判定
- checkpoint 可被 m6_infer 加载并输出六任务结果（第 3 步绿）
- 交 qa（task-9）出首轮读数（H10 11:00 前）
- GPU 释放确认 + pm 镜像登记（§9）
