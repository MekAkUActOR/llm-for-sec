# Model Data Card（模型训练数据总账）

> **语料态绑定**：本卡由 `manifest.jsonl` 机器生成（`scripts/gen_datacard.py`）——manifest 变更后本卡即过期，须重跑再生。结构对齐 docs/research/cc-by-sa-precedent.md §3 先例实践（RedPajama 式逐子集许可指针 + 逐字许可引用）。

- 生成时间：2026-09-30 02:55
- manifest 快照 sha256（前 16 位）：`32057fb3a13703d2`
- 源数：54 · 总 docs：2,045,096 · 总 tokens：1,109,582,227

## 下游用户提示（Dolma 式源级许可传递）

使用本模型时，您同时受训练数据原始来源的许可条款约束（各源逐字许可见下表）。本卡按 CC 官方 AI 训练指南的署名建议（attribution = 数据集链接式指引）逐源披露。

## 汇总

### 按 D3 分级（docs/research/d3-ledger-memo.md §3）

| 分级 | tokens | 占比 | 含义 |
|---|---:|---:|---|
| T2 | 28,221,333 | 2.5% | 需剥离重训（NC / all-rights-reserved / 未授权——开放权重前删除重训） |
| T3 | 851,973,732 | 76.8% | 需法务确认（copyleft / ShareAlike / 未公示——学界惯例可训，开放权重有争议） |
| T1 | 229,387,162 | 20.7% | 可直接发布（署名/NOTICE 义务即可） |

### 按许可家族

| 许可家族 | tokens | 占比 |
|---|---:|---:|
| CC BY-SA（ShareAlike） | 845,280,393 | 76.2% |
| CC-BY-4.0（署名） | 103,891,503 | 9.4% |
| CVE Program（公开条款） | 70,096,310 | 6.3% |
| MIT | 26,195,739 | 2.4% |
| CC0 1.0 | 19,307,005 | 1.7% |
| CC BY-NC（非商用） | 18,138,559 | 1.6% |
| MIT / GPL-2+ 双许可 | 14,675,514 | 1.3% |
| 其他（详见逐源行） | 7,924,646 | 0.7% |
| All rights reserved | 2,318,280 | 0.2% |
| arXiv（CC0 元数据/ToU） | 618,991 | 0.1% |
| 未公示 | 357,472 | 0.0% |
| Public domain（美国政府作品） | 294,491 | 0.0% |
| Apache-2.0 | 256,836 | 0.0% |
| GPL-3.0（copyleft） | 132,728 | 0.0% |
| 法定文本（无版权/官方公开） | 93,760 | 0.0% |

## 逐源清单

### T2 — 需剥离重训（NC / all-rights-reserved / 未授权——开放权重前删除重训）（6 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| msrc-cvrf | https://api.msrc.microsoft.com/cvrf/v3.0/Updates | MSRC CVRF API: no termsOfService declared in swagger; Microsoft Learn TOU personal/non-commercial (project decision 2026-09-24, docs/04 D3) | 192 | 10,083,959 | 0.91% |
| sans-isc | https://isc.sans.edu/diaryarchive.html | CC BY-NC-SA 4.0 (project decision 2026-09-24, docs/04 D3) | 10,212 | 8,054,600 | 0.73% |
| cisco-psirt | https://sec.cloudapps.cisco.com/security/center/cvrfListing.x | Cisco Baseline API Terms / (c) Cisco (project decision 2026-09-24, docs/04 D3) | 5,179 | 7,767,958 | 0.70% |
| oracle-cpu | https://www.oracle.com/security-alerts/ | Oracle Web Sites Terms of Use (all rights reserved; project decision 2026-09-24, docs/04 D3) | 158 | 2,314,816 | 0.21% |
| beavertails | https://huggingface.co/datasets/PKU-Alignment/BeaverTails (via hf-mirror) | CC-BY-NC-4.0 (PKU-Alignment/BeaverTails dataset card) | 364,170 | 0 | 0.00% |
| pku-saferlhf | https://huggingface.co/datasets/PKU-Alignment/PKU-SafeRLHF (via hf-mirror) | CC-BY-NC-4.0 (PKU-Alignment/PKU-SafeRLHF dataset card) | 82,118 | 0 | 0.00% |

