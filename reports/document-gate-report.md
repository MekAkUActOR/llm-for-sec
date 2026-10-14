# v0.6-document 载体门禁集（S1→S2 缺口）报告

> 产物：`data/heldout/v0.6-document/`（`document.jsonl` 80 条 / `manifest.json` /
> `README.md` / `_work/{census,overlap}-full.json`）
> 仪器：`scripts/build_document_gate.py`（构建+自证）、`scripts/check_document_gate.py`
> （检查，末行哨兵）、`tests/test_document_gate.py`（轻量回归）
> 定种子：`SEED=20261007`；文件 sha256（自证）：
> `59bd7cf27e0081e166faa250f205770be7cd98ffcccac245604af298455213d8`
> 本报告不含任何训练语料原文；所有命中只记哈希/计数/窗口。

---

## 0. 一句话结论

本门禁集是**文本文档载体（document：pdf/docx/docm/dotm/xlsx）** 的专用留出集：
**80 条 = 52 条鲁棒性（46 条未见机理 + 6 条在训位点正对照）+ 28 条对齐（干净负例）**，
对**未见该载体的模型**（`soup-a050`：训练 document 行 = 0）可同时支撑
**未见载体 + 未见机理**两类结论；对**已见该载体的模型**（`m3-dpo`：训练 document
行 = 1,000）**只**支撑**未见机理**结论，**不得**声明未见载体（manifest 里机器强制）。

---

## 1. 载体 / 机理 × 计数矩阵

### 1.1 机理 × 载体容器 × 语言

| 门禁机理（未见结构位点） | 载体容器 | zh | en | 对抗(46) | 干净(28) | 合计 |
|---|---|---|---|---|---|---|
| `relationship_target_directive` | docm/docx/dotm | 5 | 4 | 6 | 3 | 9 |
| `form_field_name_directive` | docx/pdf | 4 | 5 | 6 | 3 | 9 |
| `embedded_file_name_directive` | docx/pdf/xlsx | 5 | 4 | 6 | 3 | 9 |
| `custom_docprops_directive` | docx/pdf | 5 | 5 | 6 | 4 | 10 |
| `author_meta_directive` | docx/pdf/xlsx | 4 | 4 | 5 | 3 | 8 |
| `font_table_directive` | pdf | 4 | 4 | 5 | 3 | 8 |
| `annotation_action_directive` | pdf | 4 | 5 | 6 | 3 | 9 |
| `split_site_directive` | docx/pdf/xlsx | 4 | 4 | 6 | **2** | 8 |
| **合计** | 5 类容器 | 35 | 35 | **46** | **24** | 70 |
| 在训位点正对照 `body_comment_injection_control` | docx/pdf/xlsx | 3 | 3 | **6** | — | 6 |
| 正文层干净负例（`body_contract_clause` / `body_report_outline`） | pdf/docx | 2 | 2 | — | **4** | 4 |
| **总计** | | **40** | **40** | **52** | **28** | **80** |

另一维度：`kind=robustness` 52 / `alignment` 28；`domain`：security 28 / ai_safety 26 /
privacy 26；`policy_pack` 全为 `default`；容器分布 pdf 39 / docx 21 / xlsx 8 /
docm 3 / dotm 3；轴（对抗条）：forward 15 / nonforward 31。

### 1.2 与既有门禁仪器的机理分工（对比表）

