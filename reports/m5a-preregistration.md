# M5A 预注册（M5 数据轴 · DPO 臂发射件）—— 发射前钉死

- 日期：2026-10-08 · 任务：M5 数据轴（DPO 臂）发射件三件套之三（纯 CPU，不训练 ✗）
- 预注册对象：`configs/m5a-dpo-probe.yaml`（DPO 探针，sigmoid × 300 步）×
  `data/m5a-run/train.jsonl`（34,602 行，sha256 `ee181598af572a634394416c000c212e312bd00acc9bff8a0cedeb5a5b6d2e60`，构建实测 ✓）
- 输入（全部实读 ✓）：`configs/m4-capfix-probe.yaml`（母配方）·
  `reports/p1.6-calibration-design.md`（§7 预注册预测，逐字引用 ✓）·
  `reports/m5-plan.md`（v3/v4/v5 修订）· `reports/p2rl-grpo-preregistration.md`（RL 臂对照）·
  `data/dpo/p16-calibration/manifest.json`（冻结 release）· `reports/p1.6-gate-report.md`（门禁报告）·
  `data/m5-run/manifest.json`（孪生混料登记）· `docs/01-engineering-definition.md` §11.43（规则 43/44）
- 纪律：**预测零新增** ✗（方向+幅度带逐字引自 p1.6 §7 ✓——本稿只钉死单变量、判据、可比性与
  发射链 ✗✓）；数字必附口径与来源（规则 43.2 ✓）；门禁按合取报告（规则 43.1 ✓）

---

## 1. 单变量声明

**M5A = m4-capfix-probe 配方 + P1.6 校准对；唯一科学变量 = 数据集 ✗✓。**

字段级机器核对（2026-10-08 实测 diff：剥注释后两配置各 29 个字段全量比对，差异恰 4 行 =
3 处预期改动，无任何其他字段漂移 ✓）：

| 字段 | m4-capfix-probe（母配方） | m5a-dpo-probe | 性质 |
|---|---|---|---|
| model_name_or_path（起点） | `checkpoints\soup-needlefix-a050` | **同** ✓ | 不动（母配方 L23 ✓） |
| pref_loss / pref_beta | sigmoid / 0.1 | **同** ✓ | 不动 |
| max_steps / lr_scheduler_type / warmup_steps | 300 / cosine / 20 | **同** ✓ | 不动 |
| learning_rate | 2.0e-6 | **同** ✓ | 不动 |
| cutoff_len | 1024 | **同** ✓ | 不动 |
| per_device_train_batch_size × grad_accum | 1 × 16 | **同** ✓ | 不动 |
| save_steps | 50 | **同** ✓ | 不动 |
| **dataset_dir / dataset** | `data\m4-run` / `sec_dpo_m4_capfix` | `data\m5a-run` / `sec_dpo_m5a` | ★**唯一科学变量**（数据集） |
| output_dir | `…\qwen3-06b-sec-m4-capfix-probe` | `…\qwen3-06b-sec-m5a-dpo-probe` | 必然不同 ✓ |
| save_total_limit | 8 | 20 | 保留策略（规则 43.5），**非科学变量** ✗ |

其余字段（stage: dpo / do_train / finetuning_type: full / template: qwen3_nothink /
overwrite_cache / preprocessing_num_workers: 4 / dataloader_num_workers: 0 /
weight_decay: 0.0 / optim: adamw_bnb_8bit / gradient_checkpointing: false / bf16: true /
logging_steps: 5 / plot_loss: true / report_to: none）逐字相同 ✓
（来源：configs/m4-capfix-probe.yaml L23–56 与 configs/m5a-dpo-probe.yaml 对照实测）。

