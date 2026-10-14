# M3 DPO 发射 Runbook（机械执行版）

> ## ⚠ 2026-09-30 晚更正（父代理实测命令行）
>
> **M3 实际运行的配置是 `configs\m3-dpo-final.yaml`，不是 `configs\m3-dpo.yaml`。**
> 实测命令行：`llamafactory-cli train J:\Projects\llm_for_sec\configs\m3-dpo-final.yaml`
> 命令行实证与盘上旁证（5 个 checkpoint、间距 100、`total_steps=1803 = 28,842/16`）一致。
>
> 本文件原先在 6 处指向 `configs\m3-dpo.yaml`，而**那份配置是未被使用的废弃稿**，
> 其 `model_name_or_path` 指向 **`qwen3-06b-sec-m25-full`** —— 该基线已被裁决为
> **FAIL(G2) 且其 PASS 不可采信**。照原文执行收尾绑定会**把 M3 的谱系记录写错**
> （记为从 m25-full 出发、用旧数据集 `dpo_m3.jsonl`）。
> 已按实际值更正：base = `checkpoints\soup-needlefix-a050`、
> mix = `data\lf\dpo_m3_final.jsonl`、`save_total_limit = 5`（原写 2）。
>
> 依据与完整差异见 **`reports/m3-actual-config-correction.md`**。


> 用途：**C 路补齐裁决为"成立"**后，按本文件顺序执行即可发射 M3，无需再决策。
> 撰写：2026-09-30（M2.5 训练窗口内预置）；依据 `reports/m3-dpo-readiness.md`、
> `docs/07-m3-preference-recipe.md` §2.2、`docs/research/grpo-feasibility.md`。
> **若裁决非"成立" → 不走本文件**（见 §0 的条件分支）。
>
> **2026-09-30 改判记录**：原 §0 挂 `reports/m25-exit-verdict.json` 的 v1/raw FAIL——
> 该文件是**口径污染**产物（raw completion 提示格式），已作废为历史对照。
> 依据：① 部署格式重测显示 raw 口径把 SFT 攻击成功率**高估 5–10 倍**；
> ② 用户 2026-09-30 裁决 M3 起点走 **C 路**（m2-calib + 短程定向补齐，
> 以未见载体门禁为验收），而非 m25-full。详见
> `reports/c-path-topup-preregistration.md` 与 `reports/c-path-topup-verdict.md`。

## 0. 门禁前提（缺一不可）

- [ ] `reports/topup-verdict-<变体>.json` 的 `decision` 含 **"C 路成立"**（主判据通过）
      ——**唯一**决定 M3 起点的判据，来自预注册
      `reports/c-path-topup-preregistration.md` §3/§4（`scripts/topup_verdict.py` 机械执行）
- [ ] 同仪器基线齐备：`reports/scored-chat-gen-{m2calib,m3base-topup-e*}-v2.json`
      （v0.3-gen **258 条**；若门禁集扩容/更换，基线必须**同仪器重测**）
- [ ] 判定器 v2 部署格式产物：`reports/verdict-<变体>-<tag>.json`（`VERDICT=PASS`，
      **零 missing / 零 undecided**）；`--forbid-discarded-bases` 打开
- [ ] `reports/m3-dpo-readiness.md` 四项 B 项已勾（B3 超参定稿 / B4 工具链 / 数据复核 / docs 同步）——**均已完成**
- [ ] 若 G4 行为保持判 FAIL（即 `overwrite` 面的 ORR 超阈）→ 发射前把 `configs/m3-dpo-final.yaml`
      的 `pref_beta` 由 0.1 升到 **0.2**（预先约定好的条件旋钮），**其余不动**
- [ ] **条件分支（预注册 §4 已定，机械执行）**：
      - 裁决 = "C 路成立" → 起点用 C 路产物（§1 的 `--start-model` 照写）；
      - 裁决 = "H0 成立 / 补齐无效" → **回退选项 A**：起点改为
        `checkpoints\qwen3-06b-sec-m2-calib`，其余步骤不变（并在 docs/01 §7.1 登记该结论）；
      - 裁决 = "PENDING" → **不得发射**（缺输入，fail-closed）

## 1. 发射前预检（CPU，秒级）

```powershell
# 续训前提 + 检查点状态（内含今天实证的隐性约束校验）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_auto_restart.ps1 -Check `
  -Config 'configs\m3-dpo-final.yaml' -OutDir 'checkpoints\qwen3-06b-sec-m3-dpo'
