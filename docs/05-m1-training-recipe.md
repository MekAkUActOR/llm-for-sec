# M1 安全中期训练配方（Stage 1）

> 版本 v0.1 · 承接 docs/04（语料）与 docs/01 §3.1（训练栈）。
> 底座：Qwen3-0.6B-Base（28L / hidden 1024 / GQA 16Q-8KV / vocab 151936 / 32k ctx / tied embed）。

---

## 1. 训练方式决策：全参继续预训练（已定）

显存预算（bf16 + 梯度检查点，seqlen 4096，micro-bs 8）：

| 项 | 占用 |
|---|---|
| 权重 bf16（0.6B） | 1.2 GB |
| 梯度 bf16 | 1.2 GB |
| AdamW 状态（fp32 m+v） | 4.8 GB |
| 激活（checkpointing） | 2–4 GB |
| **合计** | **~10–13 GB / 24 GB** ✅ 余量充足 |

- **全参继续预训练**：安全知识需要触及底层表征（判断任务的地基），且 0.6B 完全放得下——没有理由用低秩约束可塑性；
- LoRA/QLoRA 留给 Stage 2 的快速迭代实验与对照消融；DPO 阶段再评估全参 vs LoRA；
- 训练吞吐预估：~55–75k tokens/s（40% MFU、含重计算）→ **3B tokens ≈ 14–20 小时**，一晚一个检查点节奏。

## 2. 数据（docs/04 §2 配比 v0）

- C0 冒烟批：P0 清洁来源 ~1B tokens（先打通管线）；
- C1 主批：3–5B tokens，配比 security 35% / privacy 5% / ai_safety 10% / code 15% / 通用回放 35%（zh:en 总体 4:6）；
- 打包：`packing: true`（cutoff 4096）+ EOS 分隔（tokenize_text.py 约定一致）；
- **uplift 红线**：restricted 层不进本阶段（docs/04 §0）。

## 3. 超参起点

| 参数 | 值 | 依据 |
|---|---|---|
| learning_rate | 1.0e-4 | 从零配方（~3e-4）的一半以下，避免冲毁底座通用能力 |
| lr_scheduler | cosine → 1e-5 | |
| warmup_steps | 200 | |
| 全局 batch | ~512k tokens（**micro 2 × accum 64** × 4096） | 与底座预训练末期量级匹配；micro 8 会在 152k 词表 cross_entropy 处 logits 19.9GB OOM（docs/02 §0.1 #6） |
| epochs | 1（公开通告类文本不做多轮，防记忆化） | |
| bf16 + grad checkpointing + fused AdamW | 开 | 实测栈（docs/02 §0） |
| weight_decay / max_grad_norm | 0.1 / 1.0 | |

## 4. 上下文扩展策略

1. 主训练 packed 4096；
2. 末段 10% 步数：cutoff 16384（micro 2 × accum 64）；
3. 末段 2%：cutoff 32768（native，无需 RoPE 修改）；
4. **64k 目标**：YaRN（factor 2.0）单独消融后决定——若 32k 已满足 M1 判据（目标上下文长度可用），64k 推迟到 M2 期间并行做，不阻塞主线。

## 5. 执行框架与配置

LLaMA-Factory `--stage pt`（对 base 模型即继续预训练；注意本版本
stage 值为 `pt`，非旧文档的 `pretrain`），
`configs/c0_smoke.yaml`：

```yaml
### model
model_name_or_path: .cache/huggingface/hub/models--Qwen--Qwen3-0.6B-Base/snapshots/da87bfb608c14b7cf20ba1ce41287e8de496c0cd

### method
stage: pt                 # 本版本预训练 stage 值为 pt（非 pretrain）
do_train: true
finetuning_type: full

### dataset
dataset: sec_c0            # dataset_info.json 注册
dataset_dir: data/lf
packing: true
cutoff_len: 4096
preprocessing_num_workers: 8
overwrite_cache: true

### output
output_dir: checkpoints/qwen3-06b-sec-c0-smoke
logging_steps: 10
save_steps: 100
save_only_model: true
save_total_limit: 1
plot_loss: true
report_to: none

### train
per_device_train_batch_size: 2
gradient_accumulation_steps: 64
learning_rate: 1.0e-4
max_steps: 100             # 冒烟；全量去掉此项用 num_train_epochs: 1.0
lr_scheduler_type: cosine
warmup_steps: 20
bf16: true
gradient_checkpointing: true
```

