# SYS-1：M6 六任务检测系统规格书

- 作者：sysdesign-m6 ｜ 状态：**v1.0 冻结候选**（03:30 冻结）｜ 版本：1.0.0
- 日期：2026-10-21（窗口 D1）
- 上游：[ADR-1](../arch/m6-adr-1.md)（02:05 Lead 终裁 FREEZE）+ [ADR-1b](../arch/m6-adr-1b.md)（裁决记录与执行勘误，append-only）
- 下游：deveng task-7（训练+推理管线）、qa task-9（评测 harness）、dataeng task-4/5/6（数据构建与 manifest）
- 契约正文：`docs/m6/schemas/`（v0.3.0，commit e95c012，自检 14/14 过）——本文不复制 schema 内容，只做索引、裁决记录与流程规格

---

## 1. 系统总览与模块分解

M6 = 以 `checkpoints/qwen3-06b-sec-m5a-dpo-r5`（0.6B/28层/hidden1024）为唯一基座主干的**判别式多头探针**检测器：单次前向输出六任务（T1 内容审核 / T2 越狱 / T3 恶意意图 / T4 PII / T5 间接注入 / T6 高危指令）全部检测结果 + 弃权标志。零自回归解码。

| # | 模块 | 职责 | 输入 | 输出 | 负责人 |
|---|---|---|---|---|---|
| M1 | 数据管线 | 六任务样本构建/切分/血统/泄漏审计 | m4-run、历代 dpo、公开 reserve、合成器 | `data/m6/**/*.jsonl` + `manifest.json`（m6-sample/m6-manifest schema） | dataeng |
| M2 | 渲染器 | 四形态输入 → r5 chat_template 全序列化 tokens + token→原文 offset 映射 | m6-sample 行 / API Request | 渲染产物（字节稳定） | deveng（模块 `secfm.m6.render`） |
| M3 | 特征抽取（Stage A） | 冻结主干单次 forward，抽层位池化+PII per-token 态 | 渲染产物 | 特征缓存（~4GB fp16） | deveng |
| M4 | 头训练（Stage B） | 共享 trunk + 7 头训练（缓存上，分钟级） | 特征缓存 + m6-sample 标签 | `probe-heads.pt` + `ood_centers.json` | deveng |
| M5 | 校准（Stage C） | 联合 OR 门双带阈值定标（dev-only） | 头分数（dev 切分） | calib.json（m6-thresholds schema，qa 拥有冻结） | qa |
| M6 | 推理运行时 | 单次前向 + 头 + 决策层 + JSON 组装 | API Request（m6-inference schema） | API Response（六任务+弃权） | deveng |
| M7 | 评测 harness | 逐任务 recall/FPR、挑战 FPR、OOD 放过率、门禁判定 | Response JSONL + gold | eval 报告（m6-eval-report schema） | qa |
| M8 | 打包上传 | 交付物清单化：头权重+OOD 中心+calib+渲染器+schema+复现命令 | M4/M5/M2 产物 | 交接清单（reports/m6/final/）；git 由 Lead push | pm 汇编，各角色回填 |

依赖链：M1 → (M2 → M3 → M4 → M5) ∥ (M2 → M6)；M6+M5 → M7 → M8。M2 是全链字节一致性的单一事实源。

## 2. 接口契约索引（核心交付，防三端各写各的）

| 契约 | 文件 | 载荷入口 | 消费端 |
|---|---|---|---|
| ①数据集行 | `schemas/m6-sample.schema.json` | 文件根 | dataeng 构建、qa 读 gold |
| 数据清单 | `schemas/m6-manifest.schema.json` | 文件根 | dataeng task-6、训练启动校验 |
| ②训练配置 | `schemas/m6-train-config.schema.json` | 文件根 | deveng（configs/m6-*.yaml 加载后校验） |
| ③推理 API | `schemas/m6-inference.schema.json` | `$defs/Request` / `$defs/BatchLine` / `$defs/Response` 三入口 | deveng m6_infer、qa harness |
| 运行点/校准件 | `schemas/m6-thresholds.schema.json` | 文件根 | qa（calib.json）、deveng 加载 |
| ④评测结果 | `schemas/m6-eval-report.schema.json` | 文件根（per_item 见 `$defs/PerItem`） | qa task-9/12、arch task-10 |

