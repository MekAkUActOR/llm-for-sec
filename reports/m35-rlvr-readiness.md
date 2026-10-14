# M3.5（RLVR / GRPO）就绪核查

状态：**数据层与奖励层已验证可用**；训练超参【待 M3 读数】定稿；发射前需过 §5 清单。
核查日期：2026-09-30（M2.5 训练窗口内，CPU 侧零 GPU 占用）
前置依赖：`m25-full`（训练中）→ **M3 DPO**（配置已定稿）→ M3.5 GRPO

---

## 1. 现状证据（全部为今日实测，非推断）

| 项 | 证据 | 结论 |
|---|---|---|
| 任务文件 | `data/rlvr/tasks-v01.jsonl`：**2,000 行 = 4 型 × 500**；必需列齐备；`reward_task_json` 全可解析；`ground_truth` 与 task_type 自洽（`inj_detect` verdict+action / `policy_ruling` actions / `pii_discover` verdict+action+locate / `carrier_classify` verdict+action）；**违规 0** | ✅ 可训 |
| 语言分布 | 内容级 zh 979 / en 1,021（≈49:51） | ✅ 均衡 |
| 包分布 | default 1,679 / professional 152 / conservative 169；**包语义仅在 `policy_ruling` 分化**（179/152/169），其余三型全 default | ⚠️ 见 R1 |
| 奖励库 | `scripts/rlvr_reward.py` 分量式：verdict_parse 0.15 / **verdict_correct 0.60** / policy_compliance 0.15 / action_consistency 0.10 / length_prior 0.05；None 分量归一化 | ✅ |
| 防黑不变量 | `verdict_correct(0.60) > 格式类分量和(0.30)`——`tests/test_rlvr.py::TestAntiGamingInvariant` 锁定（含 gaming sweep） | ✅ 测试级硬保证 |
| 单测 | `tests/test_rlvr.py` 全绿（奖励分量/组合/防黑/GRPO 适配/任务契约/值新鲜度/隔离扫描）；**全量 `unittest discover` = 492 项 OK**（2026-09-30） | ✅ |
| 隔离红线 | 生成器独立 RNG（与 SFT 侧种子不相交）、值级新鲜、8-gram 游程阈值测试、`TestIsolationScan` 不读 heldout/探针/参考集 | ✅ |
| 发射脚本 | `scripts/run_grpo.py` 草案 v0：**默认只打印计划，需显式 `--run`**；`DEFAULT_MODEL` 已指向 `checkpoints/qwen3-06b-sec-m3-dpo` | ✅ 安全默认 |
| 框架可用性 | LF 0.9.6.dev0 **无 GRPO 阶段**（`tuner.py` 仅 pt/sft/rm/ppo/dpo/kto）→ 直用 TRL 0.24 `GRPOTrainer`；**feasibility 备忘所记 "mergekit 硬依赖缺失导致 DPO/GRPO import 即失败" 已于今日复测确认修复**（venv 补丁在位：DPO/GRPO import 通过、LF `run_dpo`/`run_ppo` 可导入） | ✅ 前置已清 |
| 显存预算 | 0.6B @ RTX 5090 D 24GB，WDDM 保守包络 **~12–16 GB**（来源：`docs/research/grpo-feasibility.md` §2，**未经实跑验证**） | ◐ 发射前实测 |

## 2. 数据流形状（与 TRL 的对接点）

`messages=[system,user]`（会话式 prompt）+ `reward_task_json`（task_type/ground_truth 的 JSON 串）+ `reward_pack` → 后两列经 TRL reward-func kwargs 对齐传入 `grpo_reward_func`；**单样本缺元数据 → None**（TRL 0.24 多任务语义，`TestGRPAdapter` 覆盖 string/conversational/missing-metadata/weights 四种形态）。

## 3. 【待 M3 读数】清单（`scripts/run_grpo.py`）

M3 DPO 完成后按下表逐项定稿（当前为 feasibility §3A 草稿值）：

| 项 | 草稿值 | 定稿依据 |
|---|---|---|
| `learning_rate` | 1.0e-6 | RL 低于 DPO 一档；看 M3 的 lr 敏感度 |
| `adam_beta2` | 0.98 | GRPO 社区常用 |
| `lr_scheduler_type` | constant_with_warmup | RL 常用恒 LR |
| `max_completion_length` | 512 | **按 M3 实测输出长度**（VERDICT 行 + 推理正文） |
| `temperature` | 1.0 | 格式稳定性 vs 探索的权衡 |
| `loss_type` | dapo | trl 0.24 默认（长度归一化） |
| `num_train_epochs` | 1.0 | 2,000 prompt × 8 gens ÷ 8/step ≈ 2,000 步 |

