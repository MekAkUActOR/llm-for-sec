# M3 偏好优化配方（设计骨架 v0.1）

> 状态：**§2.2 超参数已定稿（2026-09-30）**；**§2.2 的"基座"同日经三次定稿，
> 生效态 = `checkpoints/soup-needlefix-a050`（2026-09-30 补记，见 §2.2）**；其余骨架保持。原标注【待 M2 读数】
> 处由 M2 全量跑结果定稿的计划，因方案 A（2026-09-28 用户决议：废弃 m2-full
> 权重、改由 M2.5 回填全量跑 m25-full）顺延为【待 M2.5 出口读数】；§2.2 的
> 超参数不依赖该读数，已按原文区间落地（见 configs/m3-dpo.yaml 定稿注）。
> 上游：docs/01 §3.3（政策条件化偏好对——核心设计）、docs/06（M2 SFT，
> M3 的基线与对照）、docs/policy-packs-v0-draft.md、scripts/score_heldout_v2.py
> （VERDICT 契约，奖励函数底座）。用户 2026-09-26 批准 M3 数据备料与
> M3.5 RLVR 工具链并行启动。

## 1. 定位：SFT 之后还缺什么

M2 交付行为契约（VERDICT 格式、政策条件化映射的离散部分）。M3/M3.5
补三样 SFT 结构性给不了的：

1. **边际案例偏好导航**——带理由拒绝 > 生硬拒绝；professional 详尽有界 >
   过详；序关系而非克隆关系；
2. **对抗泛化**——失败输出作 rejected 侧（模型自己的输出比合成错误答案
   强）；【待 M2 读数：tool_output 探针 + 改述抗性实测决定 M3.5 优先级】
3. **置信度校准**——confidence 字段匹配经验正确率。

## 2. M3：政策条件化 DPO

### 2.1 数据四构成（`data/dpo/m3/`，加工中）

| 构成 | 来源 | 目标占比 |
|---|---|---|
| 政策条件化对 | M2 policy_pairs 提取包间偏好（同查询 × 包翻转 chosen/rejected 对称对） | ≥30%（差异化设计，不被通用对稀释） |
| 储备直通对 | dpo-reserve 59,482 对清洗（hh/cvalues/pku/beavertails） | ~50-60% |
| 拒绝质量对 | 合成：带理由+替代 vs 生硬拒绝（同查询同包） | ~5-10% |
| 校准偏好对 | 合成：诚实弃权 vs 过度自信错误 | ~5% |

排除：hard-floor 行（三包同拒无偏好结构）、方向性不变量行（同理）。

### 2.2 训练配方（LLaMA-Factory stage dpo）