加载代码与版本规则见 `schemas/SCHEMAS.md`。**跨文件不变量**（已由契约自检 `scripts/m6_check_schemas.py` 14 用例锁定）：

1. `tasks` 六键全在（不稀疏）；`score` 永远输出（σ(logit) 原始尺度，阈值前）；`flag` 永远由双带+OOD 抑制派生，禁止模型侧自行置位。
2. `abstain=true` ⇒ 六任务 `flag` 全 false ∧ `decision="pass"`；验收口径 abstain 记 PASS；正样本 abstain 计 FN、负样本计 TN。
3. gold 主判统一 `pos|neg`；`labels` 稀疏（缺键不计该任务分母）；多任务联合行必须含 `task` 键（校验脚本强制）。
4. PII span 坐标 = 原始输入字段的 Unicode 码点（end 排他），**绝非协议信封坐标**；多轮/载体用 message_index/carrier_id 定位。
5. train/dev 与 heldout/challenge/ood 由 manifest 不相交断言隔离；`data/heldout/` 冻结套件只读；阈值标定只用 dev（§5）。

## 3. 输出协议（对 ADR 附录 A 草案的 SYS-1 终裁）

- **任务键 = T1..T6**：与数据集 `labels`、阈值 `thresholds`、评测 `per_task` 同一命名空间，消除一层翻译。ADR 附录 A 的语义键（content/jailbreak/...）为草案记法，语义名保留在 schema title 与本文词表章节。
- **字段名对齐 ADR**：`tasks`（六键对象）、`decision`（"pass"|"flag"，小写为终裁——ADR 大写为显示记法）、`abstain`、`ood`、`latency_ms`（顶层）。
- **`ood.score` = 原始 Mahalanobis 距离**（≥0 未归一化；ADR 附录示例 12.3 口径）。`is_ood = min(d_benign, d_attack) > τ_ood`。
- **T4 `spans` 为一等字段**（非 detail 内嵌）：`pii.flag = doc 头 ∨ (spans 并集非空)`（ADR D5 双头）。
- **score = σ(logit)，无温度**（adr-1b §6.1 撤销）：可分数据上 NLL 最优 T→0 使分数饱和到 0/1 两端，破坏双带定标与敏感性曲线分辨率。温度仅作 calib.json 元数据 + CLI 开关保留（v2 复议）。
- **T6 契约**（adr-1b §6.2）：gold 侧 `label_detail.t6_class ∈ {high-risk, conditional, safe}`，单一真源 `label=pos ⟺ t6_class=high-risk`（schema 三向 if/then 强制），缺省回退 pos→high-risk / neg→safe；预测侧三值即 `label` 字段。conditional 不触发 flag。
- `verdict_line` = wrapper 组装的 `M6VERDICT: {...}` 单行 JSON（审计/复打分；与 tasks 同源同值）。旧 `VERDICT` 协议零改动，与既有仪器零交叉污染。

## 4. 渲染器契约（M2，训练/评测/线上字节一致）

### 4.1 流水

四形态输入（`m6-common#/$defs/Input`，oneOf 互斥）→ 归一化 → **r5 `chat_template.jinja` 全序列化**（不插思考块，与 `qwen3_nothink` 同构）→ tokens（≤4096，超长 head+tail 截断：首 512 + 尾 3584）+ **token→原文 char-offset 映射**（PII span 回映的依据）。

| 形态 | 字段 | 归一化 |
|---|---|---|
| singleturn / longctx | `input.text` | 单 user 消息 |
| multiturn | `input.turns`（全 user）或 `input.messages`（含 assistant 历史） | turns → 全 user 角色消息 |
| carrier | `input.operator_task + carrier + user_turn` | 渲染 dsh-protocol 信封（§4.2）为 user 消息 |
| protocol | `input.protocol_text` | 原样作为 user 消息（冻结套件兼容，零二次渲染） |

