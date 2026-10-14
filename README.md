# llm_for_sec — 安全感知基座模型

以 decoder-only 为核心的安全感知基座模型（foundation model）：感知与理解信息载体（自然语言、代码、文档、网页、图片、音视频）中人类所关注的安全属性，并产出符合人类期望的安全回答或动作。**产品形态（分析师副驾 / 过滤 API / 安全助手 / 代理）是下游任务，不由基模定义。**

当前决议要点（详见 docs/00 §12、docs/01 §8）：

- 基座定位，操作点通过**政策包络**交给部署层；
- **AI Safety / Security / Privacy** 三个领域优先；
- 中英双语，政策条件化双辖区；
- 本机训练（RTX 5090 D v2 24GB），模型规模 **0.6B–1B**；底座已终选 **Qwen3-0.6B-Base**（Apache-2.0，路线 B，M0 实测基线 ASR=1.0/误拒=0.0）；
- 训练栈自有：数据配方 + 政策条件化 + 评估体系；框架层用 LLaMA-Factory（SFT/DPO）与自研脚本（预训练）。

## 文档地图

| 文档 | 内容 |
|---|---|
| `docs/00-problem-definition.md` | 问题定义与分析（L0–L7：使命、形式化、本体、领域、模态、能力、对抗、价值、评估） |
| `docs/01-engineering-definition.md` | 工程定义（系统形态、架构、训练栈、数据地图、评估体系、里程碑） |
| `docs/02-m0-base-audit.md` | M0 底座审计方案与实测报告（硬件实测、fertility、双路线候选、许可） |
| `docs/03-policy-pack-template.md` | 政策包模板与引用机制（政策包络的规格面） |
| `docs/04-m1-corpus-plan.md` | M1 语料地图与入库方案（uplift 控制、来源×许可×层级、manifest） |
| `docs/05-m1-training-recipe.md` | M1 安全中期训练配方（全参继续预训练、超参、上下文扩展、出口探针） |
| `docs/06-m2-sft-recipe.md` | M2 SFT 配方骨架（T1-T12 数据映射、政策条件化配对、VERDICT 契约、评估协议、消融） |
| `docs/07-m3-preference-recipe.md` | M3 偏好优化配方骨架（政策条件化 DPO + M3.5 RLVR/GRPO 提案 + 校准双路径 + 门禁） |
| `docs/policy-packs-v0-draft.md` | 政策包 v0 草案（三包实例化 + hard-floor + 阈值表 + 方向性不变量，已复核） |
| `docs/research/jev-system-one-model.md` | Jev / System One 技术调研（判断层与校准训练的外部参照） |

## 仓库结构

```
secfm/           工具链（M0，纯标准库）
  carriers/        载体序列化 v0：email / webpage(DOM) / code / text + 域名仿冒事实
  protocol/        上下文协议 v0：build/parse + 注入防护转义
  eval/            评估骨架：双指标 Pareto、政策合规矩阵、ECE、报告
  audit/           底座审计：tokenizer fertility + 合成语料生成
tests/           单元测试（44 项，兼作序列化格式的可执行示例）
scripts/         训练环境与脚本（verify_env / pretrain_1b / tokenize_text / env）
LLaMA-Factory/   SFT/DPO/评估框架（外部检出）
data/            语料与 token 文件（gitignored）
docs/            项目文档
reports/         审计报告（fertility 等）
```

## 快速开始

```powershell
. J:\Projects\llm_for_sec\scripts\env.ps1      # 激活 .venv 与缓存路径
python -m unittest discover -s tests -v        # 运行测试（44 项）
```

M0 审计工具：

```powershell
python -m secfm.audit.corpora --out data\fertility --size 65536
python -m secfm.audit.fertility --tokenizer Qwen/Qwen2.5-1.5B `
  --corpora-dir data\fertility --baseline data\fertility\baseline_mix.txt `
  --json-out reports\fertility.json
```

## 设计原则（摘要）

1. **序列化器只标注机械事实，判断归模型**（docs/01 §2.4）；
2. **不静默丢弃安全信号**：隐藏元素、注释、事件处理器、表单目标、URL 不匹配全部保留并标注（五栖居处保真，docs/00 §3）；
3. **截断必须显式**（`[truncated: …]`），永不静默；
4. **双指标纪律**：ASR × 误拒永远联合报告（docs/00 §9.2）；
5. **构造侧防注入**：协议标记在内容中一律转义，载体内容不可能提前闭合区域（`tests/test_context.py` 覆盖）；
6. **评估即代码**：每个检查点自动回归（docs/01 §5.6）。

