# CC-BY-SA 先例调研 + 署名合规方案草案（D3 最大单点：wiki 簇占 C1 60%）

> 调研日 2026-09-25（机器时钟口径）· 调研人：C2/语料 agent · 任务来源：父会话（用户选 A）
> 姊妹文档：`docs/research/d3-ledger-memo.md`（全量 D3 台账，本文展开其最大单点）
> 方法：一手来源优先（许可证原文/数据卡原文逐字），二手标注可信度；本网络实测通路
> （CC 官网直连 200、hf-mirror 200、arXiv API 200、texaslawreview.org 200）。
> **未核实项一律标注，不编造。**

---

## 1. 法律地形

### 1.1 BY-SA 4.0 法条关键文本（官方 legalcode 逐字，creativecommons.org/licenses/by-sa/4.0/legalcode，2026-09-25 抓取）

**Section 1 – Definitions（Adaptation 定义）**：

> "Adapted Material means material subject to Copyright and Similar Rights that is derived from or based upon the Licensed Material and in which the Licensed Material is translated, altered, arranged, transformed, or otherwise modified **in a manner requiring permission under the Copyright and Similar Rights held by the Licensor**."

**结构读法**：SA 义务的触发链是三段式——
1. **复制训练语料**：训练必然复制作品 → 是否需要许可取决于法域例外（见 1.3）；
2. **Adapted Material 成立**：必须同时满足"derived from or based upon"（事实因果）**和**"modified in a manner **requiring permission**"（法律评价）——**"需要许可的修改"是定义的内嵌条件**，不是"任何因果派生"；
3. **Share（公开分享）触发 3a/3b**：SA 条款只在"公开分享 Adapted Material"时生效——**不分享演绎作品 = SA 不触发**。

**Section 2(a)(4) 逐字**（技术修改豁免）：

> "For purposes of this Public License, simply making modifications authorized by this Section 2(a)(4) never produces Adapted Material."

**Exceptions and Limitations 条款逐字**：

> "For the avoidance of doubt, where Exceptions and Limitations apply to Your use, this Public License does not apply, and You do not need to comply with its terms and conditions."

——即：若训练复制落入法定例外（fair use / TDM 例外等），**整份许可证根本不适用**，更遑论 SA。

### 1.2 核心未决问题：模型权重是否构成语料的演绎作品

| 来源 | 立场 | 关键原文/论点 | 可信度 |
|---|---|---|---|
| **CC 官方《Using CC-licensed Works for AI Training》**（2025-05，CC BY 4.0）creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf | 承认多数情形非演绎作品；给保守合规路径 | "in many cases, neither the AI model nor its outputs would be considered to be derivative works of training data under copyright law"；SA 触发条件 "triggered only upon public sharing of the original work or an adaptation of it"；保守路径 "model outputs and the model itself, if shared publicly, should be made available under the same CC license"（自注："almost certainly lead to overcompliance"） | **高**（许可方官方，但明确声明不构成法律意见、不站队） |
| **IViR（阿姆斯特丹信息法研究所）《Share-Alike and Machine Learning》**（Quintais/Senftleben 等，39 页）ivir.nl/publicaties/download/Share-Alike-and-ML.pdf | 五阶段分析：stage-5 模型产物与 CLSA 义务断链 | "with the creation of the stage five artefact, the link with CLSA obligations is broken and copyright is no longer available as a tool to enforce CLSA conditions"——前提是产物不含受保护痕迹；残余风险 = 记忆化（"difficult to prove that protected traces … made their way into the trained model"）；另指出 CJEU 与加拿大最高法院在中间复制问题上的分歧 | **高**（版权法专业研究所，欧盟法视角） |
| **McCabe《Shadow Derivatives》**（Texas Law Review Online Vol.104, 2026）texaslawreview.org/wp-content/uploads/2026/04/Pub-McCabe-Shadow-Derivatives.pdf | 权重落在法定演绎作品范畴**之外** | "Model weights, embeddings, and internal parameter updates do not recast expressive content in any recognizable sense. They are internal system states that enable prediction and generation. While they may be causally influenced by training data, they do not embody expres[sion]"；提出"contractual derivatives"（合同而非法定创设的衍生财产）才是训练语料 ToS 的实际效力来源 | **中高**（学术发表，美国法视角，单作者立场性论文） |
| **美国版权局生成式 AI 训练报告**（2025 预发布版，经 Jenner & Block 客户摘要转引） | 训练复制行为在美国法下分析复杂、未一刀切 | 报告确认训练涉及复制、例外分析因案而异（转引摘要，报告原文未直接核验——**未核实**） | 中（二手转引） |