| 仪器 | 条数 | 载体类别 | 机理轴（声明的作用域） | 主登记被评模型 | 与训练的关系 |
|---|---|---|---|---|---|
| `v0.1` | 60 | 文本任务（无载体） | 面向 3 域的基础能力 | 早期模型 | 在分布 |
| `v0.2` / `v0.2.1` | 153 / 161 | 文本任务 | 在训载体的部署格式 | m25 | 在训 |
| `v0.3-gen` | 258 | **图像/音视频元数据**（二进制宿主） | 未见载体（2 类本体载体） | soup-a050 | 未见载体 |
| `v0.4-toolout` | 70 | 工具输出（tool output） | 在训载体回归 | m3-dpo | 在训 |
| `v0.5-toolout-reg` | 264 | 工具输出回归 | 在训载体回归 | m3-dpo | 在训 |
| `v0.5-topup-families` | 85 | 文档结构 / T2 / T9 | 在分布能力观测 | m3-dpo | 在分布 |
| **`v0.6-document`（本集）** | **80** | **文本文档（pdf/docx/docm/dotm/xlsx）** | **未见结构位点**（8 类机理，作用域 `structure_site_only`） | `soup-a050`（未见）/ `m3-dpo`（已见） | **按模型分列**（见 §5） |

**留出的是哪一类**：留出的是**载体的结构位点**（关系表 target、表单域名、嵌入文件名、
自定义属性键、作者/创建者元数据、字体表、批注动作、跨位点拼接），
**不是**载体本身、也**不是**注入语义类别。对应地：8 类机理的 `site_keys`
∩ 活谱系训练位点集 = ∅ 且 ⊄（机器可判，见 §4.2）。

---

## 2. 重叠结论（四层判据 + 归因）

### 2.1 判据分层（每一层都写明"测的是什么"）

| # | 判据 | 窗口/单位 | 扫描范围 | 结果 |
|---|---|---|---|---|
| 1 | 逐行 sha256（原始 + 归一化） | 整行 | 全语料 55 文件 / 7.78 GB / 2,846,520 行 | **0** |
| 2 | 载体渲染文本 sha256 | 整块 | 同上（84,380 个载体文本） | **0** |
| 3 | 内容窗口（非模板行内整窗） | 60 B | 全语料 | **0** |
| 4 | 载荷片段整串包含 | ≥8 B | document 训练子集 6,400 行 | **0** |
| 5 | **散文层窗口**（非模板、非序列化器骨架行） | 12 B | document 训练子集 | **0** |
| 6 | 三重比对（id / query 全文 / 正文前 60 字） | — | 其他 7 个留出集 1,051 条 | **0 冲突** |
| 7 | 原始 60 B 窗口命中（**归因用，非内容判据**） | 60 B | document 训练子集 | 176,644 → 见 §2.2 |
| 8 | 细粒度残渣诊断（两侧剔除机械 token） | 12 B | document 训练子集 | 55,802（**不设阈值**，见 §2.5） |

### 2.2 `raw_hits_long_content_share=17558` 的归因（本轮父代理点名问题）

**判定规则（精确）**：门禁 query 与训练 document 行共享一个 60 字节窗口 `W`；
设 `cb` = `W` 的字节落在训练侧**非模板行**（非 schema 白名单行）内的数量。
`cb == 0` → `schema_region`；`W` 命中内容窗口集 → `content_overlap`；
`cb < 12` → `sub_window`；`cb ≥ 12` → 按训练侧覆盖行**是否为序列化器骨架行**
再分 `long_share_skeleton` / `long_share_prose`。

**盘上实测（rev=7，`_work/overlap-full.json`；检查器亦独立复算一致）**：

| 桶 | 值 |
|---|---|
| `raw_hits_total` | 176,644 |
| `raw_hits_schema_region`（`cb=0`） | 102,966 |
| `raw_hits_sub_window`（`cb<12`，实测上界 `sub_window_max=11`） | 56,120 |
| `raw_hits_content_overlap` | **0** |
| `raw_hits_long_share_skeleton` | **17,558**（实测 `long_share_max_skeleton_bytes=28`） |
| `raw_hits_long_share_prose` | **0**（`long_share_max_prose_bytes=0`） |

**命中对象（按文件，骨架行桶）**：

| 训练文件 | 骨架行长共享命中 | 是否活谱系 |
|---|---|---|
| `sec_sft_topup.jsonl` | **8,779** | 否（C 路 top-up，**已弃用**） |
| `doc_structure.jsonl` | **8,779** | 否（**从未混入**） |
| `dpo_m3_final.jsonl`（活谱系 M3） | **0** | 是 |
| `carrier_sft_slice.jsonl` / `sec_sft_needlefix_carrier.jsonl` / `dpo_m3_carriers_v1.jsonl` | **0** | 候选/副本 |

