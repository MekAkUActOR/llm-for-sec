# M5 双臂训练发射报告（数据轴 DPO × RL 轴 GRPO，GPU 串行）

- 日期：2026-10-13/14 · 执行：M5 发射代理（父代理 session-10ce0896 委派）
- 任务：臂① `configs/m5a-dpo-probe.yaml`（DPO 探针 300 步）→ GPU 空闲确认 →
  臂② `scripts/run_p2rl_grpo.py --run`（GRPO 探针 300 步）；任一臂失败即停、不启
  另一臂；训练产物零覆写；报告落盘本件。
- 环境：`.venv\Scripts\python.exe` / llamafactory-cli（LF 本仓 checkout）·
  每命令显式 `HF_HOME=J:\Projects\llm_for_sec\.cache\huggingface` ·
  `HF_HUB_OFFLINE=1` · `PYTHONIOENCODING=utf-8` ·
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` · GPU 单卡 RTX 5090 D 24GB。

---

## 0. 判定总览

| 项 | 臂① M5A DPO | 臂② M5B GRPO |
|---|---|---|
| 最终 rc | **0** ✓（attempt-3） | **0** ✓（attempt-2） |
| 训练步 | 300/300（train_runtime 900s = 15:00） | 300/300（train_runtime 641s = 10:41） |
| checkpoint 子档 | **6**（50/100/150/200/250/300）= 300/50 预期 ✓ | **12**（25/50/…/300）= 300/25 预期 ✓，≤ keep 20 全留存 ✓ |
| 曲线 sanity | loss 0.65→0.0722 平稳降；**NaN/Inf=NONE** ✓ | entropy 0.4824→0.5636 稳定无塌缩 ✓ |
| watchdog | —（DPO 无此件） | **未触发即停** ✓；遥测见 §3 |
| 产物落点 | `checkpoints/qwen3-06b-sec-m5a-dpo-probe`（根=最终模型+曲线图） | `checkpoints/qwen3-06b-sec-p2rl-grpo-v1`（根=最终模型） |
| 失败尝试（全程留痕） | attempt-1 CastError / attempt-2 GBK | attempt-1 warnings_issued AttributeError |

**M5-LAUNCH 判定：双臂完成 ✗✓。**

---

## 1. 臂① M5A DPO（数据轴）：三次尝试全记录

### 1.1 attempt-1（2026-10-13 23:50:46，rc=1，零训练步）

`llamafactory-cli train configs\m5a-dpo-probe.yaml` 在数据装载阶段即败：

> datasets.exceptions.DatasetGenerationCastError: All the data files must have the same
> columns, but at some point there are 3 new columns ({'rejected_form', 'archetype_id',
> 'polarity'}) and 4 missing columns ({'src', 'src_id', 'rejected_pack', 'variant'}).
> … generating data using data/m5a-run/train.jsonl

根因取证（日志 `reports/logs/m5a-dpo-train-attempt1-casterror.log`）：混料 =
三源**字节级拼接**（build_m5a_mix.py 逐字节纪律 ✓），但 `datasets` JSON builder
按首 chunk 定 writer schema、后续 chunk 列集必须恒等——键集扫描实证：基座
28,842 行有 4 种键集变体（均为 13 列并集的**缺键子集**，可装载，m4 四臂先例）；
p16 两 release 各 2,880 行、各自单一 11 键 schema（内部同构）——跨基座→p16 边界
的 chunk 列集不匹配 ⇒ CastError。构建器断言面（逐行 JSON 可解析/结构/分布/字节
恒等）与装载面（单文件同构 schema）的盲区交集。

**按纪律冻结臂②未发射，报父代理裁决。**

### 1.2 父代理裁决与勘误链（多数据集装载，数据内容恒等）

裁决（2026-10-13）：不碰冻结混料（sha256 `ee181598…` 保留为审计锚点），改走
LF 多数据集装载。执行五步（全部完成）：

1. **源码核证 ✗不猜**：`dataset` 逗号拆分（hparams/data_args.py L156-163）→
   每条目独立 `load_dataset(json, data_files=[单文件])`（data/loader.py L164-186）
   → `align_dataset` 映射标准 schema 并 `remove_columns` 丢弃全部源 metadata 列
   （data/converter.py L393-425）→ `merge_dataset` 默认 concat 按列举序（
   data/data_utils.py L51-62）＝冻结混料的拼接顺序。三源独立装载冒烟
   SMOKE-M5A-MULTIDS=OK（28,842+2,880+2,880=34,602 ✓）。
2. **加性注册**：`data/m5a-run/dataset_info.json` 增三同名条目
   （`sec_dpo_m5a_base_m4capfix` / `sec_dpo_m5a_p16_benign` /
   `sec_dpo_m5a_p16_malicious`，各带 sha256 旁注；既有 `sec_dpo_m5a` 条目零改动）。
   三源文件 sha256 均对 build_m5a_mix.py 冻结常量复核 ✓。
3. **配置唯一键改动**：`dataset: sec_dpo_m5a` → 三数据集逗号列表（其余 28 键
   不动 ✗✓）。改后 config sha256 `c0151436…54`。
4. **预注册勘误**：`reports/m5a-preregistration.md` §7 追加（CastError 现场 +
   内容恒等证明链 + 同病警告），只追加不改写 ✗。
5. **launch_audit**（--tag m5-launch，2026-10-13 23:59）：**10/10 全 PASS
   rc=0**（A1–A5/B1–B3/C1–C2；B1/B3 复核冻结混料 sha 未动 ✓），报告
   `reports/launch-audit-m5-launch.json`，日志 `reports/logs/launch-audit-m5-launch.log`。

### 1.3 attempt-2（00:07:18，rc=1，零训练步）

LF `parser.py` L109 以 locale 默认编码（本机 **GBK**）`open(dataset_info.json)` ⇒
我首版注册条目 note 含中文 ⇒ `UnicodeDecodeError`。修复 = note 改纯 ASCII 英文
（sha256 旁注保留；终版注册件 sha256 `5761661…f4b`）。**约束登记：本机
dataset_info.json 必须纯 ASCII。**（日志 `m5a-dpo-train-attempt2-gbk.log`；
勘误节内 attempt-2 事故登记）

### 1.4 attempt-3（00:09:19–00:25:14，**rc=0** ✓✓）

发射前复核：Guard=PASS（重 worker=0）、output_dir NOT-EXIST（零覆写）、GPU 空闲。
装载链日志证据：三数据集依次装载 28,842/2,880/2,880 → 合并 tokenize
**34,602 = 冻结混料成分恒等 ✓**（trainer.py:1470 `Num examples = 34,602`）。

**结果核验**：
- `M5A_TRAIN_RC=0`（规则 30 ✓）；
- 子档 **6 个**（50/100/150/200/250/300）= 300 步/save 50 预期 ✓（≤ keep 20
  全留存，规则 43.5 ✓）；
- 最终模型 + `training_loss.png` / `training_rewards_accuracies.png` /
  `trainer_state.json` / `train_results.json` 落 output_dir 根 ✓。

**曲线 sanity（trainer_state.json 60 个 log 点）**：

| 指标 | 首（step 5） | 末（step 300） | 备注 |
|---|---|---|---|
| train_loss | 0.6500 | 0.0722 | 前 1/4 均值 0.2611 → 后 1/4 均值 0.0797，平稳下降 ✓ |
| rewards/chosen | 0.0550 | 0.2934 | 震荡正值区，无塌缩 ✓ |
| rewards/rejected | −0.0790 | −10.0613 | 强压制（capfix 配方 rejected 侧外科修法已知特性） |
| rewards/accuracies | 0.350 | 0.950 | 上升 ✓ |
| **NaN/Inf 检查** | — | — | **NONE** ✓ |

train_results：train_loss 0.1355 / runtime 900.06s / epoch 0.1387（300/2,163 步）。
**无 NaN/无爆炸 ⇒ sanity 通过（深度分析属后续门禁，规则 43.1 训练曲线不作数）。**

---

## 2. 臂间纪律（GPU 串行）

臂① 完成（00:25:14）→ 等待进程退出 → 复核：**heavy worker=0** ✓、GPU
1.4GB 残留/0% util（桌面底噪）✓ → Guard=PASS（rc=0）✓ → 臂② PREFLIGHT
output_dir NOT-EXIST（零覆写）✓ → 才发射臂②（00:32:09）。

---

## 3. 臂② M5B GRPO（RL 轴）：两次尝试全记录

### 3.1 发射前链（安全闸按设计放行 + 两处勘误修复）

1. **LAUNCH_APPROVED 批准开关**：源码级核证（--help + 源读）确认设计内开关 =
  模块常量（无 env/CLI 参数）；按其设计注释（"评审时改该行并重跑 --dry-run
  复核"，p2rl-impl.md §2 尾注同判）置 `True` + 审计注释（闸逻辑
  `if not LAUNCH_APPROVED: return 1` 原样保留，无绕过无注释代码 ✗✓）。所有者
  已批准双臂发射（60 行已批）⇒ 发射评审条件满足。
2. **--dry-run 复核 #1**（00:09:40，置 True 后）：全绿 rc=0，与 p2rl-impl.md §2
  记录逐项一致。
3. **L534 resume 语义修复**（父代理批准方案 a）：发射前源码核证发现
  `trainer.train(resume_from_checkpoint=True)` 在 transformers 5.8 语义 =
  "必须找到 checkpoint"（trainer.py L1405-1408，get_last_checkpoint 返回 None ⇒
  raise ValueError）⇒ 首发必炸。改为自适应（有档续训/无档 fresh），1 行换 3 行 +
  注释；dry-run 复核 #2 全绿 rc=0 + py_compile rc=0。勘误登记 p2rl 预注册 §12。
4. **attempt-1**（00:26:29，rc=1，零训练步/零产物）：
  `GRPOTrainer.__init__` L406（super().__init__ 之前）
  `model.warnings_issued["estimate_tokens"] = True` ⇒ AttributeError——该属性
  为 transformers 4.x PreTrainedModel 属性，**5.8 全包已移除**（grep 零命中）；
  trl 0.24 的 8 个 trainer 均有此模式。与 L534 同属「从未真跑过的路径」类隐患
  （--run 首次执行才暴露；--dry-run 不构造 GRPOTrainer）。相邻风险同步核证：
  compute_loss_func 字符串（trl L422）安全——trl 覆写 compute_loss（L1642）⇒
  transformers 调用路径（trainer.py L1990）不达，字符串仅以非 None 性参与
  training_step L1928 缩放绕过 ✓；ref model 将以 fp32 装载（+1.2GB vs 预算表
  bf16 假设）⇒ 落 18–21GB 包络上沿，登记不阻塞（OOM 则按预注册 §7.2 降档序）。
  **修复**（父代理批准方案 b，调用侧垫片）：模型装载后、GRPOTrainer 构造前
  `model.warnings_issued = {}`（1 行；HP/奖励/watchdog/安全闸零触碰 ✗✓；venv
  补丁机制被否——既有两补丁定位是 import 链断裂（调用侧无解），本件调用侧可解）。
  勘误登记 p2rl 预注册 §12 续（现场/根因/diff/覆盖面缺口/相邻核证）。dry-run
  复核 #3（00:31:22）全绿 rc=0 + py_compile rc=0。
5. 重发射前 Guard=PASS + GPU 空闲（worker=0）+ PREFLIGHT NOT-EXIST 复核 ✓。

### 3.2 attempt-2（00:32:09–00:42:55，**rc=0** ✓✓）

**结果核验**：
- `M5B_TRAIN_RC=0`；
- 子档 **12 个**（25/50/75/100/125/150/175/200/225/250/275/300）= 300 步/save 25
  预期 ✓，save_total_limit 20 ≥ 12 全留存（规则 43.5，预注册 §7.3 核算 ✓）；
- 最终模型落 output_dir 根（model.safetensors + tokenizer + generation_config）；
- train_results：train_loss −0.00541（dapo 损失型近零属正常）/ runtime 641s /
  步速 ~2.1s/步（快于 §7.2 保守估 4.5–5.5s/步）；GPU 峰值 ~17.6GB/98%（fp32
  ref 在内，包络内 ✓）；训练结束后 heavy worker=0、GPU 释放 ✓。

**熵与 watchdog 遥测（p2rl-impl.md §4.6 监控项，CollapseWatchdog 未触发 ✓）**：

| 遥测项 | 读数 | 判读 |
|---|---|---|
| entropy 走向 | 首 0.4824 → 末 0.5636；min 0.4602 / max 0.6632；前 1/4 均值 0.5285 → 后 1/4 均值 0.5369（60 个 log 点） | **稳定无塌缩** ✓（即停线 = 早段参考 ×0.35 ≈ 0.18，全程未近线） |
| think 泄漏率 | **0/2432 = 0.00%**（watchdog 累计） | 无 `<think>` 泄漏 ✓（§7.4② 预注册开口项闭环） |
| 截断率 | **4/2432 = 0.16%**（watchdog 累计；completions/clipped_ratio 末值 0.0） | 个别截断，交 D 分量罚（设计内）✓ |
| **en 分桶 D=−1 率** | **2/834 = 0.24%**（孤立事件 step 170/175；D 分布 +1.0×829 / +0.5×3 / −1.0×2） | 无聚集、无异常 ✓（§4.6 裁决线未触发，不代读） |
| zh 分桶 | 不可判（CJK 行内裁剪致池匹配失败：nomatch 1896/lossy 64/多义 112） | 如实登记；§4.6 监控项本为 en 侧 |
| 零方差组率 zv | 波动 0–0.25，末 0.0（即停线 >50% 连续 3 窗） | 远低于线 ✓ |
| kl | 末 0.0024（β=0.04 KL 锚有效） | 锚定 ✓ |
| reward | 0.2353 → 0.0611（组内归一后优势空间，非绝对质量） | 登记不判读 |

en 分桶 D=−1 率方法学登记（`scripts/_tmp_m5b_telemetry.py` →
`reports/logs/m5b-telemetry-extract.log`）：log_completions 的 rich 表样本
3,904 条 → 表内 prompt/completion 为 batch_decode(prompt_ids,
skip_special_tokens=True)（trl grpo_trainer.py L1470-1471，ChatML 标签剥离）→
末 user 轮归一化键匹配池行 → `p2rl_reward.reward()` 分量级 D 评分。en 样本
（ASCII 词折行近无损）可判 834；含 '…' 行内裁剪的 completion 剔除 614（偏差
方向 = 可能低估 D=−1）；多义剔除 384。样本级估计，非全量；深度分析属后续门禁。

---

## 4. 纪律合规记录

- **零覆写**：两臂 output_dir 发射前均 NOT-EXIST（每attempt前复核）；冻结混料
  `data/m5a-run/train.jsonl` sha256 `ee181598…` 全程未动（发射前后双复核 ✓）；
  manifest.json 零改动。
- **失败处置**：臂① attempt-1/2 失败 ⇒ 臂② 未启动（对照保护 ✗✓）；每次失败
  均完整取证 + 保全日志 + 报父代理裁决后按批准路径修复，无擅自越权改预注册件。
- **GPU 串行**：臂间 worker=0 + Guard=PASS + GPU 0% 三重确认；臂② 后释放确认。
- **日志保全**：全部 6 份发射/复核日志 + 审计日志 + 遥测日志在
  `reports/logs/`（attempt-1/2 分别存档 `-attempt1-casterror` /
  `-attempt2-gbk` / `-attempt1-warnings-issued`）。
- **launch_audit**：修复链完成后 10/10 PASS（§1.2 第 5 步）。

## 5. 勘误与登记汇总（本发射新增）

| # | 文件 | 性质 |
|---|---|---|
| 1 | `configs/m5a-dpo-probe.yaml` | dataset 键 → 三数据集列表（唯一改动键；sha256 `c0151436…54`） |
| 2 | `data/m5a-run/dataset_info.json` | 加性注册三条目（ASCII 约束；终版 sha256 `5761661…f4`） |
| 3 | `reports/m5a-preregistration.md` §7 | 勘误节：装载机制变更 + attempt-2 GBK 事故 + 同病警告 |
| 4 | `scripts/run_p2rl_grpo.py` | ① LAUNCH_APPROVED 按设计置 True（审计注释）；② L534 resume 语义修复（方案 a）；③ warnings_issued 调用侧垫片（方案 b）——HP/奖励/watchdog/安全闸零触碰 |
| 5 | `reports/p2rl-grpo-preregistration.md` §12 + §12 续 | 两件「从未真跑过的路径」类隐患留档（现场/根因/diff/dry-run 覆盖面缺口 + 后续 runner 设计参考） |
| 6 | `scripts/_tmp_m5a_multids_smoke.py` / `scripts/_tmp_m5b_telemetry.py` | 诊断脚本（三源装载冒烟 / 遥测提取，方法学留档，可退役） |

**同病警告（不阻塞，供所有者处置）**：同僚 P2.9 集成件 `m5-calib-probe.yaml`
指向 `data/m5-run/dpo_m5_calib.jsonl`（与本混料 sha256 `ee181598…` 字节恒等的
孪生件）⇒ 单文件 dataset 装载发射必现同款 CastError；需同款多数据集装载勘误
（并守 dataset_info.json 纯 ASCII 约束）。

**「从未真跑过的路径」类隐患两件（供后续 runner 设计参考，详 p2rl 预注册 §12）**：
静态正确性（注释意图）与运行动态语义（transformers 实参契约）的偏差只有真发射
或发射前源码级核证才能暴露；发射闸放行前的核证面应含训练循环关键调用的实参
契约核对（train/resume、save/load、trainer __init__ 的模型属性前置条件），或提供
一次性 smoke-launch 模式（1 步即停）补覆盖。

---

M5-LAUNCH=DONE
