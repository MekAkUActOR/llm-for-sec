# M0 底座审计方案与实测报告（活文档）

> 版本 ~~v0.3~~ **v0.4（2026-09-30 同步修订）** · docs/01 §2.1/§2.2 的执行协议 + 本机实测数据。
> 决议输入（2026-09-24）：**本机训练，模型规模 0.6B–1B**；**路线 B 已终选：Qwen3-0.6B-Base**。

---

## 0. 硬件与软件环境（实测 ✅）

来源：`scripts/verify_env.py`（logs/verify_out.txt）、nvidia-smi、.venv 检查。

| 项 | 实测值 |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 D v2，24GB（24455 MiB），sm_120 Blackwell，WDDM |
| 驱动 / CUDA | 616.92 / CUDA 13.4 |
| BF16 matmul | **223.5 TFLOPS** |
| 显存带宽 | 1029.4 GB/s |
| SDPA 后端 | cudnn ✓ / mem_efficient ✓ / math ✓ / **flash ✗**（本 torch+Blackwell 组合抛 RuntimeError；训练走 cudnn，pretrain_1b.py 已验证可跑） |
| bitsandbytes | 0.50.2，AdamW8bit ✓（QLoRA 可用） |
| 端到端训练冒烟 | 45M 模型 bf16：389,188 tokens/s，峰值 8.17 GiB |
| 1B 预设实跑 | 峰值 ~21.5GB / util 97–99% / ~550W（logs/gpu_monitor_1b.csv） |
| 软件 | Python 3.14.6（uv venv）、torch 2.14.0+cu130、transformers 5.8.0、trl 0.24.0、peft 0.18.1、accelerate 1.11.0、llamafactory 0.9.6.dev0 |
| 缓存 | **Qwen3-0.6B-Base（终选底座，快照 da87bfb6）** + Qwen/Qwen2.5-1.5B（参考模型） |

**训练容量估算**（FLOPs ≈ 6·N·D；MFU 按 35–45% 保守取）：

| 规模 | 每 10 亿 token 时长 |
|---|---|
| 0.7B | ~13–17 小时 |
| 1.3B（1b 预设） | ~24–31 小时 |

含义：~~本机可支撑 0.6–1B 模型 **5–20B token 的中期训练（连续运行 2.5–10 天）**——与 docs/01 §3.1 目标规模（10–30B）匹配，取下限并预留重训余量。~~

**（2026-09-30 修正）** 本行的参照系已作废，两处与现状不符：

1. **"与 docs/01 §3.1 目标规模（10–30B）匹配"不再成立。** docs/01 §3.1 的"目标规模 10–30B token"已于同日就地修订为**实跑口径 0.6B / 1,088M token**（C1-full：2,072 步 / 30h20m / ~52.8 s·step⁻¹，`docs/05-m1-training-recipe.md:119`）——本机实际做到的是 **10⁹ token 量级**，不是 10–30B。
2. **"5–20B token ≈ 连续运行 2.5–10 天"偏乐观。** 按 C1-full 实测口径折算：1.09B token / 30h20m ≈ **27.8 h 每 10 亿 token**，为上表 0.7B 行（13–17 h）的 **1.6–2.1 倍**；据此 5–20B token 需 **≈5.8–23 天**，而非本行原估的 2.5–10 天（偏差主因：24GB 单卡 WDDM 包络与无融合 CE 的显存/带宽瓶颈，`docs/01 §11.7`）。

本表保留为**规划期 FLOPs 外推的历史记录**，不得再作为算力预算依据；后续成本估算一律按"实测 tokens/s × 计划 tokens"给区间（`docs/01 §11.7` 规则 7 第 1 条：步时只作当次观测，**禁止跨 run/跨阶段的线性外推**）。

### 0.1 已知兼容性问题与补丁（2026-09-24 C0 冒烟实战记录 ✅）

Python 3.14 + 该版本训练栈的组合问题，均已实测解决：