### T3 — 需法务确认（copyleft / ShareAlike / 未公示——学界惯例可训，开放权重有争议）（14 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| enwiki-gen | https://dumps.wikimedia.org/enwiki/latest/enwiki-articles2-p41243p151573.bz2, enwiki-articles3-p151574p311329.bz2, enwik | CC-BY-SA 4.0 | 277,025 | 714,855,429 | 64.43% |
| zhwiki-gen | https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-pages-articles.xml.bz2 | CC-BY-SA 4.0 | 84,036 | 124,337,607 | 11.21% |
| t6_devign_lines | https://hf-mirror.com/datasets/DetectVul/devign (train 21,854 + validation 2,732 + test 2,732) | MIT (upstream Devign dataset); derivative line annotation from DetectVul (Tran et al., FGCS 2024, doi:10.1016/j.future.2024.107504) - mirror card carries no explicit license, recorded as research derivative of MIT upstream, D3 re-eval before open weights | 10,039 | 6,199,675 | 0.56% |
| zhwiki-sec | https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-pages-articles.xml.bz2 | CC-BY-SA 4.0 | 1,951 | 5,463,653 | 0.49% |
| owasp-cs | https://github.com/OWASP/CheatSheetSeries/archive/refs/heads/master.zip | CC-BY-SA | 122 | 544,254 | 0.05% |
| aiid | https://incidentdatabase.ai/ (R2 export pub-72b2b2fc36ec423189843747af98f80e.r2.dev/AIID_Excel_Export-20260921.xlsx) | 未公示（数据）; Apache-2.0 (repo code) | 1,689 | 357,472 | 0.03% |
| lolbas | https://github.com/LOLBAS-Project/LOLBAS | GPL-3.0 | 248 | 83,513 | 0.01% |
| owasp-top10 | https://github.com/GenAI-Security-Project/GenAI-LLM-Top10 (2026/final) | CC BY-SA 4.0 | 12 | 50,127 | 0.00% |
| gtfobins | https://github.com/GTFOBins/GTFOBins.github.io | GPL-3.0 | 478 | 49,215 | 0.00% |
| owasp-rtg | https://genai.owasp.org/ (GenAI Red Teaming Guide v1.0) | CC BY-SA 4.0 (OWASP GenAI Security Project) | 1 | 29,323 | 0.00% |
| credential-formats | synthesized from public format specifications (see note) | Original descriptive text; factual format strings cited from public documentation (facts, no creative expression copied). Sources: IETF RFC 7519 (Copyright (c) 2015 IETF Trust and the persons identified as the document authors. All rights reserved.; BCP 78 grants distribution), AWS Documentation Terms, GitHub Docs (MIT), Stripe/Slack/Azure/GCP public docs | 10 | 3,464 | 0.00% |
| maliciousinstruct | https://huggingface.co/datasets/walledai/MaliciousInstruct (via hf-mirror) | CC-BY-SA-4.0 (walledai/MaliciousInstruct dataset card) | 100 | 0 | 0.00% |
| wildguardmix | https://huggingface.co/datasets/allenai/wildguardmix (via hf-mirror, token auth) | ODC-By (allenai/wildguardmix dataset card 'license: odc-by'; WildGuard project originally cited under AI2 OUFRA usage norms) | 88,484 | 0 | 0.00% |
| wildjailbreak | https://huggingface.co/datasets/allenai/wildjailbreak (via hf-mirror, token auth) | ODC-By (allenai/wildjailbreak dataset card, Open Data Commons Attribution 1.0) | 263,769 | 0 | 0.00% |

### ref-only — 不入训练的参照物（仅评估/分类参照，永不入权重）（1 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| tc260 | https://huggingface.co/datasets/MuYi23/TC260-Chinese-Safety-Prompts (via hf-mirror) | Apache-2.0 (mirror) - official source TC260-003 test set, see note | 3,200 | 0 | 0.00% |

