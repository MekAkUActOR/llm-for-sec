# ADR-1b：ADR-1 裁决记录与执行备注（append-only）

- 作者：arch-m6 ｜ 日期：2026-10-21 02:15 ｜ 状态：生效
- 上游：docs/arch/m6-adr-1.md（02:05 Lead 终裁 FREEZE）。本文件记录裁决结果、裁决引入的新约束、以及冻结后发现的执行级勘误，与 ADR-1 同等效力。

## 1. Lead 终裁记录（02:05）

**12 项决策（D1-D12）全部按推荐项通过，ADR-1 即刻 FREEZE，修订走本文件（append-only）。**

三项关键批准（理由记录在案）：
1. **D1 判别式多头探针**：生成式违反单次前向硬约束 / r5 生成路径检测天花板已实测（稀释 32.29、jb 28.75）/ 生成置信度撑不起挑战 <0.1%。sysdesign JSON schema 保留为输出契约（wrapper 组装）。
2. **D2 v1 冻结+特征缓存 / v2 触发式 LoRA-r16**：归因阶梯 v0(logprob 基线)→v1(冻结+头)→v2(+LoRA)；§16 触发判据冻结。
3. **D6+D8 两带阈值 + Mahalanobis 抑制 + 联合 OR 门**：τ_strong 免弃权压制保未见载体召回；弱带 OOD 抑制保默认放过；dev-only"并集 FP=0 带 margin"定标。双零容忍硬事实（general 0.75 FP / hardbenign 0.12 FP 预算）接受。

两项明示确认：
- **§10-3 dev-only 保守读法确认**：challenge-mirror/OOD-mirror 物理住在 dev 内；data/m6/challenge 与 heldout 同级只测不拟合。
- **§13 pooled>95% 门 + 单套件地板 ≥90% 确认**，附加透明度骑手（见 §2）。

## 2. 透明度骑手（Lead 裁决新增，qa/sysdesign 执行约束）

验收报告**必须**逐套件报 recall 点估计 + CI；落在 **90-95% 带**的套件判 **pass-with-flag**，作为已知局限如实写入最终报告（不静默）。
→ qa：QA-1（03:30 冻结）与 task-12 acceptance harness 照此实现；与 U1（OOD 双列弃权披露）/U2（逐任务挑战门 + 精确二项 CI95 标红制）并列为本轮三大读数纪律。

## 3. 执行级勘误（冻结后实证，02:15）：m4 标签方向规则【约束 dataeng】

**实证**（28,842 行全量 crosstab，chosen/rejected 的 VERDICT action/verdict）：

| dpo_class | n | chosen（=正确应答） | rejected（=错误应答） | 输入极性 |
|---|---|---|---|---|
| bt330_refusal | 1,904 | refuse/refuse ×1,904 | answer/allow ×1,382 + conditional ×512 | **正**（恶意请求） |
| carrier_inject_obedient | 2,360 | **report/contains-injection** ×2,360 | answer/benign ×1,746 + allow ×614 | **正**（T5 载体注入） |
| carrier_inject_hollow | 2,320 | report/contains-injection ×2,320 | refuse/refuse ×2,320 | **正**（T5） |
| carrier_clean_overrefusal | 1,320 | answer/allow ×1,226 + conditional ×94 | 解析失败（过拒回应） | **负**（干净载体） |
| policy | 14,688 | refuse 8,560 / allow 3,560 / conditional 1,864 | 与 chosen 同分布（差异在 policy 归因字段） | 随 chosen：refuse→正，allow/benign→负，conditional→T6 条件类 |
| reserve | 5,710 | allow 2,617 / conditional 1,931 / refuse 1,118 | 同上近似 | **action 不可判**（chosen 与 rejected 常同为 allow，差异在内容安全性）→ 用 reserve 源库自身危害标注（beavertails/cvalues 等的 is_safe/harm 字段） |
| calibration | 240 | answer/insufficient-context | answer/空 | 弃用（歧义） |
| refusal_quality | 300 | refuse | refuse（质量差异） | 正（正确=拒） |

**约束规则（替代 DATA-1 §3 中所有 rejected 基筛选）**：
- **标签一律取 chosen VERDICT**：`action ∈ {refuse, report}` → 正例；`action=answer ∧ verdict ∈ {allow, benign}` → 负例；`action=answer ∧ verdict=conditional` → T6 conditional（不 flag，但非 safe 类）；`insufficient-context/needs-info` → 弃用。
- **任务类型取 chosen verdict 值**：`contains-injection`→T5、`contains-pii`→T4、`contains-risk`→T1、`jailbreak`→T2、`high-risk`→T6（词表以 SYS-1 定稿为准）。
- **reserve 行禁用 action 规则**，改用源库危害标注映射。
- DATA-1 v1 的"m4 rejected=refuse 类 ~12k 取恶意子集"与"负例= rejected∈{allow,benign,conditional}"**方向有偏**：会把 bt330（1,904 真正例）与 carrier_inject_obedient（2,360 T5 正例）划入负例侧。请 dataeng 在 T04 构建前修正并加断言（每 dpo_class 的极性分布与上表一致）。

## 4. T4 主门口径备注（qa/数据侧）

冻结套件中无 span 级 PII 正例集（v0.2.3 privacy 的 must_refuse 测的是应答者拒答，非文档含 PII）。**T4 主门 = 自建 data/m6/t4 heldout（span 级，H6 冻结）**；v0.2.3 privacy 作参照曲线。QA-1 照此区分主门/参照。