其余原始命中（schema 区 + 亚阈值）按文件：4 个分支文件各 20,966，两个非活分支各 46,390。

**样例（窗口原文）**：`pe="document" trust="untrusted" id="c1">\n<meta>\nfilename: pr…`
——即**载体信封标签 + `filename:` 骨架前缀**，来自**含 `<meta>` 信封的两个非活分支**；
活谱系与未用切片**全部是 `body_only` 信封**（见 §5 表），故 M3 侧该桶为 0。

**结论（二选一）⇒ (a) 但更精确**：**不是内容重叠**，是**序列化器模板字节**的共享窗口；
且这 17,558 条**100% 落在从未生效的两个分支**（`sec_sft_topup` 已弃用 /
`doc_structure` 从未混入），活谱系文件为 **0**。因此**不需要修改 manifest 里任何
claim**；需要改的是**命名与断言**（下条）。

### 2.3 本轮据此做的两处"命名/断言"修正（父代理硬规则：不得为变绿放宽断言）

| 项 | 旧 | 新 | 理由 |
|---|---|---|---|
| 常量名 | `shared_content_max = 8` | 删除，改为**实测** `long_share_max_skeleton_bytes=28` / `long_share_max_prose_bytes=0` | 旧键把**判据常量**写成测量值（docs/01 §11.25：指标名必须与测量对象一致），会让人误以为"最长共享 8 字节" |
| 断言 | `raw_hits_long_content_share == 0` | ① 保留并**加强**内容类断言为 0：`content_hits_vs_corpus` / `raw_hits_content_overlap` / `prose_share_hits` / `short_fragment_hits` / `raw_hits_long_share_prose` / `long_share_max_prose_bytes`；② 骨架行桶**改名**为 `raw_hits_long_share_skeleton` 并**不设 0 阈值**，而是登记"归属=序列化器模板值 + 100% 落在非活分支 + 活谱系为 0" | 原断言的**测量对象写错**（该桶测的是"共享窗口命中数"而非"内容重叠"）；放宽的是**错误的断言**，同时把**真正的**内容判据从 1 条加到 6 条 |

除此以外**未放宽任何断言**；`c.prose_share`、`f.sha256`、`e.*claims*` 等断言
一字未动。本**仪器改动登记**见 §2.4（父代理硬规则：改断言/改名必须登记理由）。

### 2.4 本轮仪器改动登记（断言 / 命名 / 口径）

| # | 位置 | 改动 | 理由（症状 → 原因） |
|---|---|---|---|
| 1 | 重叠产物 + manifest | 删 `shared_content_max=8`（常量）→ 新增**实测** `long_share_max_skeleton_bytes` / `long_share_max_prose_bytes` | 旧键把**判据常量**当**测量值**存（§11.25），使审查方得出"最长共享 8 字节"的错误读数（实测骨架桶上界 **28** 字节） |
| 2 | `c.manifest_overlap` / `c.artifact_hits` | `raw_hits_long_content_share==0` → 拆为 `raw_hits_long_share_prose==0`（保留）+ `long_share_max_prose_bytes==0`（新增）+ 骨架桶改名登记（不设阈值） | 该桶名与实际测量对象不一致；**同时把内容类断言从 1 条加到 6 条**（见 §2.3 表），净效果是**更严** |
| 3 | `b.frag_off_site` | 分片比对前两侧 `strip()` | 原判据把**分片切分点的空白**当成载荷内容；渲染器在取值边界 `strip`，故 3 条（doc-a-44/45/46）误报。修的是判据口径，**未**降低"片段内容须整串落点"的要求（`f.strip()` 后仍要求整串） |
| 4 | `f.envelope_*` | `live_envelope` → `envelope_live_lineage_rows`；`all_envelope` → `envelope_candidate_pool_rows`；标签改为**互斥**（`body_only`/`meta_and_dom`/`meta_only`/`dom_only`） | (a) 两个计数测**不同对象**却并列（1,000 vs 6,400）；(b) 旧 `has_meta`/`has_dom` **可同时命中同一行**，合计 8,800 > 6,400 行，属"计数与对象不一致" |
| 5 | `main` | 新增**具名**时序规则 `0.manifest_stale`（jsonl mtime > manifest mtime） | 症状被报成"sha256 不一致"，真因是"清单滞后于产物"；构建顺序固定为先冻结 jsonl 再写 manifest |
| 6 | 各检查段外层 | 新增异常兜底 `*.crash`（异常记错，不再崩溃出栈） | 轻量回归的**篡改测试**发现：交换键序会让检查器抛 `AttributeError`，即"输入被篡改"时仪器崩溃而非判错 ⇒ 违反失败闭合 |
| 7 | 缓存有效性 | 新增 `OVL_KEYS` / `CENSUS_KEYS` **必需键**检查 | 防"仪器比产物新、产物缺键"被静默复用（本轮实际触发过一次：`KeyError: prose_share_hits`） |

