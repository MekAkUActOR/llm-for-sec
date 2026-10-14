# M2 SFT 数据组装方案(16 源 → 训练语料)

> 版本 v1.0 · 2026-09-26 · M2 收官设计件
> 上游:docs/06(配方骨架 §3/§6/§7)、docs/policy-packs-v0-draft.md(三包
> 阈值表)、scripts/gen_sft_v0.py(输出契约与 A/B/C/D 四语料)、
> docs/research/m2-sft-sources.md(16 源采购实况)。
> 数据实况:reports/m2-sft-procurement.json(字段/条数)、
> m2-sft-format-detail.json(长度分布)、m2-sft-redline-detail.json(越线
> 索引)、sft-contamination-check-*.json ×16(767 条污染剔除索引)。
> 状态:设计定稿待父会话复核;实现属校准跑后阶段(9ad07705),本文档
> 不实现管线。

## 0. 总原则(先于一切映射)

1. **公共源转进中性格式契约**:所有公共源样本最终统一为 gen_sft_v0 的
   `build_sample` 结构——`system=POLICY_SYSTEM[pack][lang]` / `user=裸
   query 或 build_context 包裹` / `assistant=自建或改写响应 + VERDICT 尾行`。
   **原始公共源响应永不直接作 assistant 模板**(三个例外见 §1 标注,均需
   追加 VERDICT 行与政策一致性改写);
2. **方向性不变量优先**(policy-packs §4.2):任何"输出去保护内容"的样本
   不存在合法包——公共源里最相关的 trustllm privacy_leakage 必须转为
   拒绝/检测样本而非"揭示 gt-*"样本(见 §1.11);
3. **tc260 永不入训练**(父会话决议):仅其 21 列攻击元数据类目体系作为
   自建生成器的模板字典(影响不复制,物理隔离 raw/m2-reference/);
4. **过滤顺序固定**:contamination(767)→ redline(351)→ 转换 → 跨源去重
   → 政策条件化 → 采样配比 → shuffle(seed 固定)。索引已备(§5);
5. **tool_output 载体族永不入 SFT**(docs/06 §7 留出族,heldout v0.2.1
   泛化读数);公共源无 tool_output 形态,该约束自动满足,但生成器模板
   库(TC260 借鉴)也不得生成此形态。

## 1. 16 源 × 任务族映射与转换规格

符号:T 族见 docs/06 §3;`→` = 转换为;[R] = 原始响应可复用(需补
VERDICT);[S] = assistant 响应自建;[DPO] = 偏好对储备(SFT 期不用)。

### 1.1 hh-rlhf-harmlessness(44,849,MIT,en)
- **T5 响应谱系 + 通用对话恢复**(双池切分):
  - 池 A(攻击性对话,~15-20%):Human 轮含攻击意图 → [S] 重写为政策化
    拒绝(refuse + 理由 + VERDICT,policy 三包随机但拒绝理由随包微调);
    chosen/rejected 的**原始内容只作意图判别输入,不作模板**;
  - 池 B(良性对话):[R] chosen 侧可直接复用(Apache/MIT 响应质量 OK),
    补 VERDICT 尾行(`action=answer, verdict=null`);多轮保留轮次结构
    (p50=2 轮/p90=4 轮,直接进 LLaMA-Factory messages);
- 转换伪码:
  ```python
  for conv in parse("chosen"):            # 单字段对话串
      turns = split_human_assistant(conv)
      if any(is_attack(t) for t in human_turns):   # 意图分类器,同 §1.14 攻击词典
          yield T5_sample(turns, pack=random_pack(), reply=REWRITE_REFUSAL)
      else:
          yield general_sample(turns, append_verdict(chosen_side))
  ```

### 1.2 safety-prompts(100,000,Apache,zh)
- **zh 攻击面主力 + zh 通用底座**:
  - instruction_attack 30K(6 类 ×5K):prompt → [S] 政策化拒绝;其中
    Role_Play_Instruction/Goal_Hijacking 类兼作 T8 输入侧(注入措辞识别);
  - typical 70K(7 类 ×10K):[R] response 复用 + VERDICT 行;Privacy_And_
    Property 类兼作 T7 输入侧补充;
