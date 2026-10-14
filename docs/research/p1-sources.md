# P1 描述层安全数据源调研报告(厂商通告 + 漏洞研究 writeup)

> 版本 v1.0 · 2026-09-24 · 对应 docs/04 §1 P1 清单与 §4 C1 缺口 ②("P1 描述层:厂商通告 ~100M + 研究 writeups ~200M,逐源许可核验")
> 方法:纯调研 + 小样本可达性实测(HEAD / 单次 GET,≤128KB 读样),未批量下载。实测日期 2026-09-24,单线程/低并发礼貌探测。
> 实测脚本:`scripts/probe_p1_reachability.py` + `probe_p1_round2~8.py`(保留复现);第一轮原始结果:`docs/research/_p1_probe_results.json`;Oracle 条款页样本:`docs/research/_oracle_terms_sample.html` 等 3 个 `_oracle_*` 文件(许可核验证据)。

---

## 0. 执行摘要(先看这个)

| 结论 | 内容 |
|---|---|
| **最大干净源** | Red Hat CSAF v2:**CC-BY 4.0 明示授权**、静态目录免认证、实测约 1.6–2.2 万条 RHSA、下载约 1.5–3 GB、净文本估 20–40M tokens |
| **许可最干净的小源** | Debian DSA(站点 MIT/GPL-2+ 双许可)、GitHub Security Lab(MIT)、P0 0days-in-the-wild 镜像(Apache 2.0) |
| **意外发现 1** | MSRC CVRF API **v3.0 免 API key**(v2.0 已下线;swagger 无 termsOfService 字段——许可未声明,需项目决策) |
| **意外发现 2** | Cisco openVuln API 虽需 OAuth,但 `sec.cloudapps.cisco.com` 的 **CVRF/CSAF 列表与单文件可匿名直取**(实测 200) |
| **意外发现 3** | Oracle 对 Python urllib(OpenSSL 栈)TLS 握手超时,但 **curl.exe(schannel 栈)0.5–4s 稳定 200** —— 入库脚本必须走 curl 子进程 |
| **排除项** | CTFtime writeup(页脚明示版权归各作者,无再许可权);Project Zero 博客/issue tracker(本网络 Google 系全阻断,TCP 不可连) |
| **规模警示** | C1 规划中 "研究 writeups ~200M" **不可达**:许可干净且可达的 writeup 层(GHSL+0days 镜像)仅 ~2–5M tokens;缺口需从 arXiv 全文/回放层补(见 §4) |

---

## 1. 总表

