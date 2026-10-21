# M6 DATA-1 语料映射审计（六任务训练/评测数据）

- 版本：v1（首版，02:30 设计冻结门槛）
- 作者：dataeng-m6｜审计时间：2026-10-21 01:04 起，实测核实
- 下一版：v2 随构建进展更新；schema 以 sysdesign-m6 SYS-1 定稿为准对齐
- 关联：reports/m6/m6-kickoff.md（章程/验收门）；qa-m6 规模建议已并入（2026-10-21 01:40 消息）

## 0. 执行摘要

1. **六任务中四任务（T1/T2/T5/T6）有可观存量可转化**；**T4（PII）零存量全合成**；**T3 的多轮诱导 ≥3 轮与长上下文埋藏基本全合成**（存量全单轮或仅两轮）。
2. 与任务简报的三处实测差异：①`data/dpo/` 下**无 amb 各代**（歧义场景素材不存在，挑战集改道，见 §3.7）；②r9 payload pools 实测 en/zh **各 144** 条（简报写 288）；③m4-run 28,842 行**全部单轮**。
3. 规模门（qa-m6 验收分辨率倒推，已确认采纳）：每任务 heldout 正例 ≥200、heldout benign 负例 ≥1,000、challenge ≥1,200（目标 1,500）、OOD ≥500（qa 最低 300）；train 每任务正例 ≥2,000 + 负例 ≥2,000。**总量预估 ~60k 行**，规则/模板合成（CPU，无 GPU 依赖），07:00 冻结可行。
4. 乙醇纪律执行口径（§1）已报 Lead/arch：heldout 六套件只读 README 形式定义，不读题目内容、不复用 heldout 构建器 payload。

## 1. 乙醇纪律执行口径（冻结）

| 允许 | 禁止 |
|---|---|
| 训练数据来源：data/m4-run/、data/dpo/ 各配方、data/sft/（训练侧 staging 与 reserve）、**新合成** | data/heldout/ 六套件（v023/gen/jb/toolout/longctx/dilution）任何题目内容进入训练数据 |
| 读 heldout 的 **README/manifest 文档**了解形式定义与验收映射 | 读 heldout jsonl 的题目/payload 内容 |
| 复用**训练侧**生成器与载荷字典：scripts/gen_t14_authinject.py、scripts/gen_t13_retrieval.py、scripts/build_dpo_carriers.py（PAYLOADS）、secfm/carriers 序列化格式 | 复用 heldout 构建器（build_jailbreak_suite.py、build_toolout_heldout.py、build_heldout_*）的 payload/题式 |
| M6 训练引入 text/email/log/webpage/code/document/tool_output 载体（M5a 在训载体） | M6 训练引入 image_metadata/av_metadata 载体（M5a 未见载体门禁的前提保护，待 arch ADR-1 确认） |

- 依据：data/heldout/README.md（"只进评估管线，永不进入训练语料"）；data/ontology/carriers.json（tool_output 已在训 1,224 次；image/av_metadata 训练 0 次=仅存未见载体门禁）。
- 自检：构建管线含 train↔heldout/challenge n-gram 交叉检查（与 qa 独立抽查互补），结果随 manifest 交付。

## 2. 存量资产核实（实测）

### 2.1 data/m4-run/（任务①③⑥ 主素材）
- `dpo_m4_capfix.jsonl`：**28,842 行**（唯一 id，无重复）。sharegpt dict 形式（conversations + chosen/rejected 单消息 dict），rejected/chosen 带 VERDICT JSON。
  - dpo_class：policy 14,688｜reserve 5,710｜carrier_inject_obedient 2,360｜carrier_inject_hollow 2,320｜bt330_refusal 1,904｜carrier_clean_overrefusal 1,320｜refusal_quality 300｜calibration 240
  - lang：zh 17,319 / en 11,523；pack：default 13,811 / conservative 7,688 / professional 7,343
  - **human 轮数：全部 1 轮**（T3 多轮需求无法由 m4 满足）
  - rejected VERDICT：refuse 12,018 / allow 8,550 / conditional 4,340 / benign 1,746 / hold 1,320 / insufficient-context 724 / none 144
  - src_task 前缀：T5-policy 12,798 / T1-injection 4,680 / T4-grounding 3,606 / T11-calibration 144 / 空 7,614
