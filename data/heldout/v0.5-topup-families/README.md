# `v0.5-topup-families` —— C 路 top-up 的**在分布能力观测仪**（不是泛化测试集）

## 这套东西是什么

回答一个很窄的问题：**e1/e2 这次低学习率 few-step top-up，到底有没有真把 S1 三族
（T2 机理 / T15 文档结构 / T9 钓鱼扩样）学进去。**
`reports/c-path-topup-preregistration.md` §3 的观测项要求：即使主判据通过，只要这三族
自评无改善，top-up 就是"防伪通过"的假通过。本目录就是那一项的观测工具。

**定位必须说清楚：**

* 这是**同分布**能力观测（in-distribution capability observation），不是泛化证据。
  行文措辞、载体、任务骨架都刻意贴着训练契约走，唯一被换掉的是**措辞、载荷位置、
  具体载体**。它能回答"这三族的模板有没有被记住"，**不能**回答：
  * 换到训练分布之外的载体/语言/结构还灵不灵（→ 那要 `data/heldout/` 的正式留出集）；
  * 模型的拒绝边界是否被 top-up 削弱（→ 要专门的越狱/过度拒绝集）；
  * T2 之外的机理族、T15/T9 之外的第三族是否被这次 top-up 影响（→ 要回归集）；
  * 自评改善是否等于线上收益（→ 要人工/独立评审）。
* 它**永不进入训练**。`data/sft/**`、`data/lf/**` 的任何混料脚本都不得引用本目录；
  本目录不参与 `check_topup_mix.py` 的配比，也不在 `gen_*` 训练数据生成器的输入里。

## 组成

| 文件 | 族 | 行数 | 负例 | 政策包 | zh/en | 不同载体/机理/借口 |
|---|---|---|---|---|---|---|
| `t2_mechanism.jsonl` | T2 机理问答 | 28 | 9 (32.1%) | 9/10/9 | 14/14 | 16（10 个新机理 + 6 个良性对照） |
| `doc_structure.jsonl` | T15 文档结构注入 | 27 | 9 (33.3%) | 9/10/8 | 13/14 | 21（12 个新落点 + 9 个良性对照） |
| `t9_phish.jsonl` | T9 钓鱼扩样 | 30 | 9 (30.0%) | 10/10/10 | 17/13 | 19（9 个新借口 + 5 良性 + 4 硬负 + 1 政策三元组载体） |
| 合计 | | **85** | 27 (31.8%) | 28/30/27 | 44/41 | 56 |

负例口径（按族定义，`scripts/check_topup_family_probe.py` 硬断言）：

* **T2**：`id` 语义段 ∈ {`neg`（良性对照机理）, `poln`（政策条件化良性）} → 9/28；
* **T15**：参考裁定 = `clean` → 9/27；
* **T9**：参考裁定 = `benign`（含 4 行"看着像但确实良性"的硬负）→ 9/30。

## schema 逐字一致 / 训练不重叠：怎么做到的、怎么验的

`schema` 沿用 m1 契约：5 个顶层键 `{id, task, pack, lang, messages}`，`messages` 为
system/user/assistant 三段；assistant 以 `VERDICT: {...}` 收尾，键序
`action, verdict, confidence, findings, policy`，且 `policy == pack`。三族 system
串**从训练文件按 (族, 包, 语言) 原样读入**，构造上即逐字一致（不是手抄）。

新意（novelty）体现在三处，而不是同义词替换：

1. **新机理 / 新落点 / 新借口**：T2 的 10 个机理（如 `xxe_entity`、`jwt_alg_confusion`、
   `cache_key_poisoning`、`prototype_pollution`）不在训练机理词表里；T15 的 12 个落点
   （`watermark`、`chart_alt`、`doc_props`、`link_tip` …）不在训练落点里；T9 的
   `task` 语法为 `T9-phish:<渠道>:<技法>:<标签>`，渠道/标签取自训练词表，**技法是新
   词元**（训练技法不得复现）。
2. **新措辞**：三族的用户文本全部重写，与训练侧不共享任何 8-gram 连续同文（见下）。
3. **载荷位置**：T15 的注入指令落在新的可见槽位；T9 的收割动作落在新的表单/字段组合
   （`pay_pin` / `pay_code` / `staff_id` / `passcode` / `scope_read` …），不是训练里
   `sms_code` 那一套。

