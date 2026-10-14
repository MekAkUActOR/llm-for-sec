# 本机 LLM 训练能力评估报告

> 评估时间:2026-09-23 · 实测硬件数据

## 一、实测硬件清单

| 组件 | 型号/规格 | 关键参数 |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5090 D v2(GB202-240,Blackwell, sm_120) | 24 GB GDDR7 **384-bit,1344 GB/s**(出口管制削减 25%),dense BF16 峰值 ≈ **297 TFLOPS**(FP4 sparse 2375 TOPS 折算),PCIe 5.0 x16,TDP 575W |
| CPU | AMD Ryzen 9 9950X3D | 16 核 32 线程(Zen5 + 3D V-Cache) |
| 内存 | 32 GB(实测 31.1 GB 可见) | **短板:制约 CPU offload 路线** |
| 存储 | C: 500G / H: 1T / I: 361G / J: 2T | 合计可用 ~2.7 TB,充足 |
| 驱动 | 616.92(CUDA 13.4 capable) | 支持 PyTorch cu128/cu130 轮子 |
| 系统 | Windows 11,Python 3.14(未装 PyTorch/CUDA Toolkit) | sm_120 需 PyTorch ≥ 2.7 |

## 二、一句话结论

- **预训练(从零)**:舒适区 **0.5B–1B**;硬上限 **~1.5B**(8-bit 优化器 + 梯度检查点 + 短序列)。1B 模型按 Chinchilla 标准(20B tokens)实测推算约 **19 天**跑完(10B tokens ≈ 9.5 天)。
- **后训练**:
  - 全参微调:上限 **~1.5B**
  - LoRA(bf16):**7B 舒适,~10B 上限**
  - QLoRA(4-bit):**14B 舒适,32B 紧凑上限(短序列)**
  - DPO/GRPO 等 RL 后训练:**7B–14B(QLoRA 形式)可行**

## 三、能力速览表

| 任务类型 | 舒适规模 | 极限规模 | 主要约束 |
|---|---|---|---|
| 从零预训练(全参) | 0.5B–1B | ~1.5B | 显存 + 单卡算力 |
| 全参 SFT | 1B | ~1.5B | 显存 |
| LoRA / bf16 微调 | 7B | ~10B | 显存(权重 2B/param) |
| QLoRA(NF4)微调 | ≤14B | ~32B(短序列) | 显存 |
| DPO/SimPO(policy+ref) | 7B(QLoRA) | 14B(QLoRA) | 双模型显存 |
| GRPO/RLVR + vLLM rollout | 7B | 14B(QLoRA) | 显存 + rollout 速度 |
| 推理:bf16 | ≤10B | ~11B | 显存 |
| 推理:FP8 | ~22B | ~24B | 显存 |
| 推理:4-bit(llama.cpp/vLLM) | ≤32B | ~50B(临界) | 显存 |

## 四、预训练评估

### 4.1 显存模型(单卡 24 GB)

混合精度 AdamW 训练的每参数显存开销:

| 方案 | bytes/param | 24 GB 可放参数量(留激活空间后) |
|---|---|---|
| 标准 AMP AdamW(权重2 + 梯度2 + fp32优化器8 + master 4) | 16 | ~1.0B(临界) |
| bf16 + fp32 优化器状态(无 master) | 14 | ~1.1B |
| 8-bit Adam(paged) | 8 | ~1.8B |
| + 梯度检查点后激活开销 | seq 2048 下 ~1–3 GB | 已计入上表余量 |

结论:**纯 GPU(无 offload)从零预训练上限 ~1.3–1.5B**。3B 及以上必须 CPU/NVMe offload,而本机系统内存仅 32 GB,offload 7B 的优化器状态都放不下,同时速度下降 5–10 倍,**不具实用性**。

### 4.2 算力/时间模型(6ND FLOPs,有效算力 ~160 TFLOPS,MFU≈40%)

| 模型规模 | Token 数(Chinchilla 20:1) | 训练 FLOPs | 预计耗时(24h 满载) |
|---|---|---|---|
| 125M | 2.5B | 1.9e18 | ~3.5 小时 |
| 350M | 7B | 1.5e19 | ~1.1 天 |
| 0.5B | 10B | 3e19 | ~2.2 天 |
| **1B** | **20B** | **1.2e20** | **~9 天** |
| 1.5B | 30B | 2.7e20 | ~20 天 |
| 3B | 60B | 1.1e21 | ~78 天(且显存需 offload,实际更慢 → 不现实) |
| 7B | 140B | 5.9e21 | ~430 天(不可行) |

若降低数据量(欠训练,如 1B 只喂 5B tokens),时间按比例缩短,但模型质量打折。

> **实测校准(2026-09-23,环境搭建完成后)**:
> - 1B 预设(1.28B 参数,seq 2048,bf16,梯度检查点)持续吞吐 **12,170 tokens/s**(≈10.5 亿 tokens/天),MFU 31.5%(vs 峰值 297 TFLOPS),峰值显存 16.9 GiB。
> - 训练满载状态:541W、SM 2850MHz、显存满频、99% 利用率——单卡吞吐已到硬件上限,上表理论估算按此校准:1B×10B tokens ≈ 9.5 天,1B×20B tokens ≈ 19 天,125M 预设热机 76.4k tokens/s。
> - 环境与脚本细节见 `docs/setup.md`。