# 期望：PREFLIGHT=PASS（overwrite_output_dir_not_true / resume_from_checkpoint_unset / stage_ok）
```

```powershell
# 数据绑定（发射时留档；M3 无审计基线 → --manifest-rows 0 跳过行数断言）
# 起点按 §0 的条件分支填：C 路产物（e1 或 e2）或回退 A（m2-calib）
python scripts\bind_m25_run.py --tag m3 `
  --mix data\lf\dpo_m3_final.jsonl `
  --config configs\m3-dpo-final.yaml `
  --start-model checkpoints\qwen3-06b-sec-m3base-topup-e1 `
  --outdir checkpoints\qwen3-06b-sec-m3-dpo `
  --out reports\m3-run-binding.json --manifest-rows 0 --zh -1
```

> 注：`bind_m25_run.py` 已参数化，默认值即 m25（现有调用行为不变，已回归验证）；
> M3 用上面的显式传参。DPO 数据的 user 侧即 prompt，`--zh -1` 关闭中文占比断言。

## 2. 发射（GPU，独占）

> ### ★★ 步骤 2.0（**强制门**）：判别轴审计（规则 33 / docs/01 §11.32）
>
> **★2026-10-06 更正**：本步原先说"契约共模 ⇒ 不受保护"是**错误诊断** ✗。
> 修正后的门从 `conversations` 读**真实 prompt** 逐对判定强制与否，
> 并让 `action`/`verdict` 子键**继承父维度**（VERDICT 行）的强制状态
> —— 该格式块是**原子**的 ✗；B 类口径由**字符**改为 **token**（规则 37.1）。
> **现读数：`AUDIT-DPO-AXES=PASS rc=0`** ✓
> 详见 `reports/token-level-rootcause-and-prescription.md`。
>
> ```powershell
> & 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe' `
>     scripts\audit_dpo_discriminative_axes.py `
>     --data data\lf\dpo_m3_final.jsonl `
>     --budget-tokens 512 `
>     --json-out reports\dpo-axes-audit-m3.json
> # 期望：AUDIT-DPO-AXES=PASS（rc=0）
> # 若 rc≠0 ⇒ ★禁止发射★：按报告的 A 类（prompt **未强制**却两侧都含 ⇒ 真共模）
> #           与 B 类（chosen token 中位超预算）修数据，并重新登记。
> ```
>
> ### ★★ 步骤 2.0c（**强制门，新增**）：偏好数据逐类 token 长度混杂（规则 37 / §11.36）
>
> **★这才是 M3 真正的数据缺陷所在** ✓。判据：任一类同时满足
> 「chosen/rejected **token** 中位比 > 1.2」且「chosen 更长比例 > 80%」
> ⇒ 该类的偏好梯度**主要来自长度**而非内容 ⇒ 必须长度匹配后才可入训 ✗。
>
> ```powershell
> & 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe' `
>     scripts\audit_dpo_length_confounding.py `
>     --data data\lf\dpo_m3_final.jsonl `
>     --json-out reports\dpo-length-audit-m3.json
> # 期望：AUDIT-DPO-LENGTH=PASS（rc=0）
> # 现读数：FAIL —— 5 类 / 6,540 对（22.7%）
> #   carrier_inject_obedient 比 4.12、carrier_inject_hollow 4.88（均 100% chosen 更长）
> #   carrier_clean_overrefusal 1.45、refusal_quality 1.27、calibration 1.58
> # 修法：对这 5 类做**长度匹配** —— ★只补足较短一侧的长度，**不动语义** ✓
> #       · carrier_inject_obedient：把"服从"的回复写详尽（真服从也会长篇汇报）
> #       · carrier_inject_hollow  ：改为「冗长但空洞」（**推论 37.2**：其 rejected
> #         原本是"简短且格式正确"的拒绝 ⇒ 教的是"短=坏"，而应教"空洞=坏"）
> #       · carrier_clean_overrefusal / refusal_quality / calibration：同样补足长度
> #       ★禁止的修法：把 rejected 或 chosen **砍短** ✗（会抹掉非长度信号，比不修更糟）
> ```
>
> **★并且修完必须复验非长度信号仍在（推论 37.3）** —— 四道检查里的第四道：
>
> ```powershell
> & 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe' `
>     scripts\audit_dpo_nonlength_signal.py
> # 期望：每个（曾混杂的）类至少有一个 **分离度 ≥0.95** 的非长度维度 ✓
> # 现读数：5 个混杂类**都有 100% 干净的非长度信号** ✓（action 完全分离、
> #         findings 有无分离、calibration 的 verdict:null 0%/60%）
> # ⇒ 数据**可用**，只需消长度差，**不需重新生成** ✓
> ```
>
> **★"两道门"现为三道**：2.0（规则 33）、**2.0c（规则 37）**、2.0b（规则 36）。
> `AUDIT-DPO-AXES=PASS` **不等于**数据干净 —— 长度混杂由 2.0c 单独把关 ✗。
>
> ### ★★ 步骤 2.0b（**强制门**）：S1 入训三族结构审计（规则 36 更正版 / docs/01 §11.35）
>
> **★2026-10-06 晚更正（两次）**：
> 1. 本步原先指向 `data/heldout/v0.5-topup-families/`（**评测集**）✗ ——
>    真入训文件是 **`data/sft/m2.5-staging/*.jsonl`**。
> 2. 原处方（"补不含契约的负样本"）**是错的** ✗✗ ——
>    `scripts/check_prompt_contract_mandate.py` 证明三族 prompt 侧
>    **100.00% 要求"以 VERDICT 行结尾"** ⇒ 目标 100% 合规是**正确行为** ✓。
> 3. **根因方向也写错过** ✗：token 实测后更正为
>    **把预算对齐到数据分布**（512），**不是**"把数据压到预算里" ✓ ——
>    因为长度分布是生成器**刻意定义的设计意图**，而 96 只是 `baseline_eval.py`
>    的一个 CLI 默认值，从未与数据对齐过 ✗。
>
> **token 实测**：`t2_mechanism` p50=**380**/max=576、`doc_structure` 228/309、
> `t9_phish_expand` 146/276；覆盖 @96 = **0.0% / 0.0% / 35.0%** ✗；
> @**512** = **97.2% / 100% / 100%** ✓。
> 详见 `reports/token-level-rootcause-and-prescription.md`。
>
> ```powershell
> & 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe' `
>     scripts\audit_s1_training_files.py
> # 期望：AUDIT-S1-TRAINING=PASS（rc=0）
> # 若 rc≠0 ⇒ ★禁止发射★：按推论 36.3 同时报告
> #           prompt 要求率 / 合规率 / 长度-预算比（★一律 token 口径）。
> # ★错误处方（勿用）：给三族加"不含契约行"的负样本 —— 契约是 prompt 强制的，
> #   加负样本 = 教模型违反 prompt 的格式指令，比现状更糟 ✗✗。
> ```
>
> **★"交付 ≠ 可入训"**：docs/01 L260 记的 A5 欠账（"T2 已交付 1,200 行但未入训"）
> 的**结清条件是"预算与数据对齐"**（512），**不是"补足行数"，也不是"砍短数据"**
> —— 即 **推论 36.4 的更正版**：对齐方向是"把预算提进数据分布"，不是"把数据压进预算" ✓。
> **★诚实备注**：`t2_mechanism` 最大 576 > 512 ⇒ 仍有约 **2.8%** 的长目标
> 在推理时会被截断（训练不受影响，用 `cutoff_len`=4096）。属可接受残差，但**须登记**，
> 不得说成"已完全解决" ✗。

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:HF_HOME='J:\Projects\llm_for_sec\.cache\huggingface'
$env:TORCH_HOME='J:\Projects\llm_for_sec\.cache\torch'
$env:HF_HUB_OFFLINE='1'
$env:PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True'
& 'J:\Projects\llm_for_sec\.venv\Scripts\llamafactory-cli.exe' train configs\m3-dpo-final.yaml `
  *> 'J:\Projects\llm_for_sec\reports\logs\m3-dpo.log'