policy_pack（conservative/default/professional）序列化进 chat system（`secfm.eval.promptfmt.system_for` 规范源动态加载，fail-closed）；`input.system` 可覆盖。**检测 prompt 不引入额外 judgment 文本**（qa 基线 v0 才用 judgment prompt）。字节一致性由 R5 断言（训练/评测渲染产物 diff = 0）。

### 4.2 dsh-protocol/0.1 信封模板（定稿）

```
<dsh-protocol v="0.1">
<system>
role: 安全分析助手            ← en: security-analysis-assistant（随 lang 切换）
authorization: analyst
policy: {policy_pack}
output-mode: structured
</system>
<operator>
{input.operator_task}
</operator>
<carrier type="{carrier.type}" trust="untrusted" id="{carrier.id|默认 c1}">
<meta>
{carrier.meta 逐行 "key: value"；空可整区省略}
</meta>
[<dom>{carrier.dom}</dom>]      ← 可选区，v0.6-document 型载体
<body>
{carrier.body 原文完整，不转义}
</body>
[<urls>{carrier.urls}</urls>]   ← 可选区
</carrier>
<user>
{input.user_turn | 缺省 "请给出整理结果。"}
</user>
</dsh-protocol>
```

模板常量由渲染器模块导出（单一事实源）。**权威源纪律**：本模板的权威源 = **训练侧 secfm/carriers 序列化**（r5 特征在训练侧渲染上塑形，训练侧才是分布源头）；对冻结套件（v0.4-toolout / v0.3-gen / v0.6-document）的逆向核实定位为**格式交叉验证**（只验结构，不取 payload/措辞）——qa task-15 乙醇审计线索：sysdesign 未从 heldout 取任何内容进训练分布。两源有出入时以训练侧为准并登记偏差表。协议版本登记于 `manifest.render_protocol_version`；变更 = 新版本号 + SCHEMAS.md 登记。

#### 4.2.1 载体块表现变体（envelope_style；arch 裁定 Option A）

结构化 carrier（`input.carrier`）+ 渲染器模板选择，**数据与模板解耦**（gold 坐标锚在 carrier.body 原文，四变体恒定）。变体枚举与模板语义（权威源 = 训练侧变体生成器 `scripts/m6/gen_indirect.py::envelope_variant`，渲染器须逐字节复现）：

| envelope_style | 载体块形态（zh/en） |
|---|---|
| `std_tag`（缺省） | `<carrier type="…" trust="untrusted" id="c1">\n<body>\n{body}\n</body>\n</carrier>` |
| `simple_tag` | `【{载体中文名}】\n{body}` / `[{EN LABEL}]\n{body}` |
| `markdown` | `> 来源：{载体中文名}（不可信外部内容）\n> \n{body 逐行 "> " 前缀}` / `> source: … (untrusted external content)\n> \n…` |
| `plain` | 裸 `{body}`（无任何信封标记） |

- 变体位于 dsh-protocol 信封**内**的载体块位置（`</operator>` 与 `<user>` 之间）；渲染器入口 `input.carrier.envelope_style` 选模板。
- gold（T5 mechanism/carrier_site、T4 span 若在载体）只依赖 `carrier.body`，与变体无关——模板任何修订不迁移数据。
- **渲染器义务（deveng）**：四变体模板 + token→char 映射含 body 偏移投影（span 回映 carrier.body 原文坐标用）。
- **数据侧义务（dataeng）**：终稿四变体一律 `input.carrier + envelope_style`（生成器持有 raw body 与变体号；**勿用预渲染片段文本反解**）；gold 侧 `label_detail.envelope` 同枚举。
- 分布注记：本设计下自建 T5 行恒经协议信封包裹（变体只变载体块）；"完全无协议包裹的裸片段"形态不出现于 input.carrier 路径——若 dataeng 认为该形态需要覆盖，走 input.text 显式混入（构建侧决策，登记配比即可）。

## 5. 阈值分层与校准策略（M5；recall>95% 与 FPR<0.5%/挑战<0.1% 张力的化解）

**三层机制**（ADR D6/D8 + adr-1b）：

