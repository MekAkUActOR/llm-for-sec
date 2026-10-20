# M6 数据映射与配比方案（DATA-MAP v1，task-3 交付）

- 作者：dataeng-m6｜状态：v1 待 arch-m6 会签（T01 咬合点见 §8）
- 上游：reports/m6/data-inventory.md（资产实测审计底稿，数字均出自实测）
- 冻结目标：H1 2026-10-21 02:00；配比在 v2 模型轮前可按 T10 读数增补，切分口径不变
- 红线：data/heldout/（v023/gen/jb v0.7/toolout/longctx/dilution）任何内容不进训练/开发/调参；执行口径见 inventory §1

## 1. 统一 schema（临时 v0，SYS-1 定稿后一次性对齐）

```json
{"id": "m6-t4-001234", "task": "T4", "split": "train", "lang": "zh",
 "kind": "singleturn|multiturn|longctx|carrier",
 "text": "…",                    // 或 "turns": [{"role": "user|assistant", "content": "…"}, …]
 "label": "pos|neg",             // 统一二分类主判（qa 验收统计口径）
 "label_detail": {…},            // 任务细粒度（§2）
 "source_family": "synth-pii-v1|m4-capfix|r9-paired|f5|staging-t14|reserve-bt|…",
 "meta": {"lineage": {"source": "…", "src_id": "…"}, "difficulty": "easy|medium|hard", …}}
```

## 2. 六任务标签空间（映射到 kickoff 任务定义）

| 任务 | label 主判 | label_detail | 载体 kind |
|---|---|---|---|
| T1 内容审核 | pos=文本本身有风险 | {risk_domain: 15 域枚举}（域表=r9 payload pools 15 域） | singleturn |
| T2 越狱/直接注入 | pos=攻击话术框架 | {framework: roleplay\|hypothetical\|multiturn\|authority} | singleturn/multiturn |
| T3 恶意意图 | pos=多轮诱导累积或长上下文埋藏的恶意图谋 | {trigger: multiturn-accumulation\|longctx-buried} | multiturn/longctx |
| T4 PII 识别 | pos=含 PII | {spans: [{start,end,type}], type: name\|phone\|email\|id_card\|address\|bank_card\|medical_record\|passport\|license_plate} | singleturn/carrier |
| T5 间接注入 | pos=载体内容含操纵指令 | {carrier: search_result\|email\|doc_fragment\|tool_output\|webpage\|log, mechanism: ai_directive\|fake_system_prompt\|policy_claim\|task_hijack\|exfil_authorize\|verdict_suppress\|encoding_obfuscation} | carrier |
| T6 高危指令注入 | pos=指令序列含危险操作 | {op: delete\|privilege_escalation\|exfiltrate\|execute_payload\|irreversible\|mass_action} | multiturn/singleturn |

## 3. 数据源映射（存量 → 六任务，转化规则）

| 源（实测规模） | → 任务 | 转化规则 |
|---|---|---|
| m4-capfix 28,842（全单轮） | T1/T6 | rejected VERDICT=refuse 且非 carrier 类 → T1 pos（risk_domain 由 pack/src_task/关键词三路归类）；操作类（删除/提权/外传/执行关键词）→ T6 pos；rejected∈{allow,benign,conditional} → T1/T6 neg；hold/insufficient-context/none（~2,188）**弃用**防标签噪声 |
| m4 carrier_inject_obedient/hollow 4,680 + carrier_clean_overrefusal 1,320 | T5 | inject 类 → pos（mechanism 由载荷关键词归类）；clean → neg；载体信封保留 |
| p16-r9 adv 576 + paired 5,976 | T2/T3 | adv 全 pos（framework 四类已在数据内）；paired 两轮 3,766 恶意子集 → T2/T3 pos 种子；benign → neg |
| r9 payload pools en/zh 各 144 | T2/T3 正例模板基底 | 不直接入集；作合成模板的 payload 词表（15 域） |
| p16-r5 f5_paired 2,000（1,000 对×2 render） | T1 | -m render → pos、-b render → neg；**同对两 render 强制同切分**（防泄漏） |
| staging t14 2,500 / t1 375 / t9_phish_expand 1,500 / doc_structure 1,200 | T5 | 按 assistant VERDICT / 载体内容分 pos/neg；tool_output/webpage/document 载体覆盖 |
| staging t13_retrieval_longctx 200 / t13_retrieval 1,500 | T3 负例基底 | 干净长上下文（埋针为良性检索目标）→ T3 neg 长文骨架复用 |
| reserve bt 13,498 / cvalues 17,000 / hh 14,984 / pku 14,000 | T1 | 恶意 prompt → pos、良性 → neg（语言登记后按需采样） |
| fC_cvpku_release 7,602 | T1/T2 负例 + challenge 族 | 释放对（拒绝后给良性替代） |

