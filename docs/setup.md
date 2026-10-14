# 训练环境使用手册(1B 预训练就绪)

> 搭建时间:2026-09-23 · 全链路已在本机实测验证

## 一、环境总览

### 硬件

| 组件 | 规格 | 实测状态 |
|---|---|---|
| GPU | RTX 5090 D v2(GB202-240,21760 CUDA,sm_120) | 驱动 616.92,CUDA 13.0 运行时,工作正常 |
| 显存 | 24GB GDDR7 **384-bit,1344 GB/s**(出口管制版,比 5090 的 1792 GB/s 低 25%) | 训练中可用 ~22.3 GiB |
| 算力 | dense BF16 峰值 ≈ **297 TFLOPS**(FP4 sparse 2375 TOPS 折算) | 短基准 223 TFLOPS,持续训练满载 541W / 99% 利用率 / SM 2850MHz / 67°C |
| CPU / 内存 | Ryzen 9 9950X3D(16C32T)/ 32GB | 不构成瓶颈 |
| 存储 | J: 盘 1.9TB(可用 ~1.4TB)放项目与缓存 | 充足 |

### 软件栈(全部装在 `J:\Projects\llm_for_sec\.venv`,Python 3.14.6)

| 包 | 版本 | 说明 |
|---|---|---|
| torch | **2.14.0+cu130** | Blackwell sm_120 原生支持 |
| torchvision / torchaudio | 0.29.0+cu130 / 2.11.0+cu130 | LLaMA-Factory 依赖 |
| transformers | 5.8.0 | 注意:5.x 移除了 `overwrite_output_dir`/`save_safetensors` 等参数 |
| datasets / accelerate / peft / trl | 4.0.0 / 1.11.0 / 0.18.1 / 0.24.0 | trl 含 2 处手工补丁(docs/02 §0.1 #8/#9);**重装/重建 venv 后须重放** `python scripts\patches\apply_venv_patches.py` |
| bitsandbytes | 0.50.2 | 8-bit AdamW / QLoRA 用,实测可用 |
| llamafactory | 0.9.6.dev0 | editable 安装于 `LLaMA-Factory\`,CLI 正常 |
| tensorboard / uv / 其他 | 2.21.0 / 0.12.18 / … | |

环境变量(已写入用户级,新开的终端自动生效):`HF_HOME=J:\Projects\llm_for_sec\.cache\huggingface`、`TORCH_HOME=J:\Projects\llm_for_sec\.cache\torch`。

## 二、快速开始

```powershell
# 激活环境(二选一;ps1 若报执行策略错误,先执行一次
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
. J:\Projects\llm_for_sec\scripts\env.ps1
J:\Projects\llm_for_sec\scripts\env.bat

# 环境自检 + GPU 基准(约 1 分钟)
python J:\Projects\llm_for_sec\scripts\verify_env.py

# 训练管线冒烟(tiny 模型 + 随机数据,约 1 分钟)
python J:\Projects\llm_for_sec\scripts\pretrain_1b.py --preset tiny --synthetic --max-steps 20 --save-steps 20
```

## 三、1B 预训练完整流程

### 第 1 步:准备语料并 tokenize

```powershell
# 把语料(.txt/.md/.jsonl,可放目录递归扫描)转成 tokens
python scripts\tokenize_text.py --input data\corpus --tokenizer Qwen/Qwen2.5-1.5B --output data\tokens.npy
```

- 默认 Qwen2.5 tokenizer(zh+en 均优、无需申请、vocab≈152k)
- 流式处理,任意大语料都不会撑爆 32GB 内存
- 文档间自动插 `<|endoftext|>`;产出 uint32 的 .npy(memmap 零拷贝读取)

### 第 2 步:启动 1B 预训练

```powershell
python scripts\pretrain_1b.py --preset 1b --data data\tokens.npy --tokenizer Qwen/Qwen2.5-1.5B
```

默认超参(实测过显存):Llama 架构 1.28B 参数(d=2048, L=16, GQA 32/8, tied embed)、seq 2048、micro_bs 2 × accum 32(131k tokens/step)、bf16 + fused AdamW、cosine LR 3e-4 + 2% warmup、梯度检查点开启。

可选参数:`--lr`(默认 3e-4)、`--seq-len`、`--micro-bs/--accum`、`--epochs`、`--save-steps`(默认 500)、`--optimizer bnb8bit`(省 ~2.4GB 显存,可换 micro_bs 4)、`--precision fp32`(仅建议 ≤350m 预设用)。

### 第 3 步:断点续训 / 监控

```powershell
# 中断后续训(自动找最新 checkpoint-*)
python scripts\pretrain_1b.py --preset 1b --data data\tokens.npy --tokenizer Qwen/Qwen2.5-1.5B --resume

# TensorBoard 观察曲线
.venv\Scripts\tensorboard.exe --logdir J:\Projects\llm_for_sec\logs --port 6006
```

注意:HF Trainer 续训后最终汇总的 `train_loss` 是"本次执行步的损失 ÷ 累计总步数",数值会偏小,属统计口径问题;看逐步日志里的 loss 才准确。

## 四、实测性能(2026-09-23,本机)

| 基准 | 结果 |
|---|---|
| FP32 / TF32 / BF16 matmul | 62.4 / 96.9 / 223.5 TFLOPS |
| SDPA 注意力后端 | cuDNN ✓(Blackwell 快路径)、mem_efficient ✓、math ✓;flash-attn 未编译(不影响,默认走 cuDNN) |
| 125M 预设持续吞吐 | 76.4k tokens/s(热机) |
| **1B 预设持续吞吐** | **12,170 tokens/s = 10.5 亿 tokens/天**(MFU 31.5%) |
| 1B 预设峰值显存 | 16.9 GiB(总占用 ~21.5GiB 含桌面,23.9GiB 卡内放得下) |
| 端到端真实验证 | 155KB 真实文本 → tokenize → tiny 模型训练,loss 11.9 → 4.1;checkpoint 保存/恢复 ✓ |

### 1B 模型训练时长推算(按实测 12.2k tokens/s)

| Token 预算 | 预计耗时 | 说明 |
|---|---|---|
| 1B tokens | ~23 小时 | 快速领域预训练 |
| 5B tokens | ~4.8 天 | 垂直领域推荐起点 |
| 10B tokens | ~9.5 天 | |
| 20B tokens | ~19 天 | 接近 Chinchilla 20:1 |

## 五、后训练(LLaMA-Factory)

预训练完成后,用同一环境做 SFT/LoRA/QLoRA/DPO:

```powershell
# 示例:对自己的 1B 模型做 LoRA SFT
llamafactory-cli train LLaMA-Factory\examples\train_lora\llama3_lora_sft.yaml
# (把 yaml 中 model_name_or_path 改为 J:\Projects\llm_for_sec\checkpoints\pretrain_1b)

# 图形界面
llamafactory-cli webui
```

本机 QLoRA 上限 ~32B、LoRA(bf16)舒适区 ≤7B——详见 `docs\local-training-capability-assessment.md`。

## 六、常见问题

1. **PowerShell 运行脚本报执行策略错误** → `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`,或直接用 `env.bat`。
2. **中文输出乱码** → 环境脚本已设 `PYTHONIOENCODING=utf-8`;三个自研脚本也已内置 UTF-8 自适应。
3. **训练时显存富余/吃紧** → 富余:上调 `--micro-bs 4`(约 +5GB 瞬时 logits 开销);吃紧:`--optimizer bnb8bit` 省 2.4GB,或降 `--micro-bs 1`。
4. **显存被桌面占用 ~1.6GB** → 训练时尽量关闭游戏/多余浏览器窗口(本 GUI 页面本身也占一点,属正常)。
5. **网络** → pypi / pytorch.org / github / huggingface.co 实测全部直连可用,无需镜像。
6. **电费与散热** → 满载 541W,连续 10 天 ≈ 130 度电,注意机箱风道。
7. **为什么 flash-attn 显示 FAIL** → torch 官方 Windows 轮子不含 FA2 kernel;Blackwell 上 cuDNN attention 同样快,已在用。

## 七、目录结构

```
J:\Projects\llm_for_sec\
├── .venv\                # 独立训练环境(3.8GB,勿动)
├── .cache\               # HF / torch 缓存(HF_HOME 已指向这里)
├── data\                 # 语料与 token 文件(corpus_test\tokens_test.npy 为示例)
├── checkpoints\          # 训练产出(checkpoint-* + 最终权重 + tokenizer)
├── logs\                 # TensorBoard 日志
├── outputs\              # 预留(后训练导出等)
├── scripts\
│   ├── env.ps1 / env.bat # 环境激活
│   ├── verify_env.py     # 环境自检 + GPU 基准
│   ├── tokenize_text.py  # 语料 → tokens.npy
│   └── pretrain_1b.py    # 从零预训练(tiny/125m/350m/1b 预设)
├── docs\                 # 评估报告 + 本手册
└── LLaMA-Factory\        # 后训练框架(editable 安装)
```