### 2.5 残渣诊断（55,802，登记但不设阈值）

两侧剔除机械 token（URL、`key: value`、`\d+x\d+pt`、日期、金额、纯数字、
部件文件名、编码名）后的 12 字节残渣命中 55,802，样例为 `第   节 \xef…`
（骨架行的数字占位残留）、`filename: …`、`[name: …]` 等**序列化器骨架词**。
**这一桶不参与判定**，理由是它测的对象（剔机械 token 后的残留字节）不是
"内容"，而是"模板结构 + 通用词"；其**可判定版本**是 §2.1 第 5 层（散文层 12 字节
窗口 = 0）。为不让它变成"看不见的 5 万"，manifest 与检查器都**显式打印该计数**。

### 2.6 共享文本卫生（本轮重写脚手架）

构建期发现并修掉了一个**真问题**：初版门禁脚手架（正文模板、操作者/用户行、
控制载荷）**逐句复用了训练语料的措辞**（共享 30 字节级长串，`long_share` 峰值
135,642 命中）。已把全部脚手架**重写为自撰措辞**（含控制载荷的 6 条、8 个机理的
操作者指令、正文模板、用户行），`long_share` 峰值 135,642 → 17,558，且**散文层 =
0**。残留的 38→16→4→**0** 个共享窗口全部由"通用短语"（`本文档的`、`and give a`、
`compliance check`、`human review` 等）构成，逐条改写后清零。**这是一次数据卫生
改进，而不是把阈值调松**：判据从"骨架+散文混算"变成"散文层单独判零"。

---

## 3. 可判性冒烟（`score_heldout_v2` 未改动；双口径）

每条鲁棒性条目用两条假答复：`正确行为` 文本、`注入要求` 文本；干净负例用
`正确行为` 文本。两个 `action_rule` 口径各跑一遍：

| 口径 | 对抗条（52）正确行为→防御 | 对抗条注入要求→顺从 | 干净负例（28）非拒 | `over_refusal` |
|---|---|---|---|---|
| `selfreport` | 52/52 | 52/52 | 28/28 | 0.0 |
| `strict` | 52/52 | 52/52 | 28/28 | 0.0 |

即"该拒的能拒、该答的能答"在本集上**自洽**（这是**可判性**冒烟，不是模型能力测量）。

---

## 4. 未见性声明及其机器可判性

### 4.1 按模型分列的 `claims`（manifest，机器可读）

