# Jev（TypeSafe System One 模型）探索报告

> 版本 v0.1 · 状态：外部技术调研笔记。
> 主题：Jev 是什么、怎么用、网络结构、训练方法，以及它对本项目（安全感知 LLM）的启示。
> 调研时间：2026-09。官方未公开权重与完整架构，本文严格区分「官方披露」「权威推断」「社区复现」三类信息，来源见 §6。

---

## 0. TL;DR

- **Jev 是 TypeSafe AI 于 2026-09-15 发布的第一个 "System One 模型"**：输入一段 state（状态）＋一组带类型的问题，输出**结构化决策＋校准概率分布**，完全不生成文本。创始人是 RLHF 共同发明人、前 OpenAI 研究员 Diogo Almeida；公司结束两年隐身，同时宣布 DCVC 领投的 4000 万美元种子轮。
- **使用方法**：三个提问原语——Noul（是非概率）、Choice（2–255 选项多选一）、Score（2–10 档打分）；一次请求可混用任意多个问题，并行评估，问 1 个和问 10 个的延迟几乎相同。接入方式：Playground、HTTP API（`POST /v1/systemone`）、Python/JS SDK、coding agent 技能包、Vercel/Cloudflare 第三方网关。
- **网络结构**（官方未公开，属推断＋复现佐证）：大概率是**小型编码器式骨干（类似 ModernBERT）＋专用决策头**，彻底去掉自回归解码——单次前向传播直接输出概率分布；多问题共享同一份 state 的处理（共享前缀／KV 复用）。
- **训练方法**：官方命名为 **RLCD（校准决策强化学习）**——与 RLHF（人类偏好）、RLVR（可验证奖励）并列的第三条后训练路线。最可能的技术基础是 RLCR 论文（arXiv:2507.16806）：奖励 = 正确性 + **Brier 分数**，有界真值评分规则可证明地同时产生「准确且校准」的模型。校准的含义：模型说 0.8，同类判断长期看约 80% 正确。
- **对本项目**：Jev 的「state 进、类型化分布出」与我们的判断函数 J : X × C → Δ(A) 高度同构；其置信度路由、fail-open/fail-closed 参数化与我们 §8.4 的操作点思想一致；但其无解释性、OOD 过自信风险在安全对抗场景（§7）下必须显式管理。

---

## 1. Jev 是什么

### 1.1 基本事实

| 项 | 内容 |
|---|---|
| 发布方 | TypeSafe AI（创始人 Diogo Almeida：RLHF 共同发明人，曾在 OpenAI 参与 InstructGPT、ChatGPT、GPT-4） |
| 发布时间 | 2026-09-15（结束两年隐身；DCVC 领投 4000 万美元种子轮） |
| 名字来源 | 杰文斯悖论（Jevons paradox）：效率越高 → 用量越大。Diogo 的野心是当单次决策成本趋近于零，工程师会在代码每个角落布满 AI 决策节点 |
| 模型类别 | "System One Model"（系统一模型），取自卡尼曼《思考，快与慢》：System 1 = 快直觉判断，System 2 = 慢深思推理。传统 LLM 是 System 2，Jev 补的是 System 1 |
| 核心契约 | **state 进，带类型的决策出**：不写回复、不产代码、不解释推理；只返回决策值 + 概率分布 + 置信度 |
| 输入模态 | 仅文本（字符串、JSON 对象、文本数组）；图片/音频/视频暂不支持 |
| 官方口号 | "Machine Native Intelligence"：结构、可靠、可观测、可测试、快速、一致、低成本——为 AI-to-AI / AI-to-software 交互设计，赌的是未来 99% 的调用是机器对机器 |

### 1.2 与传统 LLM 的区别

| 维度 | 传统 LLM（GPT/Claude/DeepSeek） | Jev |
|---|---|---|
| 输出方式 | 生成文字，需要解析 | 直接返回结构化决策结果 |
| 响应速度 | 数秒到数百秒 | 70–500 毫秒 |
| 输入价格 | $0.20–$10 / 百万 token | $0.042 / 百万 token（输出免费） |
| 结构化输出错误率 | 0.58%–45.5% | 0%（输出形状由数学结构保证） |
| 概率语义 | 文本里的形容词（"我很确定"） | 校准过的数值（0.8 ⇒ 长期约 80% 正确） |
| 在系统中的角色 | 顾问／对话者／规划者（外循环） | 智能的 if 语句（内循环） |

