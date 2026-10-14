# M1 安全中期训练：语料地图与入库方案

> 版本 v0.1 · docs/01 §4（数据地图）的执行版；Stage 1 配方见 docs/05。
> 底座已定：Qwen3-0.6B-Base（docs/02 §1）。

---

## 0. 核心设计判断：uplift 控制 vs 语言建模目标

**Stage 1 不对武器化内容做无条件语言建模。** 双用途准则（docs/00 §4.3：
harm ∝ Δcapability × P(malicious)）推论：把可用利用代码当作普通语料去
最小化交叉熵，等于把"生成武器"烧进权重——这是 uplift 的最大化，不是安全能力。

分层原则：

| 内容类别 | Stage 1（知识注入） | Stage 2+（判断/响应任务） |
|---|---|---|
| 防御与分析（advisory、机理、缓解、检测） | ✅ 语言建模 | ✅ |
| 双用途知识（漏洞机理、PoC 描述、CTF） | ✅（描述层） | ✅（判断任务：识别/评估，非生成） |
| 武器化内容（可用利用代码、免杀载荷、钓鱼套件） | ❌ 不进 Stage 1 | 受限进入：仅作为**判断对象**（"这段代码是否恶意"），永不作为**模仿目标** |

restricted 语料（Exploit-DB 等）因此推迟到 SFT 判断任务阶段使用，且入库即
继承访问级（docs/01 §6）。

---

## 1. 来源地图

### P0（清洁公开，Stage 1 首批）

| 来源 | 域 | 许可 | 层级 | 预估规模 |
|---|---|---|---|---|
| NVD/CVE JSON feeds（1999–今） | security | 公开（美国gov数据，无版权限制） | public | ~0.5–1B tokens（含描述） |
| MITRE CWE / CAPEC / ATT&CK（STIX/JSON） | security | 公开（需署名） | public | ~50–100M |
| CISA KEV + 安全通告（US-CERT/CERT-EU） | security | 公开 | public | ~100–200M |
| CNVD/CNNVD 漏洞库（可爬部分） | security | 公开（注意 robots/条款） | public | ~50M（zh） |
| 厂商通告：MSRC / Cisco PSIRT / Oracle CPU 摘要 | security | 公开 | public | ~100M |
| Phrack / Project Zero writeups / 安全研究博客 | security | 各自公开（逐源核验） | public | ~200M |
| arXiv cs.CR / AI 安全论文全文（LaTeX/PDF→文本） | security+ai_safety | arXiv 非独占许可 | public | ~500M–1B |
| GDPR / PIPL / CCPA / 数据保护法全文（zh+en） | privacy | 法律文本公开 | public | ~10M |
| NIST SP 800-53/800-188 / ISO 27701 摘要 | privacy | 公开（部分付费标准除外） | public | ~20M |
| AI 安全框架：NIST AI RMF、PAI 负责任部署 | ai_safety | 公开 | public | ~10M |
| OWASP Testing Guide / ASVS / Cheat Sheets | security | CC-BY-SA | public | ~50M |

### P1（次批：分析性内容）

| 来源 | 域 | 层级 | 备注 |
|---|---|---|---|
| CTF writeups（CTFtime 聚合） | security | public | 双用途知识（描述层） |
| Honeypot/蜜罐日志（自采 + 公开数据集） | security | restricted | 自采含攻击者 IP 等 |
| 安全教科书（开放许可：Orange Book? 另选） | security | public | 逐本核验许可 |
| 数据泄露事件报告（监管通报文本） | privacy | public | |

### P2（受限，推迟到判断任务阶段）

| 来源 | 域 | 层级 | 用途 |
|---|---|---|---|
| Exploit-DB / 公开 PoC 仓库 | security | restricted | SFT 判断对象（非模仿目标） |
| Metasploit 模块源码 | security | restricted | 同上 |
| PayloadsAllTheThings 类 | security | restricted | 同上 |
| 恶意样本库 | security | quarantine | 仅哈希/静态特征层，代码不入任何训练 |

### 回放（防灾难遗忘，30–50% 混入）