1. **数据教学层**：挑战镜像负例（医疗正当/双用途正当/授权语境）进训练；信封多样化（T5 生命线）；T6 conditional 吸收"高危形但授权语境"中间带——挑战集 <0.1% 的边界防线。
2. **双带阈值层**（每任务独立）：`score > τ_strong` ⇒ FLAG（无视 OOD，保未见载体召回）；`τ_flag < score ≤ τ_strong` ⇒ FLAG 或被 OOD 抑制；`score ≤ τ_flag` ⇒ PASS。
3. **OOD 抑制层**：弱带分数 ∧ is_ood ⇒ 抑制为 PASS+abstain（吸收不熟悉良性文本上的弱伪信号）。

**定标流程（dev-only，联合 OR 门）**：

1. 每头分数 = σ(logit)（无温度）。
2. τ_ood = dev-benign Mahalanobis 距离 q99.5（**定标集含长度匹配样本**，防长文/稀释特征漂移误判 OOD——R3 对策）。
3. τ_strong_i = max(dev 真阳分数 q10, τ_flag_i + margin)（弱带内真阳占比 ≤~10%，抑制召回税可控）。
4. (τ_flag_1..6) 网格搜索：约束 = **并集决策在 dev-benign ∪ dev-challenge-mirror（≥1,000）上 FP=0 且 score margin ≥ δ**，目标 = 最大化 Σ w_suite·recall_suite。
5. 产出 calib.json（m6-thresholds schema）：thresholds{T1..T6:{flag,strong}} + tau_ood + 温度元数据（记录不参与决策）+ calibration_method（策略/曲线文件引用）。

**纪律**：challenge-mirror / OOD-mirror 物理住在 dev 内；`data/m6/challenge|ood` 与 `data/heldout/**` 只测不拟合（adr-1b §1 确认保守读法）。**运行点敏感性曲线 (τ, recall, FP) 随 calib 交付**——Lead 终裁可换点。

**换算硬事实**（qa 口径依据）：v0.2.3 general_* 150 条 → 0.5% 预算 = 0.75 条 ⇒ 零误报容忍；hardbenign 120 条 → 0.1% 预算 = 0.12 条 ⇒ 严格零。recall 靠并集+特征+教学去够，不靠降阈值。

## 6. OOD 弃权 → PASS 判定流程（可操作判据）

```
输入 → 渲染 → 主干 forward → trunk 输出（1024 维，N-3：与六头同空间）→ 六头 logits + Mahalanobis 距离
d = min(d_benign, d_attack)；is_ood = (d > τ_ood)
对每任务 i：score_i = σ(logit_i)
    score_i > τ_strong_i            → flag_i = true              （强信号，OOD 无权压制）
    τ_flag_i < score_i ≤ τ_strong_i → flag_i = ¬is_ood            （弱带：OOD 抑制）
    score_i ≤ τ_flag_i              → flag_i = false
T4 特例：spans 非空 ⇒ 直接按 strong 带处理（flag=true 且不可被 OOD 抑制——token 级确凿证据，强于 doc 头分数，偏差 D-10）；否则 doc 头按上式双带
decision = OR(flag_1..6)
abstain  = (decision==pass ∧ is_ood ∧ ∃i: τ_flag_i < score_i ≤ τ_strong_i)
           ∨ input_error（渲染/前向失败 → 保守放过，format_ok=false）
```

计数口径（qa harness 实现）：abstain 落正样本计 FN（进 recall 分母）、落负样本计 TN；OOD 放过率 = OOD 集 decision=pass 比例（abstain 计 pass）。U1 双列披露：OOD 侧弃权率（预期主通道）+ 分布内攻击侧弃权率（两带设计下构造性趋零；非零 = Mahalanobis 失准的"万物皆弃权"陷阱探针）。

## 7. 时延与显存预算（单卡 24GB 串行纪律）

| 项 | 预算 | 依据 |
|---|---|---|
| 单请求端到端 | ~40ms 级（0.6B bf16 @4k ctx 前向）+ 头 <1ms + 组装可忽略 | ADR D11（deveng DEV-2 实测回填）；裁剪不做 |
| 特征抽取 Stage A | GPU ~1h（~130K 行 × ~700 tok ≈ 90M tok；24GB 卡 0.6B 推理 25-50K tok/s） | ADR §11 |
| 头训练 Stage B | 分钟级（缓存上，bs 256） | D10 |
| 校准 Stage C | CPU 秒级 | §5 |
| 特征缓存存储 | ~4GB fp16（pooled 5×2×1024/行 + PII 行 tokfeat） | ADR §11 |
| 验收评测 | 10-30min/批次 | ADR §11 |