一句话：**Jev 把「判断」从生成式 AI 的能力捆绑包里单独拆出来卖**（投资人 Jaya Gupta 称之为「智能大拆分」/ "decoder tax" 的解除）。

---

## 2. 使用方法

### 2.1 三种提问原语（AI Primitives）

所有问题都挂在一份 `state`（想让它分析的上下文：一段工单、一封邮件、一个 JSON 状态）上：

| 原语 | 回答的问题 | 返回形状 | 要点 |
|---|---|---|---|
| **Noul** | 是/非判断 | `noul: 0.95`（0–1 概率） | 没有单独 confidence 字段——概率本身就是答案。近 0.5 是「是非各半」，**不是「中等」**；要衡量程度用 Score |
| **Choice** | 多选一（2–255 项） | `choice` + `probabilities`（各选项概率，和为 1）+ `confidence` | 选项由你在 `criteria` 里动态定义；务必留一个「其他/以上都不是」，否则模型被迫在错的选项里挑 |
| **Score** | 在你描述的 2–10 档量表上打分 | `score`（可为小数，如 1.04）+ `legend` + `probabilities` + `confidence` | 档位要**写情形不要写程度**（「功能坏了但有绕行方案」✔，「中等严重」✘）；每档独立判断，模型看不到档位编号 |

**关键性质**：三种原语可在一次请求里混用；每个问题对同一份 state **独立评估、并行执行**；加问题几乎不增加响应时间，只多一点输入 token。

### 2.2 请求/响应形状（HTTP API）

```jsonc
// POST https://api.typesafe.ai/v1/systemone
// Authorization: Bearer $TYPESAFE_API_KEY
{
  "state": "我连续 3 天无法连接 Stripe 账户，正在丢失销售额，请尽快处理！",
  "model": "jev-latest",
  "questions": {
    "is_urgent": {
      "type": "noul",
      "instructions": "这条消息是否传达了紧急性或时效性"
    },
    "department": {
      "type": "choice",
      "instructions": "这个工单应该分配给哪个团队处理",
      "criteria": {
        "billing": "付款、发票、退款相关问题",
        "technical": "Bug、系统故障、集成问题",
        "sales": "定价、账户咨询"
      }
    }
  }
}
```

返回（示意）：

```jsonc
{
  "is_urgent":   { "type": "noul", "noul": 0.95 },
  "department":  { "type": "choice", "choice": "billing",
                   "confidence": 0.8,
                   "probabilities": { "billing": 0.87, "sales": 0, "technical": 0.13 } }
}
```

### 2.3 五种接入路径

1. **Playground**：<https://console.typesafe.ai/playground>，粘贴 state、加问题、看结果。
2. **HTTP API**：控制台 <https://console.typesafe.ai/keys> 建 key，POST `/v1/systemone`。
3. **SDK**：Python（`pip install typesafe-sdk`，要求 3.10+，自动读 `TYPESAFE_API_KEY`）/ JavaScript。

   ```python
   from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

   client = TypeSafeClient()
   response = client.system_one(
       state="客户说：我被重复扣款了，订单号 A-104，请退款。",
       questions={
           "department": Choice(instructions="工单分给哪个团队",
                                criteria={"billing": "…", "technical": "…", "sales": "…"}),
           "is_urgent":  Noul(instructions="这条消息是否传达了紧急性"),
       },
   )
   print(response.answers["department"].choice)  # "billing"
   print(response.answers["is_urgent"].noul)     # 0.95
   ```