**去重**：规范化文本（去空白/小写）sha256 为主键，同键合并；近似重复（8-gram Jaccard>0.8）跨切分报警并强制同侧。

## 4. train/dev 配比（含跨任务负例共享）

### 4.1 规模（行=单任务视角行）

| 任务 | train pos | train neg | dev pos | dev neg | heldout pos | heldout neg |
|---|---|---|---|---|---|---|
| T1 | 3,000 | 3,000 | 250 | 600 | 250 | 1,100 |
| T2 | 2,200 | 2,400 | 250 | 600 | 250 | 1,100 |
| T3 | 2,600 | 2,600 | 250 | 600 | 250 | 1,100 |
| T4 | 2,400 | 2,400 | 250 | 600 | 250 | 1,100 |
| T5 | 2,800 | 2,800 | 250 | 600 | 250 | 1,100 |
| T6 | 2,200 | 2,400 | 250 | 600 | 250 | 1,100 |
| 合计 | 15,200 | 15,600 | 1,500 | 3,600 | 1,500 | 6,600 |

- dev/heldout 负例 = 共享良性基底采样 + ≥20% 任务相关边界负例（§4.3）
- challenge 1,500 文本 × 六任务复制 ≈ 9,000（text,task) 行（§5）；OOD 500 文本（样本级口径）

### 4.2 跨任务负例共享

- 共享良性基底池 ~10,000 文本（日常/专业问答/工单/邮件/代码评审，zh/en≈55:45）——**多任务训练池中同文本标注为全六任务 neg**（六头共学"此文本无任何风险"）；per-task 视图按任务采样避免单任务负例过度重复。
- 任务相关负例不共享（T5 干净载体 / T6 良性指令流 / T4 无 PII 文本各自生成）。
- T4 例外说明：含 PII 的文本对 T4 是 pos、对其余任务通常 neg——多任务标签按 (text,task) 独立判，不做"一票全负"。

### 4.3 边界负例（near-miss benign，≥20% 每任务负例池，qa 要求）

| 任务 | 边界负例形态 | 来源 |
|---|---|---|
| T1 | 一般安全科普/新闻转述（非 hardbenign 级难度） | 新合成 + reserve 良性筛选 |
| T2 | 真小说创作/学术讨论攻击技术（不针对模型） | 新合成（虚构叙事框架+安全论文摘要体） |
| T3 | 良性多轮渐进（越问越细但正当）/ 干净长上下文 | 新合成 + t13 骨架 |
| T4 | 类 PII 非人（书名/角色/虚构编号/ISBN/内部单号） | 新合成 |
| T5 | 干净载体（真实工具输出/文档原文/无注入搜索结果） | 新合成 + staging clean 行 |
| T6 | 良性运维序列（正当删除/配置/导出，含授权与确认步骤） | 新合成 |

### 4.4 长度与语言

- 长上下文（>4k tokens）限量：train ~1,000（T3 800 + T5 长载体 200）；heldout 长文 250——0.6B/24GB 单卡可行性（deveng 确认训练侧 max_len 后可回调）。
- zh:en ≈ 55:45（对齐 m4 实测 17,319:11,523 与部署语境）。

## 5. challenge / OOD 口径（task-5，qa 会审）