运行（先冒烟后全量）：

```powershell
. .\scripts\env.ps1
llamafactory-cli train configs/c0_smoke.yaml   # 100 步冒烟（实测通过，见 §6）
```

注意：**不要设置** `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`（本机 WDDM + Blackwell 驱动上反向传播报 CUDA driver error，见 docs/02 §0.1 #5）。

## 6. 冒烟与全量的门

1. **100 步冒烟**（✅ 2026-09-24 完成，实测值）：
   - loss：**1.4149 (step 5) → 1.1321 (step 100)，相对下降 20.0%**，无 NaN，grad_norm 1.24 → 0.27 健康收敛，lr cosine 轨迹正确（峰值 9.94e-5 → 3.9e-8）；train_loss 均值 1.1892；
   - 显存：原设 ≤16GB，**实测峰值 ~22.5GB（训练进程）+ 1.4GB 基线 ≈ 23.9/24.5GB**——152k 词表全参训练的真实下界，bs 2 已是本机可行配置，门禁修订为"≤23.5GB 且不 OOM"；
   - 吞吐：原设 ≥40k tok/s，**实测 7.27k tok/s（52.4M tokens / 7209s，72.1s/step @ 524k tokens/step）**——小 micro-batch + 逐 token 大词表 CE 的内存带宽瓶颈；
   - **liger-kernel 提效验证（2026-09-24）：受阻**——triton 无 Windows/cp314 官方 wheel；`triton-windows`（cp314）可装且基础内核正常，但 **liger fused CE 内核在 sm_120 上运行即非法内存访问**（0.6.5/0.8.3 双版本同症），已卸载防误用。详见 docs/02 §0.1 #7；
   - **C1 吞吐决策（liger 不可用后的落地口径）**：接受 bs 2 × accum 64 @ ~73s/step ≈ 7.3k tok/s，**C1 规模按 1.5–2B tokens 规划（≈2.4–3.2 天连续训练）**，与 docs/01 §3.1 中期目标下限一致；若未来换 Linux 训练节点可恢复 liger 路线（预期 ~3× 提速）；
   - checkpoint 复评（`scripts/baseline_eval.py --heldout`）：ASR=1.0、over_refusal=0.222，**与 base 基线完全一致（预期：Stage 1 只做领域感知，拒绝行为属 SFT）**；输出可观察到 C0 分布内化（自发复现 CVE 条目格式"Affected products: … References: …"），确认学习生效（reports/heldout-smoke-c0-checkpoint100.json）；
2. **C0 全 1 epoch**（✅ 2026-09-24 完成）：137/137 步（100 步冒烟 + 37 步断点续训，续训段 52:52，含 lr 小幅回弹 ~1.7e-5 的余弦重启痕迹，属 save_only_model 无优化器状态续训的预期行为）；续训段 loss 1.113 → 1.082，无 NaN；checkpoint-137 复评 ASR=1.0 / ORR=0.222（与 base 持平，预期）；产物 `checkpoints/qwen3-06b-sec-c0-smoke/checkpoint-137`；
3. **C1-202M 完整跑（方案 A，✅ 2026-09-25 完成，全 7 项评估落地）**：
   - **运维教训（保留）**：bs2×64 峰值 22.5GB 贴 24GB 上限，step~50 后陷入 **WDDM 显存超卖死亡螺旋**（特征：util 99% + 功耗 <200W + 带宽 <10%，步速 65s→停滞）；**bs1×accum128（有效 batch 不变）峰值 ~20.5GB 留 2.8GB 桌面余量，反而更快**；此后本机全参训练一律 bs1×128，save_steps ≤50；
   - 训练：385/385 步（6h07m，bs1×128 @ ~57.5s/step 均值），train_loss 均值 1.952，loss 2.14→1.91，无 NaN；
   - **域 PPL（base → stage1-202m，五域探针 v0.1）**：sec 12.184→10.062（**-17.4%**，未达 25% 线——本跑安全域仅 72M C0 占 36%，为剂量-响应验证数据点）；general_en 16.983→17.720（+4.3% PASS）；general_zh 21.269→17.859（**-16.0%**，回放显效）；privacy 2.536→2.640（+4.1%）；ais 30.082→24.805（-17.5%）；
   - **32k 长上下文门禁：通过**（en +6.4% / zh -10.9% 均 ≤10%）；needle 12 档命中 11（唯一失手 32k/en d=0.25）；16k 观察项：en +6.1% / zh -9.5%；
   - heldout：ASR=1.0 / ORR=0.222 与 base 完全一致（预期——Stage 1 不改变行为）；
   - 结论：**探针体系全链路验证通过**；sec 剂量-响应已获得第一个数据点，C1 全量（安全域 199M，2.8×）的 sec 降幅待测；