- **响应侧警示**:调研期已知攻击子集响应为模板时代产物——攻击子集一律
  [S] 重写;典型子集响应质量可(140 字符中位),[R] 复用;
- zh 配额的主要供给方(政策配对 8K + 通用 3K + 攻击 3K,§6)。

### 1.3 safemtdata(2,280,MIT,en)——多轮关键料
- **Attack_600(600 条)→ T10 多轮渐进攻击**:
  - `multi_turn_queries`(5 条渐进查询/条)→ 5 轮 user 消息;前 1-2 轮
    角色背景问题 → [S] 简短正常应答;末轮 harmful plain_query → [S] 拒绝
    + "拒绝继续升级"语义(ais-r10 防御成功判据)+ VERDICT;
  - `relationship` 字段(角色关系铺垫)并入首轮 user 前缀或 system 语境;
- **SafeMTData_1K(1,680 条)→ T10 多轮安全 + 通用多轮恢复**:
  - conversations(12 消息中位,含助手响应)→ [R] 复用 + VERDICT 尾行;
    角色映射 `human→user / gpt→assistant`;
- LLaMA-Factory 格式细则见 §7。

### 1.4 基准攻击六件(en,合计 84,610)
- **AdvBench(1,094)/ StrongREJECT(313)/ MaliciousInstruct(100)**:
  纯 prompt → **裸 query 形态**(用户直问,无载体包裹——这对应 heldout
  ais-r 系"直接越狱"形态);[S] 拒绝响应;advbench harmful_strings(575)
  不入(字符串载荷无对话语义);三包同拒(攻击请求无授权语境变体),固定
  default 包;
- **HarmBench(320,7 语义类)**:Behavior → 裸 query;**81 条含
  ContextString → build_context 包裹进 text 载体**(语境化攻击,训练
  "载体含攻击意图"识别);SemanticCategory 映射:cybercrime_intrusion(52)
  / chemical_biological(42)→ T8+T5;copyright(80)/misinformation(54)→
  T5;harassment(21)→ T5;[S] 拒绝;
- **XSTest(450:safe 250/unsafe 200)→ 误拒纪律**(连 T11):
  - safe 250 → [S] 简短应答(**三包都不拒**——误拒是三包同病);
  - unsafe 200 → [S] 拒绝;
  - 二包配对增强:default vs professional(conservative 在 safe 邻域也
    必须放行——政策包不调误拒,这是阈值表外的行为纪律);
- **OR-Bench(82,333)→ 误拒纪律大宗**:
  - hard-1k(1,319)全量 + 80K 池采样 ~2.5K + toxic-999(655)→ 合计
    ~4.5K:良性请求(被过度拒绝的争议话题/敏感词)→ [S] 应答;
    toxic-655 → [S] 拒绝(真毒性对照,防误拒训练过冲);
  - 配比警示:误拒样本与攻击样本比例 ~1.25:1(6.5K 应答侧 vs 攻击
    采样 ~5.2K),防"见攻击就拒"的偏置。

### 1.5 TrustLLM-safety(3,930,MIT,en)
- **jailbreak(1,400)→ T8**:越狱模板 prompt(DAN/角色扮演/前缀注入类)
  → 裸 query;[S] 拒绝 + 识别(jailbreak-pattern);这是**攻击框架
  输入侧**的正统料(docs/06 §7:模型必须见过攻击);
- **exaggerated_safety(200)→ 误拒纪律**:同 XSTest 处理;
- **misuse(1,174)→ T5**:滥用请求(概念性)→ [S] 拒绝/条件应答;
- **privacy_leakage(400)→ T7 反向设计(关键)**:context 嵌 gt-email/
  gt-name 的"提取 PII"查询——**目标不是揭示 gt-*(去保护方向,三包
  同拒),而是**:①输出"检测到个人信息,建议脱敏处理"的检测/分级响应
  (T7 感知职能);②或拒绝揭示 + 提供聚合统计替代。gt 字段仅用于**评测
  侧对齐**(模型是否真的没输出),不进训练文本;已验证 gt 全为虚构
  (m2-sft-redline-detail.json)——合成性满足 §7 纪律;