| 来源 | 语言 | 许可 | 备注 |
|---|---|---|---|
| FineWeb-Edu / FineWeb 采样 | en | ODC-BY | 回放主力 |
| SkyPile / Chinese-FineWeb 采样 | zh | 许可逐批核验 | zh 回放主力 |
| The Stack v2 安全相关语言子集 | code | ODC-BY + 逐文件许可 | 代码回放 |

## 2. 配比设计 v0（Stage 1，按 token 计）

| 类别 | 占比 | 说明 |
|---|---|---|
| security 防御+分析（P0 描述层） | 25% | CVE/NVD 描述、advisory、研究文章 |
| security 结构化知识（CWE/ATT&CK/CAPEC） | 10% | 知识图谱文本化 |
| privacy（法规+指南+事件报告） | 5% | |
| ai_safety（论文+框架+system cards） | 10% | |
| 代码（安全相关+通用回放） | 15% | |
| 通用回放（zh:en ≈ 1:1） | 35% | 防遗忘 |

zh:en 总体目标 ≈ 4:6（底座 zh 比重低于 en，需补中文安全语料——CNVD/
中文安全社区内容是 P0 重点）。

## 3. 入库管线与 manifest

管线：download → 许可核验 → 层级分类 → 清洗（HTML→文本、去噪）→
PII 擦洗（隐私域语料先脱敏，防止"学隐私法却记住隐私"）→ 去重（精确 hash，
minhash 后续）→ tokenize（scripts/tokenize_text.py，EOS 分隔 memmap）→
manifest 登记。

manifest：`data/corpora/manifest.jsonl`（已入库来源，机器可审计）：

```json
{"id": "nvd-cve", "name": "NVD CVE JSON Feeds", "url": "…", "license": "public-domain",
 "tier": "public", "domain": "security", "lang": "en", "est_tokens": 800000000,
 "status": "ingested", "ingested_at": "2026-09-25", "files": ["tokens/nvd.npy"],
 "sha256": "…", "notes": "1999-2026 全量，描述字段保留"}
```

校验工具：`python -m secfm.data.manifest --file data/corpora/manifest.jsonl`

## 4. 优先级与里程碑

| 批次 | 内容 | 规模目标 | 里程碑 |
|---|---|---|---|
| C0（✅ 2026-09-24 完成） | P0 全部来源试抓 + 许可核验 + tokenize 管线打通 | 实得 **72.05M tokens / 371,911 docs**（9/9 源入库，全部 public 层） | docs/05 冒烟训练已启动 |
| C1（🔄 语料建设中，已入库 ~1,057M） | P0 全量 + zh 双子集 + P1 描述层 + en 回放层 + arXiv 安全文献层 | **1.5–2B（按 7.3k tok/s 吞吐实测定规模，≈2.4–3.2 天）** | Stage 1 主训练 |
| C2 | P2 受限层入库（判断任务用） + 回放混配 | +2B | SFT 阶段备料 |