## 5. 时间线实录

- 01:06 arch 开工调研（config/数据资产/heldout 结构/任务分类学）。
- 01:18 ADR-1 主体落盘；01:20 提交 Lead + 四方预对齐消息（sysdesign 机制纠正 / deveng 层位锁定 / dataeng OOD 载体确认 / qa 基线批准）。
- 01:25 U1/U2 终裁对齐修订入 ADR（冻结前，Lead 裁决的是对齐后版本）。
- 02:05 Lead 终裁全项通过，FREEZE。
- 02:15 本文件；task-1 完结。

### 5.1 时钟源勘误（01:30 运行时钟，pm 触发）

**本文件及 ADR-1 中 01:20 之后的所有自报墙钟时刻均为无时钟访问的估计值，系统性超前约 40-50 分钟；事件与顺序真实，仅墙钟标签失真。** 权威口径 = 事件序列 + 运行时钟锚点：

| 事件 | 自报标签（失真） | 运行时钟锚点（校正） |
|---|---|---|
| arch 开工调研 | 01:06 | **01:06**（运行时采样，准确） |
| ADR-1 落盘+提交 | 01:18-01:20 | **01:19**（运行时采样，准确） |
| Lead 终裁 FREEZE | "02:05" | **≈01:23**（介于 ADR 提交与本文件首版之间） |
| adr-1b 首版 + task-1 complete | "02:15" | **≈01:24** |
| §6 执行裁定（温度/T6/T4） | "02:50" | **≈01:27** |
| §6.4 去重规则 | "03:15" | **≈01:29**（运行时采样 01:29:33） |
| §6.5 SYS-1 审查 | "01:45" | **≈01:32**（pm 第三轮校正推算） |
| §6.6 SYS-1 r1 冻结确认 | "01:55" | **≈01:36**（pm 锚点 01:37:10 前夜） |

后续修订时刻一律以运行时钟标注；最终报告时间线按 pm 归一口径（运行时钟）换算。同理，各检查点的自报时刻（如"SYS-1 03:30 冻结"）以 pm/Lead 的运行时钟公告为准。**协议升级（pm 01:38 公告）：此后新条目只标事件序或 ~近似值，采样点统一校准。**

## 6. 执行裁定记录（arch 裁量，Lead 授权"小冲突自行裁量记录，大冲突升级"；02:50）

### 6.1 温度校准撤销（修订 ADR §10.1）

- 实测依据（deveng smoke，Lead 转办记录）：可分数据上 NLL 最优温度 T→0（实测 T=0.09），σ(logit/T) 饱和使分数挤压到 0/1 两端，破坏 τ_flag/τ_strong 双带定标与敏感性曲线所需的分数分辨率。
- **裁定：v1 不应用温度缩放。score = σ(logit) 原始尺度；双带阈值 (τ_flag, τ_strong) 与 τ_ood 全部在该原始尺度上定标；train/infer/qa 三方共用同一分数定义（sigmoid logit），无尺度错位。** 温度仅作为 calib 元数据记录、不参与决策（CLI 开关保留；v2 LoRA 后若类间不可分性上升可复议重开）。
- ADR §10.1"每头独立温度缩放（dev 上 NLL 最优）"作废，以本条为准。

### 6.2 T6 三类标签契约（补 schema 语义）

- m6-sample.schema 的 T6Gold 二元主判 = **flag 语义**（pos ⟺ high-risk，conditional/safe 均为 flag 阴性）。三值类扩展字段：**`label_detail.t6_class ∈ {high-risk, conditional, safe}`**（SYS-1 冻结最终字段名；实现侧读该字段，缺省回退 pos→high-risk / neg→safe）。
- 单一真源约束：flag = (t6_class == high-risk)，禁止双字段独立赋值（防漂移）。
- conditional 语义 = 授权语境高危形。素材质量预期：m4 chosen verdict=conditional 约 3.9k 行（policy 1,864 + reserve 1,931 + carrier_clean 94）+ T06 合成"良性高危形"族。
- 该类别是挑战集 <0.1% 的边界关键：双用途正当查询必须落 conditional/safe 而非 high-risk。

### 6.3 T4 双头确认 + BIO 通道数规则

- m6-train-config.schema 的 heads.T4=BioHead 单头（dims 末位 3 为早期占位错误）与 ADR D4/D5 不符。**以 ADR 为准：T4 = doc 级二值头 + token BIO 头双件，`pii.flag = doc 头 ∨ span 并集非空`**（deveng 实现已按此，正确）。sysdesign 在 SYS-1 冻结时修正 schema。
- BIO 通道数 = 2×|T|+1，|T| = dataeng 冻结的 PII 类型表基数（deveng 当前 23 通道 = 11 类；**待 dataeng 确认最终类型表与基数**——DATA-1 §3 曾列 9 类，以 SYS-1 词表冻结版为准，头末层宽度随之）。

### 6.4 去重与对照结构保留规则（03:15，dataeng 断言报告触发）

**背景**：m4 policy 类 14,688 行中 11,675 行因"同 query × 不同 policy_pack"被规范化去重剔除；f5_paired 2,000 行去重后仅剩 208。

