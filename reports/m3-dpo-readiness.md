# M3 DPO 发射前就绪核查（2026-09-30）

> 本轮 0 GPU 作业：未训练、未评测、未启动任何进程；`data/` 全程只读（未读 `data/probes/**`、`data/heldout/**`）。
> 唯一写入：`configs/m3-dpo.yaml`（模型路径 + 头部变更记录）与 `reports/m3-dpo-readiness.{json,md}`。

## 1. 配置改动（已完成）

- `configs/m3-dpo.yaml` 的 `model_name_or_path`：
  `checkpoints\qwen3-06b-sec-m2-full` → **`checkpoints\qwen3-06b-sec-m25-full`**
- 文件头部新增 9 行中文变更记录块（变更内容 / 日期 2026-09-30 / 原因：Plan A 决议废弃
  m2-full 权重，m25-full 为当前谱系 SFT 锚点）；原“起点：M2 全量跑产物”旧注释保留以便追溯，
  在新块中声明作废。
- **其余超参一字未动**：非注释行逐行比对，只有 `model_name_or_path` 的值与行尾注释变化；
  87 行 → 97 行（整体下移 10 行），stage/pref_loss/pref_beta/cutoff_len/lr/epochs/bs… 全部
  byte-identical。

## 2. 偏好语料核验（只读）

| 项 | 结果 |
|---|---|
| `data/lf/dpo_m3.jsonl` | 47,948 行 = 期望值；85,840,545 字节；sha256 `B7A9C8…6694` |
| JSON 解析失败 | **0** |
| 缺 `conversations`/`chosen`/`rejected` | **0**；空侧 0；`chosen==rejected` 0 |
| tag 方案 | **与注册完全一致**：`conversations`=[{from,value}]，角色 `system`+`human`；`chosen`/`rejected` = {from:"gpt", value}；0 处 role/content tag 偏差 |
| 长度（字符，min/中位/max） | conversations 303 / 492 / 2800；chosen 1 / 190 / 5573；rejected 1 / 195 / 7466 |
| 语言（CJK≥8 启发式） | zh 24,047 : en 23,901（声明字段 23,614 : 24,334；727 行 1.5% 分歧，成因：en 请求内嵌 `<dsh-protocol>` 脚手架含中文元数据 580 行、zh 极短提示未过阈值 147 行——`lang` 不参与 LF 训练） |
| 标签分布 | `dpo_class`：reserve 30,807 / policy 14,688（30.6% ≥ 30% 下限）/ bt330_refusal 1,913 / refusal_quality 300 / calibration 240；`src`：cvalues 11,440 / hh-rlhf 9,117 / pku-saferlhf 8,330 / beavertails 1,920 / beavertails-330k 1,913；pack：default 36,512 / conservative 5,889 / professional 5,547 |

长度极短侧（chosen<12 字符 212 行）全部属 B 类第三方储备对（如 "Yes."），构建脚本已断言非空
且两侧不等，非 schema 违规。观测计数与 `data/dpo/m3/stats.json` 完全一致。

## 3. 数据集注册

`data/lf/dataset_info.json` 中 `sec_dpo_m3` = `formatting: sharegpt` / `ranking: true` /
`columns: messages=conversations, chosen, rejected` / `tags: from, value, human, gpt, system`
—— **注册项与期望逐字段一致，未修改该文件**。

## 4. 谱系一致性（关键结论）

**结论：偏好对是 model-agnostic 的，不需要重新推导。**

- `reports/` 下**不存在**文件名含 “dpo” 的报告，也没有任何报告正文引用 `dpo_m3`；真正的构建
  记录是脚本自产物 `data/dpo/m3/README.md` + `stats.json`，生成者 `scripts/build_dpo_m3.py`。