## 4. 风险与建议的出口检查

- **R1 包条件化可能被 RL 洗掉（本阶段最大待看点）**：包语义仅覆盖 25% 的 prompt
  （`policy_ruling` 500/2,000），而 GRPO 每 prompt 采 8 条、奖励主项是
  `verdict_correct`（与包无关）——存在把 M3 建好的"同问不同包 → 不同动作"学平的风险。
  **检查工具已落地并自测通过**：`scripts/pack_consistency.py`
  （`--selftest` 7 项断言全 PASS；**动作判定复用训练奖励库**
  `rlvr_reward._component_policy_compliance`，保证门禁与训练同口径）。
  实测物料（`--inspect`）：
  - `policy_ruling` **500 行，其中 GT 期望动作分化行 158 行（31.6%）**——分化行才承载包条件化信号；
  - 期望模式分布：三包同拒 178 / 三包同答 164 / 保守拒+中英答 **109** / 保守中拒+专业答 49；
  - 三包 system 提示是共享契约（`gen_sft_v0.POLICY_SYSTEM[pack][lang]`，packs×langs 齐备）
    → **本检查无需新造探针**，一行题跑三次包即可。
  - 扫描题已预生成：`reports/pack-consistency-sweep.jsonl`（40 组 × 3 包 = 120 条，
    取分化行，seed 20260930 确定性）。
  M3 完成后一条命令实跑：`python scripts/pack_consistency.py --run --model
  checkpoints/qwen3-06b-sec-m3-dpo --n 40` → 出**分化率 / 同口径吻合率 /
  格式错误率**（`reports/pack-consistency-score.json`）。
  ⚠️ `--run` 的 GPU 生成路径尚未实跑验证（M2.5 训练窗口内零 GPU 占用），
  首次执行前先看它的输出长度与 chat 模板是否与训练口径一致。
  **建议把"分化率 ≥ M3 读数"写入 M3.5 出口门禁**（与 M3 的 G4 同规格）。
- **R2 奖励与出口读数同源**：`rlvr_reward.py` 复用 `score_heldout_v2.classify()` 作判别层——若评分器改词表（如既定的 VERDICT `retrieved`/`not-in-doc` 扩项），**必须同步 reward 库并回归**，否则训练奖励与出口读数口径漂移（同一模型两块指标不可比）。
- **R3 无 KL 约束**（`beta=0` 跳过参考模型）：需在训练中监控长度/格式退化；`length_prior` 分量（0.05）是第一道兜底，`verdict_parse`（0.15）是第二道。建议 GRPO 期间同样挂看门狗（步时 + 分量均值曲线，不只 loss）。
- **R4 退化检测缺量表**：GRPO 的 loss 不是单调下降信号（它是策略梯度的副产品），**不能用 SFT 的 loss 判据**；出口判据应是分量均值 + 出口探针（四门禁同 M2.5 规格）。

## 5. 发射前清单（M3 完成后逐项打勾）

- [ ] M3 DPO 出口门禁通过（G1-G4；判定器 `scripts/m25_exit_verdict.py --tag m3dpo`，
      门禁口径与 M2.5 同规格——M3 是否需要独立门禁脚本在 M2.5 读数后裁决）
- [ ] §3 超参七项定稿（按 M3 实测输出长度定 `max_completion_length`）
- [ ] 显存实跑实测（保守包络 12–16 GB 是否成立；WDDM 下 bs1 × grad-accum）
- [ ] reward 与评分器**同版本**锁定（记 sha256；R2）
- [ ] 包一致性检查实跑并写入门禁（R1；工具+扫描题已就绪，`--run` 需 GPU 冒烟验证）
- [ ] GRPO 看门狗：分量均值 + 长度分布 + 格式错误率（R3/R4），非 loss
- [ ] `run_grpo.py --run` 首次实跑前 dry-run 打印计划留档

---
证据文件：`reports/m35-tasks-contract.json`（契约核查）、`tests/test_rlvr.py`、`docs/research/grpo-feasibility.md`、`scripts/rlvr_reward.py`、`scripts/gen_rlvr_tasks.py`、`scripts/run_grpo.py`
核查工具：`scripts/check_rlvr_tasks.py`（可复跑）