| # | 问题 | 症状 | 处置 |
|---|---|---|---|
| 1 | LLaMA-Factory stage 值变更 | `ValueError: Unknown task: pretrain` | 本版本预训练 stage 为 **`pt`**（tuner.py 支持 pt/sft/rm/ppo/dpo/kto） |
| 2 | dill 0.3.8 不支持 Python 3.14 pickle 内部签名变化 | datasets 指纹哈希 `TypeError: _batch_setitems() takes 2 positional arguments` | `uv pip install -U dill` → **0.4.1**（`.venv` 内升级） |
| 3 | datasets 4.0.0 自带 `Pickler._batch_setitems(self, items)` 覆写为 3.14 前旧签名 | 升级 dill 后仍在（覆写在 datasets 侧）：`save_dict` 传 3 参 | 最小补丁：`.venv/Lib/site-packages/datasets/utils/_dill.py` 签名改为 `(self, items, obj=None)` 并透传（向后兼容 try/except；升级 datasets 5.x 可官方修复，但会连带 pandas 3/fsspec 大版本跳变，暂不做） |
| 4 | pyarrow JSON 读取器对字符串内**原始多字节 UTF-8** 的严格性缺陷 | `pyarrow.lib.ArrowInvalid: Invalid encoding in string`（该行实为合法 UTF-8、无控制字符；ASCII 转义形态则通过） | C0 管线 `write_clean` 改用 `ensure_ascii=True`（纯 ASCII 线上格式，解码内容完全等价） |
| 5 | `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 在本机 WDDM + Blackwell 驱动不可用 | 反向传播 `RuntimeError: CUDA driver error: device not ready / Failed to create GPU mapping`（VMM 映射失败） | **不要启用 expandable_segments**；默认分配器即可 |
| 6 | 152k 大词表 × 大 micro-batch 的 logits 显存爆炸 | bs 8 × 4096 × 151936 × 4B(fp32 上抛) ≈ 19.9GB，cross_entropy OOM | micro-batch 降 2 + 梯度累积 64（全局 batch 不变）；吞吐优化走 liger-kernel 融合 CE（见 #7） |
| 7 | liger-kernel 官方依赖 `triton`，而 triton 无 Windows wheel（仅 manylinux）且无 cp314 | `uv pip install liger-kernel` 解析失败 | 安装可绕过：**`triton-windows`（3.8.0.post28，cp314 wheel）+ `liger-kernel --no-deps`**；但实测 **liger fused CE 内核（0.6.5 与 0.8.3 双版本）在 sm_120 上运行即 `CUDA_ERROR_ILLEGAL_ADDRESS`**（基础 triton 向量内核正常 → 系 triton-windows 对该内核的代码生成缺陷）。**结论：本机 liger 不可用，已卸载**；吞吐上限锁死在 ~7.3k tok/s（bs 2 配置） |
| 8 | trl 0.24 `trainer/callbacks.py` 顶层 `from ..mergekit_utils import ...`（mergekit 未装；装 mergekit 0.1.4 与现装 pydantic 死路，全依赖会连带升级 accelerate/hub） | `ModuleNotFoundError: No module named 'mergekit'`——`from trl import DPOTrainer / GRPOTrainer` 双炸（M3 DPO、M3.5 GRPO 阻断点，docs/research/grpo-feasibility.md §1.3） | 手工补丁（标记 `PATCH 2026-09-26`）：mergekit 导入下沉 lazy；已导出为幂等重放件 **`scripts/patches/`**（见下注） |
| 9 | transformers 5.8 的 `_is_package_available` 恒返回 `(bool, version\|None)` 元组，trl 0.24 按旧纯 bool 契约消费 | 14 个可用性守卫恒真（元组布尔上下文非空）——#8 修完后 `judges.py` 顶层 `import llm_blender` 仍炸 DPOTrainer import 链 | 手工补丁（同标记）：`import_utils.py` 加 `_avail()` shim 兼容两种契约；重放件同上 |

> **trl 补丁重放（2026-09-28 导出，#8/#9）**：两处手工补丁已导出为幂等重放件
> `scripts/patches/apply_venv_patches.py`（含两个带完整上下文的补丁模块，对
> PyPI wheel trl-0.24.0 基线逐字节可复现）。**何时需要重放：venv 重建、trl
> 卸载重装（含同版本重装——会覆盖 site-packages 文件）后必须重放**，否则 M3
> DPO / M3.5 GRPO 的 trl import 链断裂。用法：`python scripts\patches\apply_venv_patches.py`
> （已打自动跳过；`--check` 只报状态不改文件；版本非 0.24.0 默认拒绝应用）。
> 升级 transformers 修回纯 bool 契约后 #9 可退役；trl 升到自带两修复的版本后
> 两者均可退役（届时删重放件即可）。

---

## 1. 底座终选（v0.3 决议：路线 B，Qwen3-0.6B-Base ✅）

**终选**：Qwen3-0.6B-Base，快照 `da87bfb6`（2026-09-24 下载核验，项目缓存 `models--Qwen--Qwen3-0.6B-Base`）。

| 核验项 | 结果 |
|---|---|
| 许可 | **Apache-2.0**（LICENSE 全文 + 模型卡声明）✅ 继续训练 / 再分发 / 商用均允许 |
| 架构 | 28 层 / hidden 1024 / GQA 16Q-8KV / ffn 3072 / vocab 151936 / tied embeddings |
| 规模 | 0.6B 参数（非嵌入 0.44B）——决议范围内 |
| 上下文 | 32,768 native（docs/01 §2.2 地板 32k ✅；64k 目标在 M1 安全中期训练推进） |
| 阶段 | 预训练 base（非 instruct）✅ 符合 docs/01 §2.1 从-base-续训要求 |
| 双语+代码 | 119 语言、36T token 预训练（模型卡声明） |
| fertility | **全部通过**（见 §2；与 Qwen2.5 同词表族，实测数字一致） |
| 攻击面基线 | **已登记**：ASR=1.0 / 误拒=0.0（见 §4；reports/baseline-qwen3-0.6b-base.json） |
| 推理验证 | 已在本机 RTX 5090 bf16 实跑（sdpa 路径，8 条 × 96 token，31.4s） |

路线 A（从零，scripts/pretrain_1b.py）**保留为后备**：若 M1 中期训练发现底座继承的越狱面难以收敛，可回切（350m/1b 预设就绪，建议补 ~700m 预设）。

### 候选清单存档（决策依据）

### 路线 A：从零预训练（scripts/pretrain_1b.py，既有资产）

| 预设 | 参数量 | 状态 |
|---|---|---|
| 350m | ~0.5B | 就绪 |
| 1b | ~1.3B | 就绪（已实跑验证） |
| **700m（建议新增）** | ~0.74B | 一行预设：`d=1536, L=20, heads=24, kv=8, ffn=6144`（Qwen 词表、tie embeddings）——正落在决议范围 0.6B–1B 内 |

tokenizer：Qwen2.5（已缓存；fertility 已实测通过，见 §2）。

### 路线 B：开放底座继续训练

| 候选 | 规模 | 许可 | 双语 | 代码 | 备注 |
|---|---|---|---|---|---|
| **Qwen3-0.6B-Base** | 0.6B | Apache-2.0 | ✓ | ✓ | 范围内首选；需下载核验 base 检查点 |
| Qwen2.5-0.5B | 0.5B | Apache-2.0 | ✓ | ✓ | 略低于范围下限 |
| Qwen2.5-1.5B | 1.54B | Apache-2.0 | ✓ | ✓ | 已缓存；略超范围上限；tokenizer 源 + 参考/评估模型 |
| Llama-3.2-1B | 1.2B | Llama License | ✗（中文弱） | ✓ | 不满足选型标准 1（docs/01 §2.1），仅备选 |
| OLMo-2-1B | 1B | Apache-2.0 | ✗ | 中 | 数据开放性好；英文为主 |

### 终选判据与建议

按 docs/01 §2.1 六项标准 + 本文 §2–§5 审计项打分。**路线选择本身是决策点**：

- A 的优势：训练栈完全可控、"从零"研究纯度（无底座继承的越狱面与对齐冲突）；
- B 的优势：起点能力（省 5–20B token 的通用预训练）；
- **建议**：目标是安全训练管线完整验证 → A（700m）；目标是尽快得到可用安全基座 → B（Qwen3-0.6B-Base）。可并行 2–3 天评估后关门。

---

## 2. Fertility 实测（已完成 ✅）

工具：`python -m secfm.audit.corpora`（合成语料，各 64KB，种子 42 可复现）+
`python -m secfm.audit.fertility`（测量）。报告：`reports/fertility-qwen2.5-1.5b.json`。
真实语料入库后重跑同一工具对比。

| 语料组 | bytes/token | 相对基线 | 判定（阈值 1.5×） |
|---|---|---|---|
| baseline_mix（中英自然文本） | 5.08 | 1.00（参照） | — |
| hex_dump | 1.30 | 0.26 | ✓ |
| base64 | 1.34 | 0.26 | ✓ |
| obfuscated_js | 1.53 | 0.30 | ✓ |
| logs_syslog | 1.81 | 0.36 | ✓ |
| logs_json | 2.12 | 0.42 | ✓ |
| cve_ids | 2.63 | 0.52 | ✓ |
| shell | 2.91 | 0.57 | ✓ |
| c_code | 3.22 | 0.63 | ✓ |

**结论：全部通过，词表扩展手术不需要（docs/01 §2.2 的判据）。**

**终选底座复核**：Qwen3-0.6B-Base tokenizer（同 151936 词表族）重测，8 组数字与上表完全一致（reports/fertility-qwen3-0.6b-base.json）——终选底座继承本节结论。

运营含义：hex/base64 类载体 ~1.3 bytes/token——64KB 的 hex 转储 ≈ 5 万 token。大规模转储应走**上下文预算门控**（分段 + 证据链摘要，docs/01 §2.2 备选路径），而非词表手术。

---

## 3. 污染检查协议（待执行）

1. 立场：公开安全基准只作参考曲线（底座可能已见过）；判定以**私有留出集**为准（docs/01 §5.5）；
2. 私有留出集：**v0.1 种子批已交付**（`data/heldout/v0.1`，20/域 × 3 域 = 60 条；四类条目 + 6 政策对照组；zh 32 / en 28；`python -m secfm.eval.heldout` 校验通过）。扩容目标 ≥50/域进行中。**基线已实测**：reports/heldout-baseline-qwen3-0.6b.json（ASR=1.0；正当查询误拒 0；保守包 6 条全部未按包拒绝——base 无政策条件化，SFT 的核心目标之一）；
3. 评估一律经 `secfm.eval` harness 跑（评估即代码，docs/01 §5.6）；
4. 路线 B 候选下载后：canary 抽查公开基准题干改写变体（选做，低优先）。

## 4. 攻击面基线（已登记 ✅）

- **M0 实测基线**（Qwen3-0.6B-Base 原始权重，`scripts/baseline_eval.py`，经 secfm.eval harness）：
  - **ASR = 1.0**（4/4 攻击全部配合：键盘记录器 / 勒索加密代码 / 银行钓鱼步骤 / 钓鱼短信——无对齐层权重的预期起点，非缺陷）；
  - **误拒率 = 0.0**（4/4 正当安全查询正常回答）；
  - 能力数据点：base 将 IOC 误展开为 "Information Collection Object"（正确：Indicator of Compromise）——安全术语能力是 M1 中期训练的直接目标；
  - 报告：reports/baseline-qwen3-0.6b-base.json（双指标 Pareto + 逐条文本）。
- M1 实测协议（预登记，避免临时偏差）：≥5 攻击族（编码/角色扮演/低资源语言/多轮渐进/结构化诱导）× 每族 20 条固定种子；**双指标（ASR + 误拒）从第一天生效**（docs/00 §9.2）；
- 每个 Stage 出口用同一 harness 复测，与本基线对照形成攻击面收敛曲线。

## 5. 许可尽调（路线 B 适用）

- [x] Qwen3-0.6B-Base：Apache-2.0 核验（LICENSE 全文 + 模型卡 license 字段；继续训练 / 再分发 / 商用均允许）✅ 2026-09-24
- [x] 模型卡训练数据声明审查（36T token / 119 语言；含代码与推理数据）
- [x] 无区域使用限制 / 出口管制问题（Apache-2.0 无使用限制条款）
- 路线 A 自训模型：许可自主，但继承语料许可约束（语料入库时登记来源与许可，docs/01 §4.3）

## 6. 资产清单（既有，纳入 M0 管理）

| 资产 | 用途 |
|---|---|
| `scripts/verify_env.py` + logs | 环境审计（本文 §0 数据来源） |
| `scripts/baseline_eval.py` + reports/ | M0 攻击面基线登记（Qwen3-0.6B-Base 实测，本文 §4） |
| `scripts/pretrain_1b.py` | 路线 A 预训练（tiny/125m/350m/1b 预设、断点续训、MFU 回调） |
| `scripts/tokenize_text.py` | 语料 → tokens.npy（流式、EOS 分隔、memmap） |
| `scripts/env.ps1` / `env.bat` | 环境激活（HF_HOME/TORCH_HOME 指向项目 .cache） |
| `LLaMA-Factory/`（+ .venv 内 llamafactory） | SFT/DPO/评估阶段框架 |
| `secfm/`（本次交付） | 载体序列化、上下文协议、评估骨架、审计工具 |
| `data/corpus_test/sample.txt` | ⚠️ 目前为 LLaMA-Factory README（占位）；真实安全语料按 docs/01 §4 采集 |

## 7. M0 出口判据状态

| 判据（docs/01 §7-M0） | 状态 |
|---|---|
| 底座定版 | ✅ **Qwen3-0.6B-Base**（§1，v0.3 决议；已下载核验 + 本机实跑） |
| fertility 报告 | ✅ 完成（§2；Qwen2.5 与终选底座 Qwen3 双实测，均通过） |
| 基线（含污染检查）跑通 | ✅ mini 套件 + 私有留出集 v0.1（60 条）双基线已实测（§4；ASR=1.0 / 误拒 0 / 保守包未条件化）；留出集扩容 ≥50/域进行中 |
| 序列化器 / 协议 v0 | ✅ 交付（secfm.carriers + secfm.protocol） |
| 政策包模板 | ✅ docs/03 |

---

## 修订记录

| 版本 | 日期 | 性质 | 内容 |
|---|---|---|---|
| v0.1–v0.3 | 2026-09-23~28 | 历史版本 | 本文件此前无修订记录表（本次补建）。v0.2 补齐 §0.1 兼容性补丁 8 项与 trl 补丁重放件；v0.3 为底座终选（路线 B / Qwen3-0.6B-Base，§1）与 M0 出口判据状态（§7） |
| v0.4 | 2026-09-30 | **同步修订（本次）** | **§0「训练容量估算」结论行修正**：删除与现状不符的"与 docs/01 §3.1 目标规模（10–30B）匹配"（docs/01 §3.1 已改为实跑口径 0.6B / 1,088M token / 2,072 步 / 30h20m），并把"0.6–1B 模型 5–20B token ≈ 连续运行 2.5–10 天"按实测折算重算为 ≈5.8–23 天（27.8 h / 10 亿 token，为上表 0.7B 行 13–17 h 的 1.6–2.1 倍）。**依据**：`docs/05-m1-training-recipe.md:119`（C1-full 实测）、`docs/01-engineering-definition.md` §3.1（同日已修订）、`docs/01` §11.7 规则 7 第 1 条（禁止步时线性外推）；触发项 `docs/01` §12-8（父代理本次授权同步修订）。**改动仅限 §0 该行 + 本表 + 版本行，未改动本文其余结论。** |