- `dpo_m4_rebal.jsonl`：18,171 行（capfix 的再平衡子集，同 schema）。
- `dpo_m4_capfix_listform.DO-NOT-USE.*`：**禁用**（审计教训产物）。

### 2.2 data/dpo/（任务①②③ 素材）
- `p16-calibration-r9/p16_r9_adv.jsonl`：**576**（R9X 对抗覆盖：角色扮演/假设/多轮/权威四框架；en/zh 各 288；conservative pack；单轮 432 + 两轮 144；chosen 全部 refuse）。
- `p16-calibration-r9/p16_r9_paired.jsonl`：**5,976**（= base 5,400 + adv 576；两轮 3,766；verdict 词表 no-risk/contains-risk/deflect/needs-info/refuse）。
- `p16-calibration-r9/{en,zh}_payload_pool.json`：**各 144** 条风险请求（request-form only，无操作细节，15 域 × ~10）——T2/T3 正例模板基底 + 风险域枚举来源。
- `p16-calibration-r5/p16_f5_paired.jsonl`：2,000 行 = **1,000 良恶翻转最小对 × 2 render**（-b 良性 / -m 恶性，同骨架同 system）——T1 最小对素材与模板化样板。
- p16-calibration r1-r6 各代（benign_release/malicious_honest 2,736-2,880/代 + parts）：可再榨取的补充池（血统分别登记）。

### 2.3 data/sft/m2.5-staging/（训练侧家族文件——T5/T3 存量主力）
实测行数：t14_authinject **2,500**（tool_output 载体，伪造权威注入 + 干净负例混排）｜t1_injection **375**（五载体注入）｜t13_retrieval **1,500**｜t13_retrieval_longctx **200**（长上下文检索，维基语料埋针）｜t2_mechanism 1,200｜t9_phish 50｜t9_phish_expand 1,500｜doc_structure 1,200（document 载体）｜fA_policy 7,776｜fB_t4ground 6,720｜fC_cvpku_release 7,602（释放对=良性）｜fD_t6 5,001｜fE_t3t12t11 4,500｜fG_t6_devign_ext 12,000。
- messages 数组形式（system/user/assistant），assistant 以 VERDICT 结尾；task 字段带家族标签——**可直接映射六任务**。
- 载体信封格式 `<carrier type="X" trust="untrusted" id="cN">` 为训练侧 secfm 序列化惯例，M6 T5 沿用。

### 2.4 data/sft/dpo-reserve/（公开安全数据 reserve——T1 主池）
beavertails **13,498**｜cvalues **17,000**｜hh **14,984**｜pku-saferlhf **14,000**。字段：source/id/prompt/chosen/rejected（prompt+双回应）。用途：T1 正例（rejected 呈风险的子集）/负例（良性 prompt 子集）；注意 cvalues/hh 中文或双语占比高，登记语言后按需采样。

### 2.5 可复用训练侧生成器（scripts/）
gen_t14_authinject.py（tool_output 注入）｜gen_t13_retrieval.py（检索埋针）｜gen_t2_mechanism.py｜gen_t9_phish_expand.py｜gen_doc_structure.py｜build_dpo_carriers.py（PAYLOADS 载荷字典，按 (carrier, mechanism) 组织：ai_directive/fake_system_prompt/policy_claim/task_hijack/authority_disguise/exfil_authorize/verdict_suppress/encoding_obfuscation 等）。

### 2.6 data/heldout/ 六套件（**评测参照，训练零接触**；仅 README 口径）
v0.2.3（ai_safety/security/privacy 各 157 + general_* 各 30 + **hardbenign 120**）｜v0.3-gen（av/image_metadata 共 258）｜v0.7-jailbreak（150）｜v0.4-toolout（70）+ v0.5-toolout-reg（264+75）｜v0.6-document（80）｜v0.6-dilution（96）。
- qa-m6 已定参照映射：jb→T2/T3 recall；toolout/document/gen→T5；dilution→T3；hardbenign→挑战参照。不入验收门。

### 2.7 缺失确认
- **T4 PII**：全仓无现成 PII 标注数据（corpora/raw 为安全语料，无 PII span 标注）→ 全合成。
- **amb 各代**：不存在（data/dpo/ 仅有 m3 与 p16-calibration 系）。
- **T3 ≥3 轮多轮诱导**：存量最深的仅 r9 两轮（3,766）→ 新合成。
- **OOD 新场景 benign**：无现成（staging 均为安全域分布内）→ 全合成。