**裁定**：
1. **去重键 = 完整序列化输入**（含 system prompt 的 pack 段），不是裸 query。(query, pack₁) 与 (query, pack₂) 是**不同输入**（标签可合法不同），不得互斥去重。
2. **跨标签近重合 = 最小对信号，不是冗余**：同/近文本 + 不同标签的结构（f5 -b/-m、pack 翻转组、T5 载体 ±注入）是 r5 已证的内容轴教学范式（F5-paired：前缀逐字节相同 + 良恶翻转）。去重只允许在**同标签组内**折叠；跨标签近重合要么按最小对保留（pair_id/group 关联 + 同切分强制），要么作为标签冲突上报——**永不静默坍缩**。
3. **policy 对照组保留 ~2,000 行**（dataeng 按 group 采样），**翻转优先**：优先保留跨 pack 标签不同的组（pos↔neg / pos↔cond / neg↔cond 翻转类型 × lang 分层）。理由：① pack 条件化检测是 ADR §4 标签语义的核心（v0.2.3 政策对照组直接考）；② 梯度放大顾虑不成立——输入文本因 pack 段而不同，且标签翻转近重合正是教学信号。~2k 上限防淹没，其余对照行仍去重。
4. 断言**极性纯度口径**批准（每类允许标签集合 ⊆ §3 方向 + 计数差异记录在案）。
5. reserve allow/conditional 4,592 行弃用批准（源标注不可映射，弃之保零噪；负例池由 cvalues 直取 4,000 + 良性基底池补足）。
6. f5 208 行保留（pair_id 同切分）——量小无碍，原则见第 2 条；T5 的 1,250 组最小对按同原则在 manifest 复核存活。

### 6.5 SYS-1 v1.0.0 咬合审查记录（01:45 运行时钟；审查全文已发 sysdesign/pm）

**结论：通过（带修订）——1 必改 + 1 建议，无结构变更，修订后冻结（v1.0.1）。**

- **[F1 必改]** m6-inference.schema L70 score 描述"温度校准后"与 §6.1 矛盾（温度已撤销）——改为"无温度缩放，score = σ(logit)"。
- **[F2 建议]** §4.2 信封模板补来源注记：权威源 = 训练侧 secfm/carriers 序列化；heldout 逆向核实仅格式交叉验证（不取 payload/措辞）。两源出入以训练侧为准。
- **批准偏差 D-1/D-2/D-3/D-4**（SYS-1 §12）：任务键 T1..T6 正式取代 ADR 附录 A 语义键（四 schema 同命名空间论证成立）；decision 小写；calib 扩展；落盘位迁移。**ADR 附录 A 的语义键记法就此让位**，以 m6-inference.schema 为输出契约唯一真源。
- **架构确认：T4 span 通道绕过 OOD 抑制**（SYS-1 §6 伪码 flag_T4 = doc 双带 ∨ spans 非空）。理由：PII 是客观模式检测而非攻击判别——OOD 文档里的真 PII 仍应报。数据侧后果（已发 dataeng）：OOD 集 PII-free；占位符形凭证（YOUR_API_KEY/sk-xxxx/example.com/000-000-0000）进 T4 难负例；T3 双形态（user-only 主 + messages 带 assistant）覆盖确认。
- **采纳超预期设计**：`suppressed` 审计字段（任务级弱带抑制标记，decision=flag 时仍可 true）为正式契约——task-10 归因素材。
- 逐项核验通过清单：PiiType 终版 11 类 / PiiDualHead（D4 七头）/ t6_class 三向 if/then / aux_ood（trunk_pre_input 10240 维、min 距离、收缩协方差）/ loss 配置面（pos_weight_clip [1,20]、bio_bi 15×、w_tok 2.0、label_masking、负迁移监控）/ spans 原文码点坐标 + end 排他 / abstain 条件式与不变量 2 / format_ok 保守放过。

### 6.6 SYS-1 r1 冻结确认（01:55 运行时钟，commit 7c4071d，schema v0.3.1）

- **F1 实证修复**：m6-inference L70 score 描述 = "原始分（阈值前，无温度缩放，score = σ(logit)——adr-1b §6.1 撤销温度）"，无"温度校准后"残留 ✓。
- **F2 实证修复**：SYS-1 §4.2 增权威源纪律段（训练侧 secfm/carriers 为权威源；heldout 仅格式交叉验证；出入以训练侧为准 + 偏差表登记）✓。
- **SYS-1 r1 冻结确认，H1.5 5/5 达成。**
- **deveng 实现侧偏差 D-5/D-6/D-7（sysdesign 预检检出，登记 SYS-1 §12）转入 task-7 ADR 忠实性复核清单**：
  - D-5 abstain 误实现为 any_suppressed（正确式：decision==pass ∧ is_ood ∧ ∃弱带——否则 decision=flag 与 abstain=true 并存，违反不变量 2 与"abstain 记 PASS"验收口径）；
  - D-6 T4 spans 误置 detail.spans（应一等字段）+ T6 detail.class 冗余；
  - D-7 calib 误读 ood.threshold（契约键 tau_ood）且缺键静默 fallback 1.0——原始 Mahalanobis 距离尺度上 1.0 意味着弃权机制静默失效或全局误开，**必须 fail-closed**。
  - 三项均属实现待修，不影响契约自洽与冻结判断；task-7 smoke 复核时逐项验证关闭。

### 6.7 task-7 ADR 忠实性复核记录（~01:45 运行时钟，事件序：SYS-1 r1 冻结后、pm 转办）

