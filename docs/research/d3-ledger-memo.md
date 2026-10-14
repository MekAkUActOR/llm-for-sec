# D3 台账整合备忘：开放权重决策弹药（M5 评审输入）

> 整合日 2026-09-25（机器时钟真值口径）· 整合人：C2/语料 agent
> 原料：`data/corpora/manifest.jsonl`（47 源逐字许可）、docs/04 §4（P1/C2 实况）、
> docs/research/p1-sources.md（P1 条款逐字+存证）、docs/research/m2-sft-sources.md（M2 D3 簇）
> 用途：D3 决议"开放权重 vs 受控发布"（docs/00 §决策表 / docs/01 §M5）的一次性总览。
> 本备忘只整合不裁决——分级为**建议**，决策权在父会话/用户/法务。

---

## 0. 一图流：三个训练层，三种剥离成本

| 层 | 状态 | 有效 tokens | D3 风险载荷 | 剥离成本 |
|---|---|---|---|---|
| **C1 预训练**（~1.088B 有效） | 🔄 35h 在跑 | 安全域 217.2M×2 + enwiki 529M + zhwiki 124.3M | **T2 四源 28.2M（有效 5.2%）+ T3 wiki SA 簇 653M（60.0%）** | 天级：rebuild mix + C1-full 35h 全重训（M1.5 需随之重跑 1.5h） |
| **M1.5 知识针**（C2 七源 + 隐私五源 7.17M ×3 epoch + enwiki 补集回放 27M ≈ 48.5M） | 待发射 | C1 基座之上 | **T3 簇 0.57M（C2 的 7.9%）：gtfo/lolbas GPL-3.0 + aiid 未公示 + owasp×2 CC-BY-SA** | 小时级：短针重跑 ~1.5h，C1 基座不动 |
| **M2 SFT**（原料层 ~50M，实际采 100–500K 例） | 设计态 | — | **T2：PKU-SafeRLHF/BeaverTails（NC）+ lmsys（research-only）；T3：AI2 三件（OUFRA/ODC-By 门控）** | 小时级：SFT mix 删行 + rerun |

**关键结构性事实**：ShareAlike 疑问（wiki 簇）占 C1 的 60%——法务若判 SA 与开放权重不兼容，C1 需换回放源结构性重训（>35h）；若判可训（学界惯例 + LLaMA/Mistral 等 wiki 预训练先例），T3 收缩为零星小簇。**这一项的裁决权重远超其余全部条目之和**。

---

## 1. 全量清单（D3 风险项逐条）

### 1.1 P1 四源（C1 预训练，用户拍板 2026-09-25 全纳入；项目决策 2026-09-24）

| 源 | tokens | 许可逐字/核验状态 | 进权重 |
|---|---|---|---|
| msrc-cvrf | 10,083,959 | API swagger 无 termsOfService 字段；Microsoft Learn TOU 逐字："Unless otherwise specified, the Services are for your personal and non-commercial use. You may not modify, copy, distribute, transmit, publicly display…"（manifest notes 逐字登记） | C1 安全域 |
| sans-isc | 8,054,600 | 站点 footer 逐字："the data is provided using a Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) License."（p1-sources.md §SANS） | C1 安全域 |
| cisco-psirt | 7,767,958 | 通告内容 © Cisco；Cisco Baseline API Terms——**本网络 403 取不到原文，风险不可量化，如实记录**（p1-sources.md §Cisco + manifest） | C1 安全域 |
| oracle-cpu | 2,314,816 | Oracle Web Sites ToU 逐字："The Site and Content provided on or through the Site are the intellectual property and copyrighted works of Oracle or a third party provider. All rights, title and interest not expressly granted … are reserved."（p1-sources.md §Oracle + 存证 `_oracle_terms_sample.html`） | C1 安全域 |

合计 28.2M = 安全域 13.0% / C1 有效 mix 5.2%（×2 epoch）。

### 1.2 C2 知识层（M1.5，2026-09-25 入库；父会话裁决保留 + "开放权重前需重估"注记）

