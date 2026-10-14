# 训练语料目录（docs/04）

**纪律：**

1. 本目录是训练侧；`data/heldout/` 是评估侧——两者物理隔离，评估条目永不入库（docs/01 §5.5）；
2. 每个入库来源必须先在 `manifest.jsonl` 登记（许可、层级、域、规模），登记工具：
   `python -m secfm.data.manifest --file data/corpora/manifest.jsonl`；
3. 层级（docs/01 §6）：
   - `public/`——公开文献与描述层内容，Stage 1 语言建模可用；
   - `restricted/`——PoC/利用代码/自采日志：**只进 SFT 判断任务，不作为语言建模目标**（docs/04 §0 uplift 控制原则）；
   - `quarantine/`——恶意样本本体：仅哈希与静态特征，任何代码不进训练；
4. token 文件用 `scripts/tokenize_text.py` 产出（uint32 memmap，EOS 分隔）。

目录规划：

```
data/corpora/
  manifest.jsonl      # 入库登记（见 docs/04 §3 schema）
  raw/                # 原始下载（按来源子目录）
  clean/              # 清洗后文本
  tokens/             # tokenize 输出（*.npy）
  restricted/         # 受限层（访问审计）
  quarantine/         # 隔离层（哈希/特征 only）
```
