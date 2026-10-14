# GRPO 可行性备忘（M3.5 RLVR 前置核查）

日期：2026-09-27 · 核查方式：全部结论来自本仓库源码与 venv 实测（零猜测）
· GPU 纪律：核查期间未触碰训练进程（PID 13776），全部 CPU 侧验证

## TL;DR

1. **本仓库的 LLaMA-Factory 0.9.6.dev0 没有 GRPO 阶段**——stage 分发只有
   `pt/sft/rm/ppo/dpo/kto`（`LLaMA-Factory/src/llamafactory/train/tuner.py`
   实测），不能靠现有 LF 配置直接跑 GRPO。
2. **TRL 0.24.0（已装）有成熟的 GRPOTrainer**，奖励函数契约与我们
   的分量式奖励库（`scripts/rlvr_reward.py`）**精确对接**——但当前
   venv 里 **import 即失败**（mergekit 硬依赖缺失）。
3. **更严重的提前预警：DPOTrainer 同链 import 失败**——M3 的 DPO
   阶段走 LF 也会踩同一个坑，必须在 M3 启动前修。
4. 修复路径明确且低风险（见 §3）；修好后 0.6B 单卡 24GB 的 GRPO
   **VRAM 预算可行**（保守配置约 12–16 GB，余量 ≥30%）。

## 1. 实测事实链

### 1.1 LF 侧：无 GRPO

- `train/tuner.py` stage 分发：`pt / sft / rm / ppo / dpo / kto`
  （另有 megatron_bridge 与 mca 变体、hyper_parallel）——全库源码
  `grep GRPO` 零命中。
- LF 的 PPO 路径（`train/ppo/`）需要 奖励模型 + value head（先走
  `rm` 阶段训练 RM）——与 RLVR 的**规则可验证奖励**路线不匹配：
  我们的奖励是程序判分（verdict 真值比对），不是学出来的标量 RM。

### 1.2 TRL 侧：GRPOTrainer 存在且契约理想

`trl==0.24.0`（venv 已装）。源码级确认（未 import，直接读
site-packages 源文件）：

- **奖励函数契约**（`grpo_trainer.py`）：
  `RewardFunc = Union[str, PreTrainedModel, Callable[[list, list], list[float]]]`
  - 自定义函数收到 `(prompts, completions)` + **数据集额外列按
    kwargs 对齐传入**（`reward_task_json` / `reward_pack` 等列名
    即参数名）；
  - 返回 `list[float]`；**单样本可返回 `None` = 该奖励函数对此
    样本不适用**（多任务语义——与 rlvr_reward 的分量 None 归一
    语义对齐）；
  - 多个 reward_funcs 的奖励**求和**。
- **GRPOConfig 关键项**：`num_generations`（默认 8）、
  `max_completion_length`（默认 256）、`generation_batch_size` /
  `steps_per_generation`（互斥）、`num_iterations`、
  `scale_rewards`（默认 "group"）、`loss_type`（默认 "dapo"）、
  `use_vllm`（默认 False；本 venv 无 vllm，用 HF generate 路径）。
- **KL/ref 模型**：`beta == 0.0` 时**不加载参考模型**（源码：
  `use_ref_model = beta != 0.0`）——省 1.2 GB VRAM 的官方开关。

### 1.3 阻断点：import 链断裂（GRPO 与 DPO 同病）

实测 traceback 链：

```
trl/trainer/callbacks.py:40   from ..mergekit_utils import MergeConfig, ...
trl/mergekit_utils.py:22      from mergekit.config import MergeConfiguration, ...
→ ModuleNotFoundError: No module named 'mergekit'
```

`from trl import GRPOTrainer` 与 `from trl import DPOTrainer`
**双双失败**。mergekit 只被 TRL 的"模型合并回调"功能用到（我们
不用），但它是顶层硬 import。

修复路径实测（本会话做过又回滚，venv 已恢复原状）：

| 路径 | 结果 |
|---|---|
| `pip install mergekit --no-deps`（装 0.1.4） | import 链推进到下一层：`immutables` 缺失 → 再装 → **PydanticSchemaGenerationError**（mergekit 0.1.4 的 `Task[Tensor]` 泛型与已装 pydantic 不兼容）——死路 |
| `pip install mergekit`（全依赖） | 会装 mergekit 0.1.4 + **升级 accelerate→1.6.0、huggingface_hub→1.16.1**（+click/dill/immutables/pydantic 变动）——训练进行中不可做（C1-full 用的就是这个 venv），且版本漂移风险高 |
| **lazy-import 补丁**（推荐） | 对 `trl/mergekit_utils.py:22` 的 import 块包 try/except（异常时 `MergeConfiguration = None` 等 + 可用性标志 False）——约 6 行，不装任何新包，merge 相关功能（我们不用）降级为调用时报错 |

### 1.4 环境快照（备忘时的相关版本）

trl 0.24.0 · transformers 5.8.0 · torch（C1-full 训练中）· 无 vllm ·
无 mergekit（手术件已卸载，venv 恢复核查前状态）

> transformers 5.8.0 × trl 0.24.0 的运行时兼容性**未验证**（import
> 被 mergekit 挡住，无法进行到实例化层）——修完 import 后第一件事
> 就是空跑一次 `GRPOConfig(...)` 实例化冒烟。