**各法域快照**（CC 官方文件逐字归纳）：日本——训练所需复制落入例外**不需许可**；欧盟——TDM 例外但权利人可 opt-out；英澳——例外窄（英国仅非商业科研 TDM）；美国——fair use 逐案。**中国大陆：无一般 TDM 例外**（《著作权法》2020 修正第 24 条合理使用为封闭列举；此为 agent 知识，**未在线核实，法务确认项**）——训练复制行为的许可需求在 CN 法下更不确定，但这是全部语料的共性问题（非 SA 特有）；"权重是否演绎作品"在 CN 法下同样未决。

### 1.3 小结：SA 的真实风险面

法条结构 + 三方文献指向同一结论：**SA 义务成立需要连过三关**（复制无例外 → 权重构成"需许可的修改" → 公开分享）——每关在主流法域下对 LLM 权重都存在实质抗辩。风险主要来自：①记忆化（权重确实存储了表达——IViR 指出的残余风险）；②CN 法域训练复制本身的许可问题（独立于 SA）；③合同路径（语料 ToS 明示禁训练条款时，绕开版权分析直接违约——我们 wiki 语料来自官方 dump，无此类合同条款，风险低）。

---

## 2. 先例清单（开放权重模型 × CC-BY-SA 重度语料的实务处理）

| 模型/数据集 | 训练数据许可构成 | 发布许可证 | 署名实践 | SA 合规立场声明 |
|---|---|---|---|---|
| **RedPajama-Data-1T**（Together，2023-04；LLaMA 配方复现） | 1.2T = CommonCrawl 878B + C4 175B + GitHub 59B（仅 MIT/BSD/Apache 项目）+ ArXiv 28B + **Wikipedia 24B**（HF wikipedia 2023-03-20 dump，20 语言）+ StackExchange 20B | **无统一许可** | 数据卡 License 节逐字："**Please refer to the licenses of the data subsets you use**" + 逐子集链接（Wikipedia → HF 数据卡 licensing-information 页、CC → CommonCrawl ToU…）——**指针式署名** | 无（不声明权重 SA 合规，也不否认；纯指针实践） |
| **Dolma v1.7 / OLMo 7B**（AI2，2024-04） | 2.3T tokens，含 **Wikipedia & Wikibooks 16.2GB**（v1.6 起 200% epoch） | 数据集 **ODC-BY**（数据库层署名许可，2024-04-15 从旧许可切换）+ 逐字："By using this dataset, you are also bound [by] any license agreements and terms of use of the original data sources"；**OLMo 权重 Apache-2.0** | 数据卡明示源级许可传递义务（内容层）+ 数据库层 ODC-BY 署名；PII 移除表单 | 无 SA 传播主张；权重照常 Apache-2.0 |
| **RefinedWeb / Falcon**（TII，2023） | **Web-only**（论文摘要逐字 "Outperforming Curated Corpora with Web Data, and Web Data Only"）——过滤 CommonCrawl，设计上就少用 curated 语料（wiki 占比低） | Falcon-40B 权重 2023-05 起 Apache-2.0（**未在线核实**，通用认知）；RefinedWeb 数据卡本网络 401 门控（**许可细节未核实**） | 论文级描述 | 对照例：用语料设计绕开 SA 问题 |
| **Qwen3-0.6B-Base**（Alibaba，2025——**本项目底座血统**，快照对应模型卡 2026-09-25 抓取） | 36T tokens / 119 语言（卡面描述："coding, STEM, reasoning, book, multilingual, and synthetic data"）——**119 语言的多语覆盖几乎必然含 Wikipedia，但官方未列来源清单** | **Apache-2.0**（卡片 front-matter 逐字 `license: apache-2.0`） | **零语料署名、零来源披露、零许可说明**——数据构成只到类目级 | 无任何 SA 相关声明 |