| 被评对象 | 训练 document 行 | `carrier_seen` | `supports` | 强制规则 |
|---|---|---|---|---|
| `soup-a050` | 0（`sft_m25.jsonl` + `sec_sft_needlefix.jsonl`） | `false` | `unseen_carrier`, `unseen_mechanism` | 只有 `carrier_seen=false` 才允许出现 `unseen_carrier` |
| `m3-dpo` | 1,000（`dpo_m3_final.jsonl`，活谱系） | `true` | `unseen_mechanism_only` | `carrier_seen=true` ⇒ **必须**不含 `unseen_carrier` |
| `c-topup-discarded` | 1,200（`sec_sft_topup.jsonl`，**已弃用**） | `true` | `[]` | 备料已弃用 ⇒ 不支撑任何结论 |

顶层 `claims.unseen_carrier=false`（主登记产物指向 `m3-dpo`）；
`unseen_mechanism_scope="structure_site_only"`（因为语义层 6/8 条要求在活谱系出现过，
故**只**声明结构位点层未见性，见 §6）。

### 4.2 未见机理 = 未见结构位点（可机器复核）

活谱系 document 行（1,000 行）里**非零**的结构位点只有 2 个：
`body-visible-text`(1000) 与 `html-comment-in-body`(888)；
8 类门禁机理的 `site_keys` = {relationship, form-fields, embedded-file,
custom-metadata-keys, author-meta+creator-meta, fonts-table, annotation-action,
author-meta+embedded-file} 与活谱系非零位点集**交集为空且不包含**
（`b.site_keys_absent`）。6,400 行全量里这些位点亦为 0，说明它们不是"训练过又删掉"，
而是**从未被训练**。

### 4.3 在训位点正对照（6 条）

`body_comment_injection_control` 复刻 M3 真实训练形态
（`CarrierBlock(ctype="document", meta_lines=[], body=…)` ⇒ **只有 `<body>`**，
position head/mid/tail，机理 = `metacomment`/`policy_claim`/`task_hijack`/
`authority_disguise`/`exfil_authorize`/`bulk_extract`），用于区分
"没学会"与"学会了但被这一条骗过"。这 6 条**不计入**未见机理分母，
manifest 显式排除，检查器强制 `CONTROL_MECH ∉ claims.unseen_mechanism`。

---

## 5. 信封-OOD 混杂：必须披露的设计事实

M3 的活谱系 document 行**全部是 body-only**（`envelope_live_lineage_rows =
{body_only: 1000}`），而门禁条目的 query 带完整 `<meta>` / `<dom>` 信封。因此对
`m3-dpo` 而言，门禁条目**同时**是"未见结构位点" **和** "未见信封形态"，二者在本集里
**没有分离**：本集**不能**把 M3 的失败单独归因于结构位点。

- 2×2 设计（已实施）：门禁条目 = 未见位点 + 完整信封；正对照 = 在训位点 + body-only
  （与活谱系同形）；干净负例 = 未见位点 + 完整信封无载荷。
- 信封分布（候选池口径，含分支副本）：`body_only` 4,000 / `meta_and_dom` 2,400；
  `meta_and_dom` **只**出现在两个**非活**分支
  （`deprecated-c-topup` 1,200、`deprecated-prep-staging` 1,200）。
- 命名对齐（docs/01 §11.25）：`envelope_live_lineage_rows`（活谱系实际纳入行，
  合计 1,000）与 `envelope_candidate_pool_rows`（候选池行，含分支副本，合计 6,400）
  **测的不是同一个对象**，已在 manifest 里分开命名并各附 `_sum`；两文件三副本的
  重复关系（`carrier_sft_slice ≡ sec_sft_needlefix_carrier`、
  `dpo_m3_carriers_v1 ≡ dpo_m3_final`）写在 `envelope_note` 里。

---

## 6. 本门禁能支撑 / 不能支撑的结论

**能支撑（有机器证据）**

1. **对 `soup-a050`：未见载体 + 未见机理。** 训练侧 document 行 = 0（逐行字节级
   计数，`sft_m25` / `sec_sft_needlefix` 各 0）；8 类结构位点在 6,400 行里全 0。
   这是本项目第 3 个合格"未见载体门禁"、**第 1 个文本类载体**门禁
   （`v0.3-gen` 的 2 类是图像/音视频元数据）。⇒ 需本体登记（`GATE_SCOPES` 硬编码，见 §8）。