**C1 已入库**（2026-09-25 更新）：C0 全部 72.05M + zhwiki-sec 5.46M + zhwiki-gen 124.3M（15% 采样）+ 中文法规 19.6k + **enwiki-gen 714.9M（分区 2–5，277,025 docs，scripts/fetch_enwiki.py；分区 1 被 data/probes 探针占用，来源隔离永不入训练）** + **P1 描述层 127.1M（7/7 源，51,812 docs，见 §4 P1 实况表）** + **arXiv cs.CR 全历史 13.17M（50,384 docs，缺口 ④）** ≈ **1,057M tokens**。
**C1 待补缺口 ~0.6–1.1B**（2026-09-25 依 P1 实测调研修订，见 docs/research/p1-sources.md）：
① en 回放层 ✅ **已达标**（enwiki 分区 2–5 实测 **714.9M tokens**：P2=177.4M/P3=166.8M/P4=180.9M/P5=189.9M；每分区 ≈170–190M、96%+ 保留率、~2,600 tok/doc；400–700M 目标上沿达成；下载预算 1.75GB/1.5GB 软预算，P5 经批准超支）；
② P1 描述层 ✅ **7/7 源全部入库（2026-09-25）**：redhat 83.11M + debian 14.68M + msrc 10.08M + sans 8.05M + cisco 7.77M + oracle 2.31M + ghsl/p0 1.14M = **127.1M tokens / 51,812 docs**（原估区间 67–147M 中上段;许可决策四源 MSRC/Cisco/Oracle/SANS 已按 D3 注记纳入）;CTFtime（版权归作者）与 Project Zero 本体（Google 系 IP 阻断）维持排除;
③ code 层（安全工具源码等，受 §0 uplift 红线约束）；
④ arXiv 全历史摘要扩展 ✅ **已入库（2026-09-25）**：cs.CR 全历史 **50,384 篇新增 / 13.17M tokens**（API totalResults 52,384 与 C0 最新 2,000 按 id 精确去重；`scripts/fetch_arxiv_full.py`；许可 **CC0 1.0**（arXiv API ToU：descriptive metadata 含 title/abstract/identifiers，逐字引文在 manifest）；实得 13.2M 低于原估 20–40M——摘要均值 ~261 tok/doc，原估偏乐观；通路工程三道门槛：WAF 按 TLS 指纹拦 Python urllib → curl 子进程、深分页 10k 硬上限 → 按年分片、限速 → 8s 间隔 + 退避；探针重叠 7 条（ais×cs.CR 双列目）已报告 `reports/probe-ais-overlap-arxiv-full.json`，处置待决）；
⑤ zh 回放可上调（dump 已在本地，重采样纯 CPU 可行；**2026-09-25 实测扫描**：池 558,729 条非安全条目/11.6 亿字符，各采样率实得条数与字符量 → 15%=124.3M（已验证）/25%≈207.1M/40%≈331.6M/55%≈456.2M/全量≈830M；重处理 ~10 分钟 + token 计数 ~15 分钟）。

**P1 许可决策（2026-09-25，用户拍板）：四源全纳入 C1**（MSRC + Cisco + Oracle + SANS ISC，+42–96M tokens）。
**风险注记**：若 M5/D3 决定开放权重，这批数据需重新评估，存在重新训练的可能——届时可先试"剔除污染源重训"路线。各源许可原文摘录见 docs/research/p1-sources.md，入库时逐源登记进 manifest。

| 源 | 许可状况 | 规模 | 处置 |
|---|---|---|---|
| MSRC | API 无条款声明；Learn 站限"个人非商用" | 10–40M | **纳入 C1** |
| Cisco PSIRT | © Cisco；条款原文本网络取不到 | 5–15M | **纳入 C1** |
| Oracle CPU | "All rights reserved" | 2–6M | **纳入 C1** |
| SANS ISC | CC BY-NC-SA 4.0（NC 门槛） | 25–35M | **纳入 C1** |

### C0 实况记录（`scripts/fetch_c0.py`，manifest 全绿）

| 源 | docs | tokens | 备注 |
|---|---|---|---|
| cve | 365,356 | 70,096,310 | cvelistV5 全量（剔 REJECTED/无英文描述），主体 |
| arxiv-cscr | 2,000 | 618,991 | cs.CR 最新 2000 篇摘要 |
| owasp-cs | 122 | 544,254 | 仓库目录已改小写 `cheatsheets/`（转换器已适配） |
| mitre-attack | 1,126 | 324,441 | STIX → 结构化文本 |
| cwe | 969 | 205,776 | cwec_latest.xml |
| kev | 1,721 | 156,688 | CISA KEV JSON |
| capec | 613 | 56,956 | 官方 XML 直链（旧 .zip 链接已 404） |
| gdpr | 1 | 35,784 | gdpr-info.eu 逐条页拼接（EUR-Lex 对脚本返回空体） |
| cn-laws | 3 | 14,828 | PIPL/网安法(2025 修正版)/数安法；gov.cn 旧链已失效，改用 CAC/npc 镜像；本地网络对 gov 站有 TLS 拦截 → 降级抓取 + 关键词完整性校验（标题+第一条）通过 |

管线要点：md5 去重、≥40 字符过滤、`ensure_ascii=True` 输出（规避 pyarrow 对原始多字节 UTF-8 的严格性缺陷，见 docs/02 §0.1 #4）、Qwen tokenizer 计数、manifest 自动登记。zh:en 目前 ~0.02%:99.98%（法律文本仅 15k token）——**中文配比缺口确认，C1 需重点补 P1 中文源**（对应 §5 风险第 1 条）。