- 基座：~~**C 路补齐产物**（`checkpoints/qwen3-06b-sec-m3base-topup`，待 S0.4 完成后训练）。~~
  **【2026-09-30 三次定稿 / 生效态：基座 = `checkpoints/soup-needlefix-a050`（权重插值产物，产物状态 `accepted`）】**
  （定稿序列：一次 = m25-full → 二次 = C 路补齐产物 → **三次 = `soup-a050`**，即本项。）

  **① "C 路补齐产物作基座"已被机械判定否决（不是"待验收"，是 FAIL）。**
  C 路 e1/e2 在同一台仪器（`data/heldout/v0.3-gen`，**258 条 / 鲁棒性 168 条**，部署格式）上的实测：
  起点 `m2-calib` 的契约保留 **84/168 → e1 8/168、e2 16/168**；未见载体 ASR
  **6/168 → e1 101/168、e2 108/168**（p≈1e-12）⇒ **主判据 FAIL，H0 成立，回退选项 A**。
  故 `qwen3-06b-sec-m3base-topup{,-e1,-e2}` **不得作为 M3 起点**：其权重按 `docs/01 §11` 规则 4
  登记为 **`discarded`**（`scripts/m25_exit_verdict.py` 的 `ARTIFACT_STATUS`；
  `reports/c-path-topup-verdict.md` §1/§5）。崩塌形式是**输出契约失效**而非"服从注入"
  ——e1/e2 的"攻击成功"里 **93–95% 根本没有 `VERDICT` 行**。

  **② 定稿依据（用户 2026-09-30 裁定"先找加法不伤泛化的配方" → 配方搜索 R1 权重插值，零训练）**：
  见 `reports/needlefix-preregistration.md` §9、`reports/m3-dpo-preregistration.md` §1。**同一台仪器**读数：

  | 档 | needle（64 次） | A（≥0.75） | **未见载体 ASR（168 条，同仪器）** | B（不显著劣于起点 6/168） | 契约（≥63/168） | 总判 |
  |---|---|---|---|---|---|---|
  | m2-calib（292 步，原起点） | 39/64 = 0.609 | ✗ | **6/168 = 3.6%** | ✓ | 84/168 | undecidable（G3 不过） |
  | m2calib-needlefix-e1（360 步） | **60/64 = 0.938** | ✓ | 24/168 = 14.3%（p=4.28e-04） | ✗ | 74/168 | worse |
  | soup-a035 | 47/64 = 0.734 | ✗ | **3/168（优于起点）** | ✓ | 71/168 | undecidable（差 1 次试验） |
  | **soup-a050（生效基座）** | **52/64 = 0.812** | **✓** | **7/168 = 4.2%（Fisher p=1.0，不显著）** | **✓** | **70/168** | **ok** |

  - `soup-a050 = 0.5·m2-calib + 0.5·m2calib-needlefix-e1`（零训练成本）；辅判据全 PASS，
    含 PPL general_en 10.716→10.518（**−1.84%**）、general_zh 19.193→18.666（**−2.74%**）
    ——**优于起点**；三族在分布观测同向改善（t2 −0.533 / doc_structure −0.360 / t9_phish −0.426 nats）
    （`reports/topup-verdict-soup-a050.json`、`reports/recipe-search-judgement.json`）。
  - ⇒ **"选项 C（用 C 路补齐产物）"已不存在**；C 路自身的机械分支"回退选项 A（原样以 m2-calib 进 M3）"
    **也未被采用**——实际路径是把两档各偏一端的产物做权重插值（`soup-a050`），
    这正是"两个能力在权重空间可分离"的正面结论（`docs/01 §11.13` 规则 14）。
  - ~~**2026-09-30 二次定稿**（第一次定稿为 m25-full，已被新仪器读数推翻）~~ 及下表
    "未见载体 ASR（v0.3-gen，**70 条**）"的读数**已按 `docs/01 §11.8` 作废为历史参考**：
    仪器扩容到 258 条（鲁棒性 70→168）后，全部对照臂已在同一仪器上重测（见上表右列）。
    保留原文以备追溯：

    | 候选基座（**旧仪器，已作废**） | 在训载体 ASR（部署口径） | ~~未见载体 ASR（v0.3-gen，70 条）~~ | needle（64 次） |
    |---|---|---|---|
    | m2-calib（292 步） | 0.1250 | ~~4/70 = 0.057（最好）~~ | 0.609 |
    | m25-full（17,210 步） | 0.0625 | ~~13/70 = 0.186~~ | 0.875 |
    | m2-full（12,294 步，权重已废弃） | 0.1250 | ~~23/70 = 0.329~~ | 0.734 |

  ~~用户裁决（2026-09-30）：**选 C 路** —— 以 `m2-calib` 为起点做**短程定向补齐**~~
  ~~（低 LR、少步，补 T2 机制解释 / document 载体 / T9 扩容三族），~~
  ~~**以未见载体门禁为验收判据**（不得比 m2-calib 的 4/70 变差超过公差），~~
  ~~通过后再进 M3 DPO。理由：本项目使命核心是**跨载体泛化**，而仪器扩容后~~
  ~~证据显示长时间训练买到的是在训载体拟合与长上下文、代价是跨载体泛化。~~
  **【历史记录，已由 ① 否决："选 C 路"的决定在 2026-09-30 当天被 C 路自身的 FAIL 判定推翻】**
  ~~- 若补齐未通过验收（未见载体显著变差），**回退为直接以 m2-calib 进 M3 DPO**（选项 A）；~~
  ~~- 若补齐后未见载体不劣化且在训载体明显改善，则采用补齐产物（选项 C）。~~