| # | 来源 | 访问方式(实测 URL) | 许可 | 估算规模 | 本机可达性 | 入库难度 |
|---|---|---|---|---|---|---|
| 1 | MSRC 通告 | CVRF API v3.0 `api.msrc.microsoft.com/cvrf/v3.0/Updates` + `/cvrf/{ID}`(免 key) | ⚠️ 无声明;Learn 站条款限"个人非商用" → 需决策 | 192 个 CVRF 文档;估 10–40M tok | ✅ 200,0.7–3.6s | 低(CVRF XML) |
| 2 | Cisco PSIRT | openVuln v2(需 OAuth)或 **匿名 CSAF 列表** `sec.cloudapps.cisco.com/security/center/cvrfListing.x` + CSAF JSON 直链 | ⚠️ © Cisco;Baseline API Terms(本网络取不到原文)→ 需决策 | 约 2000–3500 篇;估 5–15M tok | ✅ tools/sec.cloudapps 200(4–8s);www.cisco.com 403 | 中(注册 or 列表页解析) |
| 3 | Oracle CPU | `oracle.com/security-alerts/` 索引 + `bulletin{mon}{year}.html` 季度通告 + 归档页;无 API | ⚠️ "All rights...reserved" → 需决策 | ~85 篇 CPU + ~100+ CVE alert;估 2–6M tok | ⚠️ 仅 curl.exe 通(0.5–4s);urllib TLS 超时 | 中高(HTML 大表) |
| 4 | Project Zero | 博客 blogspot / tracker issues.chromium.org / googlesource gitiles(全阻断);**GitHub 镜像可达** | 博客无声明;**镜像仓库 Apache 2.0** | 博客+issue 估 3–5M tok(不可达);镜像 0.3–1M tok | ❌ Google 系 TCP 不通;✅ api.github.com | 镜像:低;其余:不可行 |
| 5 | CTFtime | API v1(仅 events/teams/results,无 writeup 端点);writeup 页 `/writeup/{id}` HTML | ❌ "All tasks and writeups are copyrighted by their respective authors" | ~3 万 writeup;理论 15–75M tok | ✅ 200,2–6s | 高且**许可排除** |
| 6a | SANS ISC diary | `isc.sans.edu/diaryarchive.html` + `/diary/{id}` + RSS/API | ⚠️ **CC BY-NC-SA 4.0**(NC 非商用)→ 需决策 | ~3 万篇;估 25–35M tok | ✅ 200,0.8–3.9s(要求自定义 UA) | 低 |
| 6b | Debian DSA | `lists.debian.org/debian-security-announce/{year}/` 年度索引 → msg 页;`security-tracker.debian.org` | ✅ **MIT / GPL-2+**(Debian WWW License) | ~5,900+ 篇;估 3–6M tok | ✅ 200(www 慢 3–12s;lists 快 1.5–2.5s) | 低 |
| 6c | Red Hat RHSA | 静态目录 `security.access.redhat.com/data/csaf/v2/advisories/{year}/`(CSAF JSON)+ RSS | ✅ **CC-BY 4.0**(官方页明示,需署名) | ~1.6–2.2 万条;估 20–40M tok | ✅ 200,0.6–1.2s,无认证 | **最低**(纯 JSON) |
| 6d | GitHub Security Lab | 站点 `securitylab.github.com`(含 llms.txt、/advisories/)+ `github.blog/security/` + 源仓库(github.com) | ✅ **MIT**(仓库 LICENSE.md);blog 文章 © GitHub | 953 advisories + ~150 文章;估 1.5–3M tok | ✅ 200,0.5–4s;github.com **间歇**可达 | 低中 |

可达性环境注记(2026-09-24 实测):github.com / api.github.com 间歇可达(同会话内 200 与 connect-timeout 交替),codeload / raw.githubusercontent TLS 重置(与任务前情一致);Google 系(blogspot、googlesource、issues.chromium.org、web.archive.org)TCP 直连失败;oracle.com 仅 schannel 栈(curl.exe)可通;debian.org 慢但稳;redhat 静态站快且稳。全部探测显式禁用代理(`--noproxy "*"` / `ProxyHandler({})`)。

---

## 2. 逐源详情

### 2.1 MSRC(微软安全响应中心)

**访问方式**
- CVRF API v3.0(**实测免 API key**,v2.0 已 404 下线):
  - 索引:`https://api.msrc.microsoft.com/cvrf/v3.0/Updates` → 单页返回全量 **192 条**(`{"ID":"1999-Sep"..."2026-Sep"}`,48 KB JSON,无 @odata.nextLink)
  - 单文档:`https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/{ID}`,如 `2025-Jan` → CVRF XML(实测 200,7.0 MB;`2026-Sep` 9.8 MB;`2010-Jan` 仅 6.7 KB)
  - 注意:HEAD 返回 405(不支持);OData `$top` 触发 500(不支持服务端分页参数)
- 网页端:`https://msrc.microsoft.com/update-guide`(200,SPA);历史公告库 `learn.microsoft.com/en-us/security-updates/`(HTML)
- 官方工具:`github.com/microsoft/MSRC-Microsoft-Security-Updates-API`(MsrcSecurityUpdates PowerShell 模块 + `docs/swagger.json`,标题 "MSRC CVRF API" version v3)