| 源 | tokens | 许可（查证原文） | 核验状态 |
|---|---|---|---|
| gtfobins | 49,215 | **GPL-3.0**（LICENSE 全文） | 与任务口径 MIT 不符，已纠错上报；父裁决保留（D3 记账） |
| lolbas | 83,513 | **GPL-3.0**（NOTICE.md 逐字 "The LOLBAS Project is licensed under GPL 3.0."） | 同上 |
| aiid | 357,472 | **数据许可未公示**（terms-of-use/footer/工作簿均无条款；口径 CC-BY-4.0 未能在线核实；repo 代码 Apache-2.0） | Reports 表已按版权排除，Incidents 策展内容入库 |
| owasp-rtg | 29,323 | CC BY-SA 4.0（项目口径；PDF 内无逐字许可页，如实记录） | SA 义务 → 同 wiki 簇性质 |
| owasp-top10 | 50,127 | CC BY-SA 4.0（仓库徽标逐字） | 同上 |
| atlas | 75,103 | **Apache-2.0**（仓库 LICENSE，Copyright 2021-2026 MITRE） | 与口径 CC-BY-4.0 不符已上报；Apache-2.0 本身发布友好（NOTICE 义务） |
| （对照）arxiv-aisafety | 5,400,532 | CC0 1.0（API ToU descriptive metadata） | 干净 |
| （对照）nist | 111,075 | Public domain（17 U.S.C. §105） | 干净 |

### 1.3 C1 里的 SA/copyleft 大簇（非 D3 新旗标，但开放权重评审必须过）

| 源 | tokens | 许可 | 占 C1 |
|---|---|---|---|
| enwiki-gen（74% 采样入训） | 714.9M 总量 / **529M 入训** | CC-BY-SA 4.0 | 48.6% |
| zhwiki-gen | 124.3M | CC-BY-SA 4.0 | 11.4% |
| zhwiki-sec（安全域内 ×2） | 5.5M | CC-BY-SA 4.0 | ~1.0% |
| owasp-cs（C0，安全域内） | 544,254 | CC-BY-SA | 0.1% |
| debian-dsa | 14.7M | MIT-Expat OR GPL-2+（Debian WWW Pages License 逐字在 manifest） | 邮件列表文本，GPL-2+ 双许可 MIT 档 |

### 1.4 M2 SFT D3 簇（设计态，未入库；用户拍板 2026-09-25 纳入第二批采购清单）

| 源 | 规模 | 许可 | 通路状态 |
|---|---|---|---|
| PKU-SafeRLHF | 330K 偏好对（30K/10K 精选） | **CC-BY-NC-4.0**（NC 与商用冲突） | hf-mirror 200 |
| BeaverTails | 330K QA + 361K 危害标注 | **CC-BY-NC-4.0** | hf-mirror 200 |
| WildGuardTrain | 92K 审核对 | **AI2 OUFRA**（使用限制+署名+非恶意用途）+ HF 门控 | mirror 401（需账号+token） |
| WildJailbreak | 426K 对抗对话 | **ODC-By** + 门控（自动接受） | mirror 401 |
| WildTeaming | 1M 真实多轮对抗 | **AI2 OUFRA** + 门控 | mirror 401 |
| lmsys-chat-1m | 大体量真实对话 | research-only + 含 OpenAI 输出条款 | 第三批暂缓 |
| 平台政策页（×4） | anthropic AUP 606KB 锚 | ❌ 全 D3（© 平台） | 1/4 可达（anthropic 200；openai/google/meta TCP 阻断） |
| MaliciousInstruct | ~100 prompts | CC-BY-SA-4.0（walledai 数据卡） | 已克隆 |

### 1.5 零成本决策记录（不入权重的 D3 相关项）

- **GB/T 35273（个人信息安全规范）**：按许可红线**跳过全文**——国标受版权保护、openstd 在线预览图片渲染 + 页脚"版权所有 侵权必究"、无授权复用条款（docs/04 C2 隐私小节）。覆盖路径：采购正版或人工结构摘要。
- **tc260**：**EVAL-REFERENCE ONLY, NEVER INTO TRAINING**（父会话决策，manifest 注记）——官方测试集入训即污染行业基准；仅作 19 列攻击元数据分类参照。
- **CTFtime**：API 条款排除（"You can not use this API to run CTFtime clones"，p1-sources.md §CTFtime）——P1 调研期即弃。
- **CNNVD/CNVD**：无开放批量授权，调研期即弃（docs/04 §5.1）。

---

## 2. 剥离成本表