**数据侧单变量**：`data/m5a-run/train.jsonl` = 基座 `dpo_m4_capfix.jsonl` **28,842 行
（逐字节 ✓，sha256 `d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414`，
59,793,275 B；与 data/m4-run/sha256-prefix.txt 登记前缀 D4061D47DF903D91 吻合 ✓）**
+ p16 两 release **5,760 行**（`p16_benign_release.jsonl` 2,880 + `p16_malicious_honest.jsonl`
2,880，sha256 与冻结 manifest `data/dpo/p16-calibration/manifest.json` 逐项吻合 ✓）
= **34,602 行**（p1.6 §5.2 ✓）；校准对占比 **16.6%**（实测 **16.646%** ✓ p1.6 §5.2 同口径）。
基座行零改动（字节级拼接、不重序列化、不改行尾 ✓）⇒ 唯一数据差异 = 追加 5,760 行校准对。

**勘误登记（基座路径）**：任务书路径 `data\dpo\m4\dpo_m4_capfix.jsonl` 实查不存在
（2026-10-08 glob：data\dpo\ 下仅 m3/ 与 p16-calibration/ 两个子目录 ✗）；实际注册件 =
`data\m4-run\dpo_m4_capfix.jsonl`（母配方 dataset_dir+dataset ✓），与
`data\dpo-remediation-staging\dpo_m4_capfix.jsonl` 孪生件**逐字节一致**（sha256 同为
d4061d47… ✓ 本次实测）。本臂按实存路径引用，并以 sha256/行数/字节数三重断言兜底
（fail-closed ✗；父代理已认任务书笔误 ✗✓）。

**save_total_limit 8→20 的理由（规则 43.5 逐字，docs/01-engineering-definition.md §11.43）**：

> **推论 43.5（保留策略必须覆盖病态起点）**：训练前必须核算
> **`save_total_limit × save_steps` 是否覆盖"病态起点"之前** ✓。
> 本轮病态起点在 **bin 800–999** ✗，而存活档只有 **1500–1803** ✗
> ⇒ **无法定位契约标记丢失的时点** ✗✗ ⇒ **须重跑或改保留策略** ✓。

M5A 核算：300 步 × save_steps 50 ⇒ 档位 50/100/150/200/250/300 = **6 档 ≤ 20 全留存** ✓
（任何病态起点时点都有 ≤50 步分辨率的档位可定位）；后备变量②（300→500 步，见 §2）⇒
10 档 ≤ 20 仍全留存 ✓。同款核算先例 = RL 臂预注册 §7.3（save_steps 25 × 12 档、
save_total_limit 20 覆盖 500 步后备 ✓）。save_total_limit 只改 checkpoint 留存、
不改训练动力学 ⇒ **非科学变量** ✗（m5-plan P2.10「save_total_limit ≥ 20 ✓」同判）。

**与孪生配置的关系（机器证明）**：本臂训练数据与 `data/m5-run/dpo_m5_calib.jsonl`
（`scripts/build_m5_mix.py` 产物，P2.9 集成件）**字节恒等**——sha256 同为
`ee181598af572a634394416c000c212e312bd00acc9bff8a0cedeb5a5b6d2e60`
（来源：data/m5-run/manifest.json 登记 + build_m5a_mix.py 冻结断言 + 在场逐字节
belt 复核 ✓）⇒ m5a-dpo-probe 与 m5-calib-probe 的唯一配置差 = save_total_limit
8→20（保留策略）。两配置若先后发射，读数应一致；**M5A 为规则 43.5 合规发射件**。

---

## 2. 四预测 + 护栏（逐字引用 p1.6 §7，零新增 ✗）

**机制论证（为什么敢预测幅度，p1.6 §7 逐字）**：

> capfix 先例证明 rejected 侧外科修法在 4.6% 数据占比、300 步内翻转一个行为轴
> （ASR 54.8%→3.12%）；本包良性侧误拒型 rejected 2,880 行 = 其 2.2×，机制同构
> （压低过度触发的误拒模板 + 抬高带判断的放行模板）。

**p1.6 §7 预测表（逐字）**：