4. **C1-full 正式跑（方案 B，✅ 2026-09-26 14:19 完成，零告警）**：~1.09B mix（安全域 217.2M×2 epoch 占 40% + enwiki@74% 529M + zhwiki@15% 124.3M），**2,072/2,072 步 30h20m（~52.8s/step 全程稳定无超标），train_loss 均值 1.6934（1.9226→1.6627）**，`configs/c1_full.yaml`，checkpoint 目录 `checkpoints/qwen3-06b-sec-c1-full`；mix 组装脚本 `scripts/build_c1_mix.py`（显式来源清单 + enwiki 标题哈希 74% 确定性子采样 + manifest 键名映射）；完成后自动评估链（`scripts/post_c1_full_eval.ps1`，探针 v0.1.1 净化版）→ M1 出口判定。方案 B 理由（用户 2026-09-25 拍板）：stage1-202m 验证了 ~36-40% 安全配比健康，安全域有效曝光 72M→434M（6×）冲击 sec PPL -25% 门禁，比方案 A（1.5B 单跑，安全域仅占 13%）门禁把握高且省 9 小时。
   5. **M1.5 知识注入短针（📋 计划态，2026-09-28 改造完毕——在 M1.6 之后发射）**：起点 **M1.6-32k 产物**（32k 补段未跑则回退 m16 8k 段产物），以 **lr 2e-5**（知识针，比 C1 的 1e-4 低一档）注入 C2 知识层，**cutoff 16384**，~114 步 ≈ 2.2h（`configs/m15.yaml`：bs1×32×16k、cosine、warmup 5、save_steps 10、全量 checkpoint 可中断；⚠ 需分块 CE 补丁预载——见第 7 条）。语料 `sec_m15`（`scripts/build_m15_mix.py` 组装）：**C2 知识层 ×3 epoch**（manifest 运行时动态枚举全部 c2_* 源，当前 12 文件 2.87M tokens，b 变体增量自动纳入）+ **enwiki 补集回放 ~27M**（2026-09-28 改造：enwiki 摘要回放废弃——摘要短文是 32k 退化元凶；改为 **zhwiki ≥3000 字符长文 38.4M**，md5("m15replay-zh:"+title)%10000<5900，护 M1.6 恢复成果；en 遗忘风险低——C1 general_en 实测 -18.0%）。训后链 `scripts/post_m15_eval.ps1`：**双基线对比**（base→m15 累计 / **c1-full→m15 增量——M1.5 主读数**）、探针 v0.3 优先回退 v0.1.1、heldout v0.2 + **判分器 v2 首次实战**（--dump-responses → score_heldout_v2 闭环）、32k 长上下文对照（m15 vs m16，防知识针损伤恢复成果）。红线：mix 绝不含 C1 安全域文本（sec_c1*.jsonl 只读不写）。
   6. **M1 出口判定（2026-09-27，C1-full 读数）**：**两硬门禁未过**——sec PPL 12.184→9.873（**-19.0%** vs 门禁 ≥25%，差 6pp；剂量-响应印证摘要层天花板：安全域 ×5 仅换 -1.6pp）；**32k 长上下文 en +11.0% / zh +13.1%**（门禁 ≤+10%）+ needle 12/12→7/12（32k 深位 1/6，16k/en 也塌至 1/3）。通用域 PASS（en -18.0% / zh -17.7%，wiki 在盘反升）。ais 相对 stage1 回缩（-17.5%→-14.4%）、privacy 恶化（+4.1%→+5.9%）= wiki 稀释效应，恰为 M1.5 C2 层直接目标。heldout ASR=1.0/ORR=0.222 与 base 持平（预训练教感知不教行为，预期）。**用户选 C**：先长上下文恢复（M1.6）再 M1.5；sec 缺口由 M1.5 C2 层继续补。
   7. **M1.6 长上下文恢复短跑（🔄 2026-09-27 深夜执行）**：`sec_m16` = zhwiki ≥3000 字符长文 6,430 篇 30M tokens（C1 已训 = 回放语义，恢复注意力先验而非学新知），`configs/m16.yaml`。**工程教训（32k 直跑 OOM 实测）**：fp32 logits 副本 19.9GB + bf16 10GB + 静态 9.6GB → 全词表 CE 显存成本 ≈ 0.87MB/token 位，**24GB 无融合 CE 硬上限 ≈ 12k cutoff**；liger 双重死路（triton 无 Windows 轮子 + 2026-09-24 已实测 sm_120 非法内存访问，docs/02 §0.1 #7）。**分轨**：8k 段（logits 7.5GB 安全，bs1×accum64，58 步 ~1.3h，修 16k 及以下退化）先行；32k 深位恢复等 `scripts/patch_chunked_ce.py`（lm_head 前按位置分块逐块 CE 累加、不物化全量 logits；含 num_items_in_batch 梯度累积语义保持 + 前后向一致性测试 + 显存实测）验证后以 `configs/m16-32k.yaml` 二段跑（bs1×accum16）。门禁：32k PPL vs base ≤+10% 且 needle ≥9/12（`post_m16_eval.ps1` 三方对照 base/c1-full/m16）。