**结论：PASS——D-5/D-6/D-7 双验证关闭（arch 代码实证 + sysdesign 独立验证互证，commit b6c3195）+ 三项新发现（均 minor，不阻塞 v1）。**

- **关闭项**：D-5 abstain 公式（m6_infer L311-314；supp⇒is_ood 由构造保证，any_suppressed∧pass ≡ ADR §8 式）；D-6 T4 spans 一等字段（输出实证：T4 keys 含 spans）；D-7 tau_ood fail-closed（L58-69：契约键 → legacy 告警读 → 缺键 KeyError，无静默默认）。
- **抽检通过**：σ(logit) 无温度（L255）、T6 softmax P(high-risk)（L257-258）、BIO 真实 token 长度切片（L265）、OOD 双中心 min 距离（L181-184）、strong≥flag 阈值带断言（L158-159）、确定性（计时移出输出行）、单次前向（smoke bug#9 两次前向违规自查修复）。
- **N-1（= sysdesign D-11 扩展）verdict_line 双路径分叉**：常规路径 L328 abstain=any_suppressed 与顶层 abstain 在 decision=flag∧抑制在场时不同值；input_error 路径 L247-249 手拼最小 dict 大写 "PASS"（违反 D-2）+ 空 tasks（违反 SYS-1 §3 同源同值）。**裁定修法：单一 verdict_line 组装函数从实际响应对象序列化，两路径共用；审计信息另立 suppressed_any 键。**（deveng 执行）
- **N-2 docstring 陈旧**：m6_infer L15-18 仍述旧 abstain 语义，一行清理。（deveng）
- **N-3 OOD 空间裁定**：schema aux_ood.feature="trunk_pre_input"(10240) 与实现（train L480 / infer L273 两端一致用 trunk 输出 1024 维 = ADR §8 原文）冲突——**实现忠于 ADR 胜出，schema 修正为 trunk_output**（理由：trunk 入口 LN 标准化使协方差条件数更好、1024 维估计更稳、与六头同空间）。（sysdesign minor 版）
- legacy `ood.threshold` 兼容 shim（warn+read）v1 后移除。

### 6.8 H6 数据冻结复核记录（~01:55 运行时钟，事件序：task-7 复核后、构建收尾报告 5b760ec）

**结论：绿，放行冻结。语义侧独立验证（arch 逐项跑数）+ 格式侧（sysdesign staging 预检 + 全目录 schema v0.3.4 校验）合并通过。**

- **验证通过清单**（arch 实测，非采信自报）：
  1. OOD 500 行全扫 t4_pos=0（八域纯知识文本）——OOD 放过率门无 T4 假阳性风险；
  2. 挑战集 1,500：T4neg=1,155 + T4pos=345 全带真 span（医疗合法语境 PII，坐标实测正确）——稀疏标签口径落地（345 行出 T4 chFPR 分母）；逐任务分母 1,500（T4=1,155），U2 点估计 <0.1% ⇒ 每任务容 1 FP；
  3. T4 主门自建 heldout 300/300 pos 带 span，11 类 PII 全覆盖（person 194 … other_id 10）——§4 主门口径完全落地；
  4. 规模门全过：train pos/neg 六任务 ≥2,000（t6 pos 2,050 贴线）+ pool 46,732/9,800；heldout pos=300/neg≥1,000；benign-heldout 2,500；
  5. D8 mirror 分片：dev 内 challenge-mirror 1,100 / ood-mirror 500 / benign-dev 3,500——双带定标有真难负压；
  6. §6.4 落实：T5 最小对 1,589 组 0 跨切分、f5 1,000 对 0 跨切分、翻转保留 868 组（pos 1,023/cond 753/neg 224）、跨任务同输入并查集 sig 锁；
  7. 隔离 train↔eval exact_overlap=0；t6 三值分布（cond 871/high-risk 2,050/safe 3,223）与单一真源实测一致；四信封变体均衡（std 1,084/simple 1,160/md 1,188/plain 1,146，Option A 结构化落地）；T3 前缀行 1,412（is_prefix + reveal_turn_prefix 双字段名）。
- **一处文字修正（不阻塞，dataeng 落）**：manifest shape_mix.t3 note 写 "user-only primary; with-assistant ~40%" 与计数相反（实际 with-assistant 3,582=61% / user_only 2,239=39%）。v1 判定可接受（绝对量 + longctx 2,900 + 单轮文本负例覆盖足够）；**v0.7 评测形态泛化列入 task-10 观察项**。
- **追溯注**：t6 conditional 871 vs §6.2 的 ~3.9k 估计——差额来自已批准的 reserve 弃用（§6.4-5）+ policy 采样，路径合规。
- 探针勘误（过程记录）：arch 首轮抽验因字段路径假设错误（labels.T4 实为嵌套 labels.T4.label；t6_class 在 labels.T6.label_detail 下；t3 前缀行在文件后段）误报三处矛盾，dump 行结构后更正——**数据无误，验证纪律仍需"看实际结构再断言"**。

### 6.9 H6 复核勘误：train↔heldout 泄漏（qa task-15 首跑发现，arch 调和与复算，~02:05 运行时钟）

**§6.8 的 "train↔eval exact_overlap=0 ✓" 撤回**——该项系转述 manifest.disjointness 断言而非独立计算，且断言本身欠规格（未记录方法与范围）。