### 4.3 序列长度

- 1B 模型:seq 2048–4096 舒适(FlashAttention/SDPA + 梯度检查点)
- 1.5B:seq 2048 内
- 8K+ 长上下文预训练:需进一步缩小 batch 或下探模型规模

### 4.4 存储与数据

- 20B tokens ≈ 60–80 GB 文本(未压缩),2.7 TB 可用空间可容纳 ~1T tokens 级数据集 + 多份 checkpoint,不构成瓶颈
- 1B 模型 bf16 checkpoint ~2 GB/份,建议保留 5–10 份 + 优化器状态另存

## 五、后训练评估

### 5.1 全参微调(SFT)

- 显存同预训练模型:**1–1.5B 上限**(1.5B 需 8-bit Adam + 梯度检查点,seq ≤ 2k)
- CPU offload 路线受 32 GB 系统内存制约,7B 全参 offload 不可行

### 5.2 参数高效微调(PEFT)

| 方法 | 7B 显存 | 14B 显存 | 32B 显存 | 结论 |
|---|---|---|---|---|
| LoRA(bf16 base) | ~16–18 GB ✓ | ~28 GB ✗ | — | 7B 舒适,~10B 上限 |
| QLoRA(NF4 base) | ~6–8 GB ✓ | ~10–12 GB ✓ | ~20–22 GB △ | 14B 舒适,32B 紧凑可行(短序列、小批量) |
| 72B QLoRA | ~38 GB ✗ | — | — | 不可行 |

### 5.3 偏好对齐与 RL

- **DPO/SimPO**(policy + reference 双模型):全参 7B 不可行;QLoRA 7B(policy 4bit + ref 4bit ≈ 10 GB)舒适,QLoRA 14B 可行
- **GRPO/RLVR**(policy + ref + vLLM rollout):7B–14B(QLoRA)可行;rollout 用 vLLM 需 WSL2,或用 llama.cpp 后端
- 奖励模型训练:≤14B(QLoRA)

### 5.4 推理/评测参照

- vLLM(WSL2):bf16 ≤10B;FP8 ~22B;AWQ/GPTQ 4-bit 32B(~18 GB)可跑
- llama.cpp/Ollama(原生 Windows):4-bit 32B 舒适,49–50B 临界

## 六、瓶颈排序与短板

1. **显存 24 GB**——决定一切上限的核心约束(单卡无 NVLink)
2. **单卡算力**——预训练 3B+ 的时间不可接受
3. **系统内存 32 GB**——堵死 CPU offload 逃生通道(这是最容易修复的短板)
4. CPU(16C/32T 9950X3D)与存储(2.7 TB)**不构成瓶颈**
5. 满载功耗 ~850 W(GPU 600W + CPU ~230W):连续 9 天 ≈ 180 kWh,注意散热与电费

## 七、软件环境落地建议(当前:Python 3.14,无 CUDA Toolkit,无 PyTorch)

1. **必须满足 Blackwell(sm_120)兼容**:PyTorch ≥ 2.7 的 cu128/cu130 轮子;Python 3.14 需 torch ≥ 2.9 系列;建议用 `uv` 管理虚拟环境
2. **推荐 WSL2(Ubuntu)**:flash-attn、vLLM、DeepSpeed、bitsandbytes 在 Linux 下支持最完整;llama.cpp/Ollama 可原生 Windows
3. 框架选择:
   - 预训练:nanoGPT / litgpt(单卡友好)
   - 后训练:LLaMA-Factory(Windows 友好)、axolotl(WSL2)、unsloth(单卡效率优化,注意确认 sm_120 支持)
4. 驱动 616.92 已足够新,无需动

## 八、升级路径(按性价比)

| 升级 | 成本 | 解锁能力 |
|---|---|---|
| 内存 32→96/128 GB(AM5 4×32G 或 2×64G) | ~¥1500–2500 | ZeRO-Offload 全参微调 7–14B(慢但可行);大规模数据预处理更稳 |
| 再加一张 5090 D v2(共 48 GB) | ~¥14000 | 7B 全参微调舒适;8–10B 预训练(~2–4 周);4-bit 推理 70B |
| 3–4 卡平台 | — | 14B 全参 / 14B 预训练(~2–3 月);此时 CPU/内存/电源需同步升级 |

## 九、最终定位

本机是**单卡高端消费级训练机**,定位:

- ✅ **适合**:0.5–1B 从零预训练(垂直领域小模型/安全领域专用模型,数天级);7–14B 主流开源模型的 QLoRA/LoRA 后训练(SFT/DPO/GRPO 全流程);32B 级 4-bit 推理与评测
- ⚠️ **勉强**:1.5B 全参训练、32B QLoRA(短序列)、50B 4-bit 推理
- ❌ **不适合**:≥3B 预训练、7B 全参微调、70B 任何形式的训练