## M0 状态

| 交付物 | 状态 |
|---|---|
| 环境审计（硬件/软件/SDPA/bnb/训练冒烟） | ✅ `scripts/verify_env.py`（BF16 223.5 TFLOPS） |
| 载体序列化器 v0（email/webpage/code/text） | ✅ 五栖居处信号标注 + 注入中和，44 测试 |
| 上下文协议 v0（build/parse） | ✅ 含"载体内容不可闭合区域"性质测试 |
| 评估 harness 骨架 | ✅ ASR×误拒 Pareto、政策合规矩阵、ECE、报告渲染 |
| fertility 实测（Qwen2.5 + 终选底座 Qwen3） | ✅ 全部通过（docs/02 §2），词表手术不需要 |
| 政策包模板 | ✅ docs/03 |
| 底座终选 | ✅ 路线 B：Qwen3-0.6B-Base（Apache-2.0 已核验，已下载 + 本机实跑） |
| 攻击面基线登记 | ✅ ASR=1.0 / 误拒=0.0（reports/baseline-qwen3-0.6b-base.json） |
| 私有留出集（污染检查前提） | ✅ v0.1 种子 60 条（data/heldout/v0.1，版本化入库）；扩容 ≥50/域进行中 |

## M1 入口（进行中）

| 工作项 | 状态 |
|---|---|
| 私有留出集 v0.1 + base 基线 | ✅ ASR=1.0 / 正当误拒 0 / 保守包 6 条未条件化（reports/heldout-baseline-qwen3-0.6b.json） |
| 语料地图与入库方案 | ✅ docs/04（uplift 红线：restricted 不进 Stage 1 语言建模） |
| Stage 1 训练配方 | ✅ docs/05（全参继续预训练；实测显存峰值 ~23.9GB/24.5GB，吞吐 ~7.9k tok/s → C1 前需 liger-kernel） |
| C0 冒烟雾料（P0 来源抓取 + tokenize） | ✅ 9/9 源入库：371,911 docs / 72.05M tokens，manifest 全绿（docs/04 §4 实况） |
| C0 100 步冒烟训练 | ✅ loss 1.415→1.132（↓20%）无 NaN；VRAM 23.9/24.5GB；吞吐 7.27k tok/s；checkpoint 复评 ASR/ORR 与 base 持平（预期，Stage 1 不改变行为） |
| C0 全 1 epoch + 断点续训验证 | ✅ 137/137 步（checkpoint-100 → 续训 37 步 → checkpoint-137），续训段 loss 1.113→1.082 |
| liger-kernel 提效验证 | ❌ 受阻：triton-windows 上 liger CE 内核 sm_120 非法内存访问（docs/02 §0.1 #7）→ C1 按 ~7.3k tok/s 规划 1.5–2B tokens |
| C1 中文语料（②） | ✅ zhwiki 安全域 5.46M + 通用回放 124.3M（15% 采样）+ 法规 7 部 19.6k → zh 共 ~130M tokens（scripts/fetch_zhwiki.py，85 测试全绿） |
| C1 en 回放语料层 | ✅ enwiki 分区 2–5：**714.9M tokens / 277,025 docs**（每分区 167–190M；分区 1 被探针占用强制隔离，scripts/fetch_enwiki.py，14 项新测试） |
| C1 P1 描述层语料 | ✅ 7/7 源入库：redhat 83.11M + debian 14.68M + msrc 10.08M + sans 8.05M + cisco 7.77M + oracle 2.31M + ghsl/p0 1.14M = **127.1M tokens / 51,812 docs**（fetch 脚本 7 个 + 转换器单测 48 个,全套 187 测试绿;docs/04 §4 P1 实况） |
| C1 arXiv 安全文献层 | ✅ cs.CR 全历史摘要：**13.17M tokens / 50,384 docs**（API totalResults 52,384，与 C0 2,000 按 id 精确去重后新增；CC0 1.0（API ToU：descriptive metadata）；通路工程：curl 子进程过 TLS 指纹 WAF + 按年分片绕 10k 深分页上限，`scripts/fetch_arxiv_full.py`，9 项新测试；探针重叠 7 条已报告待决） |
| M1 出口探针集 v0.1 | ✅ 5 域来源隔离共 1,670 段：sec 500(GHSA)/privacy 173(GDPR 序言)/ais 200(cs.AI)/general_en 297(enwiki 分区)/general_zh 500(zhwiki 留出)；工具链 `fetch_probes.py`+`probe_ppl.py`+`compare_ppl.py`（96 测试全绿） |
| M1 出口探针集 v0.1.1 | ✅ ais 去污版 1,663 段（剔除 7 条 cs.AI×cs.CR 双列目；bit 级确定性验证通过；ais 降幅 -17.5% 去污前后一致） |
| Stage 1 首跑（方案 A：202M 全量 1 epoch） | ✅ 385 步 6h07m，loss 2.14→1.91；**五域 PPL：sec -17.4%（剂量数据点）/ general_en +4.3% / general_zh -16.0% / ais -17.5%**；32k 门禁通过（needle 11/12）；heldout 与 base 持平（预期）；探针体系全链路验证 ✅ |
| C1-full 正式跑（方案 B：~1.09B，安全域 ×2 epoch） | 🔄 2,072 步 × 61.2s ≈ 35h（2026-09-25 07:58 启动）；mix：安全域 217.2M×2（40%）+ enwiki@74% 529M + zhwiki@15% 124.3M；完成后自动评估链（v0.1.1 探针）→ M1 出口判定 |
| C2 隐私工程知识层（M1.5） | ✅ 5/5 源入库：arXiv 隐私/内鬼研究 2,680 docs + GDPR 全文（EUR-Lex 逐条）100 + CN 四法全文（PIPL/网安/数安/保密）4 + NIST 框架（PF 1.0/800-188/FIPS 199/800-171r3/800-53 AC+SC 族）80 + 凭证格式识别知识 10 = **1.02M tokens / 2,874 docs**（摘要层物理上限 ~5M 已实测,GB/T 35273 按版权红线跳过;fetch 脚本 5 个 + 单测 22 个,全套 223 测试绿;docs/04 C2 实况） |
| C2 AI-safety 知识层（M1.5） | ✅ 8 源入库：arXiv 十一查询（AI-safety/恶意代码/内容安全 + **alignment 变体 b**含标题级纯度过滤,排除 C1 7,982 跨列目重合）18,880 docs + GTFOBins 478 + LOLBAS 248 + NIST（AI 600-1/AI RMF/SP 800-226）3 + OWASP RTG 1 + OWASP LLM Top10 **2026 版** 12 + MITRE ATLAS 278 + AIID **R2 导出桶破局** 1,689 = **6.16M tokens / 21,589 docs**（红线分类：描述级知识+事件报告=OK;许可四处记档：GTFO/LOLBAS=GPL-3.0、ATLAS=Apache-2.0、AIID=未公示——D3 台账;Reports 表按版权排除;fetch 脚本 5 个 + 单测 31 个;docs/04 C2 实况） |