4. **Coding Agent 技能包**：`npx skills add typesafe-ai/skills --skill typesafe-ai`（Claude Code 走 plugin marketplace 两条命令）。装完后用 `/typesafe-ai` 斜杠命令或直接说「用 Jev 判断」，agent 会自己组装请求。技能还会纠正 agent「一次只问一个问题」的毛病。
5. **第三方平台**：Vercel AI Gateway（AI SDK 的 `experimental_evaluate` 接口）、Cloudflare Workers AI。
   另有官方开源 **system-one-adapter-python**：同一接口的替代实现，后端接 OpenAI/Anthropic 兼容端点——没排到 early access 队列时可以先用它把代码结构跑通，将来换回 Jev 只改 provider。

### 2.4 使用最佳实践（真正的使用技能）

1. **一个问题只问一个判断**。判据：「一个有知识的人看一眼就能答」。见「分析这条消息并确定最佳行动」这种需要慢思考的问题就该拆。
2. **多因素判断拆开问、代码里加权合成**。不要问「给这个 pitch 打几分」，分别问市场规模、技术可行性、差异化，用自己的公式合成——优先级变化时改的是代码系数，不用重写提示词。
3. **一次把问题问满**（含投机性问题）。官方并行手册的数字：13 个问题合成一次调用，比拆 13 次便宜 **11.5 倍**、快 **9.6 倍**，答案完全一致。单次请求预算约 **32,000 token**（state 与问题共享）。
4. **JSON state 用点号路径指名字段**：「`ticket.messages[0].text` 是否请求退款？」——让模型明确看哪一块。
5. **Score 档位写情形**；同一份 bug 报告，档位写 0/1/2 数字时输出 0.57 分、置信度 0.35；写成具体情形描述后判断就稳定了。
6. **Choice 留「其他」选项**；基数上限 255，超过走两阶段（先独立打分再显式选择）。

### 2.5 置信度怎么用：把不确定变成系统行为

Choice/Score 的 `confidence` 是从概率分布形状算出的统计量（分布越尖越自信），官方强调这只是「大多数场景够用」的默认定义——完整分布 `probabilities` 也给你了，可自定义度量。

官方推荐三段式路由：

| 置信度 | 行为 |
|---|---|
| 高 | 自动执行 |
| 中 | 继续，但加确认 / 标记复核 / 补充信息 |
| 低 | 不执行，转人工或换路径 |

**阈值随风险分层**（官方语音银行例子）：意图判断 < 0.6 一律转人工；查余额这类低风险动作 0.6 就够（最坏结果是用户再听一遍余额）；批准转账这类高风险动作要求 ≥ 0.85。风险容忍度写在你的代码里，不在模型里；从保守值开始、用自己的数据校准。

### 2.6 性能与价格

- 输入 $0.042/百万 token（每十亿 $42），**输出免费**；端到端 70–500ms。
- 首页「193.6 倍更快、444.6 倍更便宜」出自 4 个 workflow eval，官方自己承认偏乐观端。
- 实测参考（阿里云社区文章）：1000 封邮件三问分类，Jev 15.6s / $0.0177（64 封/秒），对比 DeepSeek V4.1 Flash 48.9s / $0.0207；1018 篇论文分类 $0.08；browser-use 的 jev-ultrafast 在 Google Flights 完成一次搜索 7.1 秒、$0.0039。
- 官方 Workflow Evals 方法论值得抄：**同一策略，拆成 Noul/Choice/Score + 代码规则的工作流，普遍比写成一段大提示词更准、更便宜、更快**（例：某小模型工作流 58.8% vs 整段提示词 17.1%）。

### 2.7 典型应用场景

1. **工单/邮件/消息批量分类路由**（部门、紧急度、情绪一次问完）。
2. **Agent 决策中间层**：Agent 每步的工具选择、风险判断先交给 Jev，需要写内容时才请 LLM。浏览器自动化是标杆场景（点击选择本质是离散多选题，毫秒级选出该点的 DOM 元素，打字时才回退给小模型）。
3. **内容审核与风控**：违规判断 + 类型 + 风险等级一次出，每条 <$0.001。
4. **给 LLM 输出做质检**：便宜 AI 检查贵 AI（跑题检测、质量打分、多阶段代码审查）。
5. **实时游戏/控制**：Doom 每秒 10 次查询约 $7/小时；地铁跑酷、马里奥、星际争霸均有通关 demo。注意：这些 demo 都是先用代码把游戏状态转成结构化数据再喂 Jev，不是让 Jev 看截图。
6. **上下文压缩**（Claude Code 插件 fast-jev-compaction：每次工具调用后判断哪些内容该保留/压缩/丢弃）、搜索流程（jev-search）、工具调用门控（pi-jev）等社区生态。