**先例结论**：四个主流开放权重实践中，**0/4 采取"权重按 SA 发布"**；2/4（RedPajama/Dolma）采取数据卡指针式署名（≈档位 a）；2/4（RefinedWeb/Qwen）甚至不做语料级署名。**没有任何主流模型把 CC-BY-SA 语料的 SA 条款传播到权重许可上**。我们的底座 Qwen3 本身就是 Apache-2.0 发布、含 wiki 血统、零披露——若我们对 C1 采取比上游更严的立场，将出现"底座比衍生模型披露更少"的倒挂。

来源：hf-mirror.com/datasets/togethercomputer/RedPajama-Data-1T/raw/main/README.md · hf-mirror.com/datasets/allenai/dolma/raw/main/README.md · arxiv.org/abs/2306.01116（RefinedWeb 论文） · hf-mirror.com/Qwen/Qwen3-0.6B-Base/raw/main/README.md（含 `license: apache-2.0` 与 "36 trillion tokens across 119 languages" 原文） · Qwen3 Technical Report arXiv:2505.09388。

---

## 3. 合规选项三档

### 档 (a) 发布附署名数据卡（RedPajama/Dolma 式）——**主流做法**

- **操作清单**：①模型卡数据节逐源列 tokens/许可证/来源 URL（`manifest.jsonl` 直接机器生成——47 源已有逐字许可与规模）；②按 CC 保守指南的 attribution 形式（官方例句逐字："Training data from the LAION dataset [link]"——我们版："Training data includes Chinese/English Wikipedia (CC BY-SA 4.0, dumps.wikimedia.org) …"）；③源级许可传递提示（Dolma 式："users are also bound by the licenses of the original sources"——**这是给我们下游用户的提示，不是我们对上游的义务**）；④Wikipedia/Wikimedia 商标使用注意（"Wikipedia" 名称与 logo 是维基媒体商标——模型卡描述性使用 OK，避免暗示背书）。
- **成本**：~0（文档工作，manifest 已备）。
- **风险**：若法务最终采纳"权重=演绎作品"读法，署名不能替代 SA 义务——残余风险=法务问题本身，非本档操作缺陷。

### 档 (b) 保守解释：权重按 SA 发布（CC 保守指南路径）

- **法源**：CC 官方保守指南逐字（§1.2 表）——"the model itself, if shared publicly, should be made available under the same CC license"（CC 自注此路径 "almost certainly lead to overcompliance"）。
- **操作清单**：权重与模型输出以 CC BY-SA 4.0 发布；与底座 Apache-2.0 的许可声明关系需要法务设计（Apache-2.0 与 CC BY-SA 4.0 无兼容性声明——CC 官网 compatiblelicenses 清单只认 GPL 系）。
- **成本**：许可声明混乱 + 生态收窄（下游商用/集成顾虑 SA 传染）。
- **风险**：无先例支撑（§2 四实践 0/4）；**过度合规的自主加责**——CC 官方自己都不要求。
- **结论：不推荐，仅记录该立场存在。**

### 档 (c) 剥离 wiki 层重训（>35h，D3 备忘已估）

- **操作清单**：build_c1_mix 删 enwiki/zhwiki 行 → 新通用回放源设计与配比 → C1-full 35h 重训 → 基线重验（sec PPL -25% 门禁）→ M1.5/M2 全链重跑。
- **成本**：>35h GPU + 通用域新源调研（回放质量决定 general_en/zh 门禁成败）+ **zhwiki-sec 5.5M 是安全域有效成分**（zh 安全域天然稀缺——docs/04 §5.1 实测全 zhwiki 安全树仅 5.5M，剥离后 zh 安全语料近乎归零）。
- **风险**：技术代价最大且解决的是法务未决问题；**仅在法务明确否决 (a)/(b) 时触发**。
- **副作用警示**：enwiki 529M 占 C1 的 48.6%——替代源若质量不足，通用域 PPL 门禁（回升 ≤10%）与 32k 长上下文可能全面失守。