### T1 — 可直接发布（署名/NOTICE 义务即可）（33 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| redhat-csaf | https://security.access.redhat.com/data/csaf/v2/advisories/ | CC-BY-4.0 (declared in each CSAF legal_disclaimer note) | 28,441 | 83,105,361 | 7.49% |
| cve | https://github.com/CVEProject/cvelistV5/archive/refs/heads/main.zip | CVE Program terms (public) | 365,356 | 70,096,310 | 6.32% |
| t6_cvefixes | https://doi.org/10.5281/zenodo.13118970 (canonical CVEfixes v1.0.8, CC-BY-4.0); procured via https://hf-mirror.com/datas | CC-BY-4.0 (CVEfixes v1.0.8, Zenodo DOI 10.5281/zenodo.13118970 - canonical data license governs; HF mirror card claims apache-2.0, discrepancy recorded; attribution required on model release) | 11,424 | 20,720,543 | 1.87% |
| t6_devign | https://codeload.github.com/epicosy/devign (tarball master da611bf3; original soarsmu/Devign & software-research/Devign  | MIT (epicosy/devign repository LICENSE verbatim, Copyright (c) 2020 Eduard - mirror of the Devign paper code+data release) | 27,318 | 18,448,064 | 1.66% |
| debian-dsa | https://lists.debian.org/debian-security-announce/ | MIT-Expat OR GPL-2+ (Debian WWW Pages License) | 6,944 | 14,675,514 | 1.32% |
| arxiv-cscr-full | https://export.arxiv.org/api/query (cat:cs.CR 按年分片全历史, totalResults 52384) | CC0 1.0 (arXiv API ToU: descriptive metadata) | 50,384 | 13,166,590 | 1.19% |
| arxiv-aisafety | https://export.arxiv.org/api/query (多查询, 见 raw 分目录) | CC0 1.0 (arXiv API ToU: descriptive metadata) | 18,880 | 5,400,532 | 0.49% |
| ghsl-advisories | https://securitylab.github.com/advisories/ | MIT (github/securitylab) | 816 | 960,827 | 0.09% |
| arxiv-privacy | https://export.arxiv.org/api/query (9 privacy/insider-threat abs-queries on cs.CR+cs.LG+cs.DB, full history) | CC0 1.0 (arXiv API ToU: descriptive metadata) | 2,680 | 739,883 | 0.07% |
| arxiv-cscr |  | arXiv non-exclusive license | 2,000 | 618,991 | 0.06% |
| mitre-attack | https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json | MITRE terms (attribution required) | 1,126 | 324,441 | 0.03% |
| cwe | https://cwe.mitre.org/data/xml/cwec_latest.xml.zip | MITRE terms (attribution required) | 969 | 205,776 | 0.02% |
| nist-privacy | https://nvlpubs.nist.gov/ + https://csrc.nist.gov/ (SP 800-53 v5.1 XML) | Public domain (works of the U.S. Government, 17 U.S.C. 105) | 80 | 183,416 | 0.02% |
| p0-0days | https://github.com/googleprojectzero/0days-in-the-wild | Apache-2.0 | 70 | 181,733 | 0.02% |
| kev | https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json | public-domain (US government) | 1,721 | 156,688 | 0.01% |
| nist | https://nvlpubs.nist.gov/nistpubs/ (AI 600-1 / AI RMF 100-1 / SP 800-226) | Public domain (US government work, 17 U.S.C. §105) | 3 | 111,075 | 0.01% |
| atlas | https://github.com/mitre-atlas/atlas-data (dist/ATLAS.yaml, release 2026.09) | Apache-2.0 | 278 | 75,103 | 0.01% |
| gdpr-full | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679 | EU Open Data Licence / CC-BY-4.0 (EUR-Lex legal notice) | 100 | 65,599 | 0.01% |
| capec | https://capec.mitre.org/data/xml/capec_latest.xml | MITRE terms (attribution required) | 613 | 56,956 | 0.01% |
| gdpr | https://gdpr-info.eu/ | EU 官方法律文本（镜像 gdpr-info.eu 逐条页） | 1 | 35,784 | 0.00% |
| cn-laws-full | https://www.cac.gov.cn/ , npc.gov.cn , huizhou.jcy.gov.cn (official re-publications) | Statutory texts - not subject to copyright (PRC Copyright Law Art. 5(1): laws and regulations are excluded from protection) | 4 | 23,545 | 0.00% |
| cn-regs |  | 官方法规/规章文本（公开） | 7 | 19,603 | 0.00% |
| cn-laws |  | 官方法律文本（公开） | 3 | 14,828 | 0.00% |
| advbench | https://github.com/llm-attacks/llm-attacks (data/advbench) | MIT (llm-attacks repository LICENSE) | 1,094 | 0 | 0.00% |
| cvalues | https://github.com/X-PLUG/CValues (data via hf-mirror.com/datasets/Skepsun/cvalues_rlhf) | Apache-2.0 (X-PLUG/CValues repository LICENSE; mirror tagged Apache-2.0) | 97,116 | 0 | 0.00% |
| harmbench | https://github.com/centerforaisafety/HarmBench | MIT (HarmBench repository LICENSE) | 320 | 0 | 0.00% |
| hh-rlhf-harmlessness | https://huggingface.co/datasets/Anthropic/hh-rlhf (via hf-mirror) | MIT (Anthropic hh-rlhf dataset card) | 44,849 | 0 | 0.00% |
| or-bench | https://huggingface.co/datasets/bench-llms/or-bench (via hf-mirror) | CC-BY-4.0 (bench-llms/or-bench dataset card) | 82,333 | 0 | 0.00% |
| safemtdata | https://huggingface.co/datasets/SafeMTData/SafeMTData (via hf-mirror) | MIT (SafeMTData dataset card) | 2,280 | 0 | 0.00% |
| safety-prompts | https://github.com/thu-coai/Safety-Prompts | Apache-2.0 (thu-coai/Safety-Prompts repository LICENSE) | 100,000 | 0 | 0.00% |
| strongreject | https://github.com/alexandrasouly/strongreject | MIT (strongreject repository LICENSE) | 313 | 0 | 0.00% |
| trustllm-safety | https://github.com/HowieHwong/TrustLLM | MIT (TrustLLM repository LICENSE) | 3,930 | 0 | 0.00% |
| xstest | https://github.com/paul-rottger/xstest | CC-BY-4.0 (xstest repository LICENSE: Attribution 4.0 International) | 450 | 0 | 0.00% |