## 3. 六任务矩阵（存量 / 缺口 / 合成方案 / 规模预估）

统一 schema（临时 v0，待 SYS-1 定稿）：`{id, task: T1..T6, split, lang, kind: singleturn|multiturn|longctx|carrier, text|turns, label: pos|neg, label_detail: {…}, source_family, meta}`。
规模：每任务 train ≥2,000 正 + ≥2,000 负；dev ≥200 正 + ≥500 负；heldout ≥200 正 + ≥1,000 负；challenge/OOD 见 §4。

### T1 内容审核（文本本身风险）
- 存量：m4 rejected=refuse 类 ~12k（去 policy 对后取真实恶意子集）+ reserve 四库恶意 prompt（bt/cvalues/hh/pku 合计 ~59k 池，采样）+ f5 -m render 1,000 + r9 payload pool 改写。
- 负例：m4 rejected∈{allow,benign,conditional} + reserve 良性 prompt + f5 -b render 1,000。
- 缺口：中英平衡与 15 风险域覆盖矩阵；医疗/暴力等域中文量不足。
- 方案：存量转化（VERDICT→label 映射：refuse→pos；allow/benign→neg）+ 模板扩充窄域。
- 预估：正 3,000（存量 2,600 + 合成 400）/ 负 3,000；dev/heldout 按门。

### T2 越狱/直接注入
- 存量：r9_adv 576（四框架）+ m4 中单轮框架化恶意（人工规则筛：角色扮演/假设/伪权威关键词）。
- 缺口：**大**——576 距 2,000 差 ~1,400+；需四框架 × 多 persona × 中英的模板树。
- 方案：以 r9 四框架为骨架（训练侧资产），payload 从 r9 pools 144×2 与 m4 恶意请求改写；每框架 ≥500 正例；负例=同框架良性版（学术讨论/正当防御咨询——注意与 challenge 的边界：负例可用一般良性，challenge 用高仿难负例）。
- 预估：正 2,200（存量 576 + 合成 1,600）/ 负 2,400。

### T3 恶意意图（多轮诱导 + 长上下文埋藏）
- 存量：r9_paired 两轮 3,766（恶意子集作种子）；t13_retrieval_longctx 200（长上下文埋针形式，训练侧）。
- 缺口：**最大之一**——≥3 轮渐进诱导全合成；长上下文埋藏需扩到 ≥800 且埋藏物从"检索答案"升级为"恶意图谋"。
- 方案：①多轮：诱导剧本生成器（寒暄→铺垫→越界→施压 4 幕结构 × 15 风险域 × 中英）；②长上下文：维基式长文（enwiki/zhwiki 训练侧语料 + 合成填充文本）中埋恶意请求段（位置 head/mid/tail 三档，对齐训练侧 t14 落点设计）。
- 预估：正 2,600（多轮 1,600 + 长上下文 1,000）/ 负 2,600（良性多轮 + 干净长上下文）。

### T4 PII 识别（span/类别级）
- 存量：零。
- 方案：**受控合成生成器**（最高优先级）：中英实体值生成（人名/电话/邮箱/身份证/地址/银行卡/病历号/护照/车牌），格式真实（大陆 18 位身份证校验位算法、138-号段、Luhn 银行卡、医院病历号格式）但**全合成不对应真人**；载体句式 × 领域（客服工单/邮件/聊天/表单/病历摘要/快递单）；span 标注 {start,end,type} 字符偏移；负例=同分布无 PII 文本 + "类 PII 但非 PII"难负例（书名中人名/虚构角色/格式相似的编号）。
- 预估：正 2,400 / 负 2,400；label=pos 表示含 PII。

### T5 间接注入（载体内容中的操纵指令）
- 存量：t14_authinject 2,500 + t1_injection 375 + m4 carrier_inject_obedient/hollow 4,680 + t9_phish_expand（webpage 载体）+ doc_structure（document 载体）。
- 负例存量：carrier_clean_overrefusal 1,320 + t14 干净行。
- 缺口：**搜索结果载体**（简报点名的目标分布）存量少；邮件/文档片段载体需按 M6 目标分布重组；干净负例分布需对齐正例载体分布。
- 方案：扩 build_dpo_carriers 式机制 × 载体矩阵：{search_result(新), email, doc_fragment, tool_output, webpage, log} × {ai_directive, fake_system_prompt, policy_claim, task_hijack, exfil_authorize, verdict_suppress, encoding_obfuscation}；注入位置 head/mid/tail；干净负例同载体同分布配对生成。
- 预估：正 2,800（存量转化 ~2,000 + 合成 800，搜索结果载体 ≥600）/ 负 2,800。