## 2. 0.6B 单卡 24GB VRAM 预算（WDDM 纪律保守值）

以 Qwen-0.6B 量级（hidden≈1024、28 层、GQA）bf16 估算：

| 项 | 估算 | 说明 |
|---|---|---|
| policy 权重 | ~1.2 GB | bf16 |
| ref 模型 | ~1.2 GB / 0 | `beta=0.04` 挂 / `beta=0.0` 免 |
| 优化器 | 4.8 GB / 1.2 GB | AdamW fused（fp32 双状态）/ 8-bit |
| 梯度 | ~1.2 GB | bf16 |
| KV cache | ~0.7 GB | 8 并发 × 1536 tok（GQA 每 token ≈57 KB） |
| 激活（梯度检查点） | ~2–4 GB | 生成批 64（8 prompt × 8 gens）回传 |
| WDDM 预留+碎片 | ~2–3 GB | Windows 侧不可压缩 |
| **合计** | **~12–16 GB** | 24 GB 卡余量 ≥30% ✓ |

## 3. 建议路线（按优先序）

**A. TRL 直用（主路线）**：修 mergekit import（§1.3 补丁，C1-full
结束后立即做 + 冒烟）→ GRPOTrainer + 我们的
`rlvr_reward.grpo_reward_func`。配置草稿（**不发射**，仅评审用）：

```yaml
# trl GRPOConfig 草稿（0.6B @ RTX 5090 D 24GB，WDDM 保守）
bf16: true
per_device_train_batch_size: 8        # 每 step 8 个 completion
num_generations: 8                    # 每 prompt 8 采样
generation_batch_size: 64             # 8 prompt × 8 gens（一个生成批）
max_prompt_length: 1024
max_completion_length: 512
learning_rate: 1.0e-6
beta: 0.04                            # 挂 ref；余量紧张时改 0.0
loss_type: dapo                       # 0.24 默认
scale_rewards: group
gradient_checkpointing: true
optim: adamw_torch_fused
# 数据集：gen_rlvr_tasks.py 产物 → TRL 格式（prompt 列 + 额外列
# reward_task_json / reward_pack 随 kwargs 进奖励函数）
# reward_funcs: [rlvr_reward.grpo_reward_func]
```

**B. LF 升级带 GRPO 的上游版**：换 LF 版本 = 动整个训练栈——与
C1/M2/M3 的环境冻结冲突，**不推荐**在 M3.5 前做。

**C. 自实现简化 REINFORCE**（TRL 不可用时的兜底）：HF `generate`
采样 + 自算 logprob + 组内基线（leave-one-out mean，等价 GRPO 的
零 KL 特例）+ 手动 optimizer step。估 **300–500 行 / 2–3 天**，
无 trl 依赖，完全受控；代价：没有 TRL 的 dapo/长度归一化等成
熟细节，需要自测。

## 4. 已知坑清单

1. **mergekit import 阻断影响 M3 DPO**（提前预警，最高优先）——
   LF 的 dpo trainer 从 trl 导入；M3 启动前必须打 §1.3 补丁并
   冒烟 `from trl import DPOTrainer`。
2. transformers 5.8.0 × trl 0.24.0 运行时兼容未验（import 修复后
   先空跑 GRPOConfig/DPOConfig 实例化）。
3. WDDM 下 Windows 显示占用 + 碎片：预算留 ≥30% 余量；首次 OOM
   先降 generation_batch_size（64→32）再降 max_completion_length。
4. 0.6B 模型 VERDICT 格式遵循度：M2-SFT 后应已具备；若 RL 早期
   大面积 format_error，先用手工 SFT 混合步（replay 10%）再切
   纯 RL（奖励库里 parse=0 路径已防负激励塌缩）。
5. 奖励黑客面（已防，测试锁定）：格式满分但裁决错 = 净负分
   （verdict_correct 权重 0.60 > 格式类分量和 0.30，不变量测试
   `TestAntiGamingInvariant`）。剩余面：verdict 字段枚举攻击
   （乱填 verdict 词但 action 对）——policy_compliance 独立扣分
   兜住；后续 M3.5 可加 verdict 词表白名单校验进 parse 分量。
6. 任务流新鲜性由 8-gram 游程测试锁定（≤30，房屋真复制线 40）；
   在线 RL 每轮换 `--seed` 派生流防记忆。
7. GRPO 的 prompt 需转为 TRL conversational 格式（messages 列表）
   ——`grpo_reward_func` 已兼容 str 与 conversational 两种
   completion 形态（测试覆盖）。

## 5. 本次交付物索引

- `scripts/rlvr_reward.py`——分量式奖励库（5 分量 + GRPO 适配器 +
  离线判分 CLI）
- `scripts/gen_rlvr_tasks.py`——可验证任务生成器（4 任务型，
  实例级新鲜，独立 RNG 流）
- `tests/test_rlvr.py`——27 测试（分量已知答案 / 防黑不变量 /
  GRPO 契约 / 真值自洽 / 8-gram 新鲜 / 隔离扫描）
- `data/rlvr/tasks-v01.jsonl`——常备任务批（2,000 条，4 型 × 500）