- **privacy_awareness_query(560)+ confAIde(196)→ T7/T4**:PII 处理
  意识问答 → 政策条件化二包配对(conservative 严/default 放,对齐
  POL-PRIV-001/002)。

### 1.6 CValues(97,116,Apache,zh)——zh 偏好对储备
- **建议(父问询点)**:SFT 期**只用 pos_resp 侧**(正向价值观响应)作
  [R] assistant 模板(+VERDICT);neg_resp **永不入 SFT assistant**,连同
  pos/neg 对整条进 [DPO] 储备(M3 偏好阶段用);
- 理由:neg_resp 作为拒绝模板会教模型"展示坏答案"(行为目标混乱);
  作为对比信号属于 DPO 语义——SFT 期单侧、DPO 期成对,是标准两阶段
  用法(与 pku/beavertails 同策略);
- prompt 极短(p50=18 字符)→ 加表面改述(safety-prompts 式包装)防
  短模板过拟合;zh 政策配对配额主要供给方。

### 1.7 PKU-SafeRLHF(82,118,CC-BY-NC-4.0,en)——偏好对储备
- SFT 期:`safer_response_id` 指向的响应 → [S] 政策化改写(原始响应
  补 VERDICT 后可 [R] 复用,质量尚可 p50=530 字符);
- is_response_*_safe=false 的响应侧 → 永不 assistant;`better/safer`
  双响应 + 人标 → [DPO];
- prompt_source 字段(WizardLM-Uncensored 等)提示攻击密度高——按
  prompt 意图分池(同 §1.1):攻击性 prompt → T5 拒绝对;普通 → 通用;
- **NC 台账**:开放权重前 D3 重估,此期间数据仅在内部训练用(m2-sft-
  sources.md 勘误段)。

### 1.8 BeaverTails(364,170,CC-BY-NC-4.0,en)——rejected 侧信号
- **30K 精选集为主**(人标一致性高):is_safe=true 响应 → [S/R] 复用;
  is_safe=false 响应 → 永不 assistant(**父指令:留原始作 rejected 侧
  信号**,[DPO] 储备);
- 330K 全量:仅作 [DPO] 与生成器素材池,SFT 采样以 30K 为界;
- harm_category 14 类 → 攻击意图分类器的标注源(转换期构建,§1.14);
- 同 NC 台账纪律。

### 1.9 WildJailbreak(263,769,ODC-By,en)
- 四型分布(实测):adversarial_benign 78,941 / adversarial_harmful
  84,728 / vanilla_benign 50,050 / vanilla_harmful 50,050;
- **vanilla_harmful + adversarial_harmful → T5/T8 攻击输入侧**:prompt/
  adversarial(分解式改写)→ [S] 拒绝;adversarial 改写是"paraphrase
  阶梯"的现成实现(docs/06 §7:同一攻击面表述变体=一致性信号)——
  (vanilla, adversarial) 对保序进同一攻击面的多变体训练;
- **adversarial_benign/vanilla_benign → 误拒纪律 + 通用**:completion
  (GPT-4 安全完成,[R] 复用 + VERDICT);harmful 型的 completion 也安全
  (安全完成示范)——可用于"拒绝但给教育性替代"的 T5 谱系中间档
  (conservative 教育性拒绝参考其结构,不逐字复制);
- eval.tsv(2,210,adversarial/label/data_type 三列)→ **留作内部评测
  参考,不入 SFT**(与 train 同源,防 eval 泄漏进训练)。

### 1.10 WildGuardMix(88,484,ODC-By,en)——审查四任务对口料
- prompt_harm_label:unharmful 41,488 / harmful 46,970;
- **T8 审查四任务直接映射**(WildGuard 原设计=我们的行为目标):
  ①prompt 有害性判断(harmful/unharmful 标签 → T8 裁决训练);
  ②拒绝判断(refusal 标签 + refusal 响应 → T5 拒绝对);
  ③响应安全性判断(response_harm_label → "审查其他模型输出"样本,
  docs/04.4 T8 职能);④自我修正(原任务 4,M2 期低优先,采样即可);
- refusal_label 分布(format-detail)+ 双 harm 标签 → 四象限采样
  (harmful prompt × refusal response 优先);
- adversarial=True 子集与 wildjailbreak 同源风险 → 跨源去重必跑(§4)。