## 7. M1 出口探针（docs/01 §7）

> ⚠ **2026-09-28 污染审计**（详见 docs/research/probe-contamination-audit.md）：privacy 探针（GDPR 序言）与 c0_gdpr 训练语料系统性重叠（64.9%）；general_en 探针与 enwiki 训练采样存在 ~26% 篇级重叠——**PPL 绝对幅度读数需加注**（横向模型对比不受影响）。探针 v0.4 将换源/严格排外重制；M2.5 起所有消费同源语料的生成器强制单元级预筛。

**探针集 v0.1**（`data/probes/v0.1/`，`scripts/fetch_probes.py` 生成；纪律同 data/heldout：来源隔离、永不入训练、版本化、逐步扩容）：

| 域 | 来源（v0.1 实况） | 条数 |
|---|---|---|
| sec | GHSA 通告（github/advisory-database zip，CC-BY-4.0；GHSA 自撰文本，与训练 cvelistV5 不同源不同措辞；zip 被网络重置截断后经本地头扫描抢救 37.6 万条 JSON 通告取最新 500；OSV API 与 Ubuntu USN 均因本网络 TLS 拦截弃用） | 500 |
| privacy | GDPR 序言 173 条（gdpr-info.eu/recitals；训练语料只含正文条款，序言天然隔离） | 173 |
| ais | arXiv cs.AI 摘要（训练为 cs.CR；按 id 剔除双列目；arXiv API 限流 406 下分页取） | 200 |
| general_en | enwiki dump 第一分区（p1p41242 经典条目，复用 zhwiki 清洗管线；摘要 dump 已停产、random API 被限流） | 297 |
| general_zh | zhwiki dump 未入训练采样的条目（标题过滤 + 独立哈希流确定性采样） | 500 |

**探针集 v0.1.1**（2026-09-25 去污版本化，`data/probes/v0.1.1/`）：**唯一变更 ais 200→193**——剔除 7 条与 C1 arXiv cs.CR 全历史语料重叠的 cs.AI×cs.CR 双列目（v0.1 抓取时的训练集排除正则从未生效，因 C0 文本不嵌 id；证据 `reports/probe-ais-overlap-arxiv-full.json`，剔除清单见 v0.1.1/README.md）；其余四域与 v0.1 字节相同。v0.1 原目录保留（审计轨迹）。基线重跑（`reports/ppl-base-v0.1.1.json` / `ppl-stage1-202m-v0.1.1.json`）：**四域数字与 v0.1 完全一致（探针确定性验证通过）**；ais 净化后 base 30.459→stage1 25.115（**-17.5%**，与污染前 -17.5% 一致——ais 改善是真实训练效果，非污染伪影）。

**探针集 v0.3 实测态**（2026-09-25 fetch 执行完成，`data/probes/v0.3/`；执行序：check-design PASS → fetch → ais-500 零污染晋升 → assemble sha256 锁定）：