### T6 高危指令注入（指令序列中的危险操作）
- 存量：m4 rejected=refuse 中操作类（删除/提权/外传/执行）子集 + t14 的 destructive_request/command_substitution 机制行。
- 缺口：成串指令序列（多步操作流）形态少；"良性高危形"难负例（授权运维/演练/自有资产）不足。
- 方案：指令序列生成器：正常任务流（部署/清理/备份/迁移）中插入危险步骤（rm -rf 无确认、curl|sh、提权、批量外发、不可逆删除）× 中英；op 类别六枚举标注。
- 预估：正 2,200（存量 ~800 + 合成 1,400）/ 负 2,400（良性指令流，含运维高危形）。

## 4. 共享切分（challenge / OOD / 良性基底池）

- **challenge（难负例，目标 ≥1,500）**：四族——①良性安全研究（防御性分析/CTF 写题/漏洞报告解读）；②医疗正当（临床语境的敏感但正当讨论）；③双用途正当（授权渗透测试/自有资产运维/教学演示）；④高仿注入形良性（工单里的"请优先处理"类正常指令、含机械可执行句的正常代码评审）。素材：m4 professional pack 授权语境子集 + fC_cvpku_release + r9 payload 正当化改写 + 新合成。**不使用 heldout/hardbenign 内容**（纪律），形式自研。
- **OOD（≥500，全 benign）**：全新场景（体育/烹饪/游戏/艺术/旅行/园艺等 ≥8 域），正常文本 + 正常多轮 + 正常"载体"（干净搜索结果/干净文档片段——测"不误伤"含干净载体不误报 T5）。训练零接触（生成后不进任何 train 切分）。
- **良性基底池**：~12,000 行共享基底（日常/专业问答/工单/邮件/代码评审，中英各半），供各任务 dev/heldout 负例采样 + 任务特定变形。

## 5. 切分与血统

- 目录：`data/m6/t{1..6}-{slug}/{train,dev,heldout,challenge,ood}.jsonl`（challenge/ood 亦按任务挂目录便于逐任务门测量；内容可为跨任务共享基底的采样）+ `data/m6/pool/`（多任务训练池，sysdesign schema 定稿后组织）+ `data/m6/manifest.json`。
- manifest 逐文件记录：任务/规模/来源血统分布（source_family 计数）/切分用途/sha256 前缀/生成器版本。
- 每行 meta.lineage={source, src_id}，可审计到源文件行。
- 隔离自检：train ↔ (heldout|challenge|ood) 的 8-gram 交集检查（脚本 scripts/m6/check_split_isolation.py，报告随 manifest）。

## 6. 时间表与风险

| 时点 | 动作 |
|---|---|
| 02:30 | 本审计首版 ✅ → 开始合成管线（T4/T5 优先） |
| 03:30 | SYS-1 schema 到达 → 对齐转换（预计 30min） |
| 05:30 | 六任务 train/dev 全量；heldout/challenge/OOD 建成 |
| 06:15 | 隔离自检 + manifest 落盘 |
| 07:00 | **数据冻结**，通知 qa-m6/Lead 路径 |

风险：①多轮/长上下文合成质量（缓解：剧本结构化模板 + 抽检 20 条/族人工过目）；②T5 搜索结果载体无历史参照（自研分布，qa 参照读数只覆盖 toolout/document——FPR 门以自建 heldout 为准）；③存量转化时 VERDICT→label 映射的边界样本（hold/insufficient-context 类弃用不入正负例，避免标签噪声）；④合成身份证/银行卡号的格式真实性 vs 滥用风险（值全合成+校验位算法公开格式，无真人对应；必要时对 id_card 类值做掩码变形——保留 span 任务可用性）。

## 7. 待裁决项（已发给对应 Owner）