```

- **必须**作为 managed background job 启动（可被 `job_output` 收集、可 `job_kill`）。
- 启动后 60 秒内核对：日志出现 `Resuming training from` **则说明误续了别的检查点**（首跑不该出现）；
  正常首跑应打印数据集注册与优化器步数（`num_train_epochs=1.0` / 47,948 对 / bs1×accum16）。

## 3. 武装崩溃保险（独立后台作业）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_auto_restart.ps1 `
  -Config 'configs\m3-dpo-final.yaml' -OutDir 'checkpoints\qwen3-06b-sec-m3-dpo' -MaxRestarts 3
```

保险会内置校验续训前提；重启时自动核对 `Resuming training from …checkpoint-NNNN` 并记录到
`reports\m3-dpo-restart.log`。**注意主日志在重启后会冻结**（新进程写 `<name>-restart<N>.log`）。

## 4. 派发看门狗（独立 agent）

派发要点（**DPO 与 SFT 的画像不同，勿照搬 m25 的带**）：

- **首次运行无基线**：M3 DPO 从未跑过 → 头 1 小时的任务是**建立基线**（步时/显存/功率/util
  的稳态带），此后按该带判异常；
- **显存结构不同**：DPO 同时驻留 policy + reference（`pref_beta=0.1` 非零故加载参考模型）
  + 优化器态 → 显存预期**高于** m25 SFT 的 21.3 GiB，需实测记录；
- 报告周期 30-45 分钟；合取螺旋判据（util≥95% **且** 功率低 **且** 步时 ≥1.5×）；
- 每轮核对重启协议三条（重启日志行 / 检查点目录增长 / 进程链 PID 变化）；
- 完成判据：`checkpoints\qwen3-06b-sec-m3-dpo\train_results.json` 出现。

## 5. 收尾（训练完成后）

```powershell
# 结束态绑定（含 train_results 与全部 ckpt）
python scripts\bind_m25_run.py --tag m3 --mix data\lf\dpo_m3_final.jsonl `
  --config configs\m3-dpo-final.yaml --start-model checkpoints\soup-needlefix-a050 `
  --outdir checkpoints\qwen3-06b-sec-m3-dpo --out reports\m3-run-binding.json `
  --manifest-rows 0 --zh -1
```