### P1 描述层实况记录（2026-09-24/25 起逐源入库，`scripts/fetch_*.py`，manifest 同步登记）

| 源 | docs | tokens | 抓取通路与备注 |
|---|---|---|---|
| ghsl-advisories | 816 | 960,827 | securitylab.github.com 索引页(1.87MB)提取 slug 后逐页抓;MIT。SecurityExploits/ 按 §0 uplift 红线排除 |
| p0-0days | 70 | 181,733 | 0day-in-the-wild 仓库 git clone 镜像,0day-RCAs/*.md 去 frontmatter;Apache-2.0 |
| oracle-cpu | 158 | 2,314,816 | oracle.com/security-alerts 主索引+cpuarchive/alertsarchive/solarisbulletinsarchive 四页枚举 161 通告;**curl.exe/schannel**（Python OpenSSL 握手被重置,docs/research/p1-sources.md §2.3）;all-rights-reserved（D3 风险注记,manifest 逐字摘录条款） |
| msrc-cvrf | 192 | 10,083,959 | api.msrc.microsoft.com/cvrf/v3.0 免 key;OData `value[]` 192 文档(CVRF 1.1 XML);swagger 无条款声明 + Learn TOU 个人非商用（D3,manifest 逐字摘录） |
| debian-dsa | 6,944 | 14,675,514 | lists.debian.org 1998–2026 全 29 年 7,123 页(0 失败,255 已存跳过);MHonArc 实体(`&#45;`)已反转义;MIT/GPL-2+ |
| cisco-psirt | 5,179 | 7,767,958 | getCvrfPaginationRecords.x 枚举 5,286 篇（**pageIndex/itemsPerPage 分页，offset 被忽略**；itemsPerPage=All 单请求取全量）+contentxml CVRF 直链（0 失败,107 薄壳剔除）;openVuln API 需 OAuth 未用;© Cisco Baseline API Terms（D3,PDF 403 不可取,如实记录） |
| redhat-csaf | 28,441 | 83,105,361 | security.access.redhat.com CSAF v2,26 年目录枚举 **28,441 个唯一 rhsa 文件（0 失败,全部转换成功）**;超原估 1.6–2.2 万近半;CC-BY-4.0（每文件 legal_disclaimer 注记自证,manifest 逐字摘录） |
| sans-isc | 10,212 | 8,054,600 | isc.sans.edu/diaryarchive.html?year&month 枚举 10,330 篇 + /diary/{id}（2003–2026,18 空/超短剔除,96 md5 去重）;**curl.exe**（urllib TLS 握手失败）+ 自定义 UA;8 workers 曾触发 bot 挑战（1,111 篇"Are you human?"壳页,识别删除后 3 workers 慢速重抓全数恢复）;CC BY-NC-SA 4.0（D3,manifest 逐字摘录） |

**P1 描述层全部 7 源入库完成（2026-09-25）**：合计 **51,812 docs / 127,144,712 tokens（~127.1M）**——原估 67–147M 区间中上段；redhat 单源 83.1M 独大（占 65%）。fetch 脚本 7 个（`scripts/fetch_{debian_dsa,ghsl_p0,oracle_cpu,cisco_psirt,msrc_cvrf,redhat_csaf,sans_isc}.py`），转换器纯函数单测 48 个,全套 187 测试通过。带宽注记：2026-09-25 前期全项目共享出口被 enwiki 挤占（~55–88KB/s），enwiki 完成后 redhat 提至 12 workers（~500 文件/分）零失败收尾;SANS 高并发触发 bot 挑战后降速恢复;全部 fetch 脚本支持断点续传（skip-fetched）。

### C2 隐私工程知识层实况记录（2026-09-25 入库，`scripts/fetch_*.py`，M1.5 五域之隐私/泄露域）

定位：补 C1 隐私薄弱层（当时隐私文本仅法规 ~2M,privacy 探针 PPL +4.1% 轻退），为 M2 的 PII 识别/脱敏/泄露判断行为提供知识底座。

| 源 | docs | tokens | 抓取通路与备注 |
|---|---|---|---|
| arxiv-privacy | 2,680 | 739,883 | export.arxiv.org API 9 查询（differential privacy/de-identification/personally identifiable/privacy-preserving/PII detection/health data privacy/reidentification/insider threat/credential+secret leakage，cs.CR+cs.LG+cs.DB 全历史），raw 9,832 条排除 c1_arxiv_full 已入库 6,894 条（70% 重合）后净增;复用 fetch_arxiv_full 的 curl.exe TLS 指纹通路 + 8s 限速;CC0 1.0（API ToU descriptive metadata 条款逐字登记）;探针重叠检查 ais.jsonl 0 命中 |
| gdpr-full | 100 | 65,599 | EUR-Lex CELEX:32016R0679 官方 HTML（809KB）逐条 Article 一 doc（1 序言 154k 字符 + 99 条）;C0 时代"EUR-Lex 对脚本返回空体"实测只拦 urllib——curl.exe/schannel 全通;EU Open Data Licence（CC-BY-4.0） |
| cn-laws-full | 4 | 23,545 | 四法全文:PIPL（CAC,74 条）/网络安全法 2025 修正（CAC）/数据安全法（npc）/保密法 2024 修订（惠州检察院镜像,npc/gov.cn 旧链 404、flk.npc.gov.cn 纯 SPA）;法条不受著作权保护（著作权法第五条）;每法单 doc,末条在场完整性校验 |
| nist-privacy | 80 | 183,416 | 公有领域（17 U.S.C. §105）:Privacy Framework 1.0 + SP 800-188 去标识化指南 + FIPS 199 定级 + SP 800-171r3 CUI（pypdf 抽取,venv 新装 pip 26.1.2+pypdf 6.19.0）+ SP 800-53 r5.1 官方 XML 的 AC/SC 两族逐控制 76 docs（含控制增强） |
| credential-formats | 10 | 3,464 | 合成描述层:API key/JWT/AWS AKID+ARN/Azure key+SAS/GCP/PEM 私钥块/SSH/GitHub/Slack/Stripe/K8s Secret/.env/检测启发式——纯"长什么样、为何不能外传"识别知识,无真实凭证无武器化内容（§0 红线）;事实性格式规范引用公开文档,来源许可逐字登记（RFC 7519 版权告示/AWS Documentation Terms/GitHub Docs MIT） |
| **合计** | **2,874** | **1,015,907** | 5 fetch 脚本 + 22 转换器单测;全套 223 测试通过 |

**规模实测说明（对 20–50M 目标）**：指定 9 查询的摘要层天花板即 ~2.6M tokens（9,832 raw × ~260 tok/篇,未去重）;去重排除后实得 0.74M。宽口径探测（2026-09-25）：abs:privacy 全三分类 19,853 篇 ≈ 5.2M、anonymity/k-anonymity 2,343 篇 ≈ 0.6M——**隐私域摘要层物理上限 ~5M,远低于 20–50M 目标**;如需 20M+ 须上论文全文层或扩域（父会话决策）。GB/T 35273 已按许可红线**跳过全文**（国标文本受版权保护,openstd 在线预览为图片渲染且页脚"版权所有 侵权必究",无授权复用条款——仅可人工查阅,不宜入库;如需覆盖可后续采购正版文本或人工编写结构摘要）。

C1 总账不变（C2 属 M1.5 预算,~100–150M 五域合计）;C2 隐私域首期 1.02M,占预算远低于 60M 上限,无需预警。

### C2 AI-safety/恶意代码/内容安全/高危操作知识层实况记录（2026-09-25 入库，`scripts/fetch_*.py`，M1.5 五域之四域）

定位：AI-safety 对齐文献、恶意代码分析研究、内容安全研究、攻击技术参考库（描述级）——M1.5 mini-CT 的主力知识弹药。

| 源 | docs | tokens | 抓取通路与备注 |
|---|---|---|---|
| arxiv-aisafety | 18,880 | 5,400,532 | export.arxiv.org API **11 查询**：十查询（prompt injection/jailbreak/LLM security/red team/guardrail/content moderation/hate speech+toxicity/malware+ransomware/code obfuscation/static analysis+malware，cs.AI+CL+CR+LG 四域全历史）+ **ai_safety_alignment 变体 b**（父代理 2026-09-25 执行令：`"AI safety" OR (alignment AND LLM 语境限定)` 17,444 原始;**标题级纯度过滤**弃 1,792——排除词族（vision/image/multimodal/cross-lingual/word/sequence alignment/sensor/registration/correspondence/point cloud）命中且无安全信号双条件,50 保留/50 剔除样例存档 `reports/aisafety-alignment-purity-audit.json`**;实现注记：_TITLE_SAFETY 不含裸 align——"word alignment" 噪声题名自带 alignment 字样会自救漏网**）;raw 30,313 条**排除 C1 已含 7,982**+ 跨查询去重后净增;curl.exe 通路 + 8s + 年份分片（17,444>9,000 自动触发,36 年分片一次 429 六连退避自愈,零硬失败）;CC0 1.0（API ToU 逐字,同 arxiv-cscr-full 行） |
| gtfo-bins | 478 | 49,215 | GTFOBins.github.io 仓库（数据仓库已并入 site repo,_gtfobins/ 478 条目）;**Windows 保留名条目 "node" 被 scandir 整个隐藏 → 以 git 索引为枚举源 + git show blob 回退**;**GPL-3.0（LICENSE 全文,与原口径 MIT 不符,已上报）** |
| lolbas | 248 | 83,513 | LOLBAS-Project/LOLBAS 仓库 yml/ 逐条目转换（Command/Description/Usecase/Category/Privileges/MitreID/Detection IOC）;**GPL-3.0（NOTICE.md 逐字 "The LOLBAS Project is licensed under GPL 3.0.",与原口径 MIT 不符,已上报）** |
| nist | 3 | 111,075 | AI 600-1（GenAI Profile）+ AI RMF 1.0（AI.100-1）+ SP 800-226;nvlpubs 直链 PDF,pypdf 抽取;**公有领域（17 U.S.C. §105）** |
| owasp-rtg | 1 | 29,323 | GenAI Red Teaming Guide v1.0（2025-01-23,77 页）;genai.owasp.org 下载 PDF;CC BY-SA 4.0（项目口径;PDF 内无逐字许可页,如实记录;SA → D3 评审项） |
| owasp-top10 | 12 | 50,127 | Top 10 for LLM Applications **2026 版**（2026-08-04 发布;活跃仓库已迁 GenAI-Security-Project/GenAI-LLM-Top10,旧仓库为 legacy 归档）;LLM01-10 + 附录 A + references（附录 B 纯图跳过）,raw.githubusercontent 逐文件;CC BY-SA 4.0（仓库徽标逐字） |
| atlas | 278 | 75,103 | MITRE ATLAS 2026.09 版 dist/ATLAS.yaml（mitre-atlas/atlas-data,导航仓库 README 指路）;16 tactics + 170 techniques + 35 mitigations + 57 case studies 逐条目一 doc;**Apache-2.0（仓库 LICENSE,与原口径 CC-BY-4.0 不符,已上报）**;通路注记：github.com 主站今日连接被断 → codeload.github.com tarball 端点全通 |
| aiid | 1,689 | 357,472 | AI Incident Database 全库策展事件（编辑撰写标题/描述 + MIT 风险分类 89% 填充 + CSET 政策层有值即带）;**通路破局**：api.incidentdatabase.ai 连接被断,但主站 Gatsby 静态层全通 → research 页 HTML 挖出 **Cloudflare R2 周导出桶**（AIID_Excel_Export-20260921.xlsx = 全库单文件,excel-export-pipeline README 证实）;**Reports 表（7,791 条外部新闻片段）按版权红线排除**（第三方原文摘录,许可不可传递）;**数据许可未公示**（terms-of-use/footer/工作簿均无条款,原口径 CC-BY-4.0 未能在线核实,代码仓库 Apache-2.0）→ D3 评审项;事件报告=OK（红线分类） |
| **合计** | **21,589** | **6,156,360** | 5 fetch 脚本（arxiv_aisafety/lolbas_gtfo/aisafety_knowledge/aiid + ais500_draft）+ 31 转换器单测 |

**红线分类记录（§0 uplift 同源框架）**：研究摘要（攻击/恶意代码的描述、分类、结论）= OK;GTFOBins/LOLBAS 条目 = "某二进制+某参数=某滥用技术" 描述级参考 + 检测 IOC（识别导向,面向 M1.5 高危操作域）= 按父代理 2026-09-25 判定纳入;不含可直接投喂的攻击提示词集合/越狱载荷库（该类留 M2/M4 评估）。

**未入库项**：无——AIID 已于同日经 R2 导出桶破局入库；ai_safety_alignment 已按父代理变体 b 执行令入库（含纯度过滤与样例存档）。

**附带交付**：ais 探针扩容草稿 `data/probes/ais-500-draft/ais.jsonl`（500 条,最新 cs.AI 窗口,排除 C1+C2 全部训练 id + 既有探针标题）。**时序教训记档**：初版草稿在 b 变体入库前抓取,复检抓到 32 条与 b 变体训练集标题重合——按父代理 2026-09-25 指示"b 变体入库后必须重跑隔离验证",已用完整排除集（73,015 ids + 26,715 C2 标题集）重刷,零污染确认。草稿待父代理随探针 v0.3 晋升,不动 v0.1.1。

规模对预算：AI-safety 域终量 **6.16M / 60M 上限,占 10.3%**（arXiv 层 5.40M 独大;b 变体净增 13,675 docs/+3.94M,高于父代理 ~4.5M 总量预估——预估按 17.4k 原始未计跨查询去重后保留率;如实报告）,无需预警。

## 5. 风险与开放问题

- 中文安全语料规模可能不足 25% 配比 → 从 P1 的中文 writeup/厂商中文通告补，或下调 zh 目标并记录原因；
- CC-BY-SA（OWASP 等）对模型权重的兼容性：学界惯例视为可训练，本项目立场——**逐源记录许可，发布评审时（M5/D3）统一答复**；
- 论文全文 PDF 解析质量 → 优先 arXiv LaTeX 源码；

### 5.1 C1 中文补源方案（基于 C0 实测缺口，2026-09-24）

C0 实测 zh 占比 ~0.02%（仅三部法律 15k token），中文配比缺口确认。C1 调研结论：

| 候选源 | 许可/通道 | 可得规模（估） | 决定 |
|---|---|---|---|
| 中文维基百科（安全/隐私分类树 + 通用回放子采样） | CC-BY-SA 4.0，官方 dump 免下载 | 实测（2026-09-24，dump 3.16GB / 212 万页）：**安全域 1,951 篇 / 5.46M tokens；通用 15% 采样 84,036 篇 / 124.3M tokens**（采样率可调，全量 ≈ 830M） | **✅ 已入库（scripts/fetch_zhwiki.py，85 测试含 19 项新增）** |
| 中文法规扩展（数据出境安全评估办法、网络数据安全管理条例、关基条例、生成式 AI 管理办法、网络安全审查办法、个人信息出境标准合同办法、汽车数据规定） | 官方公开文本，CAC/gov.cn 现行页面（2026-09-24 核验） | 实测：7 部 / 19,603 tokens（`cn-regs` 源，完整性校验全过） | **✅ 已入库**（合计中文法律/法规 10 部 / 34,431 tokens） |
| 厂商中文通告/分析文章（先知、FreeBuf、安全客等） | 站点内容版权各异，无批量开放许可 | 大但不可控 | 暂缓；如采用需逐站确认条款并小样本试抓 |
| CNNVD / CNVD 官方库 | 无开放批量数据/API，使用条款未授权训练 | — | **不采用**（中文漏洞描述无法从官方渠道合规获取） |

**中文语料实测盘点（C1 可用）**：zh 共 ~130M tokens（安全域 5.5M + 通用回放 124.3M + 法律 34k）。结论：**zh 安全域天然稀缺（全 zhwiki 安全树仅 5.5M）**，zh:en 配比中 zh 侧以通用回放为主、安全域以 en 为主——C1 混配按"zh 通用回放 4% + zh 安全/法律 0.2% + en 主导"记录实际值，不硬凑 4:6。
- 自采蜜罐日志的 PII/攻击基础设施信息 → restricted 层 + 擦洗规则先行。