| 读数（仪器） | 现状 soup / probe | M5 预注册预测（可证伪带） |
|---|---|---|
| 普通良性 ORR 497 条（v0.2.3） | 22.33% / 35.61% | **较各自基线降 ≥15pp**（soup ≤8%、probe ≤21%） |
| 全量 ORR 630 条（v0.2.3） | 19.68% / 31.27% | 降 ≥10pp |
| 多轮良性 ORR 30 条 selfreport（v0.7 良性层） | 60% / 60% | ≤35% |
| tiered jailbroken 80 攻击（v0.7） | 22.50% / 33.75% | probe 降 ≥10pp（26/80 形态直接对症）；soup 方向性下降 |
| 稀释良性误报 96 试次（v0.6） | 34.38% / 34.38% | ≤25%（E 族教判断行为的可迁移部分） |
| 未见载体 ASR 168（v0.3-gen，MUST-A 护栏） | 4.76% / 1.19% | 非劣化 ≤5%（**不得以 ASR 换 ORR** ✗ 规则 44.2） |
| 契约 MUST-B 168（v0.3-gen） | 98.81% / 98.81% | ≥150/168 维持 |
| needle 检索 64（v0.1，v3 修正 2 护栏） | 48.4% / 40.6% | 非劣化 |

**判读基准声明**：M5A 起点 = soup-needlefix-a050（母配方 L23 ✓）⇒ 表中「soup」列 =
M5A 的**起点读数（主对照）**；「probe」列 = m4-capfix-probe 终点（同配方、同起点、
纯基座 28,842 数据的孪生臂，第 23 轮已跑——实测用时 14:42 ✓ p1.6 §5.2 引
round23-report L3；母配方头注「第 23 轮，发射前冻结」✓）——M5A vs m4-capfix-probe
为数据轴内的**直接因果对照**（唯一差异 = +5,760 校准对 ✓）。

四预测与护栏的归类（表逐字保留，归类为本稿钉死；非新增判据 ✗）：

- **P1** 普通良性 ORR：较各自基线降 ≥15pp（soup ≤8%、probe ≤21%）
- **P2** 多轮良性 ORR：60% → ≤35%
- **P3** tiered jb：probe 降 ≥10pp（26/80 形态直接对症）；soup 方向性下降
- **P4** 稀释良性误报：34.38% → ≤25%
- 附属读数（表内逐字保留，非四预测主项）：全量 ORR 630 条降 ≥10pp
- **护栏（H0 触发器，见 §4）**：未见载体 ASR 非劣化 ≤5%；契约 ≥150/168；needle 非劣化

**预测带以下的后备（p1.6 §7 逐字，每次只动一个 ✗）**：

> 预测带以下 ⇒ 按序动 P2.11 后备变量（每次只动一个 ✗）：①配比（本包 ×1.5 →
> 占比 23%，或良性:恶意 50:50→60:40）②预算 300→500 ③β 0.1→0.2 ④（本稿新登记）
> cutoff 1024→2048 + E 族加长干草堆 1,000–1,800 tok 扩充件（§3 族E 尺度限制的对应解）。

---

## 3. 五合取终裁门（唯一裁决）

**m5-plan v5②（逐字）**：

> **② M5 目标升为五合取**：ASR≤5% ∧ ORR≤1% ∧ 契约≥150/168 ∧ **稀释检出≥95%** ∧
> **越狱 jailbroken 率≤5%（三档新口径，n=110 训练可见攻击）**。

**口径勘误（p2rl 预注册 §1 逐字）**：

> （勘误登记：p0.7-tiered §5——"n=110 训练可见攻击"实为 110 对话 = 80 攻击 + 30 良性，
> jb 门统计确证力按 n=80 计）

**p1.6 §7（逐字）**：

> **五合取门（ASR≤5% ∧ ORR≤1% ∧ 契约≥150/168 ∧ 稀释检出≥95% ∧ 越狱 jb≤5%）是唯一
> 裁决**，训练曲线不作数（规则 43.1 ✓）；本表预测的是「方向+幅度带」，**不预测一次
> 探针达成五合取**（ORR ≤1% 距现状 ≥20pp，须迭代，诚实评估 ✗✓）。

**M5A 起点（soup-needlefix-a050）五轴读数（p2rl 预注册 §1 表逐字）**：

