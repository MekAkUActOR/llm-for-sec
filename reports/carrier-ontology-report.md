# 载体本体论（S1）交付报告

> 日期 2026-10-06 ｜ 执行者：S1 载体本体论工作流代理 ｜ 纯 CPU、docs-first、**未运行任何 GPU 作业**
>
> 交付物：[`docs/08-carrier-ontology.md`](../docs/08-carrier-ontology.md) ·
> [`data/ontology/carriers.json`](../data/ontology/carriers.json) ·
> [`scripts/check_carrier_ontology.py`](../scripts/check_carrier_ontology.py) ·
> [`tests/test_carrier_ontology.py`](../tests/test_carrier_ontology.py) · 本报告
>
> **未修改**：`data/lf/**`、`data/heldout/**`、`configs/**`、`scripts/m3*`、
> `scripts/run_m3*`、`scripts/eval_*`、`reports/m3-dpo-*`、`reports/needlefix-*`（另一条工作流）。

---

## 1. 交付物与行数

| 文件 | 行数 | 性质 |
|---|---:|---|
| `docs/08-carrier-ontology.md` | 383 | 新增（§1–§7） |
| `data/ontology/carriers.json` | 781 | 新增（9 条载体 + 4 个仪器 + 覆盖矩阵 + claims） |
| `scripts/check_carrier_ontology.py` | 638 | 新增（校验器 + 普查 + `--emit-counts`） |
| `tests/test_carrier_ontology.py` | 362 | 新增（unittest，37 tests） |
| `reports/carrier-ontology-counts.json` | 465 | 新增（现算数字快照，**非权威**；权威来源永远是 checker 现算） |
| `reports/carrier-ontology-report.md` | 190 | 新增 |

`docs/08*` 此前未被占用（既有 `docs/00`–`docs/07` + `local-training-capability-assessment.md`
+ `policy-packs-v0-draft.md` + `setup.md`），**未发生编号冲突**。
`data/ontology/` 为新建目录。

> **⚠ 行号引用的时效性（本报告与 `docs/08` 里的所有 `docs/01:行号`）**：
> 本次作业期间 `docs/01` **被另一条工作流持续编辑**（我实测到该文件在几分钟内
> 796 行 → 962 行 → 瞬时 578 行 → 回到 962 行）。因此本报告里的行号锚定在
> **2026-10-06 的 962 行快照**，随时可能偏移。判据请以**节号**为准
> （§2.4 / §5.5 / §9.1 / §10.1 / §10.2 / §10.3 / §11.2 / §11.10 / §11.12 / §11.19），
> 行号只作辅助定位。

---

## 2. 复算命令与实测数字（全部我自己实跑）

### 2.1 主校验

```powershell
.venv\Scripts\python.exe scripts\check_carrier_ontology.py
```

实测输出（末行原文）：

```
[PASS] 本体 data\ontology\carriers.json 与磁盘事实逐格一致（载体 9 类 / 扫描 70 个 jsonl）
CARRIER-ONTOLOGY-CHECK=PASS errors=0
```

```powershell
.venv\Scripts\python.exe -m unittest tests.test_carrier_ontology
```

实测输出（末行原文）：

```
Ran 37 tests in 59.958s

OK
```

### 2.2 训练侧（**逐 scope**，行级计数；本次普查的核心新产物）

扫 `data/lf/*.jsonl` 全量（6,936 MB，**实测 ~20 s**）得：

| scope（文件） | text | email | tool_output | log | webpage | code | document | image_md | av_md | 行数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `sft_m25` | **10,239** | **1,768** | **1,224** | **250** | **250** | **250** | **0** | 0 | 0 | 137,670 |
| `sft_m1` | 9,204 | 733 | 0 | 175 | 175 | 175 | 0 | 0 | 0 | 98,339 |
| `m2_5_staging` | 1,035 | 1,035 | 1,224 | 75 | 1,575 | 75 | 1,200 | 0 | 0 | — |
| `sec_sft_topup` | 0 | 0 | 0 | 0 | 900 | 0 | **1,200** | 0 | 0 | 3,300 |
| `sec_sft_needlefix` | 86 | 87 | 0 | 88 | 82 | 93 | 0 | 0 | 0 | 5,748 |
| `sec_sft_needlefix_carrier` | 486 | 587 | 1,100 | 1,088 | 1,082 | 1,093 | 1,000 | 0 | 0 | 11,748 |
| `carrier_sft_slice` | 400 | 500 | 1,100 | 1,000 | 1,000 | 1,000 | 1,000 | 0 | 0 | 6,000 |
| `dpo_m3_final` | 1,548 | 1,638 | 1,100 | 1,000 | 1,000 | 1,000 | 1,000 | 0 | 0 | 28,842 |
| **`lf_total`（并集）** | **27,076** | **10,484** | **5,624** | **4,713** | **5,607** | **4,718** | **5,200** | **0** | **0** | — |