## M2.5 状态（进行中，2026-09-30 凌晨）

| 工作项 | 状态 |
|---|---|
| m25 数据组装（`scripts/assemble_sft_m25.py`） | ✅ 01:49 完成：**137,670 行**（内容级 zh **44.0%**，上限 45%；估 67.2M tokens / 293 MB），断言全过（reports/m25-assembly-check.json：errors=[] / passed=true） |
| 全族结构 + 污染复检（`scripts/check_m25_staging.py`） | ✅ PASS：10 个 staging 族、errors=[]；**464 行公共文本双侧复用裁定命中、未裁定 0**（reports/m25-staging-check.json，adjudicated_count=464） |
| `sec_sft_m25` 注册（data/lf/sft_m25.jsonl） | ✅ 谱系 **base → c1-full → m16-32k → m15 → m25-full**；data/lf/dataset_info.json 已登记 |
| M2.5 全量重训（m25-full） | 🔄 **2026-09-30 ~01:50** 从 `checkpoints/qwen3-06b-sec-m15` 发射，config **configs/m25-full.yaml**（bs1×accum16 / lr 1e-5 × 2ep / cutoff 4096）——**17,210 步 ≈ 10.3h**（~2.15 s/it），预计 **~12:10** 完成；看门狗 reports/m25-watchdog.log |
| 训后链 | 📋 `scripts/post_m25_eval.ps1`（heldout v0.2.1 行为对照 + 双 PPL 对照 + needle 水位守护）待发射 |