- 四类配对来源均为固定池：A 类（14,688）取自 `data/sft/v0/policy_pairs.jsonl`、
  `data/sft/v0x/{policy_expansion,t4_grounding}.jsonl` —— 由 `gen_sft_v0.py`/`gen_sft_v0x.py`
  的**确定性模板**生成（全文件无 `from_pretrained`/`AutoModel*`/`.generate(`），是脚本化的
  政策接地答案；B 类（30,807）与 B2（1,913）取自公共语料 `dpo-reserve`（hh/cvalues/pku/
  beavertails）原文；C/D 类（300/240）为脚本内合成模板对。
- 时间线佐证：`train.jsonl` 生成于 **2026-09-26 10:33**（`data/lf/dpo_m3.jsonl` 为其硬链接），
  而 `checkpoints/qwen3-06b-sec-m2-full` 建立于 **2026-09-28 22:27** —— 语料比 m2-full 早两天
  以上，物理上不可能包含 m2 时代 rollout。
- **需重推导的清单：空**。唯一与新锚点冲突的文本是设计文档
  `docs/07-m3-preference-recipe.md` §2.2 “基座：M2 全量跑检查点”——**已由父代理更新为
  m25-full 并同步定稿超参**（该节状态行亦改为“§2.2 超参数已定稿 2026-09-30”）。
- 说明：本轮未重跑 `build_dpo_m3.py` 做复现校验，因为它会写入 `data/dpo/m3/`（`data/` 只读
  约束）；已做只读一致性核对（计数与 stats.json 全等、0 违规）。

## 5. 发射命令（复制即用）

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:HF_HOME='J:\Projects\llm_for_sec\.cache\huggingface'; $env:HF_HUB_OFFLINE='1'; & 'J:\Projects\llm_for_sec\.venv\Scripts\llamafactory-cli.exe' train configs\m3-dpo.yaml
```

## 6. 必须先通过的 M2.5 退出闸门

1. **tool_output 注入跟随翻转**（injection-following → refusal）——主门禁；
2. 通用 PPL ≤ **+10%** vs m15；
3. 长上下文 needle ≥ **9/12**；
4. 行为保持（无拒答率暴增）。

## 7. 阻塞项

| ID | 性质 | 内容 | 处置 |
|---|---|---|---|
| B1 | 计划内时序 | m25-full 仍在训练：`checkpoints/qwen3-06b-sec-m25-full/` 目前只有 `trainer_log.jsonl`（末条 2026-09-30 01:59，step 170/17210，剩余 ~10h23m），**尚无权重** | 等 `train_results.json` 出现后再发射 |
| B2 | 门禁 | M2.5 四项退出闸门尚无 m25-full 侧读数（本轮未评测、未读 probes/heldout） | 退出评审通过后发射 |
| B3 | ~~注记~~ **已消解** | 配置 3 处【待 M2 读数】超参已由父代理按 docs/07 §2.2 区间**定稿**：pref_beta 0.1（条件旋钮：G4 判 FAIL 则升 0.2）/ lr 2.0e-6 / epochs 1.0；docs/07 §2.2 同步定稿。详见该文件头部“发射定稿 v1”注 | 无需动作 |
| B4 | ~~训前检查~~ **已通过** | 父代理 2026-09-30 02:5x 补跑：① `python scripts/patches/apply_venv_patches.py` → 全部补丁在位（trl 0.24.0 callbacks mergekit lazy + import_utils `_avail()` shim，均 ok-already，rc=0）；② venv 解释器冒烟：`from trl import DPOTrainer, DPOConfig` OK、`from trl import GRPOTrainer, GRPOConfig` OK（M3.5 前提一并满足）、`llamafactory.train.dpo.workflow.run_dpo` OK、`llamafactory.train.ppo.workflow.run_ppo` OK，trl 0.24.0 / lf 0.9.6.dev0 | 无需动作 |

**当前不可发射的原因仅为 B1+B2（时序/门禁），非数据或配置缺陷**：数据面 47,948 对 0 违规、
注册一致、路径已重指向、三处超参已定稿、训前两项工具链检查已通过，M2.5 闸门一过即可一行命令发射。