1. [arch] M6 训练不引入 image_metadata/av_metadata 载体（保护 M5a 未见门禁前提）——待 ADR-1。
2. [sysdesign] label 主判 pos|neg + label_detail 细粒度的合并方案——待 SYS-1。
3. [Lead] 简报三处差异（amb 不存在/payload 144 非 288/m4 全单轮）不改变交付，仅修正盘点事实。

---

# v2 构建结果终态（H6 冻结候选，02:25 终态波，commit 826a574）

版本：v2 ｜ 作者：dataeng-m6 ｜ 本节取代 §6 排期表，为 DATA-2 交付实测终态。

## 8. 交付结构（data/m6/，schema v0.3.4 行契约 / manifest v2）

t1-moderation / t2-jailbreak / t3-intent / t4-pii / t5-indirect / t6-highrisk（各 train/dev/heldout.jsonl）+ challenge/all.jsonl + ood/all.jsonl + heldout-shared/benign-heldout.jsonl + pool/{train,dev}.jsonl + dev-mirror/{challenge-mirror,ood-mirror,benign-dev}.jsonl + manifest.json（manifest_id=m6-data-v1，files[] 23 项：split/task/n/rows/sha256/label_counts）。

## 9. 规模门实测（全 PASS）

| 任务 | train pos/neg | dev pos/neg | heldout pos/neg |
|---|---|---|---|
| T1 | 8560/6088 | 250/1200 | 300/2200 |
| T2 | 2126/2100 | 250/832 | 300/1000 |
| T3 | 3261/4934 | 526/1200 | 300/2200 |
| T4 | 2600/3700 | 250/600 | 300/1100 |
| T5 | 10774/7007 | 250/1200 | 300/2200 |
| T6 | 2050/4194 | 250/1200 | 300/2200 |

challenge 1,500（四族：sec-research 294/medical-legit 611/dualuse 186/inj-shaped 409；345 行医疗 T4-pos 带真 span，T4 分母 1,155）；OOD 500（八域 PII-free）；heldout-shared 2,500；dev-mirror 1,100+500+3,500；pool train 47,282 / dev 9,800。

## 10. 隔离与完整性终态（isolation assert PASS）

- exact_overlap=0（NFKC→lower→空白折叠全域口径；qa L1 472 行重合与 arch 961 轻归一化重合均已根除）
- mirror_eval_overlap=0；ood_t4_pos_rows=0
- t4_entity_overlap=0（642 个 heldout span 实体 vs 六任务全部 train 行文本子串零命中，qa L5 协议固化进 build_all）
- 泄漏审计 reports/m6/leak-audit.md：冻结套件 1,401 行 vs 训练侧 127,584 行，精确 0 / 正文级近似 0（14 个 B1 命中全部归因 policy-pack 渲染模板共祖）
- pair_integrity：T5 对 1,589 / f5-policy 对 1,000 / T3 dialog 组 530，跨 split 全 0

## 11. 本轮泄漏修复审计轨迹（qa 工单 + arch P0/P1/P2）

1. norm_text 补 NFKC（根因：全角/兼容字符逃逸去重与 sig 锁）。
2. gen_pii 三段产出（train/dev/heldout 独立实体域）：键池 hash 分桶 70/20/10（zh 姓/en 姓/zh 路名/en 街名/DOB 年位），组合实体跨 split 不相交；全局 Deduper 跨 scope 去重。
3. 占位/掩码硬负例模板参数化（保持 PII 形状语义）；Pa$$w0rd 模板扩熵。
4. build_all swap-out：heldout 泄漏行（legacy 自由人名跨生成器碰撞，4 行）与 train 干净行 1:1 交换——heldout 行内容零编辑（arch 裁定"heldout 一律不动"）。
5. T5 cond→neg 全量投影 753 行（D-12，GoldLabel pos|neg）；label_counts 恒写双键；heldout-shared split=heldout；meta.eval_family 三文件 100% 覆盖。

## 12. 已知口径与遗留

- T3 full-pos dev 206（arch"顺手补"级，未阻塞；v0.7 形态泛化列 task-10 观察项）
- t6 conditional 871 vs §6.2 估计 ~3.9k：reserve 弃用（§6.4-5 已批准）+ policy 采样所致，路径合规（arch 追溯注）
- L4 5-gram containment 高读数为模板数据结构性相似（qa 已降级披露读数）；B2 正文级佐证见 leak-audit.md
- 复核链：qa leak-check 复检 → sysdesign m6_h6_audit 四层 → arch 独立复验 → 冻结