> 注：`data/lf` 里的预训练文件（`sec_c0` 371,911 行 / `sec_c1` 457,905 /
> `sec_c1_full` 1,237,447 / `sec_m15` 81,602 / `sec_m16` 6,430）以及
> `needle_longctx_slice.jsonl`（3,724）**载体标签全部为 0** —— 预训练侧没有载体维度。

### 2.3 门禁侧（4 个仪器，逐载体 + 行为门禁分母）

| 仪器 | 条目 | 鲁棒性条 | zh/en | 逐载体 | 无标签行 |
|---|---:|---:|---|---|---:|
| `v0.3-gen` | 258 | **168** | 130/128 | av 132（rb 88）, image 126（rb 80） | 0 |
| `v0.2.1` | 161 | 64 | 89/72 | tool_output 8（rb 4）, webpage 3（rb 1）, email 3（rb 2）, code 1, text 1, log 1 | **144** |
| `v0.4-toolout` | 70 | 46 | 35/35 | tool_output 70 | 0 |
| `v0.5-topup-families` | 85 | —（无 kind 字段） | 44/41 | webpage 30, document 27 | **28** |

### 2.4 覆盖矩阵（现算）

| 载体 | train (lf_total) | unseen (v0.3-gen, rb) | regression (v0.2.1+v0.4) | in-dist (v0.5) | sft_m25 |
|---|---:|---:|---:|---:|---:|
| text | 27,076 | **0** | 1 | 0 | 10,239 |
| email | 10,484 | **0** | 3 | 0 | 1,768 |
| tool_output | 5,624 | **0** | 78 (rb 46) | 0 | 1,224 |
| log | 4,713 | **0** | 1 | 0 | 250 |
| webpage | 5,607 | **0** | 3 | 30 | 250 |
| code | 4,718 | **0** | 1 | 0 | 250 |
| document | 5,200 | **0** | **0** | 27 | **0** |
| image_metadata | **0** | **126 (rb 80)** | 0 | 0 | 0 |
| av_metadata | **0** | **132 (rb 88)** | 0 | 0 | 0 |

---

## 3. 与任务书给出数字的差异

### 3.1 **无差异**（逐项相等）

| 你给的 | 我实测 | 判读 |
|---|---|---|
| `sft_m25` text ~10,239 / email ~1,768 / tool_output ~1,224 / log 250 / webpage 250 / code 250 | **10,239 / 1,768 / 1,224 / 250 / 250 / 250** | 完全一致。原因：`sft_m25.jsonl` 里同类型标签每行最多出现 1 次，故「命中数」= 「行数」（两者我都算了，逐项相等） |
| `document` / `image_metadata` / `av_metadata` 在 `sft_m25` 均为 0 | **0 / 0 / 0** | 一致 |
| v0.3-gen 258 条；av 132 + image 126 | **258；132 / 126** | 一致 |
| kind：robustness 168 / alignment 68 / capability 22 | **168 / 68 / 22** | 一致（另新增鲁棒性分载体：av 88 / image 80） |
| 语言 zh 130 / en 128 | **130 / 128** | 一致 |
| v0.4-toolout 70 条 | **70** | 一致 |
| v0.5-topup-families 85 行 | **85** | 一致 |

### 3.2 **发现差异（4 处，都要解释）**

#### D1（重要）v0.4-toolout 是 **15 种机理**，不是 17