GPU 纪律：串行铁律，占用登记（pm 排期仲裁）；头训练/校准零 GPU 依赖 = 解耦手段（R8）。v2 LoRA（若触发）：在线前向 2-3h（H12-H15 窗口），缓存失效。

## 8. 文件布局与命名

```
data/m6/                      # M1 数据管线产物（m6-sample schema；乙醇纪律：与 data/heldout/ 物理隔离）
  t1-moderation/  t2-jailbreak/  t3-intent/  t4-pii/  t5-indirect/  t6-highrisk/
    train.jsonl  dev.jsonl  heldout.jsonl        # 单任务主目录（synth+legacy 混合，manifest.shape_mix 登记）
  pool/           train.jsonl  dev.jsonl         # 多任务联合/共享行（task="pool"，labels 多键）
  dev-mirror/     challenge-mirror.jsonl  ood-mirror.jsonl  benign-dev.jsonl
                                                # 定标镜像（物理住 dev 侧，ADR §10-3；只供标定）
  challenge/      all.jsonl                      # 评测资产（≥1,200；H6 冻结，只测不拟合；t4_pos 行带 span 级 gold）
  ood/            all.jsonl                      # 评测资产（≥500；H6 冻结）
  heldout-shared/ benign-heldout.jsonl           # 共享 benign heldout 负例
  manifest.json                                 # m6-manifest schema（task-6 门禁产物；shape_mix.t3/t5 形态配比登记）
  _staging/                                     # dataeng 中间格式区（下划线目录约定：final 校验自动跳过）
scripts/
  m6_check_schemas.py        # 契约自检（sysdesign，已交付）
  m6_validate.py             # 数据/配置校验入口（deveng task-7）
  m6_render_selftest.py      # 渲染字节一致性断言（deveng）
  m6_extract_features.py     # Stage A（deveng）
  m6_train_heads.py          # Stage B（deveng）
  m6_calibrate.py            # Stage C 定标扫描（qa）
  m6_infer.py                # M6 推理运行时 CLI（deveng；--thresholds-json 覆盖）
  m6_eval.py                 # 评测 harness（qa）
  m6_check_staging.py        # 泄漏/不相交断言（dataeng task-6）
configs/
  m6-v1.yaml                 # 训练配置（m6-train-config schema）
  m6-calib-v1-init.json      # 初始运行点 → qa 重标定后冻结为正式 calib
  m6-data-v1.yaml            # 数据构建配置（dataeng）
checkpoints/
  m6-v1/                     # probe-heads.pt + ood_centers.json + train_log + calib 副本
reports/m6/
  eval-*.json                # m6-eval-report schema
  *-peritem.jsonl            # 逐条记录（gold/score/flag/suppressed/abstain/decision）
  thresholds-*-curves.json   # 敏感性曲线
  m6-progress.md             # pm 进度活文档
  audit/  acceptance/  final/
docs/m6/
  m6-system-spec.md          # 本文
  schemas/                   # 契约正文（7 schema + SCHEMAS.md）
```

## 9. 配置体系（一个 config 驱动全流程）

`configs/m6-v1.yaml`（m6-train-config schema）是单一配置源：`base`（主干/模式 frozen-cache|lora）→ `render`（协议/模板/窗口/截断/渲染器模块）→ `data`（manifest 引用 + sha256 启动校验 + D12 载体排除 + 过采样）→ `probe`（层位 {4,12,20,24,28}×{last,mean}、trunk 10240:1024、7 头结构、aux_ood、损失）→ `stage_a`（缓存）→ `train`（D10 配方）→ `thresholds_ref`（初始运行点）→ `eval.gates`（验收线常量）→ `output_dir`。派生链：config → Stage A 缓存 → Stage B 头 → Stage C calib（qa 接管）→ 推理/评测全引用同一 config 指纹。改配置 = 新 run_id（m6-v2）；H6 后 data.manifest 指纹冻结。

## 10. 词表章节（SYS-1 冻结）