| 簇 | 层 | 剥离动作 | 重训成本 | 备注 |
|---|---|---|---|---|
| P1 四源 28.2M | C1 | build_c1_mix 显式清单删 4 行 + rebuild | **C1-full 35h 全重训 + M1.5 1.5h 重跑**（天级） | 门禁基线（sec PPL -25%）需重验；mix 组装脚本为显式来源清单，删行即生效 |
| wiki SA 簇 653M | C1 | 删行=删 60% 语料 → **不可行**；须换回放源（如 C4/CommonCrawl 类） | **结构性重训 >35h**（新 mix 设计 + 新基线） | 这不是"剥离"而是"C1 重来"——法务确认 SA 可训是唯一低成本路径 |
| C2 T3 簇 0.57M | M1.5 | manifest 删行（build_m15_mix 运行时动态枚举 c2_*，删行即生效） | **短针重跑 ~1.5h**（小时级；C1 基座不动） | 剥离重训成本极低——父会话"删行重训成本极低（132k/1.09B）"判断成立且适用于整个 C2 T3 簇（0.57M/7.17M） |
| PKU/BeaverTails/lmsys | M2 SFT | SFT 采购清单删行 | **SFT 重跑小时级**（SFT 本身 1-2 epoch 轻训） | 尚未入库，当前成本为零——**采购前裁决可永久免付** |
| AI2 三件 | M2 SFT | 同上 | 同上 | 门控数据集：若不采则零成本；若已采后剥离同小时级 |
| 平台政策页 | M2 参照 | 参照文本替换为我方政策文档（docs/01 政策组） | **零重训**（非训练主体，判断任务参照） | anthropic AUP 文本是否入权重由 D3 单独裁决 |

**时序要点**：C1-full 正在跑（35h）——若 P1 四源剥离裁决能在其完成前落地，可避免一次 35h 重跑；**M5 前任何时候裁决 M2/SFT 层都是小时级**，无时序压力。

---

## 3. 分级建议（M5 开放权重评审用）

### T1 可直接发布（署名/NOTICE 义务即可，无重训需求）
CC0（arxiv-cscr-full 13.2M / arxiv-aisafety 5.4M / arxiv-privacy 0.7M）· Public domain（nist 111k + nist-privacy 183k + kev 157k）· CC-BY-4.0（**redhat 83.1M——最大单源** / gdpr-full 66k / or-bench / xstest）· MIT（ghsl 1.0M / advbench / harmbench / strongreject / safemtdata / trustllm / hh-rlhf）· Apache-2.0（p0 182k / atlas 75k / safety-prompts / cvalues）· MITRE 条款-署名（cwe 206k / capec 57k / mitre-attack 324k）· CVE Program 公开条款（cve 70.1M）· 法定文本无版权（cn-laws 15k / cn-laws-full 24k / cn-regs 20k / gdpr 36k）· Debian MIT|GPL-2+（14.7M，邮件列表文本双许可 MIT 档）· **T6 采购两源（2026-09-30 补录分级）：t6_devign 18.4M（MIT，epicosy/devign 镜像 LICENSE 逐字）/ t6_cvefixes 20.7M（CC-BY-4.0 canonical Zenodo——hf 镜像标 apache-2.0 不可信，见 §6）**。

### T2 需剥离重训（禁止性条款明确：NC / all-rights-reserved / 未授权）
**msrc-cvrf 10.1M + sans-isc 8.1M（NC）+ cisco-psirt 7.8M（条款不可核验）+ oracle-cpu 2.3M（ARR）**——C1 已入，剥离=35h 重训；**PKU-SafeRLHF + BeaverTails（CC-BY-NC-4.0）**——M2 未入，采前裁决免付；**lmsys-chat-1m（research-only）**——第三批暂缓中；**平台政策页（© 平台）**——参照用途，零重训成本替换。
*建议*：四源已按用户拍板入 C1，开放权重时执行"剔除污染源重训"路线（docs/04 §4 已预案）。

### T3 需法务确认（copyleft / ShareAlike / 未公示 / 门控——学界惯例可训，开放权重有争议）
**wiki 簇 enwiki 529M + zhwiki 124.3M + zhwiki-sec 5.5M（CC-BY-SA 4.0，C1 的 60%——本案最大单点）** · **owasp 簇 owasp-cs 544k + owasp-rtg 29k + owasp-top10 50k + MaliciousInstruct（CC-BY-SA）** · **gtfobins 49k + lolbas 84k（GPL-3.0）** · **aiid 357k（数据未公示）** · **AI2 三件（OUFRA/ODC-By + 门控）** · **credential-formats 3.5k（RFC 7519 IETF Trust "All rights reserved" + BCP 78 + AWS Documentation Terms——事实性引用，逐字已记）** · **t6_devign_lines 6.2M（上游 Devign MIT，但 DetectVul 行级衍生卡未标 license——§5 缺口条，开放权重评审前重估）**。
*建议*：① wiki/OWASP 的 SA 问题一次法务问答覆盖（同一许可家族）；② GPL-3.0 双源与 aiid 合计 0.49M——**直接按 T2 剥离**（M1.5 层 1.5h 重跑）比法务确认更便宜，可作为"法务未决时的保守发布路径"；③ credential-formats 3.5k 同理可零成本剥离。