- **实测**：`adv=46` 条里 `mech=` 去重 = **15 种**
  （`fake_system_directive`, `fake_json_field_privesc`, `mcp_schema_pollution`,
  `pagination_continuation`, `error_message_instruction`, `id_timestamp_url_smuggle`,
  `nested_tool_result`, `csv_formula_injection`, `log_line_injection`, `base64_payload`,
  `attention_dilution_long`, `hidden_markup_comment`, `unicode_zero_width_bidi`,
  `hex_payload`, `meta_field_smuggle`）。
- **交叉验证**：权威产物 `reports/toolout-heldout-stats.json` 的
  `adv.n_mechanisms = 15`（下限断言 `n_mechanisms_min_required = 12`），
  `reports/toolout-heldout-report.md:58` 也写 `adv: mech=15`。
- **17 是什么**：**17 = 全部 70 条的 `axis=forward` 行数**（我实测 `forward=17, nonforward=41, none=12`）。
  即把「前瞻轴行数」当成了「机理种数」。`reports/s0.4-g1-instrument-repair.md:13`（「70 条 / 17 机理」）
  同样带着这个错误说法 —— **建议更正为「70 条 / 15 机理」**。

#### D2（重要）`document` 在训练侧远不止 0 —— 取决于 scope

- 你给的口径是「`document` 在训练中出现 0 次」（= `sft_m25` 口径，正确）。
- 但本体的并集口径下 **`document` 在 `data/lf` 出现 5,200 行**，其中
  **`data/lf/sec_sft_topup.jsonl` 1,200 行是 `configs/m3base-topup-e1.yaml:8` 的实际训练语料**
  （T2 1,200 + T15 1,200 + T9 900 = 3,300 行；`docs/01 §11.10:694-697` 记录了这次「从 m2-calib 出发的
  低 LR 少步补训」把未见载体 ASR 从 3.6% 抬到 60.1%）。
- **后果**：`docs/01 §10.2:563` 把 document 登记为「**已注册·待入训**（混料出现 0）」
  在「**是否已入训**」这个语义上**已过期**。「`document` 未入训」这句话只在
  「`sft_m25` 混料」这个限定下成立 —— 这正是本体要把 `train_rows` **按 scope 分列**的原因。
- 这也使 `document` 成为覆盖矩阵里最裸露的一格：5,200 行训练数据、**0 条未见载体门禁、0 条在训载体回归**。

#### D3 `docs/01` 两处留出集数字是 122 条版本的残影（26/20 vs 实测 126/132）

- `docs/01 §10.2:564`：「**image_metadata（26 条）/ av_metadata（20 条）**」——实测 **126 / 132**。
- `docs/01 §9.1:513` 引用「`data/heldout/v0.3-gen` **26 条** image_metadata」；
  `§9.1:525` 引用「`data/heldout/v0.3-gen` **20 条** av_metadata 留出」。
- 机制深度扩容（122 → 258）已在 `scripts/check_gen_heldout.py`（`MIN_MECHANISM_KINDS` 等）
  与 `reports/` 里落地，但 `docs/01` 的上表未同步。
- **本体选择**：本体里写**实测值**（126/132，鲁棒性 80/88），并在
  `docs/08 §7.2` 把这两处登记为「需批准的修正」。**我没有修改 `docs/01`**
  （它属于既有文档，且正被另一条工作流编辑 —— 我实测期间该文件从 796 行涨到 962 行）。

#### D4（新发现）`v0.2.1` **不是载体级仪器**：161 条里 144 条无载体标签

- 「在训载体部署格式套件」这个描述容易被读成「按载体给了回归读数」，实测不然：
  只有 17 条带标签（tool_output 8 / webpage 3 / email 3 / code 1 / text 1 / log 1），
  **144 条（89.4%）无 `<carrier>` 标记**（它们是 `query` 直接提问，无载体信封）。
- **后果**：任何「按载体读 v0.2.1」的结论都是在下界上做的，且带标签的载体最多 8 条 ≪ 每格 34 底线。
  本体的覆盖矩阵因此显式记 `untagged_rows`，并在 `cell_caveat` 里写明该列是**下界**。

---

## 4. 我新增/修正的判据

### 4.1 新增的机械判据（checker 强制，全部有单测）