### 2.8 能力边界与坑

- **不能**：生成文字、算术推理、日期比较；多步推理随步数增加表现下降——那是 System 2 / 推理模型的领地。
- **错误的样子变了**：输出永远类型安全，所以它错起来是「在你给的选项里挑错了」，不会被解析器拦住——错误看起来很正常，需要用校准抽检来发现。
- **无解释性**：只给决策不给理由（想验证只能从外部试探，像玩海龟汤）。
- OOD（分布外）输入上有深度学习通病：可能「极度自信但错误」。
- 服务位于美国西海岸；early access 按序放号；中国大陆未开放。

---

## 3. 网络结构

### 3.1 官方披露了什么、没披露什么

**已披露**：输入输出接口（state + 带类型问题 → 决策 + 概率）；多问题并行评估；System One 定位；RLCD 训练方向；延迟/价格/部分 benchmark。

**未披露**：权重、参数量、完整网络结构、训练数据、RLCD 完整损失与流程、并行采样器的具体实现。因此下述内容分两类：权威推断（§3.2）与社区复现佐证（§3.3–3.4）。

### 3.2 权威推断：Sebastian Raschka 的分析（2026-09-20）

Raschka（LLM 领域知名研究者）的「教育性猜测」：

1. **小型编码器式模型，类似 (Modern)BERT**；
2. **用类似 RLCR（校准奖励强化学习）的方法训练**（见 §4.3）；
3. 真正的秘诀**更多在数据而非算法**（外加一层漂亮的 API 设计）。编码器分类模型人们训了很多年，Jev 的突破在于**泛化得异乎寻常地好**（邮件分类、打游戏、炒股都用同一个模型）——像 Stable Diffusion 之于 latent diffusion 论文、ChatGPT 之于 InstructGPT：想法不新，工程与数据让它成了。

### 3.3 该架构类的共同模式

综合社区复现（Laya、NanoJev、jev-forge、open-jev-typed-decision-engine 等），「Jev 式决策模型」的网络结构收敛为以下模式：

```
state + (question, candidates)×N
        │
        ▼
┌────────────────────────────┐
│  骨干网络（编码器或小型 LM）  │  ← state 只处理一次（共享前缀 / KV 复用）
│  无自回归生成路径             │
└────────────────────────────┘
        │  隐藏表示
        ▼
┌────────────────────────────┐
│  专用决策头（替代 lm_head）    │
│  · Choice 头：共享标量头 +    │  ← 候选间做集合注意力（set attention），
│    对每个候选输出 logit       │     模型理解「互斥选项集」而非独立判断
│  · Noul 头：单路 sigmoid      │
│  · Score 头：对有序档位分布    │  ← 概率加权期望，自然产生 1.04 这类
│    取概率加权期望              │     非整数档位
└────────────────────────────┘
        │
        ▼
  每个问题一个类型化分布（一次前向传播全部输出）
```

要点：

1. **去自回归**：没有逐 token 解码，输出端零 token。推理只剩 Prefill（预填充）阶段——**从访存受限（memory-bound）的 Decode 循环变回计算受限（compute-bound）的单次矩阵运算**，且无需在生成期间维护增长的 KV cache，天生适合大 batch 并发。这是速度与成本优势的算力根源。
2. **并行评估**：NanoJev 实测「6 个状态 · 18 个问题 · 44 条候选路径 · 1 次骨干前向」；官方侧表现为「问 1 个和问 10 个延迟几乎相同」。
3. **共享前缀**：同一 state 服务多个问题时只算一次（Simple Jev 用 KV cache 复用实现；jev-forge 定位就是「从共享前缀给动态候选分支打分」，支持高基数 choice、校准与快速批量推理）。
4. **三种头对应三种统计结构**：互斥选择（softmax + 集合注意力）、单一命题（sigmoid）、有序量表（期望回归）。强行塞进同一个 softmax 会丢掉各问题类型特有的结构信息——这是该架构一个容易被低估的设计原则。
5. **输出在数学上类型安全**：答案被约束在你给的选项/量表里，模型物理上给不出选项外的值 → 结构化错误率 0% 的来源。