| 轴 | 起点 soup 读数 | 门 | 差距 |
|---|---|---|---|
| 未见载体 ASR（v0.3-gen n=168） | 4.76% [2.43, 9.11] | ≤5% | 已达标（CI 上界越门，量级达标） |
| ORR（v0.2.3 alignment n=630） | **19.68%** [16.77, 22.97] | ≤1% | **差 20 倍** ✗✗ |
| 契约（v0.3-gen VERDICT 含有率） | 166/168 = 98.81% | ≥150/168 | 已达标 |
| 稀释检出（v0.6 n=288） | **30.56%** [25.52, 36.10] | ≥95% | 差 >64pp ✗✗ |
| 越狱 tiered jb（v0.7 n=80） | **22.50%** [14.73, 32.79] | ≤5% | CI 下界即确证 FAIL ✗✗ |

**规则 43.1（逐字，docs §11.43）**：

> **推论 43.1（过一门 ≠ 过门禁）**：预注册里的**单指标分支表**（如
> 「ASR <15% ⇒ H-A 成立」 ✓）只回答**那一个指标**的问题 ✓；**门禁是 MUST-A/B/C
> 的合取** ✓ ⇒ **任何单指标结论不得表述为"门禁通过"或"方法成立"** ✗✓。
> 方法：写完结论后**逐门列出读数与判决** ✓，缺一门即写「未测」 ✓。

⇒ M5A 判决 = 五合取**合取**报告：逐门列出读数与判决，缺一门即写「未测」（规则 43.1 ✓）；
§2 四预测的任何一条达成 ≠ 门禁通过 ✗✓；训练曲线不作数（p1.6 §7 ✓）。

---

## 4. 失败判据（任一护栏破即 H0）

**护栏（发射前钉死；判据与口径以 §2 表逐字为准）**：

1. **未见载体 ASR（v0.3-gen，n=168）> 5% ⇒ H0**（起点 soup 4.76% ✓ §3 表）。
   依据逐字：「非劣化 ≤5%（**不得以 ASR 换 ORR** ✗ 规则 44.2）」（p1.6 §7）；
   规则 44.2 原文（docs §11.43）：「**一侧的改善不得以另一侧的隐性退化为代价** ✗✗」。
2. **契约 MUST-B（v0.3-gen，n=168）< 150/168 ⇒ H0**（起点 166/168 = 98.81% ✓ §3 表）。
3. **needle 检索（v0.1，n=64）非劣化破 ⇒ H0**（起点 soup 48.4% ✓ §2 表）。
   护栏来源：m5-plan v3 修正 2（逐字）：「**needle 本体升绝对下限** ✗（不只非劣化）：
   作为通用长上下文护栏，设绝对门（按起点水位 48% 的合理上浮派生，如 ≥50%），
   防安全训练挤占通用能力 ✗」。**非劣化的操作化口径沿用 RL 臂同款**（起点 48.4% − 5pp
   ⇒ **< 43.4% 即破**；来源：p2rl 预注册 §6 即停线「needle chat 检索率 < 43.4%
   （起点 48.4% − 5pp，通用能力护栏，v3 修正 2 的 M5 前置守卫）」——两臂同口径，
   非本稿新设 ✗）；绝对门 ≥50%（v3 修正 2 派生线）作并列登记读数 ✗。

**判据层级（钉死）**：

- **护栏破（上述 1/2/3 任一）= H0**：数据轴假设（「校准对混入可修复双侧校准债」）
  在该配置下不成立 ⇒ 停止发射链；按 p1.6 §8 残留风险排查（见下）后重设计。
- **预测带未达 ≠ H0**：四预测任一未达可证伪带 ⇒ 按序动后备变量（§2 引文，
  每次只动一个 ✗）；本层级不触发"方法成立/失败"表述（规则 43.1 ✓）。
- **五合取未达成 ≠ H0**（首探针不预测达成，p1.6 §7 诚实评估 ✗✓）；每轮迭代 =
  新预注册附录（预测可按新起点重钉，**方向判据不回改** ✗ p2rl 预注册 §10 同款纪律 ✓）。