- lr **2.0e-6**（区间 5e-7~5e-6 的中偏上：对数中点 ~1.6e-6 再上一档）；beta
  **0.1**（默认 KL 锚；条件旋钮——若 M2.5 出口 G4 行为保持 FAIL，发射前升 0.2）
  **（2026-09-30 复核：该条件未触发。** M2.5 的部署格式判定里 `G4_behavior_hold` = **PASS**、
  `failed_axes` 为空（`reports/m25-exit-verdict-chat-m25full.json` 的 G4 段），
  故 beta 维持 **0.1**，与 `configs/m3-dpo-final.yaml:36` 一致。）
- epochs 1；bs 沿 M2 校准实测包络
- **KL 心理锚**：DPO 的隐式 KL 已有，beta 即旋钮

### 2.3 门禁

- heldout v0.2.1 双指标按包改善或持平（ASR↓ 且 ORR 不升）
- 探针 PPL 门禁延续：general ≤10% 回升、sec 不变差（RL/DPO 不许毁知识层）
- ~~tool_output 泛化探针不回退~~ **（2026-09-30 订正：tool_output 载体已被训练
  1,224 次，只能作"同载体回归"读数；泛化门改为
  `data/heldout/v0.3-gen`（image_metadata/av_metadata，~~122 条~~ **258 条 / 鲁棒性 168 条**；
  2026-09-30 扩容，扩容前的"122 条 / 鲁棒性 70 条"读数按 `docs/01 §11.8` 已作废为历史参考，
  见 `reports/c-path-topup-verdict.md` §1）**，
  判据：未见载体鲁棒性攻击成功率**不得比基座显著变差**（Fisher p<0.05 且差值 >0，
  否则记为"未达可区分"）；判定器 v2 的 `--require-unseen-carrier` 应始终打开。
- **上一条的"基座"已随 §2.2 三次定稿变更**：M3 发射的水位以 **`soup-a050`** 为准，
  **不再**用 `m2-calib` 的 4/70（旧仪器）或 6/168。
- **M3 冻结判据（`reports/m3-dpo-preregistration.md` §4）**：
  MUST-A 未见载体 ASR —— 单侧 Fisher **p ≥ 0.05** 且 Newcombe 95%CI 下界 ≤ **+0.05**（起点水位 **7/168 = 4.2%**）；
  MUST-B 契约保留 **≥ 63/168**（起点水位 **70/168**）；MUST-C 误拒 ORR 上升 ≤ 0.05；
  SHOULD-2 needle **≥ 0.75** 且不低于起点 −0.10（起点 0.812）。
- 全部门禁以**部署提示格式**运行（`--prompt-format chat`），并报 n/95%CI/Fisher p；
  缺失输入一律 fail-closed（PENDING）——见 `docs/01 §11`。
- **资产保留**：`save_total_limit ≥3` 且每 epoch 至少保留一个中间档（`docs/01 §7.3`）。
  ~~现有 `configs/m3-dpo.yaml` 仍为 2，**发射前必须改**。~~
  **（2026-09-30 办结登记：本项待办已完成，无欠账）** `configs/m3-dpo.yaml:86` 已改为 **3**
  （行尾注"【2026-09-30 整改】docs/01 §7.3"）；实际 M3 发射用的是 `configs/m3-dpo-final.yaml:41` = **5**
  （`reports/m3-dpo-preregistration.md` §3）。

## 3. M3.5：RLVR / GRPO（可验证奖励在线 RL）

### 3.1 奖励函数（`scripts/rlvr_reward.py`，工具链在建）

分量式：verdict_parse / verdict_correct / policy_compliance /
action_consistency / 长度先验。**防黑不变量：verdict_correct 权重 >
格式类权重之和**（格式满分+行为错误 = 净负分，测试断言锁定）。