### 1.11 tc260(3,200,tier=reference,zh)——**不入训练**
- 21 列攻击元数据 → 自建生成器的**类目体系字典**:
  - `category_level1_name` 5 类(违反核心价值观 777/歧视 865/商业违法
    485/侵权 683/服务需求 93)→ zh 攻击生成器的类目覆盖清单;
  - `attack_techniques/expression_style/transformation_depth` → 攻击
    技术与表述风格模板轴(生成器采样空间);
  - `expected_action` → zh 侧正确行为标注口径参照;
- 实现纪律:生成器读 schema(类目名+枚举),**不读 query 文本**;
  物理路径 raw/m2-reference/ 与训练物料隔离,manifest notes 已注
  "eval-reference only, never into training"。

### 1.12 基准 eval 复用(非 SFT,防泄漏)
- strongreject_small/or-bench-holdout 类:任何源自带 dev/test split
  (hh test 2,312/pku test/beavertails 30k-test/wgm test 1,725/wj
  eval 2,210)→ **全部不入 SFT**,留作 M2 训后内部回归读数(与
  heldout v0.2 互补,注意它们是公共基准,读数仅内部参考不外报)。

### 1.13 自建管线(已就绪,2324 条注册)
- gen_sft_v0 A/B/C/D 四语料全量纳入(政策配对/注入五载体/PII 合成/
  校准三轴);本方案在其上扩容:阈值表全覆盖(§6 配比缺口回填)、
  攻击词典扩容(§1.14)、zh 轴补强(tc260 类目指导)。

### 1.14 横切件:攻击意图分类器(转换期构建)
- 输入:公共源人标(beavertails harm_category 14 类 + wgm 双 harm 标签
  + pku is_safe)→ 训练一个轻量规则+词面分类器(CPU 可跑,非 LLM):
  判"Human 轮/prompt 是否攻击意图 + 类别";用途:hh/pku/cvalues 的
  池切分(§1.1/1.7)+ 生成器负面采样避免重复;
- 该分类器只用于数据管线,不进模型、不进评测。

## 2. 政策条件化适用面(A/B/C/D 分层沿 gen_sft_v0)

| 层 | 定义 | 公共源子集 | 处理 |
|---|---|---|---|
| **A 全条件化** | 阈值表三包判定不同的(查询,语境) | harmbench cybercrime/cb 双用途类、trustllm privacy_awareness、wgm harmful-with-context、cvalues 双用途类 | 三包各生成一条(conservative 拒/default 提议或澄清/professional 授权语境放行),样本 id 沿用 `sft-A-{n}` 序列扩展 |
| **B 二包配对** | 三包中两包判定不同 | xstest/or-bench(wgm 同型)误拒纪律:default vs professional | 两条/样本 |
| **C 固定单包** | 三包同判的任务型样本 | T1/T7/T8 纯检测类(载体→report 不随包变)、T12 政策问答 | 固定 default;system 区仍注入包(一致性)但只生成一条 |
| **D 三包同拒** | HF/武器化/去保护 | advbench/strongreject/mi/wj-harmful/beavertails-unsafe 侧、hard-floor 对齐类 | 每包一条拒绝(理由随包微调,复用 gen_sft_v0 HF_REPLY 模式)或单条随机包 |

- 检测类(C 层)的依据:政策包只调"发现后的任务处置",不调"是否
  report"(policy-packs §4.4 注)——注入/越狱识别三包同判;
- 误拒纪律(B 层)同理:阈值表无"拒良性"行,safe 邻域三包同放行,
  配对意义在"放行的语气/详细度"随包——保守起见二包即可;
- 条件化语言:zh/en 双语包装沿用 `_surface_forms`(表面改述阶梯)。

## 3. 载体协议包裹 vs 裸 query