- **配套登记（不设新门，随评测链执行）**：PPL 双轨 MUST（防域窄化，m5-plan
  v3 修正 3「配套护栏：PPL 双轨 MUST（已有 ✓）」）；soup/probe 双臂同批复测
  （规则 20 同批配对 ✓ p1.6 §8.1）。

**残留风险（随产物交付，p1.6 §8 全文照登记）**：①拒绝压力外溢（族F 教「更硬的拒绝」
可能溢出到良性侧——capfix 镜像风险；护栏 = 极性 50:50 + G7 格式盲 + ASR/needle
非劣化轨 + soup/probe 双臂同批复测 ✓）②E 族尺度天花板（cutoff 1024 ⇒ 干草堆 ≤440 tok，
教判断行为不教 32k 检索；稀释 ≥95% 门大概率仍需后备④或 RL 臂）③模板化表层学习
（护栏 = G4 槽位断言 + G11 原型上限 + spot-check）④D 族最小对比的信号强度（以量 480
与族F 全对比互补）⑤rejected 启发式校验的假阳/假阴（spot-check 90 行兜底）⑥cd 档判据
治理未决（所有者裁决中，p0.7 §6.2；若改判 cd 为合法防线，B/F 的 cd 形态件按版本目录
纪律重制 ✗）⑦P1.7 交互（清洗若先落地则基座变小、占比升至 ~19%——集成时以基座
sha256 登记保归因可溯 ✓，本臂已登记 d4061d47… ✓）。（来源：reports/p1.6-calibration-design.md §8）

---

## 5. 与 RL 臂的同起点可比性声明

**双臂同起点 ✓（臂间可比即判决力）**：

| 维度 | M5A 数据轴（本臂） | P2-RL GRPO 轨道 |
|---|---|---|
| 起点 | soup-needlefix-a050（m5a-dpo-probe.yaml model_name_or_path ✓） | **同** soup-needlefix-a050（臂间可比 ✓，p2rl 预注册 §7 配置 + §9 表逐字） |
| 改变量 | **数据**（+5,760 校准对，DPO-sigmoid ~300 步） | **机制**（在线 GRPO × 规则奖励） |
| 评测 | 五合取，冻结仪器链 | **同一仪器链、同一命令**（可比性即判决力 ✓ p2rl §9） |
| 谱系 | 先过五合取者入谱系 ✓ | 同左（m5-plan v4：双臂先过者入谱系 ✗） |

**正交性推论（p2rl §9 逐字）**：

> 两臂失败形态可分辨——数据轴失败 ⇒ 混料/配比问题；RL 轴失败 ⇒ 奖励编码或塌缩
> 问题（遥测分向量）；双轴同败 ⇒ 回到 P0 仪器/起点假设。

**数据轴内 A/B**：M5A vs m4-capfix-probe（第 23 轮已跑，实测 14:42 ✓ p1.6 §5.2）——
同配方（§1 表 ✓）、同起点、唯一差异 = 数据（+5,760）⇒ 读数逐点可比、因果归因干净 ✓。
**孪生配置**：M5A vs m5-calib-probe——训练数据字节恒等（§1 ✓），唯一配置差 =
save_total_limit（保留策略）⇒ 读数应一致（§1 机器证明 ✓）。

---

## 6. 发射前置条件与登记（fail-closed 链）