**许可**
- swagger.json 中 **无 `termsOfService` 字段**(实测解码核验)——API 数据本身未声明许可。
- learn.microsoft.com 通告页受 Microsoft Learn TOU 约束,逐字(https://learn.microsoft.com/en-us/legal/termsofuse):
  > "Unless otherwise specified, the Services are for your personal and non-commercial use. You may not modify, copy, distribute, transmit, publicly display, perform, reproduce, publish, license, create derivative works from, transfer or sell any information, software, products or services obtained from the Services (except for your own, personal, non-commercial use) without prior written consent from Microsoft."
  >
  > "Permission to use Documents (such as white papers, press releases, datasheets and FAQs) from the Services is granted, provided that … (2) use of such Documents from the Services is for informational and non-commercial or personal use only …"
- **判断:无开放许可 → 项目决策**。事实性安全通告(CVE/KB/严重度映射)与已入库的 cvelistV5 同性质,法律风险低,但须按 docs/04 §5 的"逐源记录许可"原则留痕决策。

**规模估计**:192 文档覆盖 1999-Sep–2026-Sep;早期文档 KB 级,2017 年后 0.2–1 MB,2020+ 为 2–10 MB(含 Azure/Edge 全产品矩阵)。总下载 ~300–450 MB XML;文本化(标题+漏洞描述+缓解+KB)估 **10–40M tokens**。

**本机可达性实测**:全部通过且快(服务根 1.1s / Updates 3.6s / 7 MB 文档 34s);无 TLS 拦截、无认证、未观察限流。

**入库难度:低**。CVRF 是标准 schema(ICASI),`ElementTree` 直解;一次性抓 192 文档 + 每月增量 1 文档。注意单文档大(峰值 10 MB,2020+ 平均 ~4 MB)。

### 2.2 Cisco PSIRT

**访问方式**
- 官方 openVuln API v2(需免费 CCO 账号 OAuth):`https://apix.cisco.com/security/advisories/v2/all`、`/year/{yyyy}`、`/severity/{SIR}`、`/latest/{n}`;JSON/XML;返回体附带 CVRF/CSAF 文件位置。实测无 token → 403("Authorization Header is either empty or not found in request")。
- **匿名替代路径(实测发现)**:
  - CVRF/CSAF 列表:`https://sec.cloudapps.cisco.com/security/center/cvrfListing.x`(200,22 KB)
  - 单通告 CSAF JSON 匿名直链(200,13.5 KB 样本):`https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/{slug}/csaf/{id}.json`
  - 通告列表 HTML:`https://tools.cisco.com/security/center/publicationListing.x`(200,7.6s,重定向到 sec.cloudapps)
- 官方建议 CSAF(CVRF 2023 年底已弃用,Cisco 官方原话:"Cisco recommends focusing on CSAF as CVRF will be phased out")。

**许可**:通告内容 © Cisco;API 使用需接受 **Cisco Baseline API Terms**(https://www.cisco.com/c/dam/en_us/about/doing_business/legal/supplemental-terms/Baseline-API-Terms.pdf)——**本网络对 www.cisco.com 全 403(Akamai 应用层拦截),原文无法取到,如实记录**;API 文档逐字(https://developer.cisco.com/docs/psirt/):"The Cisco PSIRT openVuln API is a RESTful API that allows customers to obtain Cisco Security Vulnerability information in different machine-consumable formats." **判断:无开放许可 → 项目决策**。

**规模估计**:openVuln 分页示例显示 2023 年 79 篇;近年(含 IR 通告)约 100–180 篇/年;1995 年至今总量约 2000–3500 篇;HTML 5–50 KB/篇。估 **5–15M tokens**。

**本机可达性实测**:apix 403(无 token,预期内);tools/sec.cloudapps 200 但慢(4–8s);www.cisco.com 403。无 TLS 拦截(连接层正常,是应用层 bot 拦截)。

**入库难度:中**。优先匿名 CSAF JSON(免注册、结构化);备选注册 API(限流:逐字 "5 calls per second / 30 calls per minute / 5000 calls per day",429 带 Retry-After)。列表页解析 + 下载 ~3000 文件。

### 2.3 Oracle Critical Patch Update

**访问方式**
- 索引:`https://www.oracle.com/security-alerts/`(curl.exe 实测 200,50 KB;含当季 + 归档链接)
- 季度 CPU 通告:`/security-alerts/bulletin{mon}{year}.html`(2021–2026 实测存在,如 `bulletinapr2026.html`);更早年份经归档页:`alertsarchive.html`(CVE 级 alert 2010–2020)、`sunalertslisting.html`(Sun Alert 历史)、`solarisbulletinsarchive.html`
- 无 API / 无 RSS(未发现);每篇 CPU 附带 PDF 版本链接。

**许可**:Oracle Web Sites Terms of Use(https://www.oracle.com/legal/terms/,已存样本 `docs/research/_oracle_terms_sample.html`),逐字:
> "The Site and Content provided on or through the Site are the intellectual property and copyrighted works of Oracle or a third party provider. All rights, title and interest not expressly granted with respect to the Site and Content provided on or through the Site are reserved."
**判断:未授予任何内容使用许可(all rights reserved)→ 项目决策**;与 MSRC/Cisco 同档(事实性厂商通告,行业普遍消费但无授权)。

**规模估计**:季度 CPU ~85 篇(2005–2026)+ 独立 CVE alert 数十至百余篇 + Solaris bulletin 归档;单篇 CPU HTML 100–500 KB(风险矩阵大表)。估 **2–6M tokens**。

**本机可达性实测(重要)**:Python urllib(OpenSSL)对 oracle.com **TLS 握手/读超时**(20–51s,多轮复现);**curl.exe(schannel)稳定 200,0.5–4s**。结论:非浏览器 TLS 指纹被干扰,入库必须走 curl.exe 或 .NET HttpClient。

**入库难度:中高**。索引→归档多级页面;CPU 正文为 HTML 风险矩阵表(产品×CVE×CVSS),解析工作量是 9 源中最大;PDF 备选解析更贵。

### 2.4 Google Project Zero

**访问方式**
- 博客:`https://googleprojectzero.blogspot.com/`(含 Atom feed `/feeds/posts/default`);issue tracker:`https://project-zero.issues.chromium.org/`;数据仓库(gitiles):`https://project-zero.googlesource.com/0day-in-the-wild/`
- **GitHub 镜像(本网络可达)**:`https://github.com/googleprojectzero/0days-in-the-wild`(组织下 27 个仓库:bochspwn、fuzzilli、TinyInst、winafl 等工具 + 0days-in-the-wild 数据集;工具类属代码层,uplift 红线另议)

**许可**
- 博客:未发现任何开放许可声明(本网络与 harness 双向取页均不可达,基于公开资料判断为默认版权保留)。
- **0days-in-the-wild 仓库:Apache License 2.0**(LICENSE 逐字确认:"Apache License Version 2.0, January 2004 … TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION"),覆盖 `_data`(0day 清单)与 `0day-RCAs/`(2019–2024 六个年度目录,P0 团队对在野 0day 的根因分析 writeup)——**P0 体系中唯一许可干净的部分**。

**规模估计**:博客 ~250–320 篇(2013–2026,估)≈ 0.8–1.2M tok;issue tracker ~3000+ 报告 ≈ 2–4M tok(两者本网络不可达);镜像数据 + RCA ≈ **0.3–1M tok(可达部分)**。

**本机可达性实测**:blogspot / googlesource / issues.chromium.org / web.archive.org 全部 **TCP 连接失败**(curl 与 urllib 双验证,21s 超时)——Google 系在本网络被 IP 级阻断,非临时抖动。api.github.com 稳定,github.com 间歇。

**入库难度**:博客/issue:本网络不可行;镜像仓库:低(git clone,但 github.com 间歇抖动需重试机制)。

### 2.5 CTFtime

**访问方式**
- API v1(https://ctftime.org/api/):仅 `events`、`teams`、`results`、`top` 等元数据端点(实测 `api/v1/events/?limit=1` 200,JSON);**无 writeup 端点**。
- writeup 托管页:`https://ctftime.org/writeup/{id}`(HTML)。实测 ID 25000–33500 均 200、35000 为 404 → ID 上界约 33–35k,扣除删除/空洞估 ~3 万篇。

**许可**
- 页脚逐字(实测 HTML):"© 2012 — 2026 CTFtime team. **All tasks and writeups are copyrighted by their respective authors.**"
- API 条款逐字:"This API is provided for data analysis and mobile applications only. You can not use this API to run CTFtime clones — most of the CTFtime data is moderated by humans, please, respect their time."
- **判断:writeup 版权归各作者,CTFtime 无权授予再使用许可 → C1 排除**。CTF writeup 语料如需要,应改为逐站采集有明确开放许可的战队博客/仓库(逐源核验,另行调研)。

**规模估计**:理论 15–75M tokens(不可用)。

**本机可达性实测**:全部 200(2–6s),无拦截。

**入库难度:高(且许可排除,不建议投入)**。

### 2.6 SANS Internet Storm Center diary(备选)

**访问方式**:归档 `https://isc.sans.edu/diaryarchive.html`(按年索引)→ 单篇 `/diary/{id}`(实测 200,37 KB HTML → ~4 KB 正文);RSS `https://isc.sans.edu/rssfeed.xml`(7.7 KB);API `https://isc.sans.edu/api/`(无 diary 列表端点,数据类 API 为主)。diary ID 从 100 到 33366 连续有效 → 总量 ~3 万篇(2001–2026)。

**许可**:逐字(API 页 "Proper Use of the API"):
> "If your lawyers ask, the data is provided using a Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) License."
linkback 页 Data Use License 补充:"Use of data premitted with attribution: SANS Technology Institute, Internet Storm Center, https://isc.sans.edu (you may feel free to change the format of the attribution according to your guidelines)."
(注:SANS 原文拼写 "premitted" 如此。)
**判断:NC(禁止商用)+ SA → 比项目已讨论的 CC-BY-SA(OWASP)更严,需项目决策**(docs/04 §5 第 2 条可挂接)。

**规模估计**:~3 万篇 × ~4 KB 正文 ≈ **25–35M tokens**。

**本机可达性实测**:全部 200(0.8–3.9s);官方要求自定义 UA(逐字:"We block some 'default' user-agents and follow the 'you have to be smart enough to set a custom user agent to use this API' rule.")。

**入库难度:低**(归档页→年索引→单篇,纯 HTML)。

### 2.7 Debian DSA(备选)

**访问方式**
- 年度索引:`https://lists.debian.org/debian-security-announce/{year}/`(MHonArc,实测 200)
- 单篇:`https://www.debian.org/security/{year}/dsa-{n}` **302 重定向**到 `https://lists.debian.org/debian-security-announce/{year}/msg{n}.html`(实测,正文即 DSA 邮件,~6.5 KB HTML)
- 结构化补充:`https://security-tracker.debian.org/tracker/`(200,1.2s,CVE↔包↔状态数据)
- 注意:`debian-lts-announce/`(DLA)归档实测 **403**(两次,不同 UA)——LTS 通告通道未核验通过,DSA 主路径可用。

**许可**:Debian WWW Pages License(https://www.debian.org/license)逐字:
> "Since 25 January 2012, the new material can be redistributed and/or modified under the terms of the MIT (Expat) License or, at your option, of the GNU General Public License; either version 2 of the License, or (at your option) any later version."
**判断:MIT/GPL-2+,训练语料可用,最干净的发行版通告源**。说明:DSA 正文经 lists.debian.org 投递,与 www.debian.org 同属 Debian/SPI 基础设施,实践上同源同条款(此为推断,已在 manifest notes 里注明)。

**规模估计**:实测年邮件数 2015:338 / 2020:232 / 2023:290 / 2024:255 / 2025:258(含少量非 DSA 通告);DSA 编号已至 5900+(2025);1997–2026 合计约 **5,900–6,300 篇**,2–4 KB/篇 → **3–6M tokens**。

**本机可达性实测**:www.debian.org 200 但慢(3–12s);lists.debian.org 200 快(1.5–2.5s);tracker 1.2s。

**入库难度:低**(单页 HTML 极简,`BeautifulSoup`/正则即可)。

### 2.8 Red Hat Security Advisories(备选)

**访问方式**
- CSAF v2 静态目录(主通道):`https://security.access.redhat.com/data/csaf/v2/advisories/{year}/`(Apache 目录列表,2001–2026 共 33 个年度目录;文件名 `rhsa-YYYY_NNNN.json`)
- RSS:`https://security.access.redhat.com/data/meta/v1/rhsa.rss`(近 3 天)
- 其他:OSV 镜像 `.../data/osv/all.json`(官方声明 OSV.dev 从此消费)、OVAL v2(维护模式将弃用)、Security Data API 文档 https://access.redhat.com/documentation/en-us/red_hat_security_data_api/

**许可**:官方 Security Data 页(https://access.redhat.com/security/data)逐字:
> "The data resources linked on this page as well as their alternative representations available through the Security Data API are licensed under the Creative Commons Attribution 4.0 International License. If you distribute this content or a modified version of it, you must provide attribution to Red Hat and provide a link to the original."
**判断:CC-BY 4.0,训练语料可用,manifest 记录署名义务即可。**

**规模估计**(目录实测:2005:269 / 2010:336 / 2015:619 / 2018:823 / 2021:1355 / 2023:2207(RHSA,另有 rhba 43 + rhea 16)/ 2024–2025 各 ≥1933 读样截断,推算 ~2000–2300):2001–2026 累计 **约 1.6–2.2 万条 RHSA**;单 CSAF JSON 50–300 KB(产品树占大头)→ 下载 ~1.5–3 GB;净文本(标题+严重度+CVE 描述+受影响包+修复)估 **20–40M tokens**。

**本机可达性实测**:目录与单文件全部 200,0.6–1.2s,无限流迹象(纯静态托管)。

**入库难度:最低**。目录列表→逐 JSON 下载→CSAF 标准 schema 解析。

### 2.9 GitHub Security Lab(备选)

**访问方式**
- 站点:`https://securitylab.github.com/`(实测 200;**官方提供 `llms.txt` 与 `/for-llms/` 页面**,逐字:"This page exists so AI systems can reference GitHub Security Lab's work accurately"——对语料工程极友好)
- Advisory 索引:`https://securitylab.github.com/advisories/`(实测页面含 **953 个 GHSL-YYYY-NNNN ID**:2020:286 / 2021:126 / 2022:85 / 2023:163 / 2024:197 / 2025:53 / 2026:43)
- 研究文章现址:`https://github.blog/security/`(实测 200)
- 源仓库:`github.com/github/securitylab`(根目录:CodeQL_Queries、Conferences、Fuzzing、**SecurityExploits**(22 个项目的深度漏洞研究)、docs;分支按 advisory 命名如 `chrome_3420`、`telerik`)

**许可**:仓库 `LICENSE.md` 逐字(MIT):
> "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software…"
**判断:MIT,干净**(站点与 advisories 内容随仓库分发)。github.blog 文章 © GitHub(无显式许可,作补充层时单独决策)。

**规模估计**:953 advisories(2–5 KB/篇)+ 站内研究内容 + 0days-in-the-wild(见 2.4)→ **1.5–3M tokens**。

**本机可达性实测**:securitylab.github.com / github.blog 全 200(0.5–4s);github.com **间歇**(200 与 connect-timeout 交替实测复现);raw.githubusercontent / codeload 阻断 → 内容抓取建议走 api.github.com contents API 或 html 页,git clone 需重试。

**入库难度:低中**。注意分层:advisories(通告文本)与站内研究文章入描述层;`SecurityExploits/` 深度利用研究建议按 docs/04 §0 红线推迟到 SFT 判断任务阶段评审。

---

## 3. 本网络环境画像(2026-09-24)

| 域 | 状态 | 说明 |
|---|---|---|
| api.msrc.microsoft.com / msrc.microsoft.com | ✅ 稳定快 | 无认证、无拦截 |
| security.access.redhat.com / access.redhat.com | ✅ 稳定快 | 静态托管 |
| lists.debian.org / security-tracker | ✅ 稳(www.debian.org 偏慢 3–12s) | DLA 归档 403 例外 |
| isc.sans.edu | ✅ 稳定 | 要求自定义 UA |
| ctftime.org | ✅ 稳定(2–6s) | — |
| tools.cisco.com / sec.cloudapps.cisco.com / apix.cisco.com | ✅ 可达(4–8s 慢) | www.cisco.com 403(Akamai 应用层) |
| oracle.com | ⚠️ **分 TLS 栈** | urllib/OpenSSL 超时;curl.exe/schannel 0.5–4s 稳定 |
| github.com / api.github.com | ⚠️ **间歇** | 同会话 200 与超时交替;raw/codeload 阻断(与前情一致) |
| Google 系(blogspot / googlesource / issues.chromium.org / web.archive.org) | ❌ TCP 不可连 | IP 级阻断,非抖动 |
| (前情)github codeload / api.osv.dev / ubuntu.com | ❌ TLS 重置 | 与本轮观察一致 |

**入库工程含义**:所有 fetcher 必须 ① 显式禁用系统代理;② 自定义 UA;③ curl.exe 子进程兜底 Oracle 类 schannel-only 站点;④ 对 github.com 做指数退避重试 + 断点续传;⑤ 限速 1–2 req/s(礼貌抓取)。

---

## 4. 对 C1 目标的影响(必须向上汇报的结论)

docs/04 §4 C1 缺口 ② 规划 "P1 描述层:厂商通告 ~100M + 研究 writeups ~200M"。本轮调研实测:

| 层 | 规划 | 实测可得 | 差距 |
|---|---|---|---|
| 厂商通告 | ~100M | 许可干净+可达:**Red Hat 20–40M + Debian 3–6M + GHSL advisories ~1M ≈ 25–47M**;若 MSRC/Oracle/Cisco/SANS 四源许可决策全通过,再加 42–96M → 理论上限 ~70–140M | 干净部分缺口 ~50M;决策依赖度高 |
| 研究 writeups | ~200M | GHSL 文章 + P0 镜像 ≈ **2–5M**(P0 博客/issue 网络阻断、CTFtime 许可排除、SANS 属 diary 不算 writeup 且 NC) | **缺口 ~195M,本清单内无解** |

**建议**:C1 缺口 ② 的 writeup 预算转移到 ① enwiki 回放层 / ④ arXiv 全历史摘要扩展(docs/04 已列的其他优先项),或另行调研开放许可的研究博客集合(Trail of Bits、PortSwigger 等未在本清单内,需新立项核验)。P1 描述层以"厂商通告 25–47M(干净)+ 决策源增量"的保守口径计入配比。

---

## 5. 推荐入库优先级排序

综合(许可清洁度 ≥ 规模 > 可达性 > 解析成本;许可不洁者一律排在"决策通过才可执行"档):

| 排名 | 来源 | 一句话理由 |
|---|---|---|
| **1** | **Red Hat CSAF v2** | 唯一"大规模 + 明示 CC-BY 4.0 + 静态免认证 + 标准 JSON"四项全满足的源,单源可顶 P1 厂商通告层半壁 |
| **2** | **Debian DSA** | MIT/GPL 双许可、体量小但稳、解析几乎零成本;与 Red Hat 形成"发行版通告"双子星 |
| **3** | **GHSL(+P0 0days-in-the-wild 捆绑)** | MIT/Apache 全干净、研究写作质量高、官方自带 llms.txt;规模小但单位 token 价值最高的 writeup 层 |
| 4 | MSRC CVRF v3.0 | 免 key 大宗结构化数据,唯一阻碍是无声明的许可(决策通过即可升至第 2 档执行) |
| 5 | SANS ISC diary | 25–35M 规模诱人、解析容易,但 CC BY-NC-SA 的 NC 门槛必须先过项目决策 |
| 6 | Oracle CPU | 许可 all-rights-reserved + 仅 curl.exe 可达 + HTML 大表解析最贵,三重成本 |
| 7 | Cisco PSIRT | 匿名 CSAF 通路已验证,但条款原文在本网络不可核验(风险不可量化),排后 |
| ✗ | CTFtime | writeup 版权归各作者,无再许可权,排除 |
| ✗ | Project Zero 博客/issue | 本网络 Google 系全阻断;仅 GitHub 镜像数据(Apache 2.0)并入第 3 名执行 |

---

## 6. 前 3 名入库方案草案

### 方案 1:redhat-csaf(P1 第一优先)

- **endpoint**:`https://security.access.redhat.com/data/csaf/v2/advisories/{year}/`(year ∈ 2001–2026,先 GET 目录页 33 次)
- **分页**:无(静态目录全量列出);单文件 `rhsa-YYYY_NNNN.json` 逐个 GET
- **过滤**:`rhba-`/`rhea-` 前缀丢弃(仅保留 `rhsa-`,实测 2023 年 2275 文件中 RHSA 占 2207)
- **调度**:静态站实测 0.6s/req;2 并发 + 1.5s 间隔 → ~2 万文件约 4–6 小时;支持断点续传(按文件名落盘幂等)
- **文本化**:CSAF JSON → 每条 RHSA 一文档:`{title} | severity | per-CVE(CVE-ID、CVSS、description)| affected packages(去重产品树)| fixed-in | references`;产品树仅保留 包名+版本区间,丢弃重复 CPE 展开行
- **预估代码量**:fetcher ~120 行 + CSAF→doc 转换 ~80 行(复用 `scripts/fetch_c0.py` 管线与 manifest 登记),预计 0.5 天
- **产出预估**:~1.6–2.2 万 docs / **20–40M tokens**;manifest license 记 `CC-BY-4.0(需署名 Red Hat + 原链)`

### 方案 2:debian-dsa

- **endpoint**:年度索引 `https://lists.debian.org/debian-security-announce/{year}/`(1997–2026,30 页)→ 逐 `msg*.html` 链接单篇抓取(~6 KB/篇)
- **分页**:无(MHonArc 年度页全量列出)
- **调度**:lists.debian.org 实测 1.5–2.5s/req,串行 1 req/s 即可,~7000 页约 2–3 小时;注意 UA 用全称(短 UA 在 DLA 上实测 403,DSA 未复现但保持一致)
- **文本化**:MHonArc HTML → 去头部导航/邮件尾注,保留 DSA 标题、正文(受影响包、漏洞描述、CVE 引用、修复版本);`X-Subject` 注释行可直接取标题
- **扩展项**:`security-tracker.debian.org` 结构化 CVE 数据可作为第二源(同域、同基础设施)
- **预估代码量**:~150 行,预计 0.5 天
- **产出预估**:~6000 docs / **3–6M tokens**;manifest license 记 `MIT-Expat OR GPL-2+ (Debian WWW Pages License)`

### 方案 3:ghsl-advisories + p0-0days(捆绑)

- **endpoint A(GHSL advisories)**:`https://securitylab.github.com/advisories/` 索引页解析出 953 个 `GHSL-YYYY-NNNN` → 逐 advisory 页(或仓库 `github.com/github/securitylab` 对应分支,经 api.github.com contents 逐文件取 markdown,避开间歇的 raw/codeload)
- **endpoint B(P0 镜像)**:`https://api.github.com/repos/googleprojectzero/0days-in-the-wild/contents/{_data,0day-RCAs/2019..2024}`(JSON base64);或 git clone(带 3 次指数退避重试,github.com 间歇可达)
- **分页**:advisories 索引页单页全量;api.github.com contents 每目录 ≤1000 文件单次
- **调度**:api.github.com 未认证限 60 req/h → 每小时窗口内完成,或配置 GITHUB_TOKEN 提到 5000/h;~1200–1500 请求,1–2 小时(带 token)
- **文本化**:GHSL advisory markdown/HTML → 保留标题、产品、严重度、描述、PoC 摘要描述(仅描述,PoC 代码块剔除——遵守 §0 描述层红线)、时间线、参考;0days `_data` JSON → 每条 0day 事件一行结构化记录;`0day-RCAs/*.md` 全文保留(根因分析叙事)
- **内容红线执行**:`github/securitylab` 的 `SecurityExploits/` 目录(22 个项目深度利用研究)**不进 Stage 1**,登记为 SFT 判断任务阶段候选
- **预估代码量**:~250 行,预计 1 天
- **产出预估**:~1100–1300 docs / **2–5M tokens**;manifest license 记 `MIT (github/securitylab)` + `Apache-2.0 (0days-in-the-wild)`

---

## 附:证据文件索引

| 文件 | 内容 |
|---|---|
| `scripts/probe_p1_reachability.py`、`probe_p1_round2~8.py` | 全部探测脚本(可复现) |
| `docs/research/_p1_probe_results.json` | 第一轮 25 端点原始结果 |
| `docs/research/_oracle_terms_sample.html` | Oracle 条款页存证(56.9 KB,许可逐字句出处) |
| `docs/research/_oracle_alerts_index_sample.html` / `_oracle_archive_index.html` | Oracle 通告索引样本(链接结构核验) |
| `docs/research/_oracle_cpu_sample.txt` | Oracle 通告正文文本样本 |
