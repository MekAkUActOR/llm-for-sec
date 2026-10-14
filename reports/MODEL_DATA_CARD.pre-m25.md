# Model Data Card（模型训练数据总账）

> **语料态绑定**：本卡由 `manifest.jsonl` 机器生成（`scripts/gen_datacard.py`）——manifest 变更后本卡即过期，须重跑再生。结构对齐 docs/research/cc-by-sa-precedent.md §3 先例实践（RedPajama 式逐子集许可指针 + 逐字许可引用）。

- 生成时间：2026-09-25 10:20
- manifest 快照 sha256（前 16 位）：`a70b4041f6284308`
- 源数：49 · 总 docs：1,644,062 · 总 tokens：1,064,213,945

## 下游用户提示（Dolma 式源级许可传递）

使用本模型时，您同时受训练数据原始来源的许可条款约束（各源逐字许可见下表）。本卡按 CC 官方 AI 训练指南的署名建议（attribution = 数据集链接式指引）逐源披露。

## 汇总

### 按 D3 分级（docs/research/d3-ledger-memo.md §3）

| 分级 | tokens | 占比 | 含义 |
|---|---:|---:|---|
| T2 | 28,221,333 | 2.7% | 需剥离重训（NC / all-rights-reserved / 未授权——开放权重前删除重训） |
| T3 | 845,774,057 | 79.5% | 需法务确认（copyleft / ShareAlike / 未公示——学界惯例可训，开放权重有争议） |
| T1 | 190,218,555 | 17.9% | 可直接发布（署名/NOTICE 义务即可） |

### 按许可家族

| 许可家族 | tokens | 占比 |
|---|---:|---:|
| CC BY-SA（ShareAlike） | 845,280,393 | 79.4% |
| CC-BY-4.0（署名） | 83,170,960 | 7.8% |
| CVE Program（公开条款） | 70,096,310 | 6.6% |
| CC0 1.0 | 19,307,005 | 1.8% |
| CC BY-NC（非商用） | 18,138,559 | 1.7% |
| MIT / GPL-2+ 双许可 | 14,675,514 | 1.4% |
| 其他（详见逐源行） | 7,924,646 | 0.7% |
| All rights reserved | 2,318,280 | 0.2% |
| MIT | 1,548,000 | 0.1% |
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
| msrc-cvrf | https://api.msrc.microsoft.com/cvrf/v3.0/Updates | MSRC CVRF API: no termsOfService declared in swagger; Microsoft Learn TOU personal/non-commercial (project decision 2026-09-24, docs/04 D3) | 192 | 10,083,959 | 0.95% |
| sans-isc | https://isc.sans.edu/diaryarchive.html | CC BY-NC-SA 4.0 (project decision 2026-09-24, docs/04 D3) | 10,212 | 8,054,600 | 0.76% |
| cisco-psirt | https://sec.cloudapps.cisco.com/security/center/cvrfListing.x | Cisco Baseline API Terms / (c) Cisco (project decision 2026-09-24, docs/04 D3) | 5,179 | 7,767,958 | 0.73% |
| oracle-cpu | https://www.oracle.com/security-alerts/ | Oracle Web Sites Terms of Use (all rights reserved; project decision 2026-09-24, docs/04 D3) | 158 | 2,314,816 | 0.22% |
| beavertails | https://huggingface.co/datasets/PKU-Alignment/BeaverTails (via hf-mirror) | CC-BY-NC-4.0 (PKU-Alignment/BeaverTails dataset card) | 364,170 | 0 | 0.00% |
| pku-saferlhf | https://huggingface.co/datasets/PKU-Alignment/PKU-SafeRLHF (via hf-mirror) | CC-BY-NC-4.0 (PKU-Alignment/PKU-SafeRLHF dataset card) | 82,118 | 0 | 0.00% |