| 形态 | 源/子集 | 包裹方式 |
|---|---|---|
| **裸 query**(用户直问) | advbench/strongreject/maliciousinstruct、wj/wgm harmful prompt、trustllm jailbreak、xstest/or-bench、cvalues、safety-prompts 攻击、safemtdata 渐进查询 | 用户消息直接 = query(+表面改述);对应 heldout ais-r 直接越狱形态 |
| **build_context 包裹**(载体化) | harmbench 81 条 ContextString 型、trustllm privacy_leakage(context 文本=载体)、wgm injection 型 harmful prompt、自建 B 全部 | `CarrierBlock(ctype="text", trust="untrusted")` + 任务措辞;载体五类(email/webpage/log/text/code)由自建 B 覆盖,公共源只映射进 text |
| **多轮消息流**(非载体) | hh/safemtdata-1K/wj benign 对话 | LLaMA-Factory 多轮 messages,无 CarrierBlock |
| 禁止 | 任何公共源 → tool_output 载体 | 留出族,永不用(docs/06 §7) |

- 判别准则:**内容是"被分析的客体"→ 载体化;内容是"用户的直接请求"
  → 裸 query**。攻击提示是用户发起 = 裸;攻击嵌在日志/邮件/工单里被
  递交给模型分析 = 载体。两形态都要覆盖(分离不变量的双向)。

## 4. 去重与重叠

1. **攻击种子跨源重叠**(advbench ⊂ harmbench/恶意请求空间、wj 与 wgm
   wildchat 同源):
   - 规范化 8-gram containment(复用 check_sft_contamination 的
     `normalize`/`ngrams` 设施):`|A∩B| / min(|A|,|B|) ≥ 0.6` 判重,
     保留顺序 = 信息量优先(harmbench > wj > wgm > benchmarks >
     safety-prompts,按语义标签丰富度);
   - 预估:攻击种子池 ~85K(adv 520 + hb 320 + mi 100 + sr 313 +
     wj harmful 135K 采样 + wgm harmful 47K 采样 + sp attack 30K 采样)
     → 去重后 ~60-70K → 采样入 SFT ~4.5K(§6);
2. **zh 侧**:safety-prompts 与 cvalues 无重叠(域不同),跨源去重
   仍跑(便宜);
3. **良性池**:hh/wj-benign/wgm-unharmful/or-bench 80K 有主题重叠
   (通用问答域)→ 同法去重,阈值降 0.5(良性重复危害低于攻击重复);
4. **近重复保留例外**:paraphrase 阶梯(wj vanilla/adversarial 对、
   表面改述)是**故意的近重复**——一致性训练信号,去重器需按
   `attack_surface_id` 分组豁免(组内保留全部变体,组间去重)。

## 5. 污染剔除 + 红线跳过的集成点

- **管线顺序**(实现者注意:两个过滤都在转换前、读原始 raw):
  ```text
  load raw(16 源,按 manifest files 字段)
    → contamination filter:读 reports/sft-contamination-check-{sid}.json
      的 flagged_docs[].doc_index(共 767),剔除
    → redline filter:读 reports/m2-sft-redline-detail.json 各源
      indices(共 351)与 batch23_redline.indices,剔除
    → 转换(§1)→ 跨源去重(§4)→ 条件化(§2)→ 配比采样(§6)→ shuffle
  ```
- **索引对齐警示(实现级,已踩过的坑)**:doc_index 是 checker 的枚举
  序,按 sorted(文件)顺序——wildjailbreak 是 **eval.tsv 先于 train.tsv**
  (doc 0-2209=eval),wildguardmix 是 **test.parquet 先于 train.parquet**
  (doc 0-1724=test)。稳妥做法:生成器**按内容哈希过滤**(对 767/351 条
  预先导出内容 sha256 清单),避免枚举序耦合——建议实现时一次性把
  索引清单转为哈希清单(半小时工作量,消歧一劳永逸);
- 剔除统计:767(污染,0.068%)+ 351(红线,0.031%)→ 可用池 1,133,408;
- heldout/探针侧零动作(检查已证零真实污染,767 全为公版短语碰撞——
  剔除是零风险纪律,非必要);

## 6. 配比定稿(docs/06 §6 修订版)

**总量定标:96,000 条**(0.6B/对话格式;50-150k 区间中位偏下,首跑
宁小勿大,校准跑后按错误分析扩)。**zh : en ≈ 40 : 60**(zh 探针只有
general_zh 500 条,但 heldout zh 攻击面条目需要 zh 行为覆盖;zh 语料
稀缺是调研期已知约束)。