## SFT 谱系与已注册数据集

| 数据集 | 文件 | 行数 | 内容级 zh | 谱系 | 备注 |
|---|---|---:|---:|---|---|
| sec_sft_m25 | data/lf/sft_m25.jsonl | 137,670 | 44.0%（内容级；上限 45%） | base → c1-full → m16-32k → m15 → m25-full | M2.5 回填终混（17,210 步 ≈ 10.3h，configs/m25-full.yaml）；464 行公共文本双侧复用裁定命中（reports/m25-staging-check.json adjudicated_count） |

## 评估注意事项

- **探针 PPL 绝对幅度受污染影响，只做相对比较**：v0.3 的 privacy 探针取自 GDPR 序言，与 c0_gdpr 训练语料 64.9% 篇级重叠；general_en 探针与 enwiki 训练采样存在 ~26% 篇级重叠——跨模型绝对读数不可直接比较，同模型前后（base → c1-full → m15/m16 → SFT/DPO 各检查点）相对变化有效；ais / content / general_zh / malware 四域完全干净，sec 与 aisafety 有少量（7 + 1 单元）已裁定的公共公告/arXiv 双侧复用残留——对**所有**阶段等权，横向比较仍有效、绝对幅度只作附注。
- **探针 v0.4 已落地（2026-09-30）**：privacy 换源到英国 ICO 指导页（非 GDPR 原文）、general_en 改用 C1 同池哈希**补集**（26% 未训标题）重建；两域成品 vs sft_m25 全量 137,670 行、vs sec_c1_full 抽样 60,000 行均 **0 命中**；其余六域字节复制以保纵向可比（证据链 data/probes/v0.4/README.md、reports/probes-v04-build.json、reports/probes-v04-vs-sft.json）。**门禁仍用 v0.3 口径**（与 base/c1-full/m15/m2* 历史读数连续），v0.4 只提供去污染后的**绝对幅度**附注——两域 v0.3↔v0.4 数值不可直接比较。VERDICT 词表 retrieved / not-in-doc 扩项属评分器级改动，顺延到 M2.5 读数之后。
- **m25 训练行的公共条文复用**：sec_sft_m25 含 464 行 GDPR 条文/序言、CISA KEV 公开描述文本（与 privacy / sec 探针语料双侧复用，已由 scripts/check_m25_staging.py 的 ADJUDICATED 表裁定为良性）——继续推高 privacy / sec 探针的绝对幅度，故上述「仅相对比较」口径对 m25 及后续检查点同样成立。
- 详见 docs/research/probe-contamination-audit.md 与 docs/research/m25-backfill-plan.md §10。

---

*本卡为工程侧披露文件，不构成法律意见；D3 分级的法律问题（权重演绎性/训练复制许可）待法务确认——见 docs/research/d3-ledger-memo.md §4 前置动作清单。*