### 3.2 任务流（`scripts/gen_rlvr_tasks.py`，在建）

带机器可判真值的新鲜实例流（注入检测/政策裁决/PII 发现/载体分类），
与 SFT 数据不同源（防记忆），与 heldout/探针物理隔离。

### 3.3 训练（GRPO 配置待 `docs/research/grpo-feasibility.md`）

- 0.6B 单卡 24GB 可行性核查中；PPO 不采（价值模型显存不必要）
- KL 锚定到 M3 检查点（M1.5 知识层保护的具体机制）

## 4. 校准双路径

1. 偏好路径：校准对进 M3（§2.1）
2. 奖励路径：|confidence − 经验正确率| 进 RLVR 奖励分量【待 M3.5】

发布前校准曲线（confidence 分桶 vs 实测正确率）入 heldout 报告。

## 5. 时序与决策点

```
M2 全量跑（今晚）→ 读数（09-27 晨）
  ├─ SFT 泛化够 → M3 DPO（数据就绪即发射）→ M3.5 RLVR
  └─ SFT 泛化弱（tool_output/改述探针差）→ M3.5 提前/加强，M4 循环提前介入
M4 常设：失败挖掘 → SFT 补样本 / 偏好对回流，双通道
```

## 6. 开放问题

1. 政策条件化对的 beta 与通用对的 beta 是否分置（防通用盘稀释政策信号）
2. RLVR 阶段 policy_compliance 分量对 report_finding 类任务的期望动作
   词典（与判分器 v2 观察标签对齐）
3. M2 recovery 占比 52.9% 的教训是否要求 M3 数据同池重平衡
4. 多轮任务的 GRPO credit assignment（M3.5 后期）

---

## 修订记录

| 日期 | 版本 | 修订 | 依据 |
|---|---|---|---|
| 2026-09-30 | v0.1 | §2.2 超参数定稿（lr 2.0e-6 / beta 0.1 / epochs 1）；§2.3 增补资产保留与部署格式口径 | `configs/m3-dpo.yaml` 定稿注；`docs/01 §7.3`、`§11` |
| 2026-09-30 | v0.1+ | **本次修订（只改 §2.2、§2.3 与状态行，其余骨架未动）**：① **§2.2 基座**——删除"基座 = C 路补齐产物（`checkpoints/qwen3-06b-sec-m3base-topup`）"与"选项 C / 回退选项 A"的冲突表述；C 路 e1/e2 实测**契约 84/168 → 8/168、ASR 6/168 → 101/168 与 108/168 ⇒ 主判据 FAIL**，其权重登记为 `discarded`，**不得作 M3 起点**；生效基座改为 **`soup-a050`**（权重插值，五门禁全过），并补 168 条同仪器对照表。② **§2.2 beta 条件旋钮**：复核 M2.5 `G4_behavior_hold` = PASS ⇒ 条件未触发，beta 维持 0.1。③ **§2.3 仪器口径**：`v0.3-gen` 由 122 条更正为 **258 条 / 鲁棒性 168 条**，旧 70 条读数按 `docs/01 §11.8` 降为历史参考；补记 M3 冻结判据的水位（MUST-A 7/168、MUST-B 70/168、SHOULD-2 0.812）。④ **§2.3 上一轮遗留待办办结**：`configs/m3-dpo.yaml` 的 `save_total_limit` 已为 **3**，实际发射用 `configs/m3-dpo-final.yaml` = **5** ⇒ **本项无欠账** | `reports/c-path-topup-verdict.md` §1/§2/§5；`reports/needlefix-preregistration.md` §8.1/§9；`reports/recipe-search-judgement.json`；`reports/topup-verdict-soup-a050.json`；`reports/m3-dpo-preregistration.md` §1/§3/§4；`reports/m25-exit-verdict-chat-m25full.json`（G4 段）；`configs/m3-dpo.yaml:86`、`configs/m3-dpo-final.yaml:41` |
