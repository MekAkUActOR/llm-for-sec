# Round-8（m5a-r8 · Qwen3-8B 对齐底座 + F5-DPO）施工简报

- 上游：r7（8B-**Base** + F5-DPO）W2 ASR 80.36% 灾难破 —— 定性为**基座先验对照臂**：裸基座无拒绝先验，单轮 LoRA-DPO 无法从零建立；0.6B 谱系的 M2.5/M3/M4 校准前奏在风险轴贡献被隔离证实
- 本轮科学问题（真·容量判定）：**对齐 8B + F5 最小对机制**能否同时过 ORR 与护栏门？0.6B 十二臂地板 7.62–13.65% 是容量限制还是方法限制——r8 直接判
- 底座：Qwen/Qwen3-8B（对齐后训练版，2026-10-16 ModelScope 下载落盘 .cache\modelscope-dl\...\snapshots\master，16 文件 16.4GB）
- 数据 = p16-calibration-r6 原套（40,458 concat，与 r6/r7 严格同件）；预算 = 300 步同剂量（隔离底座变量；剂量实验归 r9）

## 一、X1–X4 预测冻结（判读不回改，fail-closed）

| # | 门 | 依据 |
|---|---|---|
| X1 | ORR ≤8%（破 0.6B 地板带下沿即算容量证据） | 对齐先验 + 8B 容量 + F5 内容判别 |
| X2 | ASR ≤5.76%（护栏门与 r5/r6/r7 同标尺） | 对齐基座拒绝先验应守住风险轴 |
| X3 | tiered jb ≤28.75%（不劣于 0.6B 最优臂 r5） | 容量不得损风险轴 |
| X4 | 脱钩 ≤20/80（悬置机制 8B 复试；r7 侧读 deflect 3.8% 证明可转移） | 悬置正向教学 |
| 判读 | **X1+X2 双过 ⇒ 容量假说在对齐底座上成立 ⇒ 8B 主线确立（r9 = 剂量 900 步冲 1% 使命门）**；X1 fail 且 ORR ≥8% ⇒ 对齐 8B 亦地板 ⇒ 方法瓶颈实锤，回数据/方法侧 | |

## 二、执行（流水线与 r7 全同：r7-runner 续任）

1. configs/m5a-dpo-r8.yaml = r7 版复制，仅改：model_name_or_path → 本地 MS 快照目录、output_dir → qwen3-8b-sec-m5a-dpo-r8（LoRA 块 rank16 α32 lr 5e-5 全保留）
2. 时序：**r7 门禁链哨兵落地 + Guard 之后**方可发射训练（GPU 串行铁律）
3. LoRA 合并 → checkpoints\qwen3-8b-sec-m5a-dpo-r8-merged → 门禁链 run_m5a_r8_gates.ps1（r7 逐字适配 + r8 config sha）
4. X 读数提取（六读数同 r7 模式）→ 报 Lead 终裁

## 三、纪律

预测冻结不回改；append-only 勘误；谱系：r7/r8 均为 8B 新谱系容量判定臂（互为对照：Base vs 对齐），不入 0.6B 谱系；十三臂对照表扩至十五臂（r7、r8）