**challenge（1,500 文本，qa 方案 a）**：
- 四族：良性安全研究（防御分析/CTF 出题/漏洞报告解读）400｜医疗正当（临床语境正当讨论，含患者视角）400｜双用途正当（授权渗透/自有资产/教学演示）400｜高仿注入形良性（工单正常优先级指令/正常代码评审/含可执行句的正常文本）300。
- **任务归属**：每文本在六任务下各登记一行（id 加 `-t1`…`-t6` 后缀），默认全 neg → 每任务 chN≈1,500，chFPR<0.1% 门可判（FP≤1）；若 (text,task) 实为正（如医疗正当含 PII → T4 pos），该行标 pos 并从 chFPR 分母剔除、manifest 单独列示。
- 构建来源：m4-professional 授权语境子集改写 + fC_cvpku_release + 新合成四族生成器；**heldout/hardbenign 零接触**。
- dev 含同族异样难负例 150/任务（阈值选择需要，与 challenge 样本不相交——生成器分流出料）。

**OOD（500 文本，样本级口径）**：
- ≥8 全新域（体育/烹饪/游戏/艺术/旅行/园艺/宠物/手工），正常文本+正常多轮+干净"载体"（干净搜索结果/干净文档片段——测 T5 不误伤）。
- 判定：六任务全 PASS 才算放过（qa harness 按文本去重统计）。
- 训练零接触；与良性基底池域不相交（基底池域：日常/专业问答/工单/邮件/代码评审）。

## 6. 缺口清单与增补（合成管线）

| 缺口 | 量 | 方案 | 优先级 |
|---|---|---|---|
| T4 PII 全量 | ~7,000 | 受控合成生成器（中英、span 标注、格式真实不对应真人；身份证 ISO 7064 / 银行卡 Luhn） | P0 |
| T5 search_result 载体 | ≥600 pos+等量 neg | 新载体生成器（机制×位置矩阵） | P0 |
| T3 多轮 ≥3 轮诱导 | ~1,600 pos | 四幕剧本生成器（寒暄→铺垫→越界→施压 ×15 域×中英） | P0 |
| T3 长上下文埋藏 | ~1,000 pos | 长文（合成填充+训练侧语料）埋恶意段（head/mid/tail） | P1 |
| T2 框架扩量 | ~1,600 pos | r9 四框架模板树 × payload 改写 | P1 |
| T6 指令序列 | ~1,400 pos | 任务流生成器（正常流插危险步骤） | P1 |
| 边界负例全任务 | ~4,000 | §4.3 各族生成器 | P1 |
| challenge 四族 | 1,500 | §5 生成器 | P1 |
| OOD 八域 | 500 | 新场景生成器 | P2 |

## 7. 切分隔离与血统

- 同源对（f5 -b/-m、同 group 政策对）强制同切分。
- 隔离自检：train ↔ (dev∪heldout∪challenge∪ood) 规范化 sha256 精确匹配 + 8-gram 近似交并检查（scripts/m6/check_split_isolation.py，报告随 manifest）。
- manifest（data/m6/manifests/）：逐文件任务/规模/来源血统分布/切分用途/sha256 前缀/生成器版本；每行 meta.lineage 可审计到源文件行。
- M6 训练不引入 image_metadata/av_metadata 载体（保护 M5a 未见载体门禁前提，待 ADR-1 确认）。

## 8. 与 T01/T02 咬合点（会签项）

1. 标签空间：label=pos|neg 主判 + label_detail（§2）——**待 sysdesign SYS-1 确认或改**。
2. 多任务池行格式（一文本六任务标签 vs 六行复制）影响 deveng 训练效率——建议 pool 视图用"一 (text,task) 一行"、训练侧自行聚合。
3. T4 span 字符偏移 vs BIO：我按 {start,end,type} 字符偏移交付，BIO 可由 harness 现算。
4. 长上下文 token 上限（>4k 样本量）待 deveng 训练侧确认。
5. OOD"六任务全 PASS"的弃权机制判据归 T02；数据侧保证 OOD 全 benign 且域外。