| # | 判据 | 为什么必须新增 |
|---|---|---|
| J1 | **标签闭合性**：仓库里出现的每个 `<carrier type>` 标签 ⊆ 本体 id 集合；否则非零退出并打印**文件名 + 行号样本** | 这是「数据里冒出一个新载体而没人知道」的唯一机械防线。此前全项目没有这个断言 |
| J2 | **结论边界的机器可读形式**：`claims.unseen_carrier_gate_carriers` 必须**恰好**等于「训练 0 次 且 鲁棒性分母 ≥34」的载体集合 | 把 `docs/01 §10.3:578` 的表述纪律从散文变成断言。这是全文最重要的一条 |
| J3 | **门禁效力下限**：`MIN_UNSEEN_ROBUSTNESS_N = 34`；`unseen_gate.robustness_n < 34` 时**该门禁不得被写成可用门禁**（对本体声明值与现算值**双向**生效） | `docs/01 §11.2:601`。原文档只写了「不得作为决策依据」，没有机械检查点 |
| J4 | **矩阵格 ↔ 条目字段交叉自洽**：矩阵格 `n` 必须等于它所引用的 `train_rows`/`gate_items` scope 之和 | 同一数字在两处存副本 → 必须防止「两处各自漂移」 |
| J5 | **训练侧多 scope 分列**（9 个 scope，含 `m2_5_staging` 与 `sft_m25` 分离） | 「注册 ≠ 已训」（`docs/01 §10.1:555`）此前无机械形式；D2 就是这条判据抓出来的 |
| J6 | **仪器 `untagged_rows` 入本体并受断言** | D4：没有这个字段，「v0.2.1 按载体可读」这个错误印象无法被证伪 |
| J7 | **使命层映射闭合**（每个载体 id 至少被一条使命层词条引用；不许引用本体外 id） | 保证「工程层多出来的载体」（如 `tool_output`）不会被静默漏掉 —— 它正是本体发现的**反向缺口**（`docs/08 §2.4-G3`） |

### 4.2 我修正的口径（相对既有文档）

| 既有 | 本体口径 | 理由 |
|---|---|---|
| 「训练出现次数」不区分 scope | 分 9 个 scope，矩阵 `train` 列用 `lf_total` 并集，另列 `sft_m25` | 「已训」是并集问题，「§10.2 登记口径」是混料问题，两者混用会得出 D2 那种过期结论 |
| 「载体计数」用 `carrier_census.py` 的 hit 计数 | 行级计数（同行同类标签只算 1）并同时算 hit，实测两者相等 | 行级口径才能与「条目数」在同一张表里并置；实测相等说明此前也没错 |
| `census_dpo_carriers.py:16` 的 `<\s*carrier(?:\s*=\s*|\s+)([A-Za-z_]+)` | 本体用 `carrier\s+type="X"` 与 `carrier="X"` **两种显式形态** | **该既有正则会把标准形态的 `type` 当成载体名**：对 `<carrier type="email">`，它捕获的是 `type`。我未修改该脚本（属既有数据线工具），但本体**不复用**它 |
| 转义形态 `⟨carrier ...⟩` 是否算标签 | **不算**（它是 `base.py:41-45` 刻意中和的内容） | 避免把「内容里提到了 carrier 标签」误判为新载体 |

---

## 5. 覆盖缺口的可执行清单（本体产出，未执行）

| 缺口 | 现状 | 要成立「未见载体泛化」所需的动作 |
|---|---|---|
| `document` | 5,200 行训练、**门禁 0 + 回归 0**，只有 27 条在分布观测 | 建留出门禁集（鲁棒性 ≥34）+ 在训载体回归集（`docs/01 §10.3` 规则 1(b) 还要求同时补一个新的未见载体） |
| `tool_output` | 门禁 0；回归集**已达标**（v0.4，鲁棒性 46 ≥40） | 只需建未见载体门禁（但该载体已入训 → 必须先把它降级为回归载体，再引入新留出载体） |
| `webpage` / `code` / `log` / `text` / `email` | 门禁 0；回归列 ≤3 条 | 需要**新建按载体的回归集 + 未见载体门禁集**（工作量大，未估成本） |
| `instruction`（使命层） | 工程层无标签 | 要么把协议外壳纳入本体（但它不是载体），要么承认「指令」只以「被注入的载荷」形式存在 |

---

## 6. §7 未解决项（摘要；全文见 `docs/08 §7`）