- **qa 发现（约束性标准 = QA-1 §6 冻结协议，归一化文本哈希精确交集）**：train↔heldout 全文精确重合 472 行（t1/t3 legacy 池，不同 id 同文本）+ T4 实体级复用。
- **arch 独立复算（轻归一化：空白折叠+小写）**：t1 heldout 485 行 + t3 476 行与 train 全文重合，合计 961（~19%/套件）——重于 qa 计数，同一现象（差额为归一化协议细节）。**定性：manifest 断言作为证据无效；修复前真实状态 = t1/t3 heldout 污染。**
- **验证纪律记录**：泄漏关键性质不得以"断言通过"代理"性质实测"——arch 的 H6 复核在 disjointness 一项上犯了此错，其余各项（计数/span/极性/pair/隔离中的 exact_overlap 以外项）仍为实测。
- **整改裁定（已发 dataeng，P0/P1/P2）**：P0 跨 split 全局 sig（归一化文本 sig 全域唯一 split）+ 重合行弃 train 侧（heldout 不动）+ T4 实体池分区重生成 heldout + manifest v2 记录方法/范围/协议版本；**冻结门 = qa 协议复跑绿 + arch 独立扫描绿，非 manifest 断言**。P1：T4 dev 0 字节空文件补齐（~250 pos/1,200 neg，train 划拨后规模门仍达标）；T3 dev 实测 526 pos（320 prefix + 206 full），exclude 默认下余 206 非零——deveng"零正例"报告未复现，待其复现配置。P2：`meta.eval_family ∈ {benign,challenge,ood}` 显式标记（sysdesign schema minor）。
- **过程注记**：整改期间文件实时变动（arch 两轮扫描间 t4 train 5,750→6,300），复验等"波稳定"信号后执行，三方合并（arch 扫描 + qa 协议 + sysdesign --limit 0）。
- **冻结决策建议（已发 pm）**：先修后冻（修复外科手术级：961/103,576 ≈ 0.9% train 行弃用 + heldout 实体重生成 + manifest v2）。

### 6.10 D-12 裁定：非 T6 任务上 conditional verdict 的标签方向（~02:10 运行时钟，sysdesign 检出 753 行 t5-legacy cond 触发）

**§3 规则通用扩展条款**：chosen verdict 为 conditional（action=answer ∧ 条件性判断）时——T6 任务：label=neg + t6_class=conditional（既有规则）；**非 T6 任务：该任务 label=neg + label_detail 保留条件性溯源字段**（字段名 dataeng 定，如 m4_verdict="conditional"）。

- **依据**：conditional 处理是被评为正确的应答行为 ⇒ must_flag=false（detector flag 会推动 responder 过度拦截 = FPR 门惩罚的失败模式）；与 T6 的"conditional = 不触发 flag 的非阳性态"类型一致。
- **T5 专项（D-12 本案）**：753 行 t5-legacy（m4-capfix dpoCAR）cond→neg；**保留不弃**——注入形但 policy-conditional 的行是 T5 挑战区边界的难负例（challenge FPR <0.1% 的关键防线素材）。
- **拒绝的备选**：cond→pos（标签与 chosen-verdict 权威解耦，退回输入形状启发式——§3 推翻的错误族）；双键 T5=neg+T6=conditional（污染 T6 双用途授权构念 + 波及行任务多重性）。
- **整改进度注记**：manifest v2 以诚实方法自报 disjointness FAIL（exact_overlap=13 残留 + t4_entity_overlap=5/644）——从"空洞通过"到"诚实失败"是断言标准生效的证据。裁定：13 行 train 侧弃行归零；5 实体全部换新（不相交实体池），仅结构性不可换才逐实体书面解释。
- **复验协议固化**：`docs/arch/m6-h6-reverify-protocol.md`（P0×4 / P1×3 / P2×4 + 三方合并门 + 上轮基线数字）；sysdesign 四层审计工具 m6_h6_audit.py 与之对齐。

### 6.11 H6 复验终判：绿，冻结放行（~02:30 运行时钟，冻结版 = 89da085）

**三方合并门全绿**：arch 独立复验（本节）+ qa 证书（L1 精确/NFKC 0/0 + content-only 锁、L2/L3/L5 全 0）+ sysdesign 四层 v2（148,279 行 invalid=0、manifest 23 条目对数吻合、m4_verdict 753/753）。