### 决策树建议
1. 先问法务一个问题：**CC-BY-SA 语料训练的模型权重开放，是否需要 SA 合规？**（先例：学界普遍视可训）
   - 可训 → T3 仅剩 AI2 门控簇 + 小簇，全在小时级剥离范围内 → 开放权重可行
   - 不可训 → C1 结构性重训（>35h + 新回放源设计）→ 受控发布或推迟开放
2. T2 四源无论 1 的结论如何都建议剥离（35h 一次性成本，杜绝 NC/ARR 争议面）
3. M2 采购顺序：第一批（许可干净 7 源）先行；第二批 D3 簇等 1 的结论再采——**采购即负债，裁决后再买**

---

## 4. 出处引用

| 决策/记录 | 位置 |
|---|---|
| D3 决议定义（开放权重 vs 受控发布） | docs/00 §决策表 / docs/01 §里程碑 M5 |
| P1 四源用户拍板（2026-09-25 全纳入 + 开放前重评注记） | docs/04 §4 L119-120 |
| P1 逐源实况表（含各源条款核验状态） | docs/04 §4 P1 表 |
| P1 条款逐字 + Oracle 存证文件 | docs/research/p1-sources.md（§MSRC/Cisco/Oracle/SANS + `_oracle_terms_sample.html` 等 3 存证） |
| C2 AI-safety 八源（含三处许可纠错记录 + 父裁决保留） | docs/04 §4 C2 AI-safety 小节 + manifest 各行 notes |
| C2 隐私五源 + GB/T 35273 跳过决策 | docs/04 §4 C2 隐私小节 |
| C1-full mix 构成（剥离基数） | docs/05 §7 L119（方案 B：217.2M×2 + 529M + 124.3M） + scripts/build_c1_mix.py 显式清单 |
| M2 三批采购清单 + D3 簇 + 平台政策页 | docs/research/m2-sft-sources.md §采购批次 + §2.14/2.16/2.17 |
| M2 红线分类框架应用 | docs/research/m2-sft-sources.md §3 |
| CC-BY-SA 项目立场（逐源记录、M5/D3 统一答复） | docs/04 §5 风险第 2 条 |
| SANS/Oracle/MSRC/Cisco manifest 逐字注记 | manifest.jsonl 对应行 notes |
| tc260 不入训裁决 | manifest tc260 行 notes（注记载 "parent decision 2026-09-26"——**日期存疑**：机器时钟真值为 09-25，该行系他 agent 所记，建议其按日期口径裁决统一） |

---

## 5. 已知缺口

- cisco-psirt 条款原文至今不可核验（www.cisco.com 403）——若法务需要原文，经父会话通道人工取 Baseline-API-Terms.pdf
- lmsys-chat-1m / 平台政策 3/4 家：本网络阻断，文本获取依赖父会话通道（未决）
- M2 SFT 原料层 tokens 为粗估（~50M 原料 / 实采 100–500K 例），T2/T3 占比待 SFT mix 定稿后复核
- t6_devign_lines（DetectVul 行级衍生）：上游 Devign MIT，但衍生卡未标 license——**D3 开放权重评审前重估**（2026-09-28 采购，见 raw/t6/provenance.json）。**2026-09-30 处置：已按 §3 落 T3 并补录 TIER_MAP**（`scripts/gen_datacard.py`），数据卡不再报 unclassified；与 t6_devign（MIT→T1）、t6_cvefixes（CC-BY-4.0→T1）三源同批补录，`tests/test_gen_datacard.py::test_real_manifest_fully_classified` 由此转为通过。

## 6. 组装纪律增补（2026-09-28，T6 采购教训）

- **官方分类学文本（CWE/CAPEC 名称）永不内联 clean 头部**——CVEfixes 首检 2,248 条 8-gram "命中"全为 CWE 官方名称样板与 sec 探针（GHSL 通告）的公共短语碰撞，非真泄漏；clean 侧只留编号（名称可由 c0_cwe.jsonl 反查）。此类样板碰撞与 2026-09-26 SFT 源 767 条先例同性质，按哈希先例剔除后零命中。
- **许可证记账以 canonical 上游为准，镜像卡标注不可信**：CVEfixes hf-mirror 卡标 apache-2.0，canonical Zenodo（DOI 10.5281/zenodo.13118970）为 CC-BY-4.0——已按 CC-BY-4.0 记账。
- **网络侦察修正（2026-09-28 实测）**：github.com:443 直连（git clone）超时不可用；可用通道 = api.github.com + codeload.github.com（tarball）+ Zenodo（~1.3MB/s）+ hf-mirror（~1.2MB/s）。后续采购任务按此规划。