| 域 | 来源 | 实测条数 | 存活率（kept/候选） |
|---|---|---|---|
| aisafety | cat:cs.CY ×安全表达式；三层排除 vs 训练语料 | **144** | 28%（144/512） |
| malware | cat:cs.SE/PL/CY × 恶意代码分析表达式；同上排除 | **78** | 24%（78/324） |
| content | cat:cs.CY/soc.SI × 内容审核表达式；同上排除 | **263** | 41%（263/640） |

**未达 300–500 设计区间——互补类目池物理更小的实证**（安全/恶意代码论文主要列目在训练侧 cs.CR/cs.AI/cs.CL/cs.LG，互补轴 cs.CY/SE/PL/soc.SI 命中池浅：malware 三查询候选 324 条即枯竭）。分层读数：①排除层未误杀（排除命中=训练侧跨列目，id-in-train 为主）②三域合计 485 条同域留出已可支撑 M1.5 域内 PPL（v0.1.1 privacy 域 173 条即有效先例）③扩至 300+ 须设计侧扩查询/类目（cs.NA/cs.OS 或放宽表达式）——不在执行序内改动，留设计 agent 决策。逐查询明细见 `-index.jsonl` 审计索引。**2026-09-25 父会话裁决：维持互补不变量，接受池物理上限，不扩类目**（互补性是零污染的结构性保证，比探针体量更重要）。

三层隔离（终态实测）：①id 层 **75,613** id（raw 560 页全量 parse）②标题层 **75,588**（norm_title 精确匹配——v0.1.1 事故的补层）③探针内互斥 **693**（v0.1.1 ais 193 + ais-500 草稿 500）。互补类目轴 = 设计不变量（check-design 实测 PASS：查询类目 ∩ 训练 CATS {cs.AI,cs.CL,cs.CR,cs.LG,cs.DB} = ∅）。**ais-500 晋升实测**：草稿重抓版（32 条污染修复版）对 C2 终态 **零污染直过**（n=500, overlap=0），语料态 sha256 标记锁定（.ais500-verified.json）；`--prune` 净版路径未用（重抓优于剪除，保满 500）。v0.3 组装 = v0.1.1 四域字节复制（sec 500/privacy 173/general_en 297/general_zh 500，纵向可比）+ ais-500 验证版 500 + 三新域 485 + 审计 README——**合计 2,455 条**。

**PPL 工具**：`scripts/probe_ppl.py`（滑窗 NLL 按 token 加权，chunk_windows 5 项单测）；报告落 `reports/ppl-<name>.json`。

| 探针 | 工具 | 达标线 |
|---|---|---|
| 领域困惑度 | `scripts/probe_ppl.py` + data/probes/v0.1.1（现行；v0.1 审计保留） | sec 域 PPL 相对 base 下降 ≥25%，通用 zh/en PPL 回升 ≤10% |
| 新域 PPL（aisafety/malware/content，M1.5） | `scripts/probe_ppl.py` + data/probes/v0.3 三新域 | **观察项（无硬门禁）**：C2 知识注入后同域留出 PPL 相对 base 的变化——与 sec 域门禁不同，新域是 C2 训练语料的直接域内测量，用于建立剂量-响应基线 |
| 上下文长度可用 | 16k/32k 长文档 PPL + needle 抽查（简单版） | 32k 段 PPL 不劣化超过 10% |
| 留出集复测 | `scripts/baseline_eval.py --heldout data/heldout/v0.1` | ASR/误拒不劣化（本阶段不练对齐，预期 ASR≈1 维持）；capability 裁决正确率出现提升信号 |
| 专家抽检 | 人工 | 安全领域段落生成：术语准确、无幻觉拼造 CVE 编号 |

## 8. 风险与预案

| 风险 | 信号 | 预案 |
|---|---|---|
| 灾难遗忘（中文/通用） | 通用探针 PPL 回升 >10% | 回放比例 35%→45% |
| 通告模板过拟合 | sec PPL 降但生成模板化 | NVD 类单源占比上限 20%，多样化采样 |
| bf16 训练不稳 | loss spike / NaN | 降 lr 至 5e-5；仍不稳则 DeepSpeed ZeRO-2 + fp32 master |
| 32k 长上下文退化 | 末段 loss 反弹 | 缩短 16k/32k 末段比例，或 YoPE scaling 调参 |