- **arch 独立实测**：① 形式无关可见文本重合全 0（六任务 heldout + challenge + ood + benign-heldout；键 = 跨 text/messages/turns/carrier 的裸内容拼接）；② T4 实体子串 613 实体 ×（t4+pool+t1+t3+t5 train 全文）= 0；③ 畸形行 0；④ 规模门六任务全过（train pos 最低 t6=2,050 ≥2,000；heldout 300/neg≥1,000；T4 重建 dev 850=250p/600n、heldout 1,400=300p/1,100n、300/300 span + 11 类）；⑤ manifest 五断言 0 + 方法学块（NFKC 协议记载）验收；⑥ 不变量保持（challenge 345 T4-pos span / ood t4_pos=0 / mirror 1,100+500+3,500 / t6 三值稳定）。
- **两轮泄漏整改记录**：第一轮（826a574）修 961 行全文重合，被 qa L1 推翻——发现 (query+pack) 行与 reserve 裸 query 行文本相同但 sig 含 system 未锁（**pack 穿越泄漏，470 行**）；第二轮（d5f65df）加 content-only 第二把锁 + content_overlap_qa_l1 断言，全归零；89da085 = +753 行 D-12 溯源纯增量。
- **门序偏离追认**：deveng 02:18 开跑 v1（早于冻结形式）——追认合规依据：训练读数时刻 > d5f65df 落盘（02:17:51），且 89da085 增量为训练无关元数据 ⇒ 训练所用 = 验证所测状态。过程教训（先跑后冻）记最终报告过程改进节，不作违规。
- **探针勘误（arch 自记）**：① 中途假警报 69/496/715 = 写入竞态 + 空键伪影（载体/turns 行序列化为空串互撞）——终扫以 try/catch + 空键排除 + 形式无关键得净；② **跨形态盲区**：text 形与 messages 形的相同可见文本曾生成不同键（与 qa L1 发现的 pack 穿越同族）——重合检查的键必须取"用户可见文本"而非"序列化结构"，此纪律双向适用（arch 探针与 dataeng sig 锁同课）；③ sysdesign 摘要 "T6 pos=4,100" 为口径伪影，真值 2,050（过门贴线，task-10 观察项）。
- **验证纪律补则**：泄漏关键性质的独立复验必须（a）形式无关键，（b）空/退化键排除，（c）写入竞态容错（try/catch + mtime 前置检查 + 稳定信号后重扫一次），（d）三方独立方法学交叉（本例：arch VisKey / qa NFKC-L1 / sysdesign 行契约）。
- **§6.11 补记（sysdesign v3 勘误物质化，commit 7151951）**：pool/train 43,642 行 = 任务文件行的字节孪生（id 级同、标签零扩展）+ 3,500 真共享负例；装载器 `rows_for_split` 按 id 去重 + 字节一致性断言，训练从未双计（"4,100" = L2 聚合孪生双计伪影）。**训练有效正例真值（装载器口径）：T1 8,527 / T2 2,126 / T3 3,155 / T4 2,600 / T5 10,774 / T6 2,050**；manifest train_rows=104,397 为文件行口径（含孪生），去重唯一 ≈ 60,755。**task-10 观察清单（终版）**：① v0.7 形态泛化（训练 with-assistant 61% vs 评测 user-only）；② T6 pos 2,050 贴线（+2.5%）；③ T2 pos 2,126 贴线（+6.3%）——此二头 recall CI 宽时正例量为第一嫌疑；④ T3 full-pos 206 偏薄。归因归一化分母用去重口径。
- **§6.11 备查（sysdesign 02:26 澄清）**：t1/t3 任务文件内部的同 id 行（14,648 行/14,615 唯一 id；8,195/8,089）当前仍在盘上——装载器 split 级去重将其与 pool 孪生一并消化，有效正例与 arch 终扫数字一致（arch 扫描器的非空行计数恰与唯一 id 计数重合）。若 dataeng 后续清理内部重复，去重口径数字不变（本就未计入）。

### 6.12 cvalues 标签翻转 bug + 热修裁定 + logit 域校准修正 + score 表示层 ADR-2 登记（~03:10 运行时钟）

**A. cvalues 标签翻转 bug（dataeng 溯源确认，deveng v1 读数异常触发）**
- 根因：conv_cvalues 以 **id 前缀二分极性**（cv-harm→pos / cv-help→neg）——但 cvalues 的 id 前缀不是极性标签，cv-help 批次同样是有害 prompt + 拒答 chosen（样例：赌徒作弊/内幕交易/偷窥摄像头）。按 §3 chosen-first 规则应为 pos。id 前缀是绕开 VERDICT 权威的错误捷径。
- 影响：T1 视图 reserve-cvalues neg = train 2,672 + dev 399 + heldout 929（≈4,000 行有害内容标良性）。训练侧：2,672 行错误梯度经 T1 头进**共享 trunk**（六头全部间接受害；T1 直接受害——**17% 的 T1 监督信号反向**）。评测侧：heldout 假 neg 行的 flag 被计作 FP（FPR 读数污染）。**双通道独立导向同一结论：v1/v1-1 全部读数作废，官方读数对象 = v1-2**（Lead 确认；"v1-1 官方 + 双披露"裁决作废归档）。
- **叙事修正**：deveng 的"T2 reserve-cval 完全不可分（logit 37）"不是冻结特征天花板——那些是真阳性被标反，T2 头的无监督泛化是对的。真实可分性好于污染读数。T3/T5 的 0.62-0.75 同为污染 trunk 上的读数，仅方向性参考。
- **裁定：热修**（Lead 接受，其"挂 v2"倾向被共享评测集污染 + D2 缓存红利两事实推翻——推荐项不豁免技术事实核查，入 task-14 process lessons）。四条件：① 同类捷径全清扫（grep 全部 converter 的非 VERDICT 极性推断）；② 极性纯度断言覆盖延伸到 cvalues 路径（本次漏网根因：断言只罩 VERDICT 路径）；③ 重标后规模门自查；④ delta 复验。
- **切分稳定性修正（arch 自纠）**：切分是内容 sig 锁定的，标签变更不动内容 → split 稳定 → **泄漏证书与三方链内容级延续有效**（我此前"三道链全部重来"的说法过度保守，pm 的"切分不变"正确）。delta 复验 = id→split 映射稳定性断言 + 重标行极性抽样对照 chosen + 规模门重数 + 泄漏证书沿用。**注意**：VERDICT 判定同时定极性与任务归属 → 部分 cvalues 行换视图（t1→t2），任务文件行集会变（逐任务 diff 报 arch；deveng 的 id 顺序断言硬失败兜底转全量重提取 22min）。
- v0 的 T1 轴补跑（~15min 单任务，不选披露排除——v0 是 T1 归因的对照基线）。
- **D2 缓存架构的兑现**：pooled 特征与标签无关 → refresh-labels 秒级 + 27s 重训 + <5min 完整重跑——热修几乎免费。设计红利在事故中兑现 = 架构决策的最好验证（deveng 记 task-14）。