1. **我没有为任何载体补建门禁集** —— 产出是「缺口可见」，不是「缺口已填」。
2. **没有做逐语言/逐机制的载体细节普查**（只做了机制**种数**：image 24 / av 27）。
3. **没有做真实语料的载体普查**：`data/corpora/raw/**` 的原始网页/文档/日志/代码里
   **根本没有** `<carrier>` 标签（标签只在生成管线里产生）→ 本体的「真实分布」一列是空白。
4. **训练绑定未验证**：`sec_sft_needlefix_carrier.jsonl`（11,748 行）与
   `carrier_sft_slice.jsonl`（6,000 行）在 `configs/` 里**找不到 `dataset:` 引用**；
   R5「载体增广」是否真跑过我没查 → 本体把这两列标为「训练绑定未验证」，`lf_total` 对它们是上界。
5. **checker 不校验散文**：`security_attributes` / `attack_mechanisms` 等列表只校验
   「存在、非空」；`attack_mechanisms` 的机制名取自真实生成器词表，但**没有**做
   `build_dpo_carriers.PAYLOADS` ↔ 本体的集合比对。
6. **需要裁决的 3 件事**：Q1 是否为 document 建门禁集；Q2 是否把 image/av 元数据之一投入训练
   （会同时作废本体里唯一的 2 条断言）；Q3 `docs/01 §10.2`/`§9.1` 的 D2/D3 修正由谁批准。

---

## 7. 作业期间的并行写入（必须登记，影响数字时效性）

1. **`docs/01-engineering-definition.md` 在本次作业期间被另一条工作流持续编辑**
   （实测 796 行 → 962 行 → 瞬时 578 行 → 回到 962 行，grep 重锚定后 §10.2/§10.3/§11.2
   的行号未变）。行号引用已在 `docs/08` 顶部加了时效性纪律。
2. **`data/lf/dpo_m3_final.jsonl` 在我作业期间被重写**（mtime 2026-10-06 13:26，
   同时刻 `configs/m3-dpo-final.yaml` 也被改），这属于**并行的 M3 DPO 工作流**。
   后果：本体的 `dpo_m3_final` scope 数字是**时点值**。若将来 checker 只在这一格报
   `train_rows_mismatch:*:dpo_m3_final`，那意味着「**DPO 混料变了**」，而不是「本体写错了」——
   这是一个**活的绊线**，不是噪声。
3. **我本人没有写过** `data/lf/**`、`data/heldout/**`、`configs/**`：本次只**新增**了
   5 个文件（§1 表）+ 1 个快照产物。上面那些当日的 mtime 全部来自并行工作流
   （我的只读扫描不会改 mtime，我的写路径只有 `reports/carrier-ontology-counts.json`）。

---

## 8. 我最不确定的三点

1. **`lf_total` 里有多少是「真的被训练过」**。`sec_sft_topup`（1,200 行 document）有 configs 绑定，
   可确认已训；但 `carrier_sft_slice` / `sec_sft_needlefix_carrier` **在 configs 里没有 `dataset:` 引用**，
   我只能标「未验证」。若它们其实跑过，document/log/webpage/code 的「已训行数」还要上调；
   若 `sec_sft_needlefix_carrier` 跑过而未走留出排除，v0.3-gen 的留出性也可能受影响 ——
   **我没有去核对训练日志，这是本次最大的未验证假设**。
2. **本体对 `document` 的「已过期登记」判断**：我依据的是
   `configs/m3base-topup-e1.yaml:8` 的注释 + `build_topup_mix.py` 的 `SOURCES` +
   `docs/01 §11.10` 的「3,300 行定向补齐」三者的**一致指向**。我没有找到
   「run → 数据文件 sha256」的直接绑定产物来锁死这一步。若那次补训实际用的是别份数据，
   M1 结论需撤回。
3. **覆盖矩阵的「训练行数」是不是正确的分母**。行数是**出现次数**，不是**训练权重**
   （同一行可能被多轮 epoch、也可能被采样率降权）。因此「text 27,076 行」不等于
   「text 占训练量 27,076/单位」。若将来要按载体做**配比**结论，需要 token 级口径 ——
   本体目前**没有**这个口径，我在文档里显式写了这条 caveat，但没有解决它。
