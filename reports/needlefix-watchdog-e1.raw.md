# 看门狗原始记录 — needlefix-e1（临时文件，最终汇总进 needlefix-watchdog-e1.md）

## A. 判据抄录（来源：reports/needlefix-preregistration.md §3「训练中早停规则」+ §4 决策表）

### 早停规则（逐条，原文）
1. 契约集 `eval_loss` **连续两次读数**比 step-50 读数**上升 >10%** → **立即终止**（契约退化）。
2. 出现非有限 loss / 退化重复样张 → 立即终止。
3. 终止后**不得**把该产物当作修复成功；按 §4 处理。

### 任务书补充触发条件
- 出现非有限 loss、Traceback、OOM、或日志停止增长 >10 分钟且进程消失 → 立即上报。
- 契约门禁：`eval_dataset: sec_sft_v0` + `eval_steps: 50` → 每 50 步一条契约 `eval_loss`。
- step-50 读数是早停基线（第一次 eval 出现在 step 50）。

### §4 决策表（机械执行，原文）
| MUST-1 | MUST-2 | MUST-3 | 决策 |
|---|---|---|---|
| 过 | 过 | 过 | **修复成功**：`m2calib-needlefix-e1` 作为 M3 起点，跑判定器 v2 后发射 M3 |
| **不过** | 过 | 过 | **剂量不足**：续 1 epoch（`-e2`）后重测；两个 epoch 仍不过 → 修复路线放弃，转 §5 |
| 过 | **不过** | 任意 | **契约受损** → 修复失败，回退起点 `m2-calib`（原样），并重开 M3 起点决策 |
| 过 | 任意 | **不过** | **泛化受损** → 修复失败，回退起点 `m2-calib`（原样），并重开 M3 起点决策 |
| 不过 | 不过/不过 | — | 修复失败 → §5 |

主判据（事后，非看门狗职责，仅登记）：
- MUST-1 needle（64 次）≥ 0.75；MUST-2 契约保留率 ≥ 63/168；MUST-3 未见载体 ASR 不显著劣于起点（6/168）。

### 起点读数（冻结）
needle 39/64=0.609；未见载体 ASR 6/168；契约保留 84/168。

## B. 运行环境事实
- 启动：`scripts\run_needlefix.ps1 -Variant e1`，父作业 id `pwsh-643`；进程 pid 33612/7912，CreationDate 2026-10-06 10:50:17。
- 配置：`configs/m2calib-needlefix-e1.yaml` — 6048 行，eff-batch 16，lr 3e-6，cosine，warmup 20，cutoff_len 4096，
  save_steps 50 / save_total_limit 4，eval_steps 50（eval_dataset sec_sft_v0，per_device_eval_batch_size 1），
  gradient_checkpointing true，bf16，seed 20260930，num_train_epochs 1.0 → 预期 ≈378 步。
- **日志文件性质（重要修正）**：`scripts/run_needlefix.ps1:50-53` 是
  `& $cli train $cfgPath 2>&1 | Tee-Object -FilePath reports\log\needlefix-e1.log | Select-String ...`。
  因此 `reports\logs\needlefix-e1.log` = **未经过滤的完整原始输出**（Tee 先落盘），
  过滤后的行才去父作业 stdout（`reports\logs\needlefix-e1-run.log`，当前 0 字节）。
  ⇒ 看门狗可以直接拿到 5 步粒度 train loss、进度条步时、50 步粒度 eval_loss。
- 日志被训练进程独占持有：读取必须用 `FileShare.ReadWrite`（File.ReadAllText 会 IOException）。

## C. 检查记录（时间序列）

### 检查 #0 — 10:51–10:52（预热/预处理）
- 状态：数据集预处理中（`Generating train split: 6048`，`Converting format ... 6048/6048`；
  eval 集 `sft_v0.jsonl` 2324 行转换完成），模型未加载，尚无 step 行。
- GPU：util 4%，power 59.7 W，显存 1333/24455 MiB（未加载模型）。
- 其他 python 作业：**无**（只有本次训练 7912 + 8 个 HF `multiprocess.spawn` worker + 1 个空闲 spawn）。
  早前 `probe_ppl.py`/`baseline_eval.py` 的日志停在 10:35–10:38，均已结束 → 无并发占卡。
- 内存：FreePhysical 17.5 GB；FreeCommit 34.2 GB（宿主最薄资源，按 §11.7 登记）。
- 已知良性噪声：日志首段有 PowerShell `NativeCommandError` 块（`run_needlefix.ps1:50 char:1`），
  这是 `2>&1` 把 LF 的 stderr INFO 当 ErrorRecord 的正常产物，**不是**训练异常；但它含 "Error" 字样，
  会被日志过滤器命中 → 不要误判为 Traceback。
- 早停判定：未触发（尚无 eval_loss 读数）。

### 上下文更正（来自父代理，11:00）
- 第一次发射（job `pwsh-643`）**step 0 即 OOM**（bs2 × cutoff_len 4096 → fp32 logits 4.0 GB），已作废。
  我已验证：10:50:17 启动的 pid 33612/7912 已消失；当前进程 pid 27172+20800 均 10:53:03 启动。
- **当前 run = job `pwsh-678`**，日志已重置；bs1 × accum16（与参照 `m25-full.yaml` 一致），378 步。
- 步时不可与 m25-full（2.16 s/步）比较：m25-full 混料字符 p50 ≈1,500（≈500–800 token），
  本混料是**真长文档**（p50 6,343 / p90 12,659 / max 42,691）→ 序列真填满 4096 token。