---

# v2.1 热修补记（H6 冻结后，arch 裁定，commit 35943e2）

**发现**：deveng 从 v1 读数发现 reserve-cvalues 家族行内容为有害 query 却标 T1-neg（T2 头 logit 17-37）。溯源：conv_cvalues 误用 cvalues 的 id 前缀（cv-harm/cv-help）判极性——前缀实为批次标签非极性标签，cv-help 批次同样是有害 prompt + 拒答 chosen 的 DPO 对。~4,000 行（train 2,672 / dev 399 / heldout 929）标签翻转。

**修复**（arch 四条件全执行）：
1. 同类捷径全清扫：convert_legacy 仅 2 处 id 推断极性——cvalues 前缀（本 bug，已修）；f5 尾缀 -m/-b（全量 1,000 对验证 100% 一致，非 bug，登记在案）。其余路径全走 VERDICT/allowed-map。
2. 断言覆盖延伸：cvalues 路径极性纯度断言固化（emit 后 sink 内 reserve-cvalues 必须全 pos + converter 零 neg，违者 exit 2）。
3. 规模门自查：GATES ALL PASS——T1 train p8513/n3025、dev p297/n1200、heldout p300/n1263；reserve-cvalues 终态 train pos 3,843 / dev 75 / heldout 82、零 neg；T1 train neg 构成 = f5-paired 760 + r9-paired 165 + benign 投影 2,100。
4. 波稳定信号在最终 flush 后发出。

**split 全量重排连带**：T3 dev pos 526→610、t4 swap 3 行；isolation 我侧全 PASS（exact 0 / content_qa_l1 0 / mirror 0 / ood_t4_pos 0 / t4_entity 0/644）。复核链重跑：qa 热修证书 PASS（leak-check-h6-hotfix1.json：L1 0-0 / L2 0 / L3 0 / L5 0）｜arch、sysdesign 在途。

**失效类登记**（pm task-14 素材呼应）：标签语义类 bug 是冻结审计（切分/泄漏向）未覆盖的失效类——防御 = 每家族极性 spot-check 对源批次语义 + 转换路径断言全覆盖（本补记条件 2 已固化）。

---

# v3. v2 数据波（task-10 工作令 D-a~e，commit 970764a）

**事件**：~04:50 进程死亡（D-d 生成前），00:12 Lead 恢复令后 ~35min 续跑完成。恢复核查：_staging 五文件均完整（无半写），topup 系续跑补齐。

**交付**（arch 形式规格——构念推导，未读冻结套件，乙醇红线全程保持）：
- D-a t4-lawful-v1：neg 800（train，三合法语境：IRB 医疗研究/授权工单收件人/HR 记录）+ mirror 150（challenge-mirror 1,250，dev 校准 τ 保护）。语境构念：形式定实体性、语境定极性（arch T4 裁定）。
- D-b toolout-v1：pos 1,200（P1/P2/P3 载荷位置各 400）+ reg neg 200（同形式良性轨迹）。messages 形 10-20 条目。
- D-c doc-intent/inject-v1：T3/T5 各 300（2k-8.8k 字符长文档 × 四类型 × 三分位嵌入，检索增强形）。
- D-d jb-variant-v1 144（六变体族）+ topup-phish-v1 150（参数化话术）。
- D-e 投影 3,102（门两级规则：role local 豁免 + conditional/safe 语境释放，hits 0）+ forged-auth-v1 700（T6 high-risk + T2 pos 双键——伪造授权构造性=绕过意图）。

**投影门演化链**（三跳语义精化，sysdesign v0.3.14→0.3.17 归档）：双源零（盲区巧合）→ 81 扣留（T4 标注实践锚定：example 域人形邮箱=pos 106/540）→ 0/3,102（语境构念裁定：role 形=组织地址非自然人标识）。

**终态**：train_rows 108,075（+9,788）；六任务门全过；isolation 五断言全 0；泄漏 exact 0/B2 0；schema 11 目录 invalid=0。arch 抽验四项绿（含内容级独立性 0 重合实证）。

**T4 双语义注记**：识别语义（challenge 医疗 legit 行 pos+span，FPR 分母排除）vs flag 决策语义（训练/部署：合法语境不告警）——D-a 训练后者，两者不冲突但引用时需注明口径。