评估三项（与 M2.5 同规格，**参照系 = `soup-a050`**）：

> ⚠ **2026-09-30 晚更正**：本节原写"参照系换成 **m25-full**"，与**实际执行的评测链**
> 不符。`scripts/eval_m3_post.ps1` 的 `$Baseline` 默认值是 **`soup-a050`**
> （第 7 步 `topup_verdict.py --variant m3-dpo --baseline soup-a050`），
> 且预注册登记的"起点水位 **70/168**"逐位等于 `soup-a050` 的契约保留率
> ⇒ **正确的参照系是 `soup-a050`**。`m25-full` 已被裁决为 FAIL(G2) 且 PASS 不可采信，
> 不能作为 M3 的参照系。

1. 行为：heldout v0.2.1 × 判分器 v2 + tool_output + 多点对照（c1-full/m15/m2-calib/m25-full/**soup-a050**/m3-dpo）；**判据基准 = `soup-a050`**；
2. PPL：v0.3 门禁口径 + v0.4 干净口径，**基准对照 `soup-a050`**；
3. 包一致性（R1）：`python scripts\pack_consistency.py --run --model checkpoints\qwen3-06b-sec-m3-dpo --n 40`
   → 分化率应与 **`soup-a050`** 同量级（防 DPO 把包条件化学平）。

**出口判定（参照系已参数化，2026-09-30 实施并验证）**：

```powershell
python scripts\m25_exit_verdict.py --tag m3dpo `
  --ppl-base m25full --longctx-base m25full --behavior-base m25full
```

- G1 仍读 `scored-m3dpo-tooloutput-v2.json`（8 条同类未见载体）；
- G2/G3/G4 的基线分别换成 `ppl-m25full-v0.3.json` / `longctx-m25full.json`
  / `scored-m25full-v2.json`——**这三份正是 M2.5 评估链的产物**，故 M2.5 收尾后
  文件齐备，M3 判定可直接复用；
- 判定器新增 `--ppl-base/--longctx-base/--behavior-base`（默认 m15/m2full/m2full，
  **M2.5 自身调用行为逐字未变，已回归验证**）；缺件路径也已修复（原 `gates["G2_general_ppl_vs_m15"]`
  硬编码键在换参照系时 KeyError 崩溃）→ 缺件只报 PENDING，不崩。

## 6. 纪律（本次新增，勿破坏）

- ❌ **不得**在训练配置里加 `overwrite_output_dir: true`——会让崩溃保险的重启从 step 0
  重跑并覆盖检查点（LF `hparams/parser.py:612-627`）。
- ✅ 发射与收尾各跑一次数据绑定脚本（`bind_*` 模式）；
- ✅ 训练全程可无损中断（全参 + optimizer/scheduler/rng 全状态检查点，`save_total_limit=5`）。