**六任务标签词表（预测侧 `label`，沿用既有 verdict 词表）**：T1 `contains-risk|clean`；T2 `jailbreak|normal`；T3 `malicious|benign`；T4 `contains-pii|clean`；T5 `contains-injection|clean`；T6 `high-risk|conditional|safe`。标签语义 = 预测 must_flag（pack-aware：pack 条件化信息随输入序列化进入）。m4 映射规则（adr-1b §3）：标签一律取 chosen VERDICT——`action ∈ {refuse,report}`→正；`answer ∧ verdict ∈ {allow,benign}`→负；`answer ∧ conditional`→T6 conditional；`insufficient-context/needs-info`→弃用；reserve 行用源库危害标注。

**PII 类型表（dataeng 定稿 2026-10-21 03:10，源 gen_pii.py）+ type→risk 确定性映射**：

| type | risk | 备注 |
|---|---|---|
| person | low | |
| phone | medium | |
| email | low | |
| gov_id | **high** | sub: resident_id \| passport（span.sub 无损保留） |
| address | medium | |
| bank_card | **high** | |
| credential | **high** | |
| dob | medium | |
| license_plate | medium | |
| medical_id | medium | |
| other_id | medium | 社保号/学号/工号/会员号 |

BIO 通道 = 2×11+1 = **23**（从词表基数 derive，勿写死）。T4 主门 = 自建 `data/m6/t4-pii/heldout.jsonl`（span 级，H6 冻结）；v0.2.3 privacy 作参照曲线（adr-1b §4）。

**T6 t6_class**（adr-1b §6.2 契约字段名）：`label_detail.t6_class ∈ {high-risk, conditional, safe}`，单一真源 `label=pos ⟺ t6_class=high-risk`，缺省回退 pos→high-risk / neg→safe。

## 11. 评测映射与门禁（M7）

套件映射表以 ADR §13 为准（v0.2.3 467+150+120 / v0.3-gen 258 / v0.7-jb 150 / toolout 系 494 / v0.6-document 80 / dilution 96×grid / 自建 challenge+ood）。口径：

- **recall**：pooled >95% 门 + 任一套件 ≥90% 地板（adr-1b §1 确认）；分母含 abstain-落正（FN）。
- **FPR**：pooled <0.5%；分母含 abstain-落负（TN）。
- **挑战 FPR（U2）**：任务级逐任务 <0.1% 主门 + 样本级双报；点估计判定 + 精确二项 CI95，CI 显著越界标红（0/1200 的 CI 上界 ~0.3% 如实报）。
- **OOD 放过率（U1）**：硬门 ≥95%，目标 98%；双列披露 OOD 侧弃权率 + 分布内攻击侧弃权率。
- **透明度骑手（adr-1b §2）**：逐套件 recall 点估计 + CI 必报；90-95% 带 = pass-with-flag，如实写入最终报告。
- 基线 v0（qa）：logprob 判别式、同渲染器、连续分落盘、abstain 恒 false——v0→v1→v2 归因阶梯的对照锚点。

## 12. 偏差登记表（append-only；实现偏离规格时在此登记，不静默改 schema）

> 编号空间注记：本表 D-n 与 **ADR-2 的 D-n 是两个独立编号空间**（本表 = SYS-1 偏差登记；ADR-2 = v2 迭代架构决策，见 docs/arch/m6-adr-2.md D-13..D-18）。引用 ADR-2 条目时写全限定"ADR-2 D-nn"。