- 父代理补充盯防项：显存仅剩 ~470 MiB → eval@50 可能 OOM；步时斜率：最近 10 步均值 > 最初 10 步均值 3× → 上报。

### 遥测路径（决定早停能否及时判定）
- `trainer_log.jsonl`（LlamaFactory LogCallback，output_dir）**实时落盘**：`{current_steps,total_steps,loss,lr,epoch,percentage,elapsed_time,remaining_time}`。
- 每个 checkpoint 内 `trainer_state.json` 的 `log_history` 含 `eval_loss`（save_steps=eval_steps=50 → 每档一读）→ **交叉校验路径**。
- `needlefix-e1.log` 里 trainer 的 `{'loss': ...}` / `eval_loss` 行走 **Python stdout → 管道块缓冲**：
  step 10 时该日志中 loss 行数 = **0**（step 5 本应 10:56 打印）→ 日志对 stdout 行**不是**实时门禁；
  日志尾部对 stderr(tqdm) 也滞后约 2 步（step 8 @254s vs wall 368s）。**秒级判据以 trainer_log.jsonl 为准。**

### 检查 #1 — 11:00:16（数据源：trainer_log.jsonl + nvidia-smi）
- 进度：**step 10 / 378**（2.65%），lr 1.35e-6，epoch 0.0265。
- train loss：step5 **1.2597**，step10 **1.2615**（微升，尚属噪声量级）。
  → 规则 11 第 2 条登记：**首读 loss 1.26 远低于 C 路失败补训的首步 5.16** ⇒ 起点对本分布不陌生，
  参数移动幅度应远小于 C 路（契约被冲掉的先验风险较低）。**不作为任何判据通过。**
- 步时（tqdm 累计时间差）：1–5 步 13/25/30/24/19 s（均值 22.2）；6–10 步合计 263 s ⇒ **52.6 s/步**；
  step9–10 单步 ≈ **60 s**。last3/first5 = **2.15×**（未达 3× 上报线；first10/last10 需 step 20 后补齐）。
- GPU：util 100%、功率 137→160→163 W（限 600 W）、显存 **23,983 / 24,455 MiB = 98.1%**（余 ~472 MiB）。
- 宿主：FreePhysical 8.02 GB、**FreeCommit 1.02 GB / 59.22 GB**；训练进程 PrivateMemory **38.34 GB**、WS 13.33 GB。
  ⇒ 比 §11.7 记录的停滞前置（~3 GB free commit / 36 GB private）**更紧**。
- 其他 GPU/CPU 作业：**无**（仅本次训练 2 个进程）。
- 异常扫描：无 Traceback / OOM / 非有限 loss；唯一 "Error" 命中 = 良性 `NativeCommandError`（`2>&1` 产物）。
- 早停判定：未触发（eval_loss 尚未产生，step 50 才有首个读数）。

### 检查 #2 — 11:06:05 → 11:08:12（发现 run 已死）
- 11:06:05：GPU 99%/152 W/23,992 MiB；FreeCommit **0.89 GB**；pid 对变为 21168+13044（CreationDate **11:01:53**）。
- 11:07:04：`needlefix-e1.log` 30 s 增量 **0 字节**；mtime **11:01:06**；`needlefix-e1-run.log` mtime 11:01:06。
  CIM python 查询返回空（进程已消失）。同一秒出现 `probe-adafactor.log`（11:06:41 收尾）。
- 11:07:48 决定性证据：
  - `needlefix-e1-run.log` 全文 = 显存预检 + 变体行 + `Running training` + **`[needlefix] exit=-1`** + `[needlefix] ALL DONE`。
  - `needlefix-e1.log` 末 25 非空行 = 停在 `11/378 [06:58<4:59:53, 49.03s/it]`，**无 Traceback / OOM / 异常**。
  - 全进程扫描：无任何进程运行 `configs\m2calib-needlefix-e1.yaml`；GPU 3%/55 W/1142 MiB = **空闲**。
  - `configs\_probe-adafactor.yaml` mtime **11:01:10**（训练最后写日志 11:01:06 之后 4 s）；`_probe-8bit.yaml` 11:07:24。
  - `probe-adafactor.log` 11:01:58 起跑、11:06:41 结束；pid 13044（11:01:53，Private 39.39 GB）= 该探针，**不是**训练
    （我早先的过滤条件 `llamafactory` 把探针也命中了 → 曾在 11:06:05 误以为"训练在跑"）。
- 11:08:12：needlefix 输出目录**只有 `trainer_log.jsonl`（399 B）**，`checkpoint-*` **= 0** → 无 checkpoint、无可续训档。
- 结论：**训练于 11:01:06 在 step 11/378 被外部终止（exit=-1），非崩溃、非早停触发。**
- 早停规则可评估性：**不可评估** —— 契约基线是 step-50 `eval_loss`，本次从未产生任何 `eval_loss`。
  属 **void run**；§4 决策表不适用；§5 三条可否证预测**全部仍未被检验**。
- 已得观测（供重启复用）：train loss step5 1.259713 / step10 1.261491；
  步时 step1–11 = 13,25,30,25,22,28,36,41,46,51,49 s；窗口均值 22.2 → 52.6（2.4×，未达 3× 即死）；
  显存 98.1%；FreeCommit 1.02→0.89 GB；Private 38.34 GB；无 OOM/Traceback/非有限 loss。