---

## 4. 建议（结合项目实际）

**项目参数**：CN 法域（无一般 TDM 例外，训练复制许可问题独立存在）· Apache-2.0 意向（继承底座 Qwen3 惯例）· wiki 占 C1 有效 60%（enwiki 529M + zhwiki 124.3M + zhwiki-sec 5.5M）· 底座本身即"Apache-2.0 + wiki 血统 + 零披露"先例。

**推荐：档 (a) 署名数据卡为主 + 记忆化缓解动作 + 档 (c) 保留为法务否决预案；不采 (b)。**

理由：①法条三关结构（§1.1）+ 三方文献（§1.2）+ 4/4 先例（§2）同向支持"权重非演绎作品"为主流读法；②CC 官方自己标注保守路径是过度合规；③我们的管线已有两大天然缓解：**全局 md5 去重**（docs/04 §4 管线要点，降低逐字记忆化密度）与**探针/needle 评估体系**（可复用做发布前抽取审计）；④比上游 Qwen 更严的披露（逐源 manifest）反而把我们的发布实践做到先例清单最严谨档。

**前置动作清单（M5 发布评审前完成）**：
1. **法务两问**（**待用户发起**——法务触达是用户侧动作，工程侧不可代办；一次问清，覆盖全台账）：① CN 法下训练复制受版权语料是否需要逐源许可（合理使用边界）？② 模型权重是否可能被认定为语料的演绎作品（触发 SA）？——②若答"否"或"低风险"，档 (a) 定案；若答"是"，触发档 (c) 预案
2. **记忆化审计**（发布前，GPU 空闲期）：用现有探针体系对 C1-full/m15 checkpoint 跑 wiki 高频句抽取测试（前缀补全 → 与训练原文比对），量化记忆化率，写入模型卡——对应 IViR 指出的唯一残余风险
3. **数据卡生成脚本**：manifest.jsonl → 模型卡数据节 markdown（逐源 tokens/许可/URL，机器生成零手误），与 README 发布流程挂钩——**✅ 已落地（2026-09-25）：`scripts/gen_datacard.py` → `MODEL_DATA_CARD.md`，sha256 语料态锁定 + 7 项单测（含 manifest-TIER_MAP 漂移守卫）**
4. **商标注意项**：模型卡避免 Wikipedia/Wikimedia 商标暗示背门（描述性使用 + 指向 dumps.wikimedia.org）
5. **时序**：①②与 C1-full 完成解耦——先跑评估链拿 PPL 结果，法务答复落地前不发布权重即可（受控发布是默认态，开放权重是 D3 决议后的主动动作）

**风险声明**：本调研为工程侧弹药整合，不构成法律意见；1.2 表中"未核实"项与 CN 法域知识缺口已标注，法务确认前不得将档 (a) 视为定论。

---

## 附：本调研抓取的证据文件（临时目录，关键文本已录入本文）

| 文件 | 内容 | 来源 |
|---|---|---|
| `%TEMP%\by-sa-40.html` | BY-SA 4.0 官方 legalcode 全文 | creativecommons.org/licenses/by-sa/4.0/legalcode |
| `%TEMP%\cc-ai-training.pdf/.txt` | CC 官方 AI 训练立场文件（3 页全文） | creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf |
| `%TEMP%\ivir-sharealike-ml.pdf/.txt` | IViR ShareAlike×ML 研究（39 页） | ivir.nl/publicaties/download/Share-Alike-and-ML.pdf |
| `%TEMP%\shadow-derivatives.pdf/.txt` | Shadow Derivatives（36 页） | texaslawreview.org/wp-content/uploads/2026/04/Pub-McCabe-Shadow-Derivatives.pdf |
| `%TEMP%\redpajama-card.md` / `dolma-card.md` / `qwen3-06b-card.md` | 三张数据/模型卡原文 | hf-mirror.com（URL 见 §2） |