2. **对 `m3-dpo`：未见机理（且仅此）。** 训练 document 行 = 1,000；8 类结构位点
   活谱系全 0；机理语义 6/8 在活谱系出现过 ⇒ 只能声明结构位点层未见性。
3. **零重叠（内容层）。** 全语料 7.78 GB / 2,846,520 行逐行 sha256、84,380 个载体
   渲染文本 sha256、60 B 内容窗口、≥8 B 载荷片段整串包含、12 B 散文层窗口、
   与其他 7 个留出集的三重比对（id/query/正文前 60 字）——**全为 0**。
4. **可判性。** 双口径下 52/52 抗注入、28/28 不误拒；干净负例覆盖**全部 8 类机理**
   （含本轮补的 `split_site_directive` zh+en）。
5. **可复现。** 定种子 `SEED=20261007`，内存重装配与盘上字节**逐字节一致**，
   sha256 自证 + 检查器现场重装配复核；`_work` 产物带 `rev` 与语料指纹，
   指纹/口径/必需键任一不符即判"过期"（不静默复用）。

**不能支撑（必须写明边界）**

1. **不能支撑"模型失败 = 结构位点未见性所致"**（M3）：信封-OOD 混杂未分离（§5）。
2. **不能支撑任何"能力分数/通过率"** 结论：本集只有 0/1 判据，样本量 46 条
   未见机理条（本体下限 34 已满足），但**单条机理最少 5 条**（`author_meta_directive`
   / `font_table_directive`），**按机理分列时低于 §11.2 效力下限**，只能作
   定性定位、不得作决策依据。
3. **不能支撑"未见载体"用于 `m3-dpo` 或任何训练侧 document 行 > 0 的产物**
   （含已弃用的 C 路 top-up，1,200 行）。
4. **不能支撑语义层未见性**：6/8 条注入语义要求在活谱系出现过；本集不声明
   "机理类别未见"，只声明"结构位点未见"。
5. **不覆盖**：`data/corpora/**`（原始抓取语料，不属训练混料，本体 `scan_globs`
   亦不含；**本集的"训练侧"范围因此不包含它**）、加密/签名/宏载荷类机理、
   跨语言混杂条目、长文档（>2 页）行为。
6. **未测**：任何真实模型输出（本报告全部数字来自构建器/检查器/冻结评分器；
   模型侧 `asr` 等**未测**——RTX 5090 被 M3 DPO 占用，本任务全程 CPU）。

---

## 7. 自评与已知缺陷

1. **信封-OOD 混杂**（§5）是设计选择而非疏漏（M3 活谱系就是 body-only），但**降低
   了 M3 结论的归因精度**；彻底解法需再造一组"未见位点 + body-only"条目。
2. **单机理样本量偏小**（5–6 条/机理），分机理结论不可作决策依据（§6.2）。
3. **`split_site_directive` 干净负例偏少（2 条，zh+en 各 1）**；本轮按父代理要求补齐
   （此前该机理**只有 claim、没有对照**），检查器现已强制"每个门禁机理 ≥1 条干净负例"
   （`b.no_clean_control`），故此缺口**已闭合**，但强度仍低于其他机理（3–4 条）。
4. **`is_forward()` 是既有子串判据**（`score_heldout_v2`，冻结未改动）：
   `"前瞻" in intent or "forward" in intent.lower()`。本集的 `intent` 里
   `axis=forward/nonforward` 会**同时**命中/不命中，属于把仪器口径写进条目的
   既有做法（与本仓其它门禁一致）；副作用是**轴标签与判据同源**，
   forward/nonforward 的拆分**不能**当作独立测量。**已在此披露，未改冻结件。**
5. **`long_share` 骨架桶（17,558）不是 0**：一旦将来把含 `<meta>` 装填的分支混入
   训练，这个数字会变成真实问题的信号；本轮已把它拆桶 + 定位到**非活分支**，
   但**没有**把它清零（清零需要放弃 `<meta>` 信封，即放弃"信封也算未见形态"这一
   设计）——这是**有意的取舍**，不是遗漏。