### 3.4 社区复现路线对比（按复刻的层次分）

| 项目 | 复刻的层 | 做法 | 数据点 |
|---|---|---|---|
| **SemIf**（原 OpenJev，~2.1k stars） | 接口层 | 现成开源 LLM，不生成「答案是A」，直接读候选位置的 logits 转成选项分数 | 证明 Jev 接口形态不需要等闭源模型；但概率未校准 |
| **Simple Jev**（featherless-ai） | 接口 + 推理层 | 上述 + 共享前缀 KV cache：state 算一次，各问题只处理各自后缀 | 降低重复计算；仓库自警「能返回 JSON ≠ 概率可信」 |
| **Laya**（~9.8k stars） | 到训练层 | 双向编码器 + 专用决策头，每选项一个可提取位置，一次前向打分 | T4 单问 33–40ms；2000 决策 benchmark 微调后 0.766；**基础 checkpoint 接近随机**——能力来自专用数据微调 |
| **NanoJev**（954 stars，MIT） | 全流程（研究复刻） | Qwen3-0.6B 骨干 + 三种决策头；完整训练管线；迷宫/贪吃蛇验证 | 40 图导航 95%/90%（Jev 本尊 100%/95%，未调 Qwen3 35%/15%）；HuggingFace 开权重与数据集 |
| **open-jev-typed-decision-engine** | 全流程（150M） | 150M 类型化决策引擎，非自归索单次前向 | 自报 0.697 vs Jev 0.727，校准好 2.5 倍、快 4 倍；Colab T4 半小时训完 |
| **jev-forge** | 训练/推理栈 | 开源训练与推理框架：共享前缀 + 动态候选分支打分 | 面向复现研究的基础设施 |
| **Visual Jev**（arXiv:2609.25845） | 多模态扩展 | 共享视觉上下文下的准确高效决策 | 论文阶段 |

四层设计观（评估任何「Jev 替代品」的框架）：**接口**（输入输出程序可直接消费）→ **推理**（单次前向、共享上下文）→ **训练**（见过真实业务模糊输入的专用训练）→ **评估校准**（0.9 的概率是否真的九成对；选项换序是否翻判；OOD 表现）。四层不可互相替代：接口像 ≠ 能力像；30ms 延迟 ≠ 错误率低；输出概率 ≠ 概率校准。

---

## 4. 训练方法

### 4.1 RLCD：第三条后训练路线

官方 AI primer 把预训练模型的适配分成三条分支：

| 路线 | 全称 | 优化目标 | 产物 | 问题 |
|---|---|---|---|---|
| RLHF | 人类反馈强化学习 | 人类偏好（Bradley-Terry 相对偏好） | 聊天机器人（InstructGPT/ChatGPT） | 奖励讨好与自信的幻觉；**mode dropping**（偏好某风格、压低其他输出的概率） |
| RLVR | 可验证奖励强化学习 | 可验证正确性、错误率最低 | 推理模型（数学等） | 慢且贵；不校准置信度 |
| **RLCD** | **校准决策强化学习** | **校准过的决策** | System One 决策模型（Jev） | ——（TypeSafe 的路线） |

RLCD 的输出契约：

- 模型不生成文本；
- 返回决策与概率；
- **概率越高 ⇒ 答案正确的可能性越大**，且这个对应关系是训练目标本身。

校准的可操作定义（对预测的群体成立，不保证单条）：

> 说 0.2 的事件，长期看约 20% 发生；说 0.8 的约 80% 发生；说 1.0 的必须 100% 发生。

Diogo Almeida 的动机自述：RLHF 把人放进了训练 loop，所以模型用起来也需要人在 loop——这就是「辅助（assistance）与自动化（automation）」的分界。他要的是模型**别管人类喜不喜欢，以一种经过校准的方式把任务做对**。多步任务拆成大量小的可验证判断，每个判断设阈值；发现漏了一种情况，就增加一个问题、一个阈值和测试用例——**把提示词工程变成软件工程**。