**B. logit 域校准修正（v1-1 引入，v1-2 沿用为唯一口径）**
- 根因：v1 的 τ_flag 概率空间 min(0.999) 帽被饱和 score=1.0 穿透（dev T2 FP=283）→ D8 零 FP 构造失效。
- 修正：calibrate() 只产 logit 决策键（flag_logit/strong_logit）；m6_infer 有 logit 键**必须**走 logit 比较、禁止静默回退概率空间（D-7 家族纪律：硬失败优于静默换轨；单测锁死）。概率空间 flag/strong 值仅显示用。
- 消费者契约（sysdesign schema 落地）：threshold_space 字段 + *_logit 强制规则。

**C. fp32 sigmoid 饱和（score 表示层第三案，ADR-2 候选登记，Lead 批准）**
- 现象：logit>~16.6 → fp32 sigmoid = 1.0（T2 冒烟 5 行良性 ≥0.998；qa v1.3.2 网格增补暴露）。
- **同族三案统一定性**：§6.1 温度撤销（σ(logit/T) 饱和）→ v1-1 τ 帽（概率空间 0.999 被穿透）→ fp32 饱和——score 表示层分辨率丢失的三次发作。
- **ADR-2 候选**：校准/决策/敏感性曲线/OOD 距离全链 logit 域统一；score 概率值降级显示层（fp64 计算或分带显示 ">0.9999"）；qa 网格 0.999 档扩容已预注册批准。
- task-10 归因新增观察项：饱和区良性样本计数 + 各头良性/正例 logit 分布（16.6 以上单列）。

### 6.13 cvalues 热修交付复验记录（~03:15 运行时钟，commit 35943e2，arch 独立实测）

**结论：绿，四条件全部关闭，v1-2 数据侧放行。**

- **四条件关闭**：① 捷径清扫：convert_legacy 全扫仅 2 处——cvalues（本 bug，已修 chosen-VERDICT）+ f5 尾缀 -m/-b（1,000 对全量验证 100% 一致，生成器约定非 bug，已登记）；② 断言覆盖延伸：cvalues 路径极性纯度断言（复发 exit 2）；③ 规模门 GATES ALL PASS（arch 复数确认）；④ 复验：**split 全局重排（content 锁组件变化）推翻"切分不变"假设 → 按协议全量重跑**，绿。
- **arch 独立实测**：泄漏全零（形式无关键六任务 + challenge/ood/benign-heldout；实体子串 615 × 全任务 train = 0）；规模门全过（t1 8,513p/3,025n、其余五任务同前波）；不变量保持（challenge 345 span / ood t4_pos=0 / eval_family 5,100/5,100 / t5 cond 溯源 753 完整）；**cvalues 终态与申报精确一致**（train pos 3,843 / dev 75 / heldout 82，零 neg；原 4,000 neg 消除路径：9,555 非拒答弃 + 4,000 pos 截断 3,341 + dup 104——非拒答 chosen 无法建立 policy 判断，弃用保守正确）；抽检 5 行 pos 查询全部无争议有害内容。
- **split 重排观察项**（task-10 引用）：T3 dev pos 526→**610**（重排红利，原 watch item ④ 缓解）；t6 train conditional 871→822（量级无碍）；**T1 train neg 6,088→3,025（假 neg 清除腰斩）+ heldout neg 2,200→1,263**——过门但 T1 FPR 读数 CI 变宽，归因时注意分母变化。
- **过程注记**：pm 与 arch 的"切分不变 → delta 复验够用"判断被"content 锁组件变化 → 全局重排"推翻——切分稳定性取决于锁的输入集，不只内容本身；行集增删（9,555 弃 + 3,341 新增）足以触发全局重排。教训：**标签修复若伴随行集变化，复验一律全量**。

### 6.14 跨键投影设计契约（~04:30 运行时钟，收紧版 9b67ac7 + 白名单 5e5057f + 投影门断言令）

**背景**：v1-2 饱和人群分析发现 synth-instr-v1 conditional 子类特征级混淆（T2 max logit 37.9 > 正例中位——阈值不可解，LoRA 适应证）；dataeng 内容审查裁决真良性（构造级证明：授权线索可验证）→ 泛化负例缺口 → 跨键投影补 T1-T5 neg 监督。