### T3 — 需法务确认（copyleft / ShareAlike / 未公示——学界惯例可训，开放权重有争议）（11 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| enwiki-gen | https://dumps.wikimedia.org/enwiki/latest/enwiki-articles2-p41243p151573.bz2, enwiki-articles3-p151574p311329.bz2, enwik | CC-BY-SA 4.0 | 277,025 | 714,855,429 | 67.17% |
| zhwiki-gen | https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-pages-articles.xml.bz2 | CC-BY-SA 4.0 | 84,036 | 124,337,607 | 11.68% |
| zhwiki-sec | https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-pages-articles.xml.bz2 | CC-BY-SA 4.0 | 1,951 | 5,463,653 | 0.51% |
| owasp-cs | https://github.com/OWASP/CheatSheetSeries/archive/refs/heads/master.zip | CC-BY-SA | 122 | 544,254 | 0.05% |
| aiid | https://incidentdatabase.ai/ (R2 export pub-72b2b2fc36ec423189843747af98f80e.r2.dev/AIID_Excel_Export-20260921.xlsx) | 未公示（数据）; Apache-2.0 (repo code) | 1,689 | 357,472 | 0.03% |
| lolbas | https://github.com/LOLBAS-Project/LOLBAS | GPL-3.0 | 248 | 83,513 | 0.01% |
| owasp-top10 | https://github.com/GenAI-Security-Project/GenAI-LLM-Top10 (2026/final) | CC BY-SA 4.0 | 12 | 50,127 | 0.00% |
| gtfobins | https://github.com/GTFOBins/GTFOBins.github.io | GPL-3.0 | 478 | 49,215 | 0.00% |
| owasp-rtg | https://genai.owasp.org/ (GenAI Red Teaming Guide v1.0) | CC BY-SA 4.0 (OWASP GenAI Security Project) | 1 | 29,323 | 0.00% |
| credential-formats | synthesized from public format specifications (see note) | Original descriptive text; factual format strings cited from public documentation (facts, no creative expression copied). Sources: IETF RFC 7519 (Copyright (c) 2015 IETF Trust and the persons identified as the document authors. All rights reserved.; BCP 78 grants distribution), AWS Documentation Terms, GitHub Docs (MIT), Stripe/Slack/Azure/GCP public docs | 10 | 3,464 | 0.00% |
| maliciousinstruct | https://huggingface.co/datasets/walledai/MaliciousInstruct (via hf-mirror) | CC-BY-SA-4.0 (walledai/MaliciousInstruct dataset card) | 100 | 0 | 0.00% |

### ref-only — 不入训练的参照物（仅评估/分类参照，永不入权重）（1 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| tc260 | https://huggingface.co/datasets/MuYi23/TC260-Chinese-Safety-Prompts (via hf-mirror) | Apache-2.0 (mirror) - official source TC260-003 test set, see note | 3,200 | 0 | 0.00% |

### T1 — 可直接发布（署名/NOTICE 义务即可）（31 源）

| 源 | URL | 许可（逐字） | docs | tokens | 占比 |
|---|---|---|---:|---:|---:|
| redhat-csaf | https://security.access.redhat.com/data/csaf/v2/advisories/ | CC-BY-4.0 (declared in each CSAF legal_disclaimer note) | 28,441 | 83,105,361 | 7.81% |
| cve | https://github.com/CVEProject/cvelistV5/archive/refs/heads/main.zip | CVE Program terms (public) | 365,356 | 70,096,310 | 6.59% |
| debian-dsa | https://lists.debian.org/debian-security-announce/ | MIT-Expat OR GPL-2+ (Debian WWW Pages License) | 6,944 | 14,675,514 | 1.38% |
| arxiv-cscr-full | https://export.arxiv.org/api/query (cat:cs.CR 按年分片全历史, totalResults 52384) | CC0 1.0 (arXiv API ToU: descriptive metadata) | 50,384 | 13,166,590 | 1.24% |
| arxiv-aisafety | https://export.arxiv.org/api/query (多查询, 见 raw 分目录) | CC0 1.0 (arXiv API ToU: descriptive metadata) | 18,880 | 5,400,532 | 0.51% |
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

---

*本卡为工程侧披露文件，不构成法律意见；D3 分级的法律问题（权重演绎性/训练复制许可）待法务确认——见 docs/research/d3-ledger-memo.md §4 前置动作清单。*