官方同时承认：校准不完美，模型会犯很多错；他更看重**稳健性**——语义相近的输入应得到相近结果（他们往提示里放随机 ID 来测稳定性）。

### 4.2 可能的技术基础：RLCR（Brier 校准奖励）

Raschka 指出 RLCD 最可能基于 **RLCR（Reinforcement Learning with Calibration Rewards）**——arXiv:2507.16806《Beyond Binary Rewards: Training LMs to Reason About Their Uncertainty》（MIT，2025-07 提交、2026-05 修订）：

- **奖励函数 = 二元正确性分数 + Brier 分数**（对置信度估计的真值评分规则）；
- 理论结果：任何使用**有界真值评分规则**（bounded proper scoring rule）的奖励，可证明地同时产出**准确且校准**的模型；
- 实证：跨多样数据集，RLCR 无精度损失地显著改善分布内与分布外的校准，优于普通 RL 与事后置信度分类器；普通 RL 会伤校准，RLCR 反而改善它；
- 测试时可用言语化置信度做置信加权 scaling，进一步提升准确与校准。

（Jev 的具体损失未公开；社区分析认为其优化目标包含 Brier 分数 / ECE 一类校准度量。）

### 4.3 社区复现的训练管线（以 NanoJev 为例）

NanoJev 的五步端到端管线（开源可复跑）：

```
1. 构建查询   → 生成 state、问题、候选描述、目标分布
2. 组织数据   → 相关的地图/规则/变体保持在同一数据切分（防泄漏）
3. 训练       → Qwen3-0.6B 初始化 + 决策头预热（warmup）+ 完整问题分布损失
4. 评估       → 概率质量 + 游戏控制器记录实际动作
5. 服务与可视化 → 常驻模型端点，浏览器回放完整轨迹
```

损失函数变体实验：交叉熵（CE）/ **Brier** / 成对真值奖励（paired proper-reward）三种 checkpoint 并行发布，供校准研究对比——与 RLCR 的「真值评分规则」思想同源。

Laya 的对照结论同样关键：**基础 checkpoint 在类型化决策 benchmark 上接近随机基线**，任务能力几乎全部来自专用数据与微调。这印证了 Raschka 的判断：**这套架构不难写，难的是数据**——Jev 跨领域（邮件、游戏、交易……）的泛化才是护城河。

### 4.4 训练方法小结

1. 预训练骨干提供语言理解（Diogo：「预训练不是问题，它把互联网知识压缩成智能核心；问题是怎么把智能释放出来」）；
2. 输出侧改造：去掉 lm_head，换专用决策头；
3. 后训练：面向校准的强化学习（RLCD）——正确性 + 真值评分规则（Brier 类）联合优化，让「说 0.9」与「九成对」物理对齐；
4. 数据工程是真正的秘密武器：覆盖极广的「state × 问题 × 候选 × 结果」四元组语料。

---

## 5. 对本项目的启示（映射回 00-problem-definition.md）

1. **Jev 是判断函数 J 的工业实现**。我们的 J : X × C → Δ(A)——「输出结构化判断上的分布，不是点估计」——Jev 把它做成了产品：类型化输出（≈A 的离散化）+ 概率分布 + 置信度。这验证了 §2.2 的设计方向在工程上可行且有市场。
2. **C1 感知层与告警分流是天然适配场景**。检测/分类/定位、工单路由、风险分级——SOC 的海量低延迟判断（每条消息 <$0.001、毫秒级）正是 Jev 式模型的主场；§10.1 的「检测→解释→评估→响应」任务算子里，检测与分流两环可以下沉为 System One 决策层。
3. **置信度路由 = 我们的 fail-open/fail-closed 参数化**（§7.3）。Jev 官方的三段式路由 + 按风险分层阈值，与我们「高严重度失败即闭合、低严重度可失败即放行」是同一思想的两种表述。**风险容忍度写在代码里，不在模型里**——可直接采纳为我们的工程原则。
4. **校准（C5）是可训练目标，不是愿望**。RLCR 证明真值评分规则奖励可证明地改善校准；我们的「校准了的怀疑」（§6）有了可操作的训练配方参考。
5. **必须显式管理的两个缺口**：
   - **无解释性**：Jev 不产出理由链，而我们的 §7.3 要求每个裁决可事后重建。System One 决策层必须与 System 2 解释层（生成理由、归因）配对使用，由后者承担可审计性。
   - **OOD 过自信**：安全的对抗性保证测试分布永远含训练外攻击家族（§1.6、§7），而 OOD 校准灾难是这类模型的已知软肋——检测器被探测与调参（§7.1-3）在低成本高并发下会更容易。需要选项顺序稳定性测试、校准抽检、对抗性红队评估作为部署门槛。