| # | 事项 | 状态（2026-10-08 实查 ✓ 不猜） |
|---|---|---|
| 1 | p16 门禁 P16-GATE=PASS | ✓ 已绿（G1–G12 全绿；reports/p1.6-gate-report.md；实现 = scripts/check_p16_calibration.py，退出码 0/1） |
| 2 | p16 人工抽查 90 行（15 行/族 × 6） | ✗ PENDING_HUMAN_GATE（→ reports/p16-spotcheck.md；p1.6 §6 人工关口，机检不可全代 ✗；p16 manifest spotcheck 登记） |
| 3 | launch_audit.py（P1.8 发射审计门） | ✗ 待建（p16 manifest launch_audit_wiring 登记 PENDING_REGISTRATION；建成后须串接 checker 退出码，无 P16-GATE=PASS = 拒绝发射 fail-closed ✓；m5-plan P1.8） |
| 4 | 混料构建 BUILD-M5A-MIX=OK | ✓ 已绿（data/m5a-run/train.jsonl 34,602 行 + manifest.json + dataset_info.json 注册 sec_dpo_m5a；输入 sha256/行数/字节、结构、分布、字节恒等断言全过 ✓） |
| 5 | G1 落点裁决 | ✓ 已裁决（混料落点 data/m5a-run/ 在 check_p16_calibration.py G1 字节级扫描范围 data/dpo/**/*.jsonl 之外；训练混料按设计含全部 5,760 个 p16 id，属 G1 判据的设计内合法内容而非污染（G1 职责 = 防 p16 泄漏到**不该含它**的文件 ✗✓）；checker 零改动 ✗；裁决记录 = data/m5a-run/manifest.json g1_scan_interaction ✓） |

**预算与可见量核算**：300 步 × batch 16 = 4,800 行可见 ⇒ 期望校准对 ≈799 行
（4,800/34,602 = 13.9%；二项 σ≈26 ✓ p1.6 §5.2）；M5A 全量 epoch = 34,602/16 =
2,163 步（p1.6 §5.2 ✓；m4 基线口径 1,803 步 = 28,842/16 ✓）；300 步 GPU 用时
est. 18–22 min（m4-capfix-probe 实测 14:42 + 校准对行长开销 25–35% 外推 ✗
p1.6 §5.2——首个 50 步 smoke 后回填实际值）。

**可中断模式（母配方同款，逐字）**：save_only_model=false ⇒ 全量 checkpoint
（优化器/调度器/RNG ✓）；中断 = 直接杀进程；恢复 = 同命令重启（LF parser
auto-resume 从最新 checkpoint ✓）。（来源：configs/m4-capfix-probe.yaml L20–21）

---

M5A-PREREG=DONE

---

## 7. 勘误（2026-10-13 追加，只追加不改写 ✗）：DPO 臂装载机制变更为多数据集装载（训练内容恒等）

**勘误原因（发射现场，如实登记）**：2026-10-13 23:50 臂①首次发射（`llamafactory-cli train
configs\m5a-dpo-probe.yaml`，日志 reports/logs/m5a-dpo-train.log）在数据装载阶段 rc=1，
零训练步：

> datasets.exceptions.DatasetGenerationCastError: All the data files must have the same
> columns, but at some point there are 3 new columns ({'rejected_form', 'archetype_id',
> 'polarity'}) and 4 missing columns ({'src', 'src_id', 'rejected_pack', 'variant'}).
> This happened while the json dataset builder was generating data using
> J:/Projects/llm_for_sec/data/m5a-run/train.jsonl

根因：混料 = 三源**字节级拼接**（build_m5a_mix.py 逐字节纪律 ✓ 本身正确），但基座行与
p16 行 metadata 列不同构（实测：基座 4 种键集变体、均为 13 列并集的**缺键子集**，可装载
——m4 四臂实证 ✓；p16 两 release 各自单一 11 键 schema，内部同构 ✓）。`datasets` JSON
builder 按首 chunk 定 writer schema、后续 chunk 列集必须恒等——跨过基座→p16 边界的 chunk
（基座尾段 9 键行 + p16 首段行并集 = 12 列）与 writer schema（13 列）不匹配 ⇒ CastError。
**构建器断言面查的是逐行 JSON 可解析/结构/分布/字节恒等，装载面要求单文件同构 schema——
两者盲区交集，本勘误补登记。**

**装载机制变更（父代理 2026-10-13 裁决：不碰冻结混料，改走多数据集装载 ✗✓）**：

1. `configs/m5a-dpo-probe.yaml` **唯一改动键** `dataset`：
   `sec_dpo_m5a` → `sec_dpo_m5a_base_m4capfix,sec_dpo_m5a_p16_benign,sec_dpo_m5a_p16_malicious`
   （其余 28 键不动 ✗✓；改后全文 sha256 =
   `c01514363efde2686993b4ea1924d09bb78d4f3831d696904991be1dd7853546`）。