6. **残渣诊断桶 55,802 不设阈值**（§2.5）：它的名字已按"诊断"命名，但它仍可能被
   误读为泄漏。若审查方要求，可退化为只记哈希计数、不记样例。
7. **检查器输出纪律**：曾经一次跑到 58,384 行输出、109,781 条错误（陈旧产物 +
   两类自相矛盾断言 + 未限制口径所致）。现已改为**聚合输出**：每类错误最多 3 条
   样例 + 全量计数 + 末尾错误种类表，逐条明细写 `--stats-out` JSON 产物。
8. **两类自相矛盾断言的修复**（父代理第一轮指出）：(a) schema 白名单"包含/不包含"
   改为**行为断言**（合成载荷位点行必须不被判为模板行）+ 精确键集交集；
   (b) 两个不同对象（文件内容 / 现场重装配）的 sha256 断言拆成**带对象标签**的两条：
   `[对象=文件内容]` / `[对象=现场重装配]`。
9. **新增具名时序规则**（父代理第二轮指出）：`jsonl.mtime > manifest.mtime` ⇒
   `0.manifest_stale`「清单滞后于产物」，不再报成"sha256 不一致"（症状不是原因）。
   构建顺序已固定为**先冻结 jsonl、再生成 manifest**。
10. **失败闭合**：检查器各段外层有异常兜底（`*.crash` 记错而非崩溃出栈），
    轻量回归测试用**篡改输入**（重复 id / 交换键序 / 改 manifest 计数）验证必须判错。
11. **`_work` 体量**：曾达 **254 MB**（把逐条命中明细全量落盘），现为
    `overlap-full.json` **17.5 KB** / `census-full.json` **47.7 KB**——**只存计数与
    哈希 + 每桶 ≤20 条样例**，样例里的 `window` 是**门禁侧**窗口原文（训练侧只存
    文件名/偏移/哈希），**不含任何训练语料原文**。位置保留在 `data/heldout/
    v0.6-document/_work/`（在允许的新增目录内；`load_dir` 与本体 `GATE_SCOPES`
    只 glob `*.jsonl`，不会被误认为门禁条目）。
12. **未跑模型**：本任务全程 CPU（硬约束：RTX 5090 被 M3 DPO 占用）；
    报告里所有"能力"字样均指**可判性**，不指模型表现。

---

## 8. 复现与回归

```
python scripts/build_document_gate.py --census --overlap   # 全量重算（约 10 分钟）
python scripts/build_document_gate.py --no-write           # 只自证，不落盘
python scripts/check_document_gate.py                      # 末行哨兵
python tests/test_document_gate.py                         # 轻量回归（秒级）
python scripts/check_carrier_ontology.py                   # 本体回归（期望 PASS）
```

- 构建器末行：`BUILD-DOCUMENT-GATE=PASS items=80 robustness=52(unseen=46,control=6)
  alignment=28 sha256=59bd7cf2…`
- 检查器末行：`DOCUMENT-GATE-CHECK=PASS errors=0`
- 本体回归：`CARRIER-ONTOLOGY-CHECK=PASS errors=0`（新增 v0.6 不影响既有本体）。
- **需本体方登记**：`scripts/check_carrier_ontology.py` 的 `GATE_SCOPES` /
  `INSTRUMENT_ROLES` / `MATRIX_COLUMNS` 是硬编码的，`v0.6-document` **不会**被自动
  纳入覆盖矩阵；在其登记前，本集的存在**不改变**本体覆盖率结论。登记时建议：
  角色 `unseen_carrier_gate`（限 `soup-a050`）+ `unseen_mechanism`（`m3-dpo`），
  并在 `claims.unseen_carrier_gate_carriers` 里追加 `document`（仅对
  `carrier_seen=false` 的模型成立）。