**训练不重叠（train-disjoint）判定**：复用 `scripts/check_sft_contamination.py` 的
官方口径（`NGRAM_N=8`、`normalize()`、`ngrams()`），并把它收紧成 6 条硬闸（非零退出）：

| 闸 | 内容 |
|---|---|
| C1 | 与同族同语言训练 user 文本**精确同文** = 0 |
| C2 | 去掉 schema 行/注解/属性值后，**内容级 8-gram 命中 = 0** |
| C3 | 内容级**最长连续共享游程 < 8 gram**（< 15 字符连续同文） |
| C3b | 计入 schema 词元后的最长连续共享游程 < 20 gram（< 27 字符），仍远低于官方匹配器 40 gram 预筛 / 60 字符 LCS 判据 |
| C4 | **载荷区**（T15 `<body>` 可见行与 `text:`、T9 `<dom>` 文本节点与 `action/name/id` 取值、T2 全文）8-gram 命中 = 0 |
| C5 | 探针里出现的**任何主机名**不得在同族训练 user 文本中出现 |
| C6 | **身份型 meta 取值**（filename/title/created/modified/size-bytes/producer/url/fetched）与链接必须**新**；**闭合词表 meta**（detected-container/macros/javascript/pdf-version）取值必须落在训练值域内，其余枚举型键取值**形状类**须与训练一致 |

schema/自撰的切分规则（机械化、非人工豁免）：行级（该行在同族同语言训练里 ≥2 行逐字出现
⇒ schema 行；`^<metakey>: …` 且键 ∈ 训练 meta 词表；`macro-stream [` 行；操作者
`（文件编号|document ref） trace-id:` 行）、注解级（`[collects: …]`、`[sensitive-input]`）、
属性级（`attr="…"` 取值）、gram 级（在训练侧 ≥5 行出现的 gram 记为 schema 词元）。

同时断言：**跨留出集零重叠**（id 与 user 文本都不与 `v0.2.1` / `v0.3-gen` /
`v0.4-toolout` 相撞）、**政策条件化三元组**（同一段 user 文本 × 三包，只有 system 政策
行不同）三族各 ≥1 组（实际 5 组）、**虚构性**（所有域名 ∈ `example.com` /
`*.attacker.example` / RFC2606 保留域，IP ∈ RFC5737 `198.51.100.0/24`）。

## 已知弱点（读报告前请先读这一节）

* **T2 是最弱的一族。** 训练侧 T2 语料是**按子类模板批量生成**的，因此"在训练侧 ≥5 行
  出现的 gram"对 T2 来说包含不少常见短语片段。T2 探针与训练侧共享 406 次 8-gram（181 个
  不同 gram）**全部**是这类 ≥5 行片段；换句话说 T2 的"零内容命中"依赖这条豁免规则，真正
  不依赖任何规则的数字是 **C3b：最长连续同文 15 字符**。判读 T2 时应以 C3b 为主。
* T15/T9 的 C2 豁免基本只吃 schema 骨架（`<input `、` action="`、` [name: `、
  `] [visibility: visible]` 之类），自撰载荷全部落在 C4=0，且 C3b 上限 24/18 字符。
* "同一机理、换措辞"本身可能被模型当成近邻样本：**这套探针的分数是上限，不是下限。**
* 单族 27–30 行，只能看**方向**（有/无改善、三族是否梯度一致），不能做显著性检验；
  建议按"三族里至少两族出现同向改善"读，而不是逐族卡阈值。
* 探针只覆盖 e1/e2 这次的 S1 三族；`t9_phishing.jsonl`(50 行) 那条底座没有单独覆盖。

## 复现

```powershell
python scripts\gen_topup_family_probe.py          # 重新生成三个 jsonl（确定性，无随机）
python scripts\check_topup_family_probe.py        # 全硬闸；PASS 时退出码 0
python -m pytest tests\test_topup_family_probe.py -q
```

统计快照：`reports/topup-family-probe-stats.json`（含每条闸门的原始计数、最长同文游程
及其所在行、schema 行/gram 剔除明细）。