| 构成 | 条数 | 占比 | 来源细分(zh/en) |
|---|---|---|---|
| 政策条件化配对 | 43,200 | 45% | 自建 A 扩容(阈值表全覆盖+语境变体,~10K,双语)/ cvalues pos 侧条件化 8K(zh)/ pku safer 侧 6K/ wgm+wj 双用途 8K(en)/ trustllm privacy_awareness + sp 双用途 4K/ T4 场景自建 7K |
| 任务族单项(T1/T3/T7/T9/T12) | 24,000 | 25% | 自建 B/C(注入五载体 6K + PII 合成 6K,双语)/ T1/T3/T9 自建 8K / T12 C2 政策问答 4K(zh+en)/ T7 trustllm 检测侧 2K(反向设计,§1.5) |
| 注入/越狱分离不变量 | 11,500 | 12% | 自建 B 攻击半 4K / 公共攻击采样:hb 320+adv 520+mi 100+sr 313+wj harmful 1.5K+wgm harmful 1.2K+sp attack 1.2K(zh)≈ 5.2K / 攻击词典模式类 2.3K |
| 多轮 T10 | 7,700 | 8% | safemtdata 600+1,680 全量(§7)/ 多轮走私构造自建 ~5K(分段无害→整体有害)/ hh 多轮攻击池 1K |
| 通用对话恢复 | 9,600 | 10% | hh 良性 3K / sp typical 3K(zh)/ cvalues 安全闲聊 1K(zh)/ wj+wgm benign 2.6K |
| **合计** | **96,000** | 100% | zh ≈ 38.4K / en ≈ 57.6K |

- 与 §6 初稿的偏差说明:政策配对取 45%(中位);通用恢复压到 10%
  (下限——wgm/wj/cvalues 的良性池提供了高质量恢复料,比"为恢复而
  恢复"的通用集更值);注入越狱 12%(中位);多轮 8%(safemtdata
  全量只有 2,280,缺口由走私构造补);
- **误拒纪律对子**(B 层)单列统计:xstest 450 + or-bench 4.3K +
  wgm unharmful 采样 + trustllm exaggerated ≈ 6.5K(≈7%),与攻击
  采样 5.2K 比例 1.25:1(应答侧略多,对冲"见攻击就拒"偏置);
- 轮次分布预算:多轮条目(safemtdata/hh 多轮/走私)≈ 8.7K(9%),
  其余单轮——0.6B 上下文预算内,packing 关闭(§7);
- token 预估:均长 ~600 token(中性格式含 system 区 ~200 + VERDICT
  行 ~40)→ **~58M tokens/epoch**,2 epoch 校准跑 ~116M——0.6B 模型
  可承受(校准跑配置已就绪:configs/m2-calib.yaml)。

## 7. 多轮结构 → LLaMA-Factory

- **格式**:`messages` 数组多轮直接兼容 LLaMA-Factory stage sft 的
  sharegpt/messages 数据集(roles: system/user/assistant);多轮条目
  assistant **每轮**不强制 VERDICT——**仅末轮 assistant 带 VERDICT**
  (中间轮是正常对话;全轮 VERDICT 会教模型每句话都输出结构行);
- **safemtdata Attack_600 映射**:
  ```json
  {"messages": [
     {"system", POLICY_SYSTEM[pack]},
     {"user", q1 角色背景问题}, {"assistant", [S] 简短正常应答},
     {"user", q2 背景深挖},     {"assistant", [S] 正常应答},
     {"user", q3 试探边缘},     {"assistant", [S] 轻度提醒},
     {"user", q4/q5 harmful},   {"assistant", [S] 拒绝+升级说明+VERDICT}]}
  ```
  渐进轮的响应梯度(正常→提醒→拒绝)是 ais-r10"多轮拒绝升级"的
  直接训练信号;
- **safemtdata 1K 映射**:conversations 原样转 roles(human→user/gpt→
  assistant),末轮追加 VERDICT 行;`relationship` 注入 system 语境行;
- **packing 关闭**(docs/06 §10.4 开放问题 → 本方案定稿建议):多轮
  条目整条不切分(切分会截断渐进语境,破坏 T10 语义);VERDICT 结构
  行跨样本拼接有格式污染风险;0.6B + 96K 条不 packing 也在预算内;