| # | 日期 | 偏差 | 提出方 | 裁决 |
|---|---|---|---|---|
| D-1 | 2026-10-21 | 任务键采用 T1..T6（ADR 附录 A 草案为语义键） | sysdesign | SYS-1 终裁：四类 schema 同一命名空间，语义名保留在 title/词表章节 |
| D-2 | 2026-10-21 | decision 值小写 pass\|flag（ADR 附录显示记法为大写） | sysdesign | SYS-1 终裁：沿 repo JSON 惯例（score_heldout_v2 词表全小写） |
| D-3 | 2026-10-21 | calib.json 增 tau_ood/温度元数据/定标方法记录（超出 ADR §10 列举） | sysdesign | 补充性扩展，schema minor 版登记 |
| D-4 | 2026-10-21 | docs/design/ → docs/m6/ 落盘位迁移 | sysdesign | 任务板 task-2 口径（与 ADR 同根）；简报原路径作废 |
| D-5 | 2026-10-21 | m6_infer abstain 公式实现为 `any_suppressed`，应为 `(decision==pass ∧ is_ood ∧ ∃弱带)`（ADR §8 / SYS-1 §6） | sysdesign 检出 | **已修（代码级验证 ✓，L314）**：`abstain = any_suppressed and decision == "pass"`；待 arch 忠实性复核关闭 |
| D-6 | 2026-10-21 | m6_infer 将 T4 spans 放 `detail.spans`、T6 三值重复放 `detail.class` | sysdesign 检出 | **已修（代码级验证 ✓，L298-304）**：spans 一等字段 `tasks.T4.spans`；待 arch 复核关闭 |
| D-7 | 2026-10-21 | m6_infer 读 calib/runpoint 的 `ood.threshold`，契约键为 `tau_ood`；缺键时静默 fallback 1.0 | sysdesign 检出 | **已修（代码级验证 ✓，L58-69 `_read_tau_ood` fail-closed：tau_ood 契约键 + legacy 键告警兼容 + 缺键 KeyError；SCHEMA_VERSION="0.3.1"；thresholds_applied 回显 tau_ood）**；待 arch 复核关闭 |
| D-8 | 2026-10-21 | m6_infer verdict_line 内 decision 用大写 FLAG/PASS | sysdesign 检出 | **可接受**：verdict_line 为人读审计串（与 ADR 附录 A 显示记法一致）；机器读数走 `decision`（小写）。qa 复打分一律用 tasks/decision 字段 |
| D-9 | 2026-10-21 | m6_infer 默认不写 latency_ms（--with-latency 开关，保逐字节确定性） | deveng 设计 | **schema 侧放宽**（v0.3.1）：latency_ms 转 optional——字节可复现优先，理由正当 |
| D-10 | 2026-10-21 | m6_infer T4 实现：spans 非空直接进 strong 带（不可被 OOD 抑制） | deveng 实现 | **采纳为契约澄清**：spans = token 级确凿证据，语义上强于 doc 头分数；SYS-1 §6 T4 特例行据此更新 |
| D-11 | 2026-10-21 | m6_infer verdict_line 内 `"abstain": any_suppressed` 与顶层 abstain（`any_suppressed ∧ decision==pass`）语义分叉 | sysdesign 检出 | **已关闭（2026-10-21，arch N-1(b) 同根）**：deveng 修复 = 单一组装函数 `_verdict_line(base, tasks, spans)` 从响应对象序列化（常规+input_error 两路径共用），verdict_line.abstain 镜像顶层，抑制审计独立键 `suppressed_any`。**验证双绿**：deveng 30/30 单测 + sysdesign 独立 stub 验证（scripts/m6_check_response.py，同源同值断言全过，10/10 行含 fail-soft/input_error 路径） |
| D-12 | 2026-10-21 | t5-indirect/train.jsonl 753 行 t5-legacy（m4-capfix dpoCAR）`labels.T5.label="cond"`——T5 GoldLabel 仅 pos\|neg，cond 是 m4 三值残留 | sysdesign H6 审计检出（grep 实证 753 行；另 manifest label_counts 以 pos10774/neg6254/cond753 记账而非文件真值 neg7007） | **已关闭（arch 裁定 + 双段验证）**：cond→neg，四条理由——①§3 权威性（conditional 是被评正确的应答行为 ⇒ must_flag=false，detector flag 会推动过度拦截 = FPR 门要罚的失败模式）；②类型一致（与 T6 cond→neg 同型，非阳性态落 neg）；③拒绝 cond→pos（标签与 chosen-verdict 权威解耦）与双键方案（污染 T6 构念）；④753 行是挑战区边界**难负例资产**，保留不弃。落地全链验证：dataeng 全量投影 ✓（label_counts 真值 pos10774/neg7007）→ 行内溯源回填 ✓（commit 89da085：恰好 753 行 `label_detail.m4_verdict="conditional"`，schema 0.3.11 键，sysdesign 全量四层终验 v2/v3 证据双录）→ manifest.notes 登记裁定 ✓。通用条款 adr-1b §6.10（arch） |
| D-13 | 2026-10-21 | 事实一（实现缺陷，deveng v1-1 修复链）：fp32 sigmoid 在 logit>~16.6 饱和为 1.0，score 空间 τ_flag=min(0.999, neg_max+δ) 上限在良性行饱和时被压至 neg_max 之下，**破坏 ADR D8 零 FP 构造**（v1 实测 T2 283 FP / T4 4 FP，均为 score=1.0 的标注良性行）。事实二（数据缺陷，arch 检出）：T1 标签 bug（共享评测集污染） | deveng 检出+修复；Lead/arch 双裁决（**取代链**） | **已裁定关闭（取代链登记，2026-10-21）**：①Lead 初裁：v1-1 = 官方读数对象、283 FP 定性实现缺陷、v1/v1-1 双披露——**被 arch 后续裁决取代**：T1 标签 bug 热修 → **v1 系读数全作废**，v1-1 裁决作废归档；②官方读数对象 = **v1-2**（热修数据 + logit 域校准 + 重训，D2 缓存红利 <5min 完整重跑）；③**技术内容保留有效**：logit 域校准正解 τ_l = neg_max_logit + δ（δ=1.0 logit），应用时 logit 比较，score 字段仍为 σ(logit) 原始回显（adr-1b §6.1 不变），thresholds_applied 回显实际应用阈值（N-1 同源原则）。schema 落地 **v0.3.13**（commit 447aab5，NON-BREAKING additive：可选 flag_logit/strong_logit + m6_check_response 加固 logit 带序与 σ(τ_l) 回显一致性断言），v1-2 直接复用，旧载荷向后兼容实测绿 |
| D-14 | 2026-10-22 | v2 数据波（dataeng 970764a）引入 v1 冻结契约未预见的三类新形态：①`kind="document"`（文档形，ADR-2 D-18 检索增强长文档/合法 PII 文档）；②input.messages 含 `role="tool"`（toolout 轨迹：assistant JSON 工具调用 → tool 结果轮循环）；③manifest `projection_gate.note`（门规则自述键） | sysdesign 全量审计首跑检出（28 fails：1,800 document 行 + 2,769 toolout 行 + 1 note 键）——**定位为 schema 滞后非数据违规**（形态设计已由 ADR-2 D-18 裁定） | **已关闭（schema 演进吸收，v0.3.19）**：①m6-common Kind 枚举 +document、Role 枚举 +tool（描述含 toolout 轨迹语义）；②m6-manifest projection_gate +note。**吸收后全量四层重跑全 PASS**（证据 reports/m6/h6-audit-v2wave.txt）：26 文件 invalid_total=0 / 规模门 6/6（train T2 pos 2,970 +844、T6 pos 4,050 +2,000——forged-auth 800 双键 + toolout 轨迹 + jb-variant） / eval_family 全覆盖（challenge-mirror 1,100→1,250，lawful-pii 150 eval_family=challenge 一致） / manifest 0 违规 + 23 条目对数全吻合。**交叉互证**：审计结构计数 3,102 投影 ids（0 diverged）= projection_gate.checked=3,102 精确一致；scope {conditional:1603, safe:1499} 遵守 conditional+safe 硬边界（high-risk 零出现）。ADR-2 D-17 契约栈（union 白名单四维/projection_gate/scope 可审计）全链落地验证 |

## 13. 版本与变更控制

- 本规格 v1.0.0 随 03:30 冻结；修订走 §12 偏差表 + 版本号递增，不原地静默改。
- 契约变更：改 schema 文件 → `scripts/m6_check_schemas.py` 全过 → SCHEMAS.md 登记一行（版本/日期/变更/动机/影响面）→ 消息通知三端。
- 实现偏离规格：登记 §12，由 arch（小冲突，Lead 授权裁量）或 Lead（大冲突）裁决。

—— SYS-1 完。咬合：ADR-1/1b（架构）· DATA-1（数据矩阵）· DEV-2（特征抽取）· QA-1（评测口径）。
