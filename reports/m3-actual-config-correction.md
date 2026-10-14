# ★M3 实际运行的配置是 `m3-dpo-final.yaml`，不是 `m3-dpo.yaml`（2026-09-30 晚，父代理实测）

## 一、证据（命令行，非推断）

```
"J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "...\llamafactory-cli.exe" train J:\Projects\llm_for_sec\configs\m3-dpo-final.yaml
```

盘上旁证**逐位吻合**：
- 保留 **5** 个 checkpoint（1200/1300/1400/1500/1600），间距 **100**
  ⇒ 与 `m3-dpo-final.yaml` 的 `save_steps: 100` / `save_total_limit: 5` 一致；
  与 `m3-dpo.yaml` 的 `200` / `3` **不一致**。
- `total_steps = 1803`，而 `m3-dpo-final.yaml` 注释写 "28,842 / 16 = 1,803 步"
  ⇒ **精确吻合**（`m3-dpo.yaml` 的注释写的是 "预计 ~2,997 步（47,948 × 1 epoch ÷ eff 16）"）。

## 二、两份配置的实质差异（**不是 cosmetic**）

| 参数 | `m3-dpo.yaml`（**未使用**） | **`m3-dpo-final.yaml`（实际运行）** |
|---|---|---|
| `model_name_or_path` | `checkpoints\qwen3-06b-sec-m25-full` | **`checkpoints\soup-needlefix-a050`** |
| `dataset` | `sec_dpo_m3` | **`sec_dpo_m3_final`** |
| **`cutoff_len`** | **2048** | **1024** |
| `save_steps` / `save_total_limit` | 200 / 3 | **100 / 5** |
| `num_train_epochs` | 1.0 | 1 |
| `pref_beta` | 0.1 | 0.1（同） |
| `learning_rate` | 2.0e-6 | 2.0e-6（同） |
| `pref_loss` | sigmoid | sigmoid（同） |
| `finetuning_type` | full | full（同） |

⇒ **不同点集中在"起点模型、数据集、截断长度、存档密度"四项**，其中**起点模型**与
**`cutoff_len`** 是实质性差别。

## 三、更正：我此前关于 M3 的若干陈述以本文件为准

1. **"轮转失效"是我的误判。** 我先前由"盘上有 5 个 checkpoint 而 `save_total_limit: 3`"
   推断轮转未生效；实际配置值是 **5**，盘上正好 5 个 ⇒ **轮转正常**。
   **★事后实证（同日晚，训练至 97.6% 时）**：checkpoint 集合由
   `{1200,1300,1400,1500,1600}` 变为 **`{1300,1400,1500,1600,1700}`** ——
   **`checkpoint-1200` 被自动删除** ⇒ 滑动窗口正好 5 个，
   **`save_total_limit: 5` 确实在工作** ✓✓。误判被彻底证伪。
   **教训**：我拿了一份**同名的、未被使用的**配置文件当权威，而没有先看**命令行**。
   （与本节会话早前"把注释当事实""看结论不看数"同源：**先确认被测对象是不是你以为的那个**。）
2. `reports/m3-launch-runbook.md` 关于 `save_total_limit` 的表述需按实际值（**5**）更新；
   该文件若仍写 2，则是更早一稿的残留。
3. M3 的超参应引用 **`configs/m3-dpo-final.yaml`**；`configs/m3-dpo.yaml` 为**废弃稿**。

## 四、★由此产生的两个待查项（真实，不是修辞）

### 4.1 `configs/m3-dpo.yaml` 是**指向已废弃基线的活陷阱**
它 `model_name_or_path` 指向 `qwen3-06b-sec-m25-full`——而 `m25-full` 在本轮被裁决为
**FAIL(G2) 且其 PASS 不可采信**（六个 `m2full` 废弃基线）。
一份目的相同、名字近似、**起点却是已废弃模型**的配置留在 `configs/` 里，
是**可被误用**的：任何评审若按 `m3-dpo.yaml` 描述 M3，都会把起点说错。
**处置建议（待做）**：改名加 `_deprecated` 后缀或在头部加显式废弃标记。

### 4.2 `cutoff_len: 1024` 是否截断了 DPO 对 —— **实测：几乎不截断** ✓

脚本 `scripts/check_dpo_cutoff_truncation.py`（仅 tokenizer，CPU，基座 tokenizer 快照，
不加载模型、不碰 GPU）。数据集 = `data/lf/dpo_m3_final.jsonl`（55.9 MB，**28,842 对**，
与 `28,842 / 16 = 1,803` 步**精确吻合**，再次印证配置）：

| 序列 | n | 超 1024 | min | p50 | p90 | p95 | p99 | max | 截掉 token |
|---|---|---|---|---|---|---|---|---|---|
| prompt+chosen | 28,842 | **0（0.00%）** | 191 | 293 | 589 | 631 | **689** | 843 | **0** |
| prompt+rejected | 28,842 | **1（0.0035%）** | 186 | 298 | 470 | 499 | 563 | **1152** | 128 |

⇒ **`cutoff_len: 1024` 与数据集规模匹配**：p99 只有 689 / 563，唯一的 1 条超长
（1,152 → 1,024）损失 128 token，占全部 2×28,842 条序列的 **0.0017%** ⇒ 可忽略。
**本次 DPO 训练侧没有实质性的静默截断。**

**与评测侧的尖锐对比（值得记住）**：
- **评测侧** `max_new_tokens=96` ⇒ **67.8%** 的响应被截断（本会话已证），
  且该截断恰好是 ORR 轴层 3 分支的**存在条件**；
- **训练侧** `cutoff_len=1024` ⇒ **0.0035%** 越界。
⇒ **本项目目前真正的截断风险在生成侧，不在训练侧。**
（但两者**同源**：都是"上限写小了、而且没人检查它是否绑定"。
评测侧的 96 是`baseline_eval.py` 的默认值，训练侧的 1024 是显式配置——
**默认值是隐患，显式配置是纪律**。）


## 五、当前状态

M3 已完成约 91.8%（1655/1803），checkpoint-1600 **内容完整、可无损续训**：
`model.safetensors` 2,273.8 MB + **`optimizer.pt` 2,041.4 MB** + `rng_state.pth` +
`scheduler.pt` + `trainer_state.json` + `training_args.bin` ⇒
**常驻要求"所有训练可中断无损续训"在 M3 上满足** ✓。