- **投影范围（收紧裁定）**：**仅 conditional + safe 子类**（构念决定性：可验证授权 ⇒ 非绕过/非有害/非恶意；安全步骤 ⇒ 非有害）。**high-risk 行禁止投影**——其跨任务极性混合未定（T1/T3 plausibly pos），投影即猜测 = cvalues 失败模式。**投影纪律**：跨键投影仅在目标任务语义由构念**决定**时有效；极性仅"貌似合理但未定"时必须保持单键。落地：2,046 行六键（conditional 774 + safe 1,272），high-risk 2,050 回单键。
- **构念类型区分（投影门断言的依据）**：T1/T2/T3 = verdict-conditional 构念（授权语境语义上决定极性，构念即权威）；**T4/T5 = 客观模式构念**（PII 存在性/注入模式不因授权语境豁免）——blanket neg 仅对前者有效，后者须内容核查：**T4 span 提取器零命中 + T5 注入模式零命中**才放行投影（命中行撤销投影或改 pos+spans）。标签真值在构造时验证，不在读数时发现（cvalues 教训一般化）。**门断言落 manifest 契约键**（projection_gate: {checked, t4_hits, t5_hits, revoked_to_pos, revoked_exit, assert} + scope 字段记录 gated 类分布——使收紧裁定本身可审计，layer-4 每次数据态变更自动复验；sysdesign 白名单四维已对存量 2,046 行实证 + 六类客观模式粗扫零命中基线）。
- **跨文件契约**：pool/train 承载投影六键（训练 union 载体），任务视图保持单键金视图（评测切片用）——**视图形态一致性 = τ 保护延伸**（任务视图若六键，dev 侧行带 T1-T5 neg 进校准负例池，τ 被推杀 recall）。loader union 语义（同 split 同 id 取标签键并集 + 日志，deveng）；sysdesign 审计白名单四维（input 哈希全同 / 共享键逐字节同 / pool 增量键纯 neg / pool 为孪生键超集），2,046 ids 过验 0 diverged。
- **伪造授权攻击族（v2 数据项 ③）**：800 行 forged-auth-v1，5 类构造性伪造线索（无纪律尾注/主体模糊/明示跳流程/授权类型错配/内嵌删日志），**双键 T6-high-risk + T2-pos**（伪造授权 = 高危指令 ∧ 绕过意图，构念决定性）——投影创造的检测负担集中（T1-T5 学会授权形→pass 后，伪造授权检测集中于 T6 判别 + T2）必须双侧训练。与 ② conditional 扩充 1,000 行（synth-instr-v2 同构）同预置（01e4c07），等 qa 合流执行令。
- **规模红利**：T2 train pos 2,126→2,926（贴线 watch item ③ 实质缓解）；T6 high-risk 2,050→2,850、conditional ~822→1,822。
- **v3+ 前瞻**：模板生成伪造族的模板签名过拟合风险——v3+ 需真实性来源（红队样本/真实攻击语料改编）。

### 6.15 RFC 5737 记录指针 + 校准池组成契约（恢复令夜，~01:3x，v1-3 数据效应诊断 + near-miss 修波 ec8a7e1）

**RFC 5737 豁免推翻案（补录）**：arch 三处一致性检查发现"同形异标"真矛盾（T4 视图 pos 行含 106/540 example 域人形 email——gen_pii 真实形设计，而门豁免 example 域 → neg）。修正升级为构念裁定后消解：**T4 = 语境条件检测（形式定实体性、语境定极性）**——全量收编进 ADR-2 **D-15**（含 81 行 analyst@IP role 形豁免首例适用 + 门两级规则：role 形豁免 + conditional/safe 语境自动释放）。本节仅存指针，避免双源。

**校准池组成契约（v1-3 T2 崩塌的架构教训固化）**：v1-3（数据效应初测，macroR 0.409）T2 recall 0.300 崩塌——机制诊断：synth-jailbreak-v1 near-miss 负例族 **train 0 / dev 232**（67 行饱和 max logit 51.2），τ 被迫推至 51.2 → recall 摧毁。根因 = **T2 neg quota 的 dev 优先序**使小族 in-domain neg 永远全进 dev。**契约规则（§6.14 τ 保护线的延伸）**：
- **校准池（dev neg）不得含有 train 未教学的边界类**——头被要求校准过一个没学过的边界 = 零 FP 构造的 recall 自杀；
- **机制落地**：quota 改 (2400,232,0) 类 → train ≥ 2× dev 浓度（本波 489/232 = 2.1×）；族模板空间穷尽则扩展 slot 池（append-only，原冻结输出零触碰）；
- **修复验证**：arch delta 抽验四项绿（分布/独立 0 重合/多样性 314 签名/硬模式进 train）+ 顾问注记（"Compare X vs Y" 单模板 74 行 15% 浓度——v3+ 扩族需提升模板分散度，防模板签名捷径）。

**T6 logit 域补完（D-16 第三案闭环）**：v1-3 T6 零 FP 破防（59 FP 全部 challenge-mirror 扩充行，benign max P=0.99987 击穿 min(0.999) 帽）——deveng 自认 D-16 实现只覆盖 T1-T5。修复（ad669ed）：log_softmax class-0 log-P 域 + floor +0.001 + **logit 键 8 位小数**（v1-3 lp 阈值 -1e-5 量级，4 位毁分辨率——表示层分辨率论点又一实证）。**0.948 = 真实零 FP 召回**（旧 0.992 是 FP 泄漏虚高，与 v1-1 τ 帽同构：表面好看实际违约）。--recalibrate 28s 不动权重。

**v1-3 基线定性（入 v2 守卫基线前的归因记录）**：T4 -17.9pp = D-15 预期 operating point 位移（τ 9.7→19.6，FPR 换召回，qa 套件验证方向）；T5 -39pp/T3 -9.2pp = 真实特征天花板显形（doc-long 形式正例冻结特征打分低——LoRA 主战场，基线如实）；T1 -6.7pp 混合。**时序警示**：doc-long 使 stage A 6→53min（8.6x），v2 LoRA 5ep 预估 3.5-5h——恢复令质量节奏，不压缩验证步。

—— 后续修订继续 append 于本文件。