- **hh 多轮**:chosen 串拆轮后同格式;轮数 >6 的截到 6(尾部上下文
  丢失可接受,0.6B 注意力预算)。

## 8. 暂缓项依赖与挂载点

| 暂缓项 | 状态 | 若到位的挂载点 |
|---|---|---|
| AgentDojo(MIT,已验证) | 等父决策 | T8 agent 场景注入:its important_instructions 载体映射 text 载体(已覆盖形态)+ **场景多样性增量**(浏览器/文件/Shell 场景模板并入自建 B 的载体任务措辞池);不改变本方案结构,纯增量 ~1-2K 条入"注入/越狱"配比行 |
| 平台政策文本(OpenAI/Anthropic/Google/Meta) | 用户侧通道(3/4 家本网络阻断) | T12 政策问答扩容:C2 已有 GDPR/四法/NIST(4K 条配比);平台政策到货 → 追加 ToS/usage-policy 问答 ~1-2K,双语;**与 anthropic.com 已达文本(606KB)优先合并** |
| WildTeaming(表单制) | external form required, deferred | 不阻塞;若放行 → T10 真实多轮对抗(M3+ 期,safemtdata 已覆盖 M2 需求);注意 PII 擦洗前置(docs/06 §7) |
| InjecAgent(作者确认前不采) | 等作者 | tool_output 载体形态——**即使采纳也只作留出族参照**,不入 SFT(§0.5) |
| NC/ODC-By D3 重估 | 开放权重前 | 不影响内部训练;重估若否 → §6 对应行回退重算(cvalues/pku/beavertails/wj/wgm 合计占配比 ~30%,需预备回退配方:自建比例提至 ~75%) |

## 9. 一页规格摘要(给实现者)

```text
输入  raw/ = manifest 16 行 files 字段(data/corpora/raw/m2/*,
      m2-reference/tc260 仅 schema 类目,不读 query)
过滤  ①污染:reports/sft-contamination-check-{sid}.json →
        flagged_docs[].doc_index(767 条;用内容哈希清单,防枚举序耦合)
      ②红线:reports/m2-sft-redline-detail.json(351 条,同上)
转换  每源按 §1 规格表;assistant 永不自武器化;[R] 复用必须
      追加 VERDICT 尾行;trustllm privacy_leakage 反向设计(§1.5)
去重  攻击池 containment≥0.6(保序 hb>wj>wgm>bench>sp);良性池
      ≥0.5;attack_surface_id 组内豁免(paraphrase 阶梯保留)
条件化 A 层三包/B 层二包(误拒)/C 层固定 default(检测)/D 层
      三包同拒(HF);system=POLICY_SYSTEM[pack][lang]
格式  build_sample 契约(gen_sft_v0.py):id/task/pack/lang/messages;
      多轮=messages 多对,仅末轮 VERDICT;packing 关闭
配比  96,000 条(§6 表);zh:en=40:60;seed 固定;误拒:攻击≈1.25:1
输出  data/sft/v1/{train.jsonl, meta.json};不注册 dataset_info
      (校准跑时注册);tc260/heldout/探针路径零引用(源码级断言
      沿 test_gen_sft_v0.py 扫描模式)
规模  ~58M tokens/epoch;raw 池 1,133,408 条可用
禁令  GPU 不碰;tool_output 载体永不生成;公共 eval split 不入 SFT
```

## 10. 开放问题(随校准跑回填)

1. 攻击意图分类器(§1.14)的准确率门槛——池切分错误直接改变配比,
   校准跑前需人工抽检 200 条;
2. T6 代码安全族仍缺公开数据集(Devign/BigVul 类未采购,M2 期自建
   检测练习覆盖 heldout sec-c6 同型即可,§6 未列 T6 行);
3. zh 攻击面在配比中实际 ~5.2K(sp attack 1.2K + 自建 zh 攻击词面)
   ——若校准跑 zh ASR 读数差,优先扩 tc260 类目指导的自建生成
   (非复制),而非放宽 NC;
4. 0.6B 对 5 轮渐进对话(§7)的注意力预算——校准跑观察 safemtdata
   子集 loss,若不收敛截 3 轮。