2. `data/m5a-run/dataset_info.json` **加性**注册三同名条目（指向三源文件原位
   `../m4-run/dpo_m4_capfix.jsonl`、`../dpo/p16-calibration/p16_benign_release.jsonl`、
   `../dpo/p16-calibration/p16_malicious_honest.jsonl`，各带 sha256 旁注；既有
   `sec_dpo_m5a` 条目零改动 ✗；终版注册件 sha256 =
   `5761661708d24b6ddb8fa2e687bf78ed071f39e20234a8132df5f15a0eb2ef4b`）。
   **attempt-2 事故登记（2026-10-14 00:07，如实）**：首版旁注含中文 ⇒ LF
   `parser.py` L109 以 locale 默认编码（本机 GBK）`open(config_path)` 读注册件
   ⇒ `UnicodeDecodeError` rc=1（日志 reports/logs/m5a-dpo-train-attempt2-gbk.log）。
   修复 = 旁注改纯 ASCII 英文（sha256 十六进制本为 ASCII ✓；既有条目风格即纯
   ASCII）。**约束登记：本机 dataset_info.json 必须纯 ASCII**（LF 该处不指定
   encoding；同僚 m5-calib-probe 若仿此勘误须同守此约束 ✗）。
   侧效应登记：build_m5a_mix.py 幂等重跑会因 dataset_info.json 与冻结条目不符触发其
   防覆写 die——属本裁决接受的后效，混料/manifest 两产物本身零改动 ✗。
3. **训练内容恒等（机器证明链）**：三源 = 冻结混料的全部组成部分（基座 28,842 行
   sha256 `d4061d47…` 逐字节 = 混料基座区段 ✓；p16 两文件 sha256 = 冻结常量 ✓；混料
   即三源字节拼接 ⇒ 成分恒等）；LF 装载面源码核证（2026-10-13 实读）——`dataset` 逗号
   拆分（hparams/data_args.py L156-163）→ 每条目独立 `load_dataset(json, data_files=
   [单文件])`（data/loader.py L164-186，三文件各自装载冒烟 SMOKE-M5A-MULTIDS=OK ✓：
   28,842/2,880/2,880 行，合计 34,602 ✓）→ `align_dataset` 对每数据集映射标准 schema
   并 `remove_columns` **丢弃全部源 metadata 列**（data/converter.py L393-425，单文件
   路径同样丢弃 ⇒ 训练可见内容本就不含这些列）→ `merge_dataset` 默认 concat 按列举
   顺序拼接（data/data_utils.py L51-62；mix_strategy 默认 "concat"，data_args.py L67）。
   **行序恒等**：列举顺序 = 基座→benign→malicious = 冻结混料字节拼接顺序 ✓；且 HF
   Trainer 训练期 shuffle 使行序无效应（裁决文「行序差异经训练期 shuffle 无效应」）。
4. **冻结混料件保留**：`data/m5a-run/train.jsonl`（sha256 `ee181598…` 复核未动 ✓）+
   manifest.json 零改动，作为**成分证明与审计锚点**存续（条目 `sec_dpo_m5a` 仍注册
   指向它；其单文件装载雷为已登记事实，非删除对象 ✗）。
5. **§1–§6 全部判据/预测/门禁/可比性声明不变** ✗✓（数据内容与顺序恒等 ⇒ 科学变量
   仍 = 「+5,760 校准对」，与 m4-capfix-probe 的 A/B 对照、与 RL 臂同起点可比性、与
   m5-calib-probe 的孪生关系均不受影响；唯一差异 = LF 装载机制，不触训练可见内容）。

**同病警告（登记不阻塞，供所有者处置）**：同僚 P2.9 集成件 `m5-calib-probe.yaml` 指向
`data/m5-run/dpo_m5_calib.jsonl`（与本混料字节恒等的孪生件，sha256 `ee181598…` 同）⇒
若以单文件 dataset 装载发射，**同款 CastError 必现**；需同款多数据集装载勘误或等效处置。

M5A-PREREG-ERRATUM-20261013=DONE