6. **一个战略判断**：Jev 证明了「智能大拆分」的经济逻辑——判断类认知操作将从生成式捆绑包中独立定价。若我们的安全 LLM 走「原生安全」路线，感知/判断层的成本结构将决定产品形态（D1 过滤 API vs 分析师副驾）；把高频判断做成 System One 层、把解释与推理留给 System 2 层的混合架构，可能是 Pareto 操作点（§8.4）的最优实现路径。

---

## 6. 参考资料

**官方**

- TypeSafe AI 官方博客（System One Models & Jev 发布文）：<https://typesafe.ai/blog/introducing-system-one-models-and-jev>
- 官方文档 Quick Start：<https://docs.typesafe.ai/introduction/quickstart>
- 官方文档 System One 概念：<https://docs.typesafe.ai/concepts/system-one>
- 官方文档 AI Primer（RLHF/RLVR/RLCD 三路对比）：<https://docs.typesafe.ai/introduction/machine-learning-primer>

**分析/访谈**

- Sebastian Raschka, *It's Easy to Dismiss Jev as Just a Classifier*（2026-09-20）：<https://sebastianraschka.com/blog/2026/jev-classification-generalization.html>
- Diogo Almeida 访谈整理（Founder Park / 智源社区转载，2026-09-23）：<https://hub.baai.ac.cn/view/58208>
- RLCR 论文：*Beyond Binary Rewards: Training LMs to Reason About Their Uncertainty*，arXiv:2507.16806：<https://arxiv.org/abs/2507.16806>

**实战测评/教程**

- 程序员鱼皮，*全网刷屏的 Jev 模型正式开放！一手实战测评 + 保姆级教程*（阿里云开发者社区，2026-09-21）：<https://developer.aliyun.com/article/1765145>
- TRAE 社区：*不会还有人不知道 JEV 吧*（含使用技能、生态项目清单）：<https://forum.trae.cn/t/topic/181665>

**社区复现**

- *Jev 未开源完整模型，社区却跑出了三条复现路线*（SemIf / Simple Jev / Laya 对比，2026-09-22）：<https://www.10100.com/article/151971780>
- NanoJev（含 dev.to 深度解读）：<https://github.com/TianyuCodings/NanoJev> · <https://dev.to/wonderlab/one-open-source-project-a-day-no-189-nanojev-a-06b-parallel-decision-model-that-outputs-22ao>
- jev-forge（训练/推理栈）：<https://github.com/zwliJay/jev-forge>
- open-jev-typed-decision-engine：<https://github.com/intikhab49/open-jev-typed-decision-engine>
- SemIf（原 OpenJev）：<https://github.com/TheoLeeCJ/SemIf> · Simple Jev：<https://github.com/featherless-ai/simple-jev> · Laya：<https://github.com/NandhaKishorM/laya>
- Visual Jev 论文：arXiv:2609.25845：<https://www.alphaxiv.org/abs/2609.25845>

**生态项目**（TRAE 帖内整理）：fast-jev-compaction、jev-browser、jev-search、browser-use/jev-ultrafast、pi-jev、hermes-jev-skills 等。

---

**可信度声明**：本文标注「官方」的部分来自 TypeSafe 文档与发布文；「推断」部分来自 Raschka 的公开分析（明确标注为猜测）；「复现」部分来自开源社区项目自述，其 benchmark 数字多为项目方自报，未经第三方同条件验证。
