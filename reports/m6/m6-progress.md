# M6 六任务检测器 · 项目进度活文档

> **PM 维护（pm-m6）**｜窗口：2026-10-21 01:04 → 2026-10-22 01:04（24h）
> 基座主干：`checkpoints/qwen3-06b-sec-m5a-dpo-r5`（0.6B / 28 层 / hidden 1024）
> 纪律：`data/heldout/` 冻结评测套件**绝对不进训练/调参/阈值标定**（乙醇纪律）；GPU 单卡 24GB **严格串行**（GPU 步骤前查 nvidia-smi）；git main 各角色自行 commit（消息带角色前缀），**只有 Lead push**；pytest 未装（用 python assert/unittest）
> 更新节奏：每 2h 或检查点后由 pm-m6 更新；任务板（team_task_list）为唯一权威状态源，本文件是镜像快照

---

## 1. 验收标准（冻结，不可协商）

| # | 指标 | 目标线 | 当前最好（模型/轮次） | 达标? |
|---|------|--------|----------------------|-------|
| A1 | 检出率 recall（六任务各） | > 95% | — | — |
| A2 | 误报率 FPR | < 0.5% | — | — |
| A3 | 挑战集 FPR（良性安全研究/医疗正当/双用途正当/授权渗透测试难负例） | 任务级逐任务 <0.1% 主门 + 样本级双报；点估计判定 + 精确二项 CI95（CI 显著越界标红） | — | — |
| A4 | OOD 放过率（高精度运行点 + 弃权→PASS） | 硬门 ≥95%，目标 98%；弃权率双列披露（OOD 侧 + 分布内攻击侧） | — | — |
| A5 | 一次推理输出全部六任务结果 | 必须 | — | — |

六任务：①内容审核 ②越狱/直接注入 ③恶意意图（含多轮诱导、长上下文注入）④PII 识别 ⑤间接注入 ⑥高危指令注入

## 2. 检查点时刻表

| 检查点 | 时刻 | 里程碑 | 状态 | 备注 |
|--------|------|--------|------|------|
| H1 | 10-21 02:30 | 设计冻结：ADR-1（task-1）+ 数据映射 DATA-1（task-3） | ✅ ~01:23 达成 | 运行时钟提前 ~67min（自报 02:05；三次校正后 turn 插值映射，见 §8） |
| H1.5 | 10-21 03:30 | SYS-1 系统规格 + schema 契约（task-2）+ QA-1 验收规格冻结 | ✅ ~01:35 达成（提前 ~115min） | 5/5 全清：task-2 ✅ + schema v0.3.1 ✅（F1/F2 修复，自检 14/14，commit 7c4071d）+ QA-1 v1.2 FROZEN ✅ + task-7/9 双 claim ✅ + arch 咬合审查闭环 ✅（adr-1b §6.6）；关键路径转 dataeng T04/05/06 + deveng task-7 |
| H6 | 10-21 07:00 | 数据冻结：六任务五切分 + manifest + 泄漏审计（task-4/5/6） | ✅ **完成（~02:24-02:25 实钟，提前 ~4.5h）** | 三方链闭合：qa 证书 ✓ + sysdesign 四层 ✓（89da085）+ arch 独立复验 ✓（全量实测全 0）；冻结 tag = **89da085**；v1 训练（02:18 起）追认合规不 kill；task-3/4/5/6 全 complete |
| H10 | 10-21 11:00 | v1 模型 + 首轮评测读数（task-8/9） | ✅ **达成（~04:40-50，提前 ~6.2h）** | task-8 ✅；**官方读数 = v1-2 双运行点全落盘**（主读数 qa-report-v12.md + QA 独立点交叉列 + sensitivity + per-item ×2；verdict=FAIL 两点一致 = 首迭代对终验门的预期姿态，信息丰富：T4/T5/T6 recall 达标 100/98.3/100@QA 点、T4 FPR 7.3% 实现层 span 误报、T1/T3 分离度短板、B 族全穿）；task-10 归因报告落盘（§16 全触发）；**v2 GO**；task-9 板面 complete |
| H16 | 10-21 17:00 | v2 模型迭代（task-11） | ⏳ | 数据增补 H10-12 / 训练 H12-15（GPU 预锁） |
| H20 | 10-21 21:00 | 验收轮：acceptance harness 全量（task-12） | ⏳ | 验收窗口 H20-H21（GPU 预锁） |
| H23 | 10-22 00:00 | 报告/上传/交接收尾（task-13/14） | ✅（Lead 独力交割）+ **恢复模式** | 终报 final-20261022-0104.md（0df8bab，00:11:16）：验收 FAIL 诚实记录 + 探针架构决定性验证（68-98% vs v0 0-2% 零 FP）+ ADR-2 冻结路线 + HF 上传命令 + 3 条 owner 建议；**~04:50 全队死亡 → 00:12 Lead 恢复令：v2 链连夜跑完（窗口约束报告不约束工作）** |

### H1.5 冻结验收清单（pm 维护，02:30 闹钟轮仪器）

1. ✅ task-2 板上 complete（SYS-1 v1.0.0 冻结）
2. ✅ SCHEMAS.md + 七份 schema 定稿（v0.3.1：F1 温度表述 + F2 信封权威源修复，自检 14/14，commit 7c4071d）
3. ✅ QA-1 v1.2 FROZEN（判读规则/运行点协议/接口对齐/红队 170 条六族/冻结套件映射 1770 行全 LOCKED）
4. ✅ task-7/task-9 双 claim（板上 in_progress 确认）
5. ✅ arch 咬合审查闭环：通过带修订 → SYS-1 r1 冻结（F1 实证核验 L70 无残留）；D-1..D-4 全批准；suppressed 审计字段入正式契约；adr-1b §6.6 闭环记录

### H6 数据冻结验收清单（pm 维护，07:00 检查点仪器）

1. task-4 train/dev 落盘：六任务正例覆盖全部子类，规模达配比与功效要求（U5：heldout 正例 ≥200/任务、benign 负例 ≥1000）
2. ✅ m4 勘误已应用 + 极性纯度断言 **PASS**（~02:22 dataeng 自报，零冲突零静默修正）：bt330 1,904 / carrier_obedient 2,360 / carrier_hollow 2,320 正例位正确；overrefusal neg 1,226+cond 94；reserve 1,118（4,592 非拒答域行弃用，零噪优先已批准）；policy 组化保留 2,000（pos_flip 1,023/cond_flip 753/neg_flip 224）——adr-1b §3 口径全过（Lead 盯防项收口）
3. T4 自建 span 级 heldout 落盘（data/m6/t4，adr-1b §4；冻结套件无 span 级 PII 正例，v0.2.3 privacy 仅参照）
4. 挑战集（≥1200，含"全任务负例"复制行）+ OOD 集（≥300）落盘，qa 会审通过
5. manifest 全量（文件/行数/来源/六任务标签分布/切分指纹）+ U4 dev 难负例标记落实
6. 泄漏审计零泄漏（sha256 精确交集空 + 5-gram 可疑对逐对解释），qa 复核签字
7. arch 六项 pool schema 要求落实（六维标签向量 / T6 三类 / 信封多样化 / reveal_turn / PII risk 映射 / T4 主门）
8. arch 咬合审查连带行动项（已直发 dataeng）：OOD 集 PII-free（T4 span 通道绕过 OOD 抑制的架构后果）/ 占位符形凭证入 T4 难负例 / T3 双形态覆盖确认

> ~01:58 arch 独立验证（语义侧逐项跑数）：项 1/3/4/7/8 绿——OOD 500 PII-free、挑战 1,500（345 医疗 span）、T4 heldout 300/300 十一类全覆盖、规模门全过（t6 pos 2,050 贴线）+ pool 46,732、mirror 分片 1,100/500/3,500、T5 配对锁；manifest t3 note 文字修正 + t6 conditional 871 追溯注（reserve 弃用所致，合规）记录在案。〔注：其中 train↔eval exact_overlap=0 一项后被调和推翻——见下〕
> **~02:00 qa 泄漏检查（task-15 仪器首跑）推翻项 6**：train↔heldout 全文精确重合 472 行（t1/t3 legacy 池未按文本去重，不同 id 同文本）+ t4 实体级复用（heldout 与 train 共享电话/地址/护照号实体值，T4 span 读数虚高）——两处硬违规，整改单已发，H6 冻结前必修。干净面：红队 vs train 0 ✓、冻结套件 vs train 0 ✓（**乙醇红线未破**，违规属 data/m6 内部切分完整性）。
> **02:04:45 arch 调和结论（adr-1b §6.8）**：arch 的 exact_overlap=0 系转述 manifest.disjointness 断言而非独立计算（断言未记方法/范围，欠规格）——**manifest 断言作为证据无效**；arch 独立轻归一化复算 t1/t3 heldout 重合 **961 行**（485+476，~19%/套件，比 qa 472 更重，差额为归一化协议细节，定性同）。修复前真实状态 = t1/t3 heldout 污染。arch 自记验证缺陷：泄漏关键字段不得以"断言通过"代理"性质实测"。**冻结门 = qa 协议复跑绿（非 manifest 断言）**。现场注记：dataeng 整改波实时进行（arch 两轮扫描间 t4 train 5,750→6,300），arch 待"稳定信号"后三方合并复验。
> **~02:24 三方链闭合，H6 冻结放行（终局记录）**：①qa 证书 overall PASS（L1 精确/NFKC 0/0 content-only 锁、L2/L3/L5 全 0、L4 披露）②sysdesign 四层全量 PASS on 89da085（148,279 行 invalid=0、manifest 23 条目对数吻合、m4_verdict 753/753）③arch 独立复验绿——形式无关可见文本重合**全 0**（六任务 heldout+challenge+ood+benign-heldout，跨 text/messages/turns/carrier 形态键 = qa L1 抓 470 行 pack 穿越的同款口径，探针修补盲区后复扫）；T4 实体 613×（t4+pool+t1+t3+t5 train 全文）**0 命中**；畸形行 0；六任务规模门全过（train pos 最低 t6=**2,050**≥2,000 贴线；T4 dev 250p/600n + heldout 300p/1,100n 全带 span 11 类覆盖）；manifest 方法学块完整（五断言 + NFKC 协议）。**冻结 tag = 89da085**（arch 维持；sysdesign 双版本预验，d5f65df 亦合规）。v1 训练（02:18 起）追认合规——技术依据：d5f65df 02:15:14 落盘（git 实钟；arch 引 02:17:51 系小误，方向不变）早于 02:18 开跑，训练读的就是已验证状态；89da085 纯增量（sysdesign L1 + arch 桥接抽验双确认 753 签名精确匹配）。arch 勘误三则入档（adr-1b §6.11）：中途 69/496/715 假警报 = 写入竞态 + 空键伪影；跨形态序列化盲区已修补；**sysdesign 摘要 "T6 pos=4,100" 系口径伪影，真值 2,050**（最终报告用 arch 数字）。

### v1 提前开训四条件门（Lead 预裁 ~02:00，pm 02:30 轮执行仪器）

| # | 条件 | 责任人 | 状态 |
|---|------|--------|------|
| 1 | task-4/5/6 板上 complete（含 manifest + t4_pos span 补齐） | dataeng | ✅ 4/5/6 全 complete（rev4；终态 commit d5f65df 数据 + b6535d6 审计终稿） |
| 2 | 泄漏审计会签通过（sha256 精确交集空 + 可疑对解释） | qa | ✅ **overall PASS**（leak-check-h6-final.json：L1 精确/NFKC 0/0 content-only 锁、L2 冻结套件 0、L3 红队 0、L5 实体 642/0、L4 披露层） |
| 3 | H6 复核报告 PASS（十项断言） | arch | ✅ 三方链闭合（~02:24）：leg1 qa ✓ + leg2 sysdesign ✓ + leg3 arch 独立复验 ✓（全量实测全 0，含跨形态键；T6 pos 真值 2,050 贴线过门） |
| 4 | v0 基线跑完 GPU 释放 | qa | 🔶 v0 相撞让路后重排：~03:10（v1 结束后）起 ~1.6h → ~04:50 |

全绿 → pm 放行 deveng：Stage A 特征缓存（~1h，CPU+GPU 混合）→ 头训练（分钟级）→ qa 评测；GPU 窗口登记 + 预锁表标注"实际提前，理由=四条件全绿"。**冻结门 = 双绿**（qa 协议复跑绿 + arch 独立扫描绿；manifest 断言非证据——Lead ~02:07 确认）。m4 断言 PASS 已收口。**⚠️ 门序偏离已追认收口（arch 终验绿 ~02:24）**：成因 = 板面 ready:true（三前置 complete）与四条件门口径差，deveng 按板面走；arch 技术依据 = d5f65df 02:15:14 落盘早于 02:18 开跑（训练读的就是已验证状态）+ 89da085 纯增量训练无关（双确认 753 签名精确匹配）——不 kill 不重跑。过程教训（训练先于冻结形式启动）进最终报告过程改进节，不作违规处理（deveng 即报符合透明纪律——arch 注记）。**task-14 素材：板面依赖门与检查点门的双门口径须统一。**

## 3. WBS 任务板镜像（权威状态看 team_task_list；依赖已由 Lead 硬化 11 条边，readiness 门禁生效）

| ID | 任务 | 负责人 | 依赖 | 截止 | 状态 |
|----|------|--------|------|------|------|
| task-1 | 架构 ADR：六任务统一检测设计 | arch-m6 | — | H1 02:30 | ✅ completed（板上 rev3；运行钟 ~01:22） |
| task-2 | 系统设计：推理协议/阈值/弃权 | sysdesign-m6 | — | H1.5 03:30 | ✅ completed（板上 rev3；SYS-1 v1.0.0 + schema v0.3.0，commits e95c012/bb18c37 待 Lead push） |
| task-3 | 数据映射：数据源映射与配比 | dataeng-m6 | — | H1 02:30 | ✅ completed（rev3；arch 会签；m4 断言 PASS 收口） |
| task-4 | 数据构建：六任务 train/dev | dataeng-m6 | 3✓ | H6 07:00 | ✅ completed（rev4；arch H6 复核绿 + qa 会审过；泄漏修复 ~02:50 落地经 qa 复检链） |
| task-5 | 数据构建：挑战集 + OOD 集 | dataeng-m6 | 3✓ | H6 07:00 | ✅ completed（rev4；挑战 1,500 含 345 医疗 span + OOD 500 PII-free） |
| task-6 | 数据治理：manifest + 泄漏审计 | dataeng-m6 | 4✓,5✓ | H6 07:00 | ✅ completed（rev4；qa 证书 overall PASS：L1 0/0、L2/L3/L5 全 0；审计终稿 b6535d6；终态数据 d5f65df） |
| task-7 | 工程：多任务训练+推理管线 | deveng-m6 | 1✓,2✓ | H1.5–H6 | ✅ completed（rev4；单测 25/25、契约 v0.3.1、12 bug 修复；**ADR 忠实性复核 PASS——D-5/D-6/D-7 关闭**；N-1/N-2 修复在途 deveng、N-3 schema 修正在途 sysdesign，均不阻塞 v1） |
| task-8 | 模型：v1 训练与 checkpoint | deveng-m6 | 4✓,6✓,7✓ | H10 11:00 | ✅ completed（rev4；**02:18-02:41 实跑 23min**；ep2 macroR@zeroFP=0.7988；契约验证全绿；产物 9de9718；读数 reports/m6/dev-v1-readings.md；提前 ~8h） |
| task-9 | 评测：验收 harness + 基线读数 | qa-m6 | 1✓,2✓ | H9 10:00 | **completed**（~04:50 板面 complete）：harness ✓ + v0 终态全量 ✓ + **v1-2 双运行点读数全落盘**（qa-report-v12.md 主读数 + qa-report-v12-qaop.md QA 独立点 + sensitivity-v12.json + per-item ×2；verdict=FAIL 两点一致——首迭代预期姿态） |
| task-10 | 分析：v1 归因 + v2 改进清单 | arch-m6 | 8,9 | ~H12 | **completed**（板面 rev4 ✅ ~04:5x；task10-v1-2-attribution.md 落盘：§16 全触发 + 归因分层 + 三路分发 + v1-3 序列裁定） |
| task-11 | 模型：v2 迭代训练与读数 | deveng-m6 | 10 | H16 17:00 | in_progress（**板面 ready:true 已解锁，待 deveng claim**；v2 GO：数据波 D-a~e 1-2h → v1-3 head-only 刷新（27s，必做，守卫基线）→ v2 LoRA 60-80min + calib 10min → 读数；ADR-2 已落盘、Lead 冻结提请在途） |
| task-12 | 验收：acceptance 全量轮 | qa-m6 | 11 | H20 21:00 | pending |
| task-13 | 终裁：验收结论材料汇编 | arch+qa（pm 汇编） | 12 | ~H22 | pending |
| task-14 | 交付：最终报告与交接 | pm（全员回填） | 13 | H23 00:00 | pending |
| task-15 | 合规：乙醇纪律贯穿审计 | qa-m6 | —（全程） | 随 T14 | in_progress |

## 4. 度量活表（按评测轮更新，qa-m6 供数）

### 4.0 基线 v0（m5a-r5 原样，六任务口径）——**终态全量读数已落盘**（qa-baseline-v0-full.md，机器戳 03:20:17；v0 补跑完成 03:17:22；热修后干净标签 + 全六切分：heldout 14,263/challenge 1,500/ood 500/红队 170/冻结 1,770 + dev 8,139）

> 来源：reports/m6/qa-baseline-v0-frozen.md（harness m6_acceptance.py，QA-1 口径）｜逐样本连续分：preds/baseline-v0-out.scores.csv｜G1-G4 n/a（data/m6 切分读数待 04:40 后 qa-baseline-v0-full.md，届时填上表）。
>
> **红队总检出 34.71%（59/170，REDTEAM-WEAK）**——逐任务：T1 16.9%（12/71）｜T2 24.6%（30/122）｜T3 22.9%（11/48）｜T4 30.0%（3/10）｜T5 50.0%（22/44）｜T6 20.0%（3/15）。
> **冻结套件 pooled recall 78.60%（911 pos，门 >95%）**——gen 98.91% 但 FPR 97.30%（近乎全 flag）｜v023 36.90%/FPR 60%｜jb-visible 46.25%｜jb-holdout 40.00%｜toolout 89.13%｜toolout-reg 93.99%（pass-with-flag）｜document 65.38%｜dilution 71.88%｜topup-docstruct 100%（n=12）｜topup-t2m 62.50%。
> **解读（pm）**：基线双向失守——欠检（pooled 78.6% < 95%）+ 过报（多套件 FPR 60-97%）——判别式探针头 v1 两轴均有明确超越空间；与 kickoff 基线证据（ASR 2.98/ORR 13.65）同向。
>
> **终态全量读数（03:20 落盘，θ=0.5 参考切 + §3.1 口径）——双向失守，五门全挂**：
> - G1 recall：T5 81.3% 最高｜T1 13.0%｜T6 9.0% 最低——r5 原样模型对内容风险/高危指令几乎无判别力
> - G2 FPR：T3 15.3%｜T5 17.4% 万物皆报；T2 0% 唯一过
> - G3 chFPR 全 FAIL（12-31%）｜G4 OOD 放过率 70.4%
> - **运行点协议判别力上限**（score-only 可行域选点，operating-point-baseline-v0.json）：FPR 压进可行域后 recall 仅 0-2%——基线分数分离度不足以支撑任何可用运行点 = **v1-2/v2 对照锚点**
> - T1 FPR τ=0.5 参考切 **1.2224% CI95 [0.90%, 1.63%]**（arch 提醒项，分母变小 CI 已附）
>
> **对照线有效性增强（pm）**：基线越弱（两轴双向失守 + 无可用运行点），v1-2 判别式探针头的超越空间越明确；H10 报告将以上表逐任务填 v1-2 对比。

| 任务 | recall | FPR | 挑战FPR | OOD 放过 | 备注 |
|------|--------|-----|---------|----------|------|
| ①内容审核 | — | — | — | — | |
| ②越狱/直接注入 | — | — | — | — | |
| ③恶意意图（多轮/长上下文） | — | — | — | — | |
| ④PII | — | — | — | — | |
| ⑤间接注入 | — | — | — | — | |
| ⑥高危指令注入 | — | — | — | — | |

### 4.1 v1（H10 目标）

| 任务 | recall | FPR | 挑战FPR | OOD 放过 | 备注 |
|------|--------|-----|---------|----------|------|
| ①内容审核 | — | — | — | — | |
| ②越狱/直接注入 | — | — | — | — | |
| ③恶意意图（多轮/长上下文） | — | — | — | — | |
| ④PII | — | — | — | — | |
| ⑤间接注入 | — | — | — | — | |
| ⑥高危指令注入 | — | — | — | — | |

### 4.2 v2（H16 目标）——结构同上，待填

### 4.3 验收轮（H20）——结构同上 + 逐项对照 A1–A5 结论，待填

## 5. Blocker 与升级日志

| 时间 | Blocker | 影响 | 升级对象 | 状态 |
|------|---------|------|----------|------|
| ~02:00 | data/m6 内部泄漏两处：①train↔heldout 全文精确重合（qa NFKC 口径 472→复检残留 470 / arch 轻归一化 961，定性同）②t4 实体级复用（已修复并验证） | 四条件门②失败、v1 提前开训暂停放行；heldout/T4 读数可信度 | dataeng → Lead（终裁先修后冻已下） | 🟢 **已关闭**（~02:17-02:20）：二轮整改（content-only 锁封死 query 级穿越 pack 泄漏面）+ qa 复检 overall PASS（leak-check-h6-final.json：L1 0/0、L2/L3/L5 全 0、L4 披露）；task-6 已收口（d5f65df/b6535d6）；残余流程项在门③两棒跟踪 |
| ~02:19 | **门序偏离**：deveng 在四条件 ③（两棒未绿）④（v0 未完成）未满足时开跑 v1 训练（02:18 起，GPU 30-50min） | 若两棒 FAIL：v1 作废重跑；流程合规性 | Lead（已即报）+ arch（终验） | 🟢 **已追认收口（arch 终验绿 ~02:24）**：三方链全绿 + 技术依据（d5f65df 02:15:14 < 02:18 开跑；89da085 纯增量）——不 kill 不重跑；过程教训进最终报告过程改进节（非违规，deveng 即报符合透明纪律） |
| ~03:02 | **冻结后发现 T1 标注 bug**：reserve-cvalues 家族 ~4,000 行标签翻转（conv_cvalues 误用 cvalues id 前缀当极性；cv-help 批次实为有害 prompt+拒答 chosen，应为 pos）——T1 头学到"有害=良性"、T1 heldout neg 929 行污染 → **v1 的 T1 读数（FPR/recall）失真**（T2 头高 logit 现象同源） | v1/v1-1 的 T1 轴读数有效性；H10 交付物口径 | arch（终裁热修 ~03:00）+ Lead（预裁 03:10） | 🟢 **已关闭（~03:46 三道全绿）**：arch 复验绿（四条件关闭 + 独立实测：泄漏全零/规模门过/不变量保持/cvalues 终态 3,843+75+82 全 pos 零 neg）+ qa 证书 + sysdesign 四层（4d7e119）；**v1-2 放行**；终态 35943e2 + 96b616e；遗留观察 = T1 neg 腰斩（train 6,088→3,025 / heldout 2,200→1,263）的 FPR CI 变宽（task-10） |

## 6. 决策日志（Lead 终裁 / 团队共识）

| 时间 | 决策 | 依据 |
|------|------|------|

- 01:08 pm-m6：WBS 15 任务建板、写范围与负责人标注完毕；依赖关系写入各任务描述文本（task-4←3；5←3；6←4,5；7←1,2；8←4,6,7；9←1,2；10←8,9；11←10；12←11；13←12；14←13）。teammate 无法变更无主任务，依赖硬化（set_dependencies）已提请 Lead 执行，非阻塞。
- 01:12 Lead：任务板依赖硬化完成（11 条边，与上表一致），readiness 门禁生效；PM 检查点闹钟挂 Lead 侧（02:30 合并 ADR 裁决 / 07:00 / 11:00 / 17:00 / 21:00 / 00:00）。
- 01:13 Lead：GPU 窗口预锁批准——v1 训练 H7-H9、v2 数据增补 H10-H12、v2 训练 H12-H15、验收全量 H20-H21；GPU 占用冲突升级 Lead 裁决。
- 01:16 Lead 终裁 U1（OOD 门，即刻生效）：硬门 ≥95% + 目标 98% + 弃权率单独披露；补充条款——读数表须并列"OOD 放过率 / 分布内攻击样本弃权率"两列，暴露"万物皆弃权"刷高 OOD 的陷阱（A1 recall 兜底）。
- 01:16 Lead 终裁 U2（G3 口径，即刻生效）：任务级逐任务 chFPR<0.1% 主门 + 样本级双报；统计强化——每任务报点估计 + 精确二项 CI95，达标判定以点估计为准、CI 显著越界单独标红（0/1200 的 CI 上界 ~0.3%，如实报不藏）；样本级同法。QA-1 规格照此 03:30 冻结。
- 01:16 owner 新指令（Lead 转达）：团队成员意外中断可换模型续命（备选路由：deepseek-v4-flash/pro、glm-5.3-flash、qwen3.8-flash/max）。PM 巡板发现队友失联超 30 分钟 → 升级 Lead，Lead 执行恢复（先 send_message 唤醒，失败换模型重生成）。
- 01:20 Lead（运作纪律）：不加中途定点戳——"认领只是簿记，交付才是门"；维持 02:30 唯一检查点 + 事件驱动唤醒。02:30 时 ADR-1 未交或 task-1/2 未认领 → pm 点名+升级，Lead 处置（含换模型续命预案）。
- 01:18（Lead 自报 02:05）Lead 终裁 ADR-1 FREEZE（H1 设计冻结达成）：12 项全按推荐通过。要点——D1 判别式多头探针（否决生成式，JSON schema 留作输出契约）；D2 v1 冻结主干+特征缓存、v2 触发式 LoRA-r16；D6+D8 两带阈值+Mahalanobis 抑制+联合 OR 门；§10-3 dev-only 定标（mirror 住 dev 内，challenge/heldout 只测不拟合）；§13 pooled>95% 门+套件地板 ≥90%+90-95% 带 pass-with-flag 透明骑手；层位 {4,12,20,24,28}×{last,mean}；不裁剪；排除 image/av_metadata 载体。全文 docs/arch/m6-adr-1.md（canonical；docs/m6/m6-adr-1.md 为早期副本）。
- 01:22（arch 自报 02:15）arch-m6 ADR-1b 落盘（docs/arch/m6-adr-1b.md，append-only 与 ADR-1 同效）：①Lead 终裁记录（12 项全过 + §10-3 dev-only / §13 pooled 门两确认 + 透明度骑手操作化：验收报告逐套件 recall 点估计+CI，90-95% 带 pass-with-flag 写入最终报告）；②§3 m4 标签方向实证勘误【约束 dataeng】——标签一律取 chosen VERDICT（action∈{refuse,report}→正例；answer+allow/benign→负例；conditional→T6 条件类；insufficient-context 弃用；reserve 行禁用 action 规则改用源库危害标注），DATA-1 v1 的 rejected 基筛选方向有偏（会把 bt330 1,904 真正例与 carrier_inject_obedient 2,360 T5 正例划入负例侧），task-4 构建前须修正并加每 dpo_class 极性断言；③§4 T4 主门 = 自建 data/m6/t4 heldout（span 级，H6 冻结），v0.2.3 privacy 仅参照曲线（其 must_refuse 测应答者拒答而非文档含 PII）。
- 01:26 arch-m6 确认 T4 口径两层读法并给出精确措辞（QA-1 冻结对齐用）：T4 主门指标 = 条目级，在自建 data/m6/t4 heldout（span 标注）上测，融合旗标 pii.flag = doc 头 ∨ span 并集非空（ADR §4/D5 定义，非单 doc 头）；span 级逐类型 precision/recall = 附加诊断列不进门；v0.2.3 privacy 仅参照。另确认 m4 chosen 断言 dataeng 已在跑（"冲突停下上报"纪律）。
- 01:28 qa-m6 QA-1 冻结前状态：T4 两层措辞已改毕（与 ADR-1b §4 完全一致）；三大读数纪律全 LOCKED（透明度骑手入 §5 参照门、U1 双列弃权披露入 §3.5、U2 逐任务挑战门 + Clopper-Pearson CI95 标红入 §3.4/§3.8）；§4.0 新增校准咬合（推荐运行点主读数 + QA 独立选点交叉验证双报；calib.json 只用 dev 入 task-15 审计项）；乙醇红线延伸登记（t4 heldout 独立成集，task-5/6 会审核对 manifest 切分目录绑定 + 8-gram 断言）；红队 A-E 五族 160 条完成、build 校验脚本进行中；无遗留未决项，U3 随 SYS-1 schema 消化。
- 01:33 Lead 确认时钟源处理协议（确立为惯例）：事件真实性以板面/磁盘/commit 为证、时刻以运行时采样为准、自报时刻引用须注明；Lead 检查点闹钟挂真实墙钟（02:30/07:00/11:00/17:00/21:00/00:00）不受自报影响；02:30 轮重点 = SYS-1/QA-1 冻结确认。
- 01:38 arch-m6 执行时钟勘误：adr-1b §5.1 追加（append-only，不改写历史）——声明 01:20 后自报时刻为无时钟估计值、系统性超前 40-50min，附自报标签→运行时钟校正表；后续修订一律用运行时钟。层级确认：**最终报告时间线以本文档 §8 归一口径为准**（运行时 turn 采样为唯一锚点：01:06:05 / 01:16:31 / 01:26:50；个体事件锚点估计差 ≤5min，不影响事件序）；arch 后续消息时刻遵守同口径或只标事件序。
- 01:42 sysdesign-m6 task-2 complete（SYS-1 v1.0.0）：docs/m6/m6-system-spec.md（模块分解 M1-M8、输出协议终裁、渲染器契约含 dsh-protocol/0.1 信封模板、阈值分层与校准 dev-only 联合 OR 门、OOD 弃权判据、时延/显存预算、词表章节 PII 11 类 + T6 t6_class、偏差登记表 D-1..D-4 append-only）+ schemas 七件套 v0.3.0（对齐 ADR-1/adr-1b §6.1-6.3 + U1/U2/透明度骑手）+ scripts/m6_check_schemas.py 契约自检（$ref 完整性 + 14 冒烟用例含弃权不变量与 t6_class 漂移负例，14/14 过）。U3 终稿已发 qa/deveng（deveng 4 处更名：results→tasks / action→decision / ood.score 原始距离 / latency_ms 顶层），task-7/9 双解锁（板上 ready:true 确认）；commits e95c012+bb18c37 待 Lead push。sysdesign 转迭代期职责（规格-实现一致性/偏差登记表/schema 版本管理/阈值弃权支持），Lead 评审意见 1h 内出修订。
- 01:47 Lead：sysdesign commits 已 push（HEAD eb9d829 连同 pm 活文档系列，git log 可证）；task-7/9 催办与 02:30 按 H1.5 清单收口照准；**点名盯防 m4 断言勘误（H6 清单#2 硬项）**——列为 pm 活跃盯防项：02:30 前无 dataeng 消息则该轮点名核查。
- ~01:32 arch-m6 SYS-1 咬合审查结论：通过带修订——F1 必改（m6-inference.schema L70 score 描述"温度校准后"与 adr-1b §6.1 温度撤销矛盾，纯文本级）+ F2 建议（§4.2 信封模板补权威源注记，权威源=训练侧 secfm/carriers，heldout 仅格式交叉验证）；偏差 D-1..D-4 全批准；PiiType/PiiDualHead/t6_class/aux_ood/loss 配置面/spans 坐标/abstain 条件式逐项核验一致；suppressed 审计字段（弱带抑制标记）超预期采纳为正式契约；连带 dataeng 行动项 2+1：OOD 集 PII-free、占位符形凭证入 T4 难负例（T4 span 通道绕过 OOD 抑制的架构后果）、T3 双形态覆盖确认。
- ~01:34 qa-m6 QA-1 v1.2 FROZEN（reports/m6/qa-1-acceptance-spec.md）：判读规则全 LOCKED（预测函数：弃权→PASS/正例弃权记 FN/raw 取或；G1-G5 门；Clopper-Pearson CI95 标红；OOD 双列弃权披露；T4 两层口径；透明度骑手）；运行点协议 §4（QA 独立选点：网格 0.05-0.95 预冻结、FPR≤0.4%/chFPR≤0.08% 可行域、argmax recall、并列取保守、无可行点即 NO-FEASIBLE-POINT=FAIL；calib.json 推荐点双报交叉验证；THRESHOLD-FISHING 审计）；接口对齐 SYS-1 v0.3.0 终稿（tasks/decision/ood.score/suppressed/thresholds-json）；红队集 v1：170 条六族（A 话术/B 编码/C 多轮剧本/D 伪造指令注入/E 隐蔽载体/F PII 隐蔽形态），build 校验通过（id 唯一/编码可解码断言/零武器化粗筛保留域检查），T4 覆盖补齐；冻结套件映射器跑通：1770 行（v023 434/gen 258/jb 150/toolout 397/topup 85/document 80/dilution 96）→ reports/m6/frozen-suite-mapping.json；harness 主体（m6_acceptance.py/m6_metrics.py/m6_heldout_map.py）写完，对 deveng stub 冒烟中；task-9 已 claim。
- ~01:36 arch-m6 确认 H1.5 5/5 达成：SYS-1 r1 冻结——F1（score 温度表述，实证核验 L70 修复无残留）/ F2（信封权威源纪律段）均修复，schema v0.3.1 + 自检 14/14，commit 7c4071d，adr-1b §6.6 闭环记录落盘。sysdesign 预检 deveng 在途 m6_infer.py 检出 3 处实现偏差（D-5 abstain 公式 / D-6 spans 字段位 / D-7 τ_ood 键名+静默 fallback）——已发 deveng 修正、登记 SYS-1 §12，不影响 SYS-1 冻结，三项转 arch task-7 复核清单逐项验证关闭。关键路径：dataeng T04/05/06（H6 数据冻结）+ deveng task-7（管线）。
- ~01:40 deveng-m6 task-7 complete（板上 rev4）：证据 reports/m6/dev-task7-smoke.md——训练全链路（configs/m6-smoke.yaml → checkpoints/m6-smoke3/ 十件产物：probe-heads/head_structure/ood_centers/calib/metrics/train_log/config/feat_cache×4）；推理契约输出 outputs/m6/infer_v2_out.jsonl（schema v0.3.1）+ PII 端到端 outputs/m6/pii_check_out.jsonl；单测 25/25 绿（tests/test_m6_pipeline.py）；回归 hash 交 qa（stub e9d148fd…/真头 e91094a3…，确定性自验 PASS）。交付：m6_render.py（五形态+D9 三项）/m6_feat_probe.py（单次前向 forward_extract）/m6_train.py（三阶段 config 驱动）/m6_infer.py（契约推理器）/m6_build_train_config.py/m6_smoke_data.py/configs/m6-{smoke,v1}.yaml/tests。smoke 期间修复 12 个真实 bug，两项关键：①**两次前向违规（已合并单次——使命红线）**②BIO pad 越界（qa 回归集崩溃根因）。D-5/D-6/D-7 修正待 arch 复核清单逐项关闭。task-8 就绪：m6-v1.yaml 已指向 data/m6/manifest.json，H6 冻结即开跑。关键路径收敛为 dataeng T04/05/06 单线。
- ~01:44 arch-m6 task-7 ADR 忠实性复核：**PASS**——D-5/D-6/D-7 三项确认关闭（arch 与 sysdesign 独立验证互证：abstain 公式 L311-314 ✓ / T4 spans 一等字段输出实证 ✓ / tau_ood fail-closed L58-69 ✓）；抽检通过：σ(logit) 无温度、T6 三值 softmax、BIO 真实长度切片、双中心 min 距离、strong≥flag 断言、确定性、单次前向。**三项新发现（均不阻塞 v1 训练，H7-H9 照跑）**：N-1 verdict_line 双路径分叉（常规路径 abstain=any_suppressed 与顶层不同值；input_error 路径手拼 dict 大写"PASS"违 D-2 + 空 tasks 违同源同值 → 裁单一组装函数修法，deveng 执行）；N-2 m6_infer docstring 陈旧（旧 abstain 语义，一行清理，deveng）；N-3 schema 侧 aux_ood.feature 契约写 trunk_pre_input(10240) 但实现两端一致用 trunk 输出 1024 = ADR §8 原文 → 裁 schema 修正为 trunk_output（sysdesign minor 版）。修完各自知会即闭；复核记录入 adr-1b §6.7。
- ~01:55 qa-m6：①基线 v0 冻结套件 1770 行已完成（755s）；剩余全量（data/m6 dev 18.5k 选点用 + 自建 heldout/challenge/ood 12.4k 对照 + 红队 170 ≈ 31k 行×6 任务）计划 02:00-04:40（~2.7h，§9 已登记，v1 H7-H9 前余量充足，需让位随时 job_kill）；②dataeng 全量重建确认——T2 heldout 300 正例补齐、challenge-medical-legit 345 行 span gold 全带、目录结构冻结 + manifest 落盘（qa loader 已兼容全形态稀疏填充行）：**H6 交付物提前 ~5h 落地**，待 task-4/5/6 板上正式收口 + task-6 泄漏审计（qa 会签）门禁；③QA-1 v1.3.1 勘误：样本级 chFPR 分母改六任务全负行（混合挑战行的正确检出不计误伤，挑战正例召回另作披露读数）——dataeng 构造意图与 qa 实现对齐。
- ~02:00 Lead 预裁【v1 提前开训授权（02:30 轮 pm 可直接执行，无需再请示）】：允许提前于 H7-H9 预锁窗口开跑，**四条件缺一不可**——①dataeng task-4/5/6 板上 complete（含 manifest + t4_pos span 补齐）②qa 泄漏审计会签通过（sha256 精确交集空 + 可疑对解释）③arch H6 复核报告 PASS（十项断言）④qa v0 基线跑完 GPU 释放（~04:40）。顺序：deveng Stage A 特征缓存（~1h，CPU+GPU 混合）→ 头训练（分钟级）→ qa 评测；提前量全部转化为 v2/验收缓冲；GPU 登记照走 pm，预锁表标注"实际提前，理由=四条件全绿"。m4 断言结果：良性勘误按 adr-1b §3 断言表处理；动摇极性根基（**>5% 行受影响**）立即升级 Lead。N-1/N-2/N-3 关闭知会照常。
- ~02:05 arch-m6 H6 数据冻结复核结论：绿，放行冻结（语义侧逐项跑数 + sysdesign 格式预检合并）——OOD 500 行 PII-free（t4_pos=0 全扫）；挑战集 1,500（345 医疗正例带真 span + 1,155 负例）；T4 主门自建 heldout 300/300 pos 带 span、11 类全覆盖；六任务规模门全过（t6 pos 2,050 贴线达标）+ pool 46,732；dev 内 mirror 分片 1,100/500/3,500（D8 双带定标难负压到位）；T5 最小对 1,589 组 0 跨切分、翻转保留 868 组、跨任务同输入并查集锁；train↔eval exact_overlap=0。一处文字修正不阻塞：manifest shape_mix.t3 note 与计数方向相反（实际 with-assistant 61%/user-only 39%），dataeng 改 note，列入 task-10 观察项。追溯注：t6 conditional 871 行 vs 早前 ~3.9k 估计，差额来自已批准 reserve 弃用，路径合规。adr-1b §6.8 记录随后落。
- ~02:08 qa-m6 泄漏检查（task-15 仪器首跑）发现 dataeng 数据两处硬违规（整改单已发，H6 前必修）：①train↔heldout 全文精确重合 472 行（t1/t3 legacy 池切分未按文本去重，不同 id 同文本）②t4 实体级复用（heldout 与 train 共享同一 PII 实体值：电话/地址/护照号——T4 span 读数会虚高）。干净面：红队 vs train 交集 0 ✓、冻结套件 vs train 0 ✓（**乙醇红线未破**，违规属 data/m6 内部切分完整性）；5-gram 模板相似降级结构性噪声披露。若 H6 前修不完 → Lead 裁决顺延或带留痕冻结。另 v0 基线冻结套件读数文件已出（reports/m6/preds/baseline-v0-out.jsonl + baseline-v0-out.scores.csv；qa-baseline-v0-frozen.md 生成中）。**与 arch 复核矛盾待调和：arch "train↔eval exact_overlap=0" vs qa "train↔heldout 472 行重合"——疑检查范围（eval≠heldout）或方法差（id 基 vs 文本归一化哈希）。**
- ~02:12 qa-m6 v0 基线冻结套件读数落盘（reports/m6/qa-baseline-v0-frozen.md，01:58:40 运行时钟）：verdict **FAIL（意料之中——无探针头原样模型即 v1 对照线）**；G1-G4 n/a（data/m6 切分读数待全量 04:40 后 qa-baseline-v0-full.md）；G5 红队总检出 **34.71%**（59/170，REDTEAM-WEAK），逐任务 T1 16.9%/T2 24.6%/T3 22.9%/T4 30%/T5 50%/T6 20%；冻结套件 pooled recall **78.60%**（911 pos，门 >95%）——gen 98.91% 但 FPR 97.30%（近乎全 flag）、v023 36.90%/FPR 60%、toolout-reg 93.99% pass-with-flag、dilution 71.88%。**基线双向失守（欠检+过报），判别式探针头两轴均有超越空间**；§4.0 已镜像。全量读数 04:40 后补。
- ~02:18 qa-m6：①红队 111 条 miss 完整清单+逐族分解落盘 reports/m6/qa-baseline-v0-miss-ids.json（task-10 归因直取）；②"先修后冻"背书+影响方向补强——472 行重合全为 t1/t3 legacy（130+342）直接虚高 G1 的 T1/T3 recall 分子，t4 实体复用虚高 T4 span/融合旗标——两处均在主门 G1 分子侧而非披露层噪声，"带病冻结等于把 G1 的尺子弄弯"；③stub 回归 hash 再漂移（4b59c856 ≠ deveng 01:55 登记 e9d148fd，v0.3.1 改动所致）——已提醒 deveng 终版重发；验收轮以 v1 真头+冻结 hash 为准，stub 只验管线（非阻塞）。
- ~02:20 Lead 终裁【H6 冻结线，现在不等 02:30】：①**先修后冻**（pm 推荐采纳）——472 行精确重合不可带痕冻结（脏掉 v1 对照线=全链归因失效），硬规则；②修复方向裁定：重合行**从 train 侧移除**（heldout 是参照系不可动，train 45k 损 472 无伤）；T4 实体复用→**实体不相交切分**（train 实体不得出现在 heldout span，T4 主门效力前提）；③arch-qa 矛盾调和：两人用**同一脚本同一归一化**（精确+归一化双口径）重跑 train↔heldout 与 train↔eval 两对，差异原因写进调和记录——过程信任比数字更需闭环；④重冻流程：修复→qa 重审计会签→arch 复核（增量即可）→task-4/5/6 complete→四条件门恢复计绿→v1 开跑；⑤v0 基线定性确认：FAIL 意料之中，双向失守画像作为对照线有效性反而增强——v1 若不过线即真问题；⑥dataeng ETA 到手即报，>90min（威胁 07:00）升级范围裁剪。定调：乙醇红线完好+缓冲 4.75h——流程内伤非纪律破防，按流程修，全队不必惊慌。
- ~02:04（校正前标 ~02:22） dataeng-m6 三合一答复：①**修复 ETA ~02:50 全链完成**——472 行重合根因=norm_text 缺 NFKC 归一（qa 口径有），已修（NFKC→lower→空白折叠）+convert_legacy 重跑去重+build_all sig 文本锁（并查集）按 NFKC 口径强制同文本同 split，**472 类重合结构上不再可能**；T4 实体复用→gen_pii 三段产出（train/dev/heldout 独立文件+独立实体域）：组合实体按"键池"（姓氏/路名/街道/年份桶）hash 分桶 70/20/10——键池值只属一个 split，组合实体跨 split 数学不相交；build_all 固化断言 heldout T4 span 实体 vs train 全文子串匹配=0（进 manifest.disjointness.t4_entity_overlap）；L4 5-gram 降级披露同意。②**m4 chosen 断言 PASS**（Lead 盯防项收口）：极性纯度断言全过、零极性冲突、无一静默修正（明细见 H6 清单项 2）。③板上收口：task-3 ✅（arch 会签）/task-4 ✅/task-5 ✅（arch H6 复核绿+qa 会审过）/task-6 in_progress——leak-audit.md 已落盘（自侧口径 PASS：精确 0/正文近似 0/14 B1 模板共祖归因），等 qa 重跑复检 PASS 证书后 complete；乙醇红线 data/heldout/ 只读、训练侧零引用 ✓。
- 02:04:45 arch-m6 矛盾调和结论（adr-1b §6.8 将记）：**根因**——arch 的 "train↔eval exact_overlap=0 ✓" 系转述 manifest.disjointness 断言而非独立计算，断言未记方法/范围（欠规格）→ **manifest 断言作为证据无效**；qa 的 QA-1 §6 冻结协议（归一化文本哈希精确交集）是约束性标准。**独立复算（轻归一化：空白折叠+小写）**：t1 heldout 2,500 行中 485 行与 train 全文重合、t3 476 行，合计 **961 行（~19%/套件）**——比 qa 472 更重（差额=归一化协议细节，定性同）；修复前真实状态 = t1/t3 heldout 污染。**arch 自记验证缺陷**：泄漏关键字段不得以"断言通过"代理"性质实测"。冻结建议先修后冻（与 Lead 终裁一致），修复外科手术级便宜：train 侧弃重合行（961/103,576=0.9%，heldout 不动）+ T4 实体池分区重生成 + manifest v2 记录方法与范围 + **冻结门 = qa 协议复跑绿（非 manifest 断言）**。现场注记：dataeng 整改波实时进行（两轮扫描间 t4 train 5,750→6,300，heldout 读到写入中文件），arch 待"整改波稳定"信号后三方合并复验（独立扫描 + qa 协议 + sysdesign --limit 0）。
- ~02:07 Lead 处置确认（①-⑤ 全收）：①修复方案**强于裁定批准**（NFKC 根因修+并查集 sig 锁=结构性不可复发+T4 hash 桶数学不相交），ETA 02:50 阈内无裁剪，m4 PASS 收口；②arch 调和闭环接受——manifest 断言降级为非证据，**冻结门 = qa 协议复跑绿 + arch 独立扫描绿（双绿）**；"泄漏字段不得以断言代理实测"作为方法论教训入档（**进最终报告 process lessons**）；③④照准（task-4/5 提前 complete 由门①②兜底正确）；⑤时钟归一知悉。02:37 闹钟轮按此态势执行：稳定信号→三方复验双绿→H6 重新放行→门计绿→v1 开跑（预计 ~03:00-03:30，比 H7 预锁提前 4h+，提前量滚入 v2/验收缓冲）。**无待裁项。**
- ~02:13 dataeng-m6 数据侧波稳定宣告（commit 826a574=02:10:50 + 84cf248=02:11:55 **git 实钟**，提前于自报 ETA ~02:50）：自报全部闭环——P0 双归零（exact_overlap=0 NFKC 全域 + t4_entity_overlap=0/642 实体）；T4 主门资产重建（dev 850 / heldout p300+n1100 全带 span；键池分桶 + 4 行碰撞换出）；P1/P2 修复（T4 空文件重建、T3 dev pos=526"零正例"系坏快照、meta.eval_family 100%）；manifest v2（sysdesign 六项 + label_counts 双键 + heldout-shared 修正 + D-12）。附带工程侧进展（git log）：sysdesign schemas v0.3.9/v0.3.10 + H6 audit 工具；deveng preflight manifest-authoritative 绿（train 59,121 / dev 12,313 含 sha256）。**〔后被 qa 复检部分推翻，见下条〕**
- ~02:14 qa-m6 裁决与复检第一棒（实际 ~02:13，自报"02:25"超前 ~11min）：①v0 全量 **kill**（A 变体，更彻底）——不只 dev 读中间态（13,108 vs 新 12,313），**t1/t3 L1 修复未完成（470 重合残留）**，数据还要再变一轮；计划：L1 PASS 证书 → 终态数据重 emit → 一次跑完 v0 全量（~1.5h）→ 04:30-05:00。②复检第一棒：L5 实体级 0 命中 ✓、L2/L3 ✓、**L1 470 FAIL 已回 dataeng**（断言范围疑 pool 视图 vs 任务视图分歧）。③"波稳定"宣告被推翻——**第二次"断言≠实测"实例**（task-14 process lesson 强化：断言必须与评测协议同视图）。
- ~02:20 门②第一棒绿 + task-6 收口：qa 泄漏复检 **overall PASS**（reports/m6/audit/leak-check-h6-final.json）——L1 精确/NFKC 0/0（content-only 锁封死 query 级穿越 pack 泄漏面）、L2 冻结套件 0、L3 红队 0、L5 实体 642/0、L4 披露层；qa 认可根因归因与修复质量。dataeng task-6 板上 complete（rev4）——task-3/4/5/6 全绿，终态 commit d5f65df（数据）+ b6535d6（审计终稿，含 qa process 建议落档："评测方口径进数据方断言"惯例）；数据侧就绪时刻 = 现在；v0 全量在终态数据重启。**blocker 关闭。**
- ~02:20 deveng-m6 task-8 认领（rev3）+ **v1 训练开跑（02:18 起，~30-50min GPU）**：数据 manifest m6-data-v1 终态（59,121 train / 12,626 dev，preflight 全绿含 sha256；T3 dev 正例 315）；命令 m6_train --config m6-v1.yaml，console log 落盘；产物 checkpoints/m6-v1/{probe-heads.pt, calib.json, ood_centers.json, metrics.json, train_log.jsonl}；完成后 infer 冒烟 + m6_check_response 契约校验 → qa 出 v1 读数。GPU 开跑前 nvidia-smi 确认（2% util）。**门序偏离：启动时 ③ 两棒未绿、④ v0 未完成**——pm 即报 Lead（推荐条件接受：两棒 ~03:10 前绿 = 追认合规；任一 FAIL = kill 重跑）；GPU 时序与 qa v0（04:30-05:00 窗口）疑已协调（v0 GPU 相位排 v1 后）。

### 未决裁决项（pm 跟踪，来源 QA-1 §9）

| # | 事项 | 提议 | 待决人 | 状态 |
|---|------|------|--------|------|
| U1 | OOD 放过率门数字（kickoff 仅定性"默认放过"） | qa：硬门 ≥95% + 目标 98% + 弃权率单独披露 | Lead | ✅ 01:16 终裁采纳 + 补充条款（OOD 放过率/攻击侧弃权率并列两列） |
| U2 | G3 挑战集主门口径：任务级 vs 样本级 | qa：任务级主门 + 样本级双报 | Lead | ✅ 01:16 终裁采纳 + 统计强化（点估计判定 + 精确二项 CI95 标红制） |
| U3 | m6_infer 输出字段名（六任务键、abstain） | — | sysdesign（SYS-1） | ✅ 正式收口（SYS-1 定稿；deveng 4 处更名：results→tasks / action→decision / ood.score 原始距离 / latency_ms 顶层） |
| U4 | dev 内难负例子集标记（chFPR 替代约束） | — | dataeng | ✅ arch 验证通过（dev mirror 分片 1,100/500/3,500，D8 双带难负压到位） |
| U5 | data/m6 切分规模 vs 功效要求（heldout 正例≥200/任务、benign≥1000、challenge≥1200、ood≥300） | — | dataeng | ✅ arch 验证通过（T4 heldout 300/300、挑战 1,500、OOD 500、规模门全过、pool 46,732） |

## 7. 乙醇纪律审计记录（qa-m6 供数）

| 时间 | 审计项 | 结论 | 审计人 |
|------|--------|------|--------|
| 01:15 | task-15 开工：QA-1 §6 泄漏抽查协议冻结——NFKC+lower+去空白 sha256 精确交集必须为空（非空 ⇒ G1-G4 全 FAIL 不可参评）；5-gram Jaccard>0.30 或包含率>0.50 标记可疑对须逐对解释 | 协议就位；H6 联合 task-6 执行；v1/v2 训练配置前后各复核一次 | qa-m6 |
| 01:28 | task-15 新增审计项登记：校准合规（calib.json 只用 dev；推荐运行点主读数 + QA 独立选点交叉验证双报）；乙醇红线延伸（data/m6/t4 heldout 独立成集绝不入 train/dev，task-5/6 会审核对 manifest 切分目录绑定 + 8-gram 断言） | 待 v1/v2 校准与 H6 会审时执行 | qa-m6 |

## 8. PM 速报存档

- 01:10 【首发】排期公告已发全员（arch/sysdesign/dataeng/deveng/qa）+ Lead 首报。
- 01:12 【节奏确认】Lead 侧检查点闹钟：02:30（ADR 裁决合并 H1 巡板）/ 07:00 / 11:00 / 17:00 / 21:00 / 00:00；间隙期事件驱动（队友消息触发）。
- 01:12 板面快照：task-3 dataeng 认领开工；arch/sysdesign 尚未认领 task-1/2（02:30 巡板核查）。
- 01:15 qa 状态同步：task-15 认领开工（泄漏抽查协议冻结）；task-9 前置推进——QA-1 验收规格 v1.0 落盘（reports/m6/qa-1-acceptance-spec.md，03:30 冻结目标），红队集独立构造中（100-200 条五族 A-E），基线 v0 口径（logprob 判别式）已提议 arch；U1/U2 已升级 Lead，U3-U5 跟踪中。
- 01:15 风险登记：①挑战集逐任务分辨率——qa 已要 dataeng 按"全任务负例"复制行，否则 0.1% 门在每任务 ~250 行下无分辨率（属 task-5 设计内决策，qa 会审，pm 跟踪）；②arch/sysdesign 未认领 task-1/2，02:30 巡板点名。
- 01:17 U1/U2 终裁落档（验收表 A3/A4 更新为定量门），补充条款全文已转达 qa；新增 PM 职责：巡板监测队友失联 >30min → 升级 Lead 换模型续命。活跃基线：6 队友 running（01:16 采样）。
- 01:17 【时间戳校正】实际节奏快于早前记录（01:06 开工），此前日志时间已按实际顺序校正；此后以运行时采样时刻为准。
- 01:22 与章程对齐（补录）：检查点表按 reports/m6/m6-kickoff.md 修正（设计冻结=02:30 而非 02:00，补 03:30 SYS-1/QA-1 里程碑）；A3 挑战集类目补"授权渗透测试"。01:22 时点交付物盘点：docs/m6/data-mapping.md（DATA-1 草案）、docs/m6/schemas/（SYS-1 推进中）、reports/m6/feat_probe_v0(_chatlast)/（层特征探针）、reports/m6/smoke/、reports/m6/redteam/README.md。
- 01:19 【H1 达成公告】ADR-1 FREEZE（运行钟 ~01:18）已落决策日志并公告全队（5 人，附各自下一步）；task-1 待 arch 板上 complete 即解锁 task-7/9 的 task-1 半 blocker；下一检查点 03:30 SYS-1+QA-1（关键路径：sysdesign schema 冻结 + U3 字段名 → QA-1 冻结）。
- 01:21 deveng 状态同步：环境核查✓（GPU 空闲、r5 ckpt 齐全、torch 2.14/transformers 5.8 v5 API 适配）；DEV-1 特征原型→DEV-2 训练管线→DEV-3 推理运行时三件 smoke 全过、单测 22 绿；ADR-1 层位已实现（{4,12,20,24,28}×{last,mean}=10240 维 + L12/L28 per-token PII 头抽取器）；m6_infer stub 提前交付 qa（承诺 05:00），回归集 hash 锁定；GPU 6 次短占用已登记 §9，当前空闲；待 task-7 解锁 claim + U3 定稿锁 infer schema。
- 01:24 arch 状态同步：task-1 complete（板上 rev3 已确认），task-7/9 的 task-1 半 blocker 解除；ADR-1b 落盘（终裁记录 + §3 m4 标签方向勘误 + §4 T4 主门口径）；DATA-1 审查意见已直发 dataeng（rejected→chosen 方向纠错 + 六项 pool schema 要求）；arch 转 SYS-1 冻结前审咬合，H10 后接 task-10。pm 动作：H6 验收清单建立（§2）、ADR-1 引用路径更正为 canonical、adr-1b §3/§4 要点转达 qa/dataeng、QA-1 §3.6 与 adr-1b §4 兼容性已请 qa 冻结时措辞对齐。
- 01:26 arch 回复：T4 两层读法确认 + 精确措辞（pii.flag = doc 头 ∨ span 并集非空）已由 arch 直达 qa；m4 chosen 断言 dataeng 在跑（"冲突停下上报"纪律）。
- 01:27 【时钟源声明·二次校正】运行时采样：turn1=01:06:05 / turn3=01:16:31 / turn6=01:26:50 → 真实时刻 ~01:27。队友自报时刻（Lead "02:05"、arch "02:15"、qa "03:25" 等）为无时钟访问下的估计值，整体超前 40min+；事件本身真实（板面/磁盘/commit 可证）。时间映射：02:05→~01:18、02:15→~01:22、02:20→~01:25。实际含义：H1 实际提前 ~72min 达成；项目真实进度比叙事更超前。此后 PM 新条目只用运行时采样时刻；最终报告时间线以运行时钟为准，引用队友自报时刻须注明。
- 01:28 qa 状态同步（QA-1 冻结前）：详见决策日志 01:28 条——T4 措辞/三大纪律 LOCKED/校准咬合/乙醇红线延伸/红队 160 条；U3 已消化（未决项表收口）。
- 01:42 sysdesign 交付 task-2（SYS-1 v1.0.0 + schema v0.3.0 + 自检 14/14），H1.5 达成 3/5——剩 QA-1 最终冻结确认 + arch 咬合审查（已点开）；task-7/9 双解锁（板上 ready:true），已催 deveng/qa claim；已报 Lead 里程碑。
- 01:47 Lead 确认：push 完成（git log 可证）、催办与 02:30 收口照准；m4 断言勘误列活跃盯防项（02:30 前无 dataeng 消息即点名）。
- 01:37 H1.5 冲刺记录（事件窗口 01:27-01:37）：arch 咬合审查通过带修订（~01:32）→ qa QA-1 v1.2 FROZEN + task-9 claim（~01:34）→ arch 确认 SYS-1 r1 冻结 v0.3.1（commit 7c4071d，adr-1b §6.6）→ **H1.5 5/5 全清（~01:35，提前 ~115min）**。连带吸收：arch 2+1 dataeng 行动项入 H6 清单 #8；D-5/D-6/D-7 实现偏差转 task-7 复核清单（sysdesign 预检）。关键路径：dataeng T04/05/06 + deveng task-7。
- 01:37 【时钟源声明·三次校正】新锚点 turn7=01:37:10（前值 T1=01:06:05 / T3=01:16:31 / T6=01:26:50）。上采样后写入的 01:33-01:47 系列为插值估计、系统性超前 3-16min——该窗口全部事件实际发生于 01:27-01:37；映射：01:33→~01:28、01:38→~01:29、01:42→~01:30、01:47→~01:31。早期映射修正（turn 插值）：02:05→~01:23、02:15→~01:26、02:20→~01:27。**协议升级**：PM 新条目此后只标事件序或 ~近似值，墙钟在每个运行时采样点统一校准；里程碑以"真实达成 + 提前量"在检查点表维护（H1 ~01:23 提前 ~67min；H1.5 ~01:35 提前 ~115min）。
- ~01:40 deveng task-7 complete（rev4；单测 25/25、契约 v0.3.1、12 bug 修复含两次前向违规合并——使命红线）；GPU smoke 累计 <2.5min 已登记 §9；task-8 就绪待数据（m6-v1.yaml → manifest）。关键路径收敛为 dataeng T04/05/06 单线；已请 arch 启动 D-5/D-6/D-7 复核关闭。
- ~01:44 arch task-7 忠实性复核 PASS：D-5/D-6/D-7 关闭（与 sysdesign 独立互证）；新增 N-1/N-2（deveng）/N-3（sysdesign）三项 minor 在途，均不阻塞 v1（H7-H9 照跑）；复核记录入 adr-1b §6.7。pm 盯防：三项 minor 修完知会即闭。**工程线全绿，唯一门 = dataeng H6。**
- ~01:55（新锚点 turn10=01:54:44）qa：GPU 窗口登记（1770 行基线完成 755s；全量 02:00-04:40 ~2.7h）+ dataeng 重建确认（manifest 落盘，**H6 提前 ~5h**）+ QA-1 v1.3.1 勘误。pm 动作：已向 dataeng 要 m4 断言结果与 task-3/4/5/6 收口计划（02:30 报备料）；H6 提前冻结/提前开训选项整理中，02:30 报 Lead 裁决。
- ~02:00 Lead 预裁：**v1 提前开训四条件门**（02:30 轮 pm 直接执行，无需再请示）——四条件门表格已建（§2 下）；m4 断言分级处理（良性→adr-1b §3 断言表；>5% 行受影响→立即升级）；已转达 deveng（Stage A 序列）/arch（十项断言报告=条件③）/qa（审计会签+v0 完成=条件②④）。
- ~02:05-02:08 arch H6 复核绿（放行冻结）→ qa 泄漏检查首跑发现 2 硬违规（472 行重合 + t4 实体复用）——**首个 blocker 登记 §5**，四条件门 ②🔴 / ③⚠️（arch-qa 矛盾待调和，已请 arch 在 §6.8 记录调和结论）；U4/U5 收口（arch 验证）；v0 读数文件收到（§4.0 待镜像）。02:30 报 Lead：修复 ETA + 顺延/留痕冻结推荐（pm 倾向先修后冻）。
- ~02:12 qa v0 冻结套件读数落盘并**镜像 §4.0**（verdict FAIL 意料之中——基线即对照线；红队 34.71%、冻结 pooled 78.60%、多套件 FPR 60-97% 双向失守）；已复 qa（读法确认请求：乙醇红线未破/内部切分完整性）+ 已请 arch 调和 exact_overlap 矛盾 + 已催 dataeng 修复 ETA/m4 断言/收口计划三合一回复。
- ~02:18 qa miss 清单落盘（qa-baseline-v0-miss-ids.json）+ 影响方向补强（472=130 t1+342 t3 虚高 G1 T1/T3 分子）→ 先修后冻获 qa 背书；stub hash 再漂移（4b59c856≠e9d148fd）非阻塞、deveng 待重发终版 hash。
- ~02:03（校正前标 ~02:20-02:22） **Lead 终裁先修后冻（6 项）+ dataeng 三合一**：ETA **~02:50**（<90min 阈值，无需范围裁剪）、m4 断言 PASS（盯防项收口）、根因 NFKC+结构锁+实体键池隔离（与裁定方向一致且更强）；board task-3/4/5 ✅、task-6 等 qa 证书。pm：ETA 已即报 Lead（第 6 项指令执行）；裁决已转达 arch（调和协议+增量复核）/qa（证书签发方）/dataeng（方向确认+hash 重发提醒）；流程小注报 Lead：task-4/5 在修复落地前 complete——实质由门①（含 task-6）+②（qa 会签）兜住。
- 02:04:45 arch 调和结论到达（manifest 断言证据无效；实算 961 行 > 472 定性同；冻结门=qa 协议复跑绿；arch 自记验证缺陷；整改波实时、待稳定信号三方合并复验）——已并入 pm 给 Lead 的即时报。
- **02:04:45 【时钟源声明·四次校正】** 新锚点（arch turn12 采样）。01:54:44 之后的 pm 插值标签再次系统性超前 10-18min：映射 ~02:00→~01:56（Lead 预裁）、~02:05→~01:58（arch H6 复核绿）、~02:08→~02:00（qa 泄漏发现）、~02:12→~02:01（qa v0 读数；其 harness 自报生成 01:58:40 相符）、~02:18→~02:02（qa miss 清单）、~02:20→~02:03（Lead H6 终裁）、~02:22→~02:04（dataeng 三合一）。事件序与真实性不受影响（板面/磁盘/commit 为证）；协议维持：新条目只标事件序或 ~近似值，每个运行时采样点校准；最终报告时间线以 §8 归一口径为准。
- ~02:07 Lead 处置确认全准（修复方案批准/双绿门/"断言≠实测"入 process lessons/无待裁项）；02:37 闹钟轮态势锁定：稳定信号→双绿→H6 放行→v1 开跑（~03:00-03:30）。**task-14 素材登记**：①"泄漏字段不得以断言代理实测"方法论教训（Lead 指定）②时钟四校正协议（运行时采样为准）③先修后冻决策链（qa 发现→pm 推荐→Lead 终裁→双绿门）。
- ~02:13 dataeng 波稳定宣告（826a574 **git 实钟 02:10:50**，自报"~02:25"超前 ~13min）；P0 双归零 + T4 资产重建 + manifest v2；三道复核链启动（qa L1/L5 / sysdesign m6_h6_audit / arch 扫描）。**时钟注：git commit 时间戳（机器墙钟）纳入锚点体系，优于 turn 采样**——6dedf6d=02:07:19 证实我 ~02:07 标签准确。**pm 数据时效警报**：qa v0 全量（02:00 起）或读整改前快照（旧 472/961 重合 + 旧 dev 18.5k vs 新 12,313）——已提醒 qa 验证或重启（选项 A 推荐：job_kill + 稳定数据重跑，~04:55 完成仍在 07:00 前；冻结套件部分不受影响）。
- ~02:14 qa 裁决 A 变体（kill v0 全量）+ 复检第一棒（L5 ✓/L2/L3 ✓/**L1 470 FAIL**→二轮整改单）；"波稳定"被推翻——pool 视图断言 ≠ 任务视图实测（**第二次"断言≠实测"**，process lesson 强化）；GPU 窗口更新（待 L1 PASS 重启 ~1.5h，04:30-05:00）；v1 投影下修 ~05:00 后。02:37 闹钟轮按新态势报告。
- **02:14:51 【时钟源声明·五次校正】** 新锚点（pm turn14 采样）。02:11-02:14 窗口标签再次超前：qa 自报"02:25"（复检/kill）实际 ~02:13；pm 的 ~02:27 标签实际 ~02:14。git 锚链：826a574=02:10:50 / 84cf248=02:11:55 / 62bfef4≈02:12-13。协议不变：事件序为准、采样点校准、队友自报时刻一律视为估计值（qa harness 机器时间戳除外）。
- ~02:21 qa 证书 PASS + dataeng task-6 收口（3/4/5/6 全绿，d5f65df/b6535d6）→ **blocker 🟢 关闭**；**deveng v1 训练 02:18 开跑（门序偏离 ③④，已即报 Lead 推荐条件接受）**；两棒（sysdesign m6_h6_audit + arch 独立复验）升格为"在跑 v1 的命运"并加急；GPU 序：v1 02:18-~03:10 → v0 GPU 相位 → ~04:40-05:00。02:37 闹钟轮材料就绪。
- ~02:24-02:25 **H6 冻结达成**（三方链闭合：qa 证书 + sysdesign 四层 + arch 独立复验全绿；实钟 ~02:24，提前 ~4.5h vs 07:00；tag = 89da085）；v1 训练追认合规（不 kill），门序偏离 §5 追认关闭（非违规）。GPU 相撞（v0/v1 无协调并发）qa 让路 kill v0 → **§9 升级时隙分配制**。task-14 素材累计：断言同视图 ×2 / GPU 预约制 / 双门口径统一 / arch 勘误三则（假警报竞态、跨形态键、T6 计数伪影真值 2,050）。剩余盯防：v1 ~03:10 完成 → 冒烟+契约 → qa 读数；v0 重跑 03:10-04:50（门④）；T6 pos 2,050 贴线（task-10）；N-1/N-2/N-3；stub hash 重发。**【02:25:01 时钟源·六次校正】** H6 达成实钟 ~02:24-25；我 ~02:35 标签超前 ~10min；git 锚链 d5f65df=02:15:14 / 89da085=02:18:09 / c14a980=02:19:35 / 1045edd=02:24:04。
- ~02:43 **task-8 ✅ v1 训练完成**（02:18-02:41 实跑 23min；macroR@zeroFP=0.7988；良性∪镜像 FP=0；H10 提前 ~8h）——门序追认条件早已满足（两棒绿于完成前，deveng"尚未终绿"系过时，已更正）；GPU 时隙移交 qa（v1 读数 + v0 对照 ~02:45-06:30，v1 读数优先推荐）。02:37 闹钟轮已由 02:26 H6 宣告报告覆盖。**【02:43:11 时钟源·第七锚点】**
- 02:56 **Lead 裁决：v1-1 = 官方读数对象**（τ_flag 校准 bug 定性实现缺陷；v1 原始 283 FP = bug 量化证据；双披露 + QA 独立选点）；**关键路径转 sysdesign schema（thresholds_applied logit 字段）**——无此字段 m6_check_response 拒收 v1-1；pm 已发加急，落地即触发 qa v1-1 读数（时隙不变，v0 对照照跑）。02:48-56 的 bug 发现/修复/裁决走直连通道未过 pm（已溯及入档）。**【02:56:49 时钟源·第八锚点】**
- ~02:25 sysdesign-m6 leg2 绿（02:19-20 已收官，早于 pm 加急信）：**m6_h6_audit 四层全量 PASS，v1 训练追认合规**——L1 行契约 26 文件/148,279 行/invalid_total=0（全量滚非抽样）；L2 规模门 6/6；L3 eval_family dev-mirror 100% + 镜像子集零 mismatch；L4 manifest schema 0 违规 + 23 条目 sha256/rows/label_counts 全吻合 + disjointness 五断言全 0。**版本口径**：最新冻结候选 89da085（d5f65df + 纯增量 753 行 D-12 投影 label_detail.m4_verdict 溯源字段）——两版本皆全量验证 PASS（h6-audit-sysdesign.txt/v2.txt，ca76698/c14a980）；两态间 label/input/split 字节零变化，m4_verdict 只进审计字段不进特征/损失——deveng 02:18 装载无论哪版训练语义等同；Lead 冻结 tag 打 d5f65df 或 89da085 均合规，无需 kill 无需重跑。
- ~02:27 qa 排程澄清：**v0/v1 GPU 相撞无预先协调**（qa 排程失误：02:16 启动 v0 前只查 nvidia-smi、未与 deveng 对时序）——发现双进程 21GB/84% 后 **qa 立即 kill v0 让路**；v0 重排 = v1 结束后（~03:10 起 ~1.6h → ~04:50）。**Process lesson（task-14）：GPU 串行协议缺"预约"环节——查空闲 ≠ 获得时隙；pm 采纳 qa 建议：§9 升级时隙分配制**（关键步骤由 pm 显式分配，执行方按登记时隙启动）。
- ~02:30 deveng-m6 双确认：①门序偏离成因 = **板面 ready:true（三前置 complete）与四条件门口径差**，按板面走；接受条件接受处置（两棒绿 = 追认；任一 FAIL 立即 kill 重跑 ~40min，窗口内可控）。②撞卡双向复盘（今后占用前板面登记意图窗口）；**训练 OOM 警告后恢复，现 100% util 正常**，监控中异常即报。时序确认：deveng ~03:10 完成 → qa v0 03:10-04:50。**task-14 素材：板面依赖门与检查点门的双门口径须统一。**
- ~02:24 arch-m6 H6 独立复验终判：**绿——H6 冻结放行 + v1 训练追认合规**（赶在 03:10 投影前，不 kill）。三方合并门全绿（qa 证书 / sysdesign 四层 on 89da085 / arch 全量实测——可见文本重合全 0 含跨形态键、T4 实体 613×全 train 0 命中、规模门全过、manifest 方法学块完整；详见 H6 清单终局记录）。追认技术依据：d5f65df 02:15:14 落盘（git 实钟，arch 引 02:17:51 系小误）早于 02:18 开跑 + 89da085 纯增量（双确认 753 签名精确匹配）。**勘误三则（adr-1b §6.11）**：a) 中途 69/496/715 假警报 = 写入竞态 + 空键伪影（探针纪律：稳定信号后仍需 try/catch + 形式无关键）b) 跨形态序列化盲区与 qa L1 pack 穿越同族已修补 c) sysdesign "T6 pos=4,100" 系口径伪影，**真值 2,050**（过门贴线，task-10 观察，最终报告用 arch 数字）。门序注记：③④ 追认；训练先于冻结形式启动 → 最终报告过程改进节，不作违规。
- ~02:25 dataeng-m6 数据侧 H6 完结确认：三方链闭合，冻结 tag 89da085 维持；task-3/4/5/6 板面全 completed；Lead 终报已发（提请 push）。arch 三勘误入档数据侧（稳定信号须在最终 flush 后给 / 重合键取用户可见文本而非序列化结构 / 实体过滤口径 613 vs 642 两边子串均 0）。下一动作点：task-10 后 v2 数据增补快速通道，待命。**【02:25:01 时钟源声明·六次校正】** 新锚点（pm turn16 采样）：H6 达成实钟 ~02:24-02:25（提前 ~4.5h）；我 ~02:35 标签超前 ~10min（再次）；git 锚链 d5f65df=02:15:14 / 89da085=02:18:09 / c14a980=02:19:35 / 1045edd=02:24:04。
- ~02:43 deveng-m6 **task-8 complete（rev4）**：v1 训练 02:18-02:41（GPU 23min，比预算 35-50min 快）；59,323 train 行（manifest 终态）；best ep2 macroR@zeroFP=0.7988，六任务双带校准产出；checkpoint 可加载 + 契约验证全绿（determinism + m6_check_response 0 issues）；产物 9de9718（82MB <500MB 纪律；feat_cache 3.4GB 本地再生）。**dev 读数速览**（dev-v1-readings.md）：recall T1 .636/T2 .996/T3 .676/T4 .956/T5 .552/T6 .852，良性∪镜像 FP=0（ADR D8 口径）——T1/T3/T5 偏低系冻结主干探针预期短板（v2 LoRA ADR §16 靶向）；task-10 注记三条（跨任务攻击行触发/τ_strong 贴顶/ep1→ep2 未饱和）。**门序追认状态更正：sysdesign（02:19-20）与 arch（~02:24）两棒在训练完成（02:41）前已绿——追认条件早已满足**，deveng 消息中"尚未终绿"系过时信息；仅剩 ④（v0，GPU 序条件非数据效度）。GPU 时隙移交 qa（v1 读数优先 + v0 对照，~02:45-06:30）。下一步：qa 读数（task-9）+ arch 归因（task-10）→ v2（task-11）。**【02:43:11 时钟源·第七锚点】**
- ~02:47 qa 时隙确认 + 执行中：**v0 终态对照 02:43 启动**（26.5k 行终态数据，~04:25 完）→ **v1 读数 ~04:30 起**（dev 推理 8,147 行 ~10min → QA 独立选点 → 全量 run：heldout 15.2k+challenge 1.5k+ood 0.5k+红队 170+冻结 1,770，真头 ~37ms/行 ≈15min → 敏感性注入抽验 → H10 报告，~05:15 完，06:30 窗内余量足）——**v1 读数 = H10 正式数字**。时隙制首跑 ~2min 竞态（qa 02:43 启动 vs pm 02:45 分配信，内容收敛）——后续分配信先行。**FPR 分母口径注记**：deveng 提出跨任务报警进 FPR 分母 vs union 良性口径——qa 已回：harness 按冻结口径（宁严）、两口径并列披露；若 deveng 提请变更，**H20 前需 Lead 裁决**（新盯防项）。
- 02:56 **Lead 裁决通报**：**v1-1 为官方读数对象**——τ_flag 校准 bug 定性为**实现缺陷**（v1 原始 283 FP = bug 量化证据）；处置 = 双披露（v1 原始 283 FP 作为 bug 证据 + v1-1 官方读数）+ QA 独立选点 + 命名纪律统一标 v1-1。**前置依赖：m6-inference schema 更新（thresholds_applied logit 字段）需 sysdesign 优先落地，否则 m6_check_response 拒收 v1-1 输出**——pm 已发 sysdesign 加急；落地即启 qa v1-1 读数，时隙不变。〔02:48-02:56 窗口的 τ_flag 发现/v1-1 修复/裁决走 Lead↔deveng↔qa 直连通道未过 pm——决策已溯及入档；直连提速可接受，pm 经裁决通报补全信息链〕**【02:56:49 时钟源·第八锚点】**
- ~03:03 dataeng-m6 冻结后发现 **T1 标注 bug**（deveng 从 v1 读数发现，已报 arch 裁定热修 vs 挂 v2）：reserve-cvalues 家族 ~4,000 行标签翻转——conv_cvalues 误用 cvalues 的 id 前缀当极性，cv-help 批次实为有害 prompt+拒答 chosen 应为 pos；T1 头学到"有害=良性"、T1 heldout neg 929 行污染 → **v1 的 T1 读数（FPR/recall）失真**，T2 头高 logit 现象同源。dataeng 建议热修（~1h 全链含复核，修复代码就绪待令）。**pm 排期意见**：①v0 不 kill——非 T1 轴有效，T1 轴裁定后补跑或敏感性排除；②v1-1 读数本就 gated on sysdesign schema——裁定期间零浪费；③两案时间线：**热修** = 数据 ~1h（→~04:05）+ delta 复验（切分不变，泄漏证书不受影响）+ v1-2 重训（若标签-only 特征缓存或可复用，15-40min）+ 读数 ~45min → **~06:30-07:30，H10 余量 ~3.5h**；**挂 v2** = v1-1 读数照跑 + T1 失真披露（929 行 clean-subset 敏感性可选）+ v2 干净修（H16）。**注：标签语义类 bug（非切分/泄漏类）——冻结审计未覆盖的失效类，task-14 素材（每家族极性 spot-check 对源批次语义）。与 τ_flag bug 叠加 = v1 两层已量化缺陷（实现层 + 标签层）**。
- 03:10 Lead 预裁两项（arch 裁定参考 + 披露口径）：①倾向挂 v2——热修数据救不了已训成的 T1 头（~4,000 翻转行已进 v1 权重），有效修需 v1.2 全链 ~2h 只换一轴；T1 本就最弱轴 + v2 反正重训；三版本复杂度高。**但预授权例外：若 arch 判 T1 基线对 v2 归因不可或缺，热修可行不否决**。②披露口径（挂 v2 案）：v1-1 + T1 隔离披露注（verdict 5 有效轴 T2-T6；T1 隔离区数字照登 + 污染量化 + "失真非模型失败证据"；v2 修复后恢复）；v0 不 kill 同意。〔后 arch 裁热修——②口径 moot，见 ~03:18 条〕
- ~03:15 sysdesign-m6 schema 更新落地（**v0.3.13，commit 447aab5**，02:57 加急 18min 兑现）：thresholds_applied.T* 增 flag_logit/strong_logit（可选 ["number","null"]，NON-BREAKING additive，字段缺省=旧行为）；m6-thresholds 同轮收编 deveng ckpt calib 形态（owner/runpoint_id/curves，calib.json 实测零违规）；m6_check_response 加固（logit 带序 + σ 回显一致性断言）。**实证：deveng v1-1 输出 10/10 零 issues（原 50 拒收项清零）+ 向后兼容（旧 stub 输出仍绿）**。
- ~03:18 **arch 终裁：热修**（~03:00 下达，与 pm 转达消息交叉；行使 Lead 预授权例外——T1 基线对 v2 归因不可或缺），dataeng 执行中，附四条件（同类捷径全清扫 / 断言覆盖延伸 cvalues 路径 / 规模门自查 / 复验）。**三处精确化**：①pm"切分不变"论断正确（切分内容 sig 锁定，标签变更不动内容 → split 稳定 → **泄漏证书与三方链内容级延续有效**——arch 修正自己此前"三链全重来"的过度保守）；delta 复验 = id→split 映射稳定性断言（逐行比对）+ 重标行极性抽样对照 chosen + 规模门重数 + 泄漏证书沿用（内容基）。②**VERDICT 同时定极性与任务归属**——jailbreak 形 cvalues 行从 t1 视图移入 t2 视图 → 任务文件行集变；delta 复验加逐任务行集 diff 报 arch；deveng id 顺序断言硬失败兜底（转全量重提取 22min，窗口仍足）。③**v0 T1 轴补跑**（~15min 单任务）选补跑不选披露排除——H10 交付物 T1 轴必须干净，v0 是 v1 归因对照锚点。时间线认可 ~06:30-07:30，H10 余量 ~3.5h+；§6.12 记录随后。**衍生口径更新：官方读数对象 v1-1 → v1-2（τ_flag 修 + 干净标签）；Lead 隔离披露口径（挂 v2 案）moot；v1-1 读数跳过（superseded）**。
- ~03:26 sysdesign-m6 排期注记（**证据链同步**，非阻塞）：热修动标签层且涉共享评测集侧 → data/m6 树 + manifest 指纹将变（89da085 → 热修版）——**热修 commit 落地时 sysdesign 跑一轮 m6_h6_audit（~3min，工具现役）**，为 v1-2 读数配对热修后数据态的行契约/manifest 对数证据（v3 证据只对 89da085；读数对象换数据态时证据链应同步）；若热修走"只改 gold 标注不动 manifest 指纹"路径则免（注：label_counts 双键 + t1→t2 视图迁移大概率动指纹——以 dataeng 落地实现为准）。**delta 复验链汇总（pm 跟踪）**：arch 五项（id→split 映射稳定性 / 极性抽样 / 规模门重数 / 泄漏证书沿用 / 逐任务行集 diff）+ sysdesign audit 重跑 + qa 证书内容级延续 = **v1-2 证据包**；v1-2 输出自动过 v0.3.13 检。触发约定：dataeng 热修 commit 落地 → pm ping sysdesign。
- ~03:30 qa 时隙确认 + **热修落地进展**：①**泄漏热修复检 PASS**（reports/m6/audit/leak-check-h6-hotfix1.json：L1 exact/NFKC 0-0、L2/L3/L5 全 0，eval 16,263 行热修后口径）——dataeng 热修 commit **35943e2** 落地且 qa 侧干净（远快于 ~1h 预估：~03:18 执行中 → ~03:22 前落地）；②v1-1 stage1 已弃（dev 预测跑旧行集，作废不读数——与 arch 终裁一致）；③**v0 补跑 03:22-~03:50**（dev 8,139 + heldout 14,263 两段 ~25min；challenge/ood/redteam 行集未变、旧预测继续有效；dev/heldout 新行集全量重推 = T1 轴 + T3 dev 变化）；④v1-2 读数等 deveng 重训知会；H10 报告排版确认（τ_flag 双披露 + T1 正常判定）。**timeline 提速**：v1-2 全链投影 ~03:50-~05:15（vs 原 06:30-07:30），H10 余量 ~6h。**delta 链状态**：qa 证书 ✓（热修态）/ sysdesign audit 触发条件已满足（35943e2）→ pm 已 ping / arch 五项复验执行中。
- ~03:38 sysdesign-m6 **audit 重跑 PASS（热修态）**：m6_h6_audit 对 **35943e2 四层全 PASS**（commit 4d7e119，h6-audit-hotfix1.txt）——L1 26 文件 invalid_total=0（全量滚）；L2 规模门 6/6（热修重分布最贴线位：heldout T1 neg=1,263 +2,500 共享补充，域内门 1,000 上 +26%；T6 train pos=2,050 不变；T1 train pos 8,513）；L3 eval_family 镜像子集零 mismatch（benign 3,500/challenge 1,100/ood 500）；L4 manifest 0 违规 + 23 条目对数全吻合（sha256/rows/label_counts 对热修后树）。**热修前后 delta（readout 记录用）**：t1 train 14,648→11,538、t1 heldout 2,500→1,563（污染共享评测行移除）、pool/train 47,142→44,087、t1 dev +47、t3 dev/train ±84——**净移除 ~10.5K 行**；train 唯一正例 T1 8,527→8,513（-14）。**delta 链双绿（qa 证书 + sysdesign audit）——剩 arch 五项复验**；v1-2 重训输出落地即验（v0.3.13 + logit 断言）。
- ~03:46 **热修链三道全绿，v1-2 放行**：①arch 复验绿——四条件全部关闭（捷径清扫/断言延伸/规模门/全量复验），独立实测：泄漏全零、规模门全过、不变量保持、**cvalues 终态精确一致（3,843+75+82 全 pos 零 neg）**、抽检查询全部无争议有害（§6.13 随后）；②qa 证书 ✓；③sysdesign 四层 ✓——**delta 链闭合，deveng v1-2 链放行**。**split 重排波及（arch 入档）**：T3 dev pos 526→610（watch ④ 缓解）；t6 conditional 871→822；**T1 train neg 6,088→3,025 腰斩 + heldout neg 2,200→1,263**（假 neg 清除代价——过门但 T1 FPR 读数 CI 变宽，task-10 归因注意）。排期：v1-2 重训（deveng 5min 链：refresh-labels → 重训 → logit 校准 → runpoint；split 全局重排可能触发预期内 22min 全量重提取分支）→ qa 评测 + v0 T1 轴补跑 → task-10（arch）。H10 余量 ~3h+。
- ~03:47 dataeng-m6 热修链状态 + 终态汇总（其"sysdesign 在途"系消息交叉过时——4d7e119 已绿）：watch 项入档（T1 train neg 3,025 过门但 FPR 分母变小 CI 变宽 / T3 dev pos 610 重排红利 / t6 cond 822 量级无碍）；**数据侧终态 = 35943e2（热修）+ 96b616e（inventory v2.1 补记，含 arch 四条件执行轨迹 + 失效类登记——task-14 素材）**；v1-2 deveng 5min 链即刻可开，读数窗口 pm 已排；下一动作点 = task-10 后 v2 增补。**热修全链（发现 ~03:02 → 放行 ~03:46）~45min——两轮数据失效类（泄漏 + 标注语义）处置范式成型**。〔时间标签系九次校正前口径，实际见下条：全链 ~10min〕
- **03:07:34 【时钟源声明·九次校正】** 新锚点（pm turn22 采样）。02:57-03:07 窗口标签大幅超前（~20-40min）：标签 ~03:15（schema 落地）→ 实际 **02:59:24**（447aab5）；标签 ~03:18（arch 终裁）→ 实际 **~03:00**；标签 ~03:20（热修落地）→ 实际 **03:00:50**（35943e2）；标签 ~03:38（sysdesign audit）→ 实际 **03:05:16**（4d7e119）；标签 ~03:46-47（三道全绿）→ 实际 **~03:05-03:07**。**热修全链实际仅 ~10min**（02:57 bug 报告 → 03:06:18 deveng v1-2 prep 落地 2e85aa6）——"~45min"系插值膨胀；qa 自报"v0 补跑 03:22 起"同为估计（实际 ~03:02 起）。**协议再确认：近实时事件窗内插值标签不可信，git commit 时间戳为唯一硬锚**。
- 03:20 qa **基线 v0 终态全量读数落盘**（qa-baseline-v0-full.md，机器戳 03:20:17；v0 补跑完成 03:17:22；热修后干净标签 + 全六切分 18,203 行 + dev 8,139）：**双向失守五门全挂**——G1 recall T5 81.3%/T1 13.0%/T6 9.0%；G2 FPR T3 15.3%/T5 17.4%（T2 0% 唯过）；G3 chFPR 全 FAIL 12-31%；G4 OOD 放过 70.4%；**运行点协议判别力上限：score-only 可行域选点后 recall 仅 0-2%**（operating-point-baseline-v0.json）——基线分离度不足以支撑任何可用运行点 = **v1-2/v2 对照锚点**。T1 FPR τ=0.5 参考切 1.2224% CI95 [0.90%, 1.63%]（arch 提醒项已附）。**【03:20:28 时钟源·第十锚点】qa 机器戳（03:17:22/03:20:17）与运行时采样一致——机器时间戳纪律全队生效。**
- 03:32 deveng **v1-2 时隙超时预警**：remap 实测 CPU 887s / GPU 5%——终态数据（96b616e，晚于 2e85aa6 的 id 命中测量）疑似重换行 id，remap 退化为近全量提取（arch 预批准 +22min 分支，静默发生）；ETA ~03:41，读数窗口压至 ~03:45 起（GPU 占用 5% 极低，qa CPU 活不受影响）。**教训（task-14）：remap 前先跑 id 命中测量——临时脚本应保留为 remap 的 dry-run 模式（deveng 收尾后补）**。**【03:32:18 时钟源·第十一锚点】**
- 03:57 deveng **v1-2 全量重提取分支确认 + fail-closed 逮到真内容漂移**：remap 的 2% 验证抽样发现 216/1053（20.5%）同 id 行文本在热修波中被改（NFKC/模板参数化）——缓存按 id 重用不安全，fail-closed 断言正确触发（**"测量而非断言"设计价值实证**：若信任 id 命中，v1-2 将吃到五分之一陈旧特征）。stage A 全量提取中（56,268 train + 12,618 dev）→ stage B（30s）→ 重训 → 校准 → 验证；**ETA 全链 ~04:15**，读数窗口顺延 ~30min。GPU 串行占用中。**【03:57:11 时钟源·第十二锚点】**
- ~04:18 arch **task-10 基线确立（v1-2 dev 读数）**：六任务零 FP——**T1 0.680/T2 0.812/T3 0.751/T4 0.885/T5 0.948/T6 0.976**（vs v1 dev：T1 +4.4pp/T3 +7.5pp/T5 +39.6pp/T6 +12.4pp；T2 -18.4pp/T4 -7.1pp = 污染效应清除后的正常化）。**归因关键修正（已发 deveng）**：T5/T6 大幅受益真因 = cvalues 行经 pool 全任务负例身份的直接污染（非 cond 投影）；T1 剩余缺口 = 真实构念难度 = LoRA 适应证。**v2 方向暂定**：LoRA 焦点 T1>T3>T2 + T5/T6 保护规则（逐 epoch 监控 + >1pp 回退即弃 + task_weights 杠杆）+ epoch 5-6ep/patience2；正式 §16 触发 + task-10 完整报告等 qa 套件评测（dev 读数方向性，判据口径在套件）；ADR-2 素材已齐（logit 域统一 + epoch 修正 + LoRA 触发记录）。arch 请排 qa 套件评测 + v0 T1 轴补跑。**pm 排期答复**：①套件评测时隙已分配 ~04:15-05:05（触发 = deveng v1-2 链完成知会，dev 读数在手表明链已完成）；②**v0 T1 轴疑已被覆盖**——qa pivot（03:02-03:17 新行集全量重推含 T1 轴）+ 报告 03:20:17 带 T1 FPR 1.2224% CI95 + operating-point 分析——已请 arch 确认口径（若需 runpoint 协议匹配对照，qa 单任务 ~15min 可补）。〔时间标签系十三次校正前口径，实际 ~04:03-05〕
- ~04:06 arch 排期答复三项：②**v0 T1 轴覆盖性裁定：现有覆盖已足，无需补跑**——task-10 T1 归因两锚点均已在新行集出数：(a) 实用运行点 τ=0.5（T1 FPR 1.2224% CI95 [0.90,1.63]，v0 距 <0.5% 门差 2.4 倍）+ (b) 匹配运行点 operating-point-baseline-v0.json（零 FP 域 recall 0-2%，基线方法在 M6 零 FP 体制内基本不可操作）；合成归因叙事决定性——**M6 探针架构零 FP 下 68%（T1）-98%（T6）vs v0 同体制 0-2%；T1 0.68 缺口 = 冻结特征天花板而非架构问题**（架构对 T5/T6 已证 95-98%）；runpoint 匹配补跑只会锐化"0-2% vs 68%"、无模糊可消，不值 15min GPU——省给 v2 准备。③**task-10 认领被板面正确阻塞**（blocker task-9 in_progress = arch 正式输入在途）——qa 关 task-9 之时即 arch 认领之时；dev 读数归因 = 合法预工作。④task-10 完整报告（§16 正式触发 + LoRA 焦点终版 + v2 改进清单三路分发）后 pm 锁 v2 GPU 时隙。**【04:07:14 时钟源·第十三锚点】上轮标签 ~04:18 实际 ~04:03-05（v1-2 链完成快于 04:15 ETA）；deveng 完成知会在途，~04:15 未到则催。**
- 04:21 arch **v2 前置就绪确认（三重验证）**：数据 **9b67ac7** 抽验精确一致（投影范围/单键回退/mirror 零污染）+ config **256ab33** 裁定值忠实落地（task_weights/epoch/守卫基线/LoRA 参数）+ 机制 **dfe84e2** 冒烟绿——**就绪状态从"dataeng/deveng 自报"升级为"arch 独立验证"**（pm 时隙预排依据）。剩最后一路：qa 套件读数（~05:05）→ arch §16 正式执行 + task-10 报告 → pm 排 GPU 时隙 → v2 开跑（60-80min 训练 + 10min calib）。**注：v2 训练预锁窗 H12-15 为 no-later-than 界——按当前节奏 task-10 报告后（~05:3x）即具备开跑条件，早启需 Lead 预授权（v1 四条件门先例）——task-10 报告时刻一并提请。**【04:21:05 时钟源·第十四锚点】
- ~04:25 **Lead v2 早启预授权（消除 05:3x 等待点）**：v2 允许在 **task-10 报告落盘 + GPU 空闲**两条件满足时立即开跑（早于 H12-15 预锁窗；no-later-than 语义不变）。依据：v2 前置三重验证已闭环（9b67ac7/256ab33/dfe84e2），早启仅剩报告与算力两个机械条件——照 v1 四条件门先例，机械条件全绿即开，无需再等 Lead。**附两条**：①§16 正式触发判据的执行结果（无论触发与否）必须进 task-10 报告——若判据未触发但 LoRA 仍启动，报告需注明"判据外主动迭代"依据（时间充裕 + T1 构念难度适应证），保持决策链诚实；②v2 训练期间 qa 的 v1-2 套件读数复核/敏感性抽验照走 **CPU/GPU 分离原则**，时隙冲突走 pm 登记表。执行方式：task-10 报告 + v2 开跑知会即可，无需请示。已转 deveng/arch/qa。
- ~04:31 arch 附则①接受：task-10 报告 §16 章节采用**固定结构**——判据逐条求值表（gen/jb/dilution/others/pooled 各自触发与否）→ 触发结论 → 若未触发但 LoRA 仍启动，显式标注"**判据外主动迭代**" + 依据（时间充裕 + T1 构念难度适应证 + **D2 缓存红利使迭代成本低**）；**决策链诚实性优先于叙事整洁**。两条件早启知悉。
- ~04:40 **task-10 报告落盘 + v2 GO（H10 达成，提前 ~6.4h）**：reports/m6/task10-v1-2-attribution.md（arch；qa run-v12-041243 + deveng 归因输入）。**§16 判据全触发**（gen 85.3<90 / dilution 82.3<85 / document 30.8<95 / toolout 84.8<95）——LoRA 判据内启动，无附则①标注需求。**归因分层**：T4 构念缺口 = challenge/OOD 门主犯（OOD 500 行 453 flag 中 T4 占 450；FP 100% span 驱动；**构念裁定：T4 = 语境条件检测——形式定实体性、语境定极性**；修法 = 良性含 PII 负例）；**形式零覆盖 = document/toolout 缺口主体**（T6×toolout 0/329、T3×document 1/52、T5×document 16/52、T1×topup-t9 0/18、T2×jb-holdout 20/40——LoRA 单独不可解）；T1-T3 特征天花板 = LoRA 适应证。**v2 关键裁定**：LoRA + 数据补充**一次迭代**（避免 v2.1）+ **v1-3 基线刷新序列必做**（数据波 → head-only 刷新 27s → 新基线设守卫——分离数据效应与 LoRA 效应）。**三路分发**：dataeng D-a~e（T4 良性 PII 负例 ~500-1k / T6 toolout ~300-500 / T3-T5 document ~200-400/任务 / T2-T1 变体 / 预置②③ 3,039/2,958/81 释放；乙醇红线：同形式族独立合成、heldout 只作形式参照）；deveng（LoRA r16 lr1e-4 L14-28 + task_weights T1:2.0/T3:1.7/T2:1.4 + 5ep patience2 + >1pp 守卫）；sysdesign（ADR-2 threshold_space + 投影契约 v0.3.14+81）。观察项终版七条（报告 §5）。**【04:38:59 时钟源·第十五锚点】**
- ~04:50 qa **task-9 闭环（板面 complete）+ v1-2 双运行点 H10 读数全落盘**：主读数 qa-report-v12.md + eval-v12.json（calib 推荐点）+ 交叉验证列 qa-report-v12-qaop.md（QA 独立点）+ sensitivity-v12.json + per-item ×2 + v0 对照。**verdict=FAIL（两运行点一致）——性质信息丰富**：T4/T5/T6 recall 达标（100/98.3/100@QA 点）；T4 FPR 7.3% 与运行点无关（spans 良性误报，实现层）；G4 OOD 强带误伤（two-band 机制边界）；T1/T3 分离度短板；B 族编码全穿。**v2 信号清单五条已发 deveng**（①T4 spans 语境条件化 ②T1/T3 分离度 ③强带 OOD 抑制 ④B 族对抗增强 ⑤calib dev 过拟合披露）。附则②确认：qa GPU 侧只剩 H20 验收全跑（+可能敏感性 GPU 段），冲突走 pm §9。**板面链**：task-9 ✅ → task-10 claim+complete（arch，解锁中）→ task-11 claim（deveng）→ v2 链。
- ~04:56 arch 状态交叉更正：**task-10 认领+闭环已在其上一轮完成**（board rev4 completed——与 pm 提醒消息交叉）；**ADR-2 已落盘**（qa 五项信号并入观察项 ⑨-⑬，与 arch 八项互补并引）；ADR-2 提请 Lead 冻结在途。task-11 板面 ready:true 解锁（pm 快照核实）——deveng claim 后 v2 链开跑。
- 00:12-00:25（10-22）**【恢复令·全队死亡后重启——5/5 唤醒成功】**Lead 窗口后恢复令（**【00:12:49 时钟源·第十六锚点】**）：~04:50 全队进程死亡（v2 链刚启动即中断）；Lead 已按窗口约束交割终报（final-20261022-0104.md，HEAD 0df8bab）；**窗口约束的是报告不是工作——v2 链连夜跑完**。
  **pm 连续性**：最后记忆 a1edd89（~04:57 task-10 闭环轮）；缺口 a1edd89→HEAD 仅含终报——**v2 链零产出**。
  **唤醒检查（00:15 五发，全部即回）**：dataeng 00:14（末记忆 04:45:39：D-c 完成 600 行 + D-d 生成器修三 bug；**staging 判定全部完整无半写**——D-a 800/D-b 1,400/D-c 600/预置②③ 1,800/mirror 1,250；死亡点在 D-d 生成前）→ 续跑 D-d + build_all ~30-40min；qa 00:14（末记忆 04:46:17：v12-qaop2 交叉验证 run 启动后）→ 盘点 + 读数待命；deveng 00:14（末记忆 ~04:44：task-11 已 claim rev3 仍有效；归因提取物已验提交 **8b437f5**；**发现 dataeng 复活**——topup-v2.jsonl 00:14:59 写入；**manifest 仍 23 文件未晋升**——死亡发生在波完成与晋升之间；链计划 v1-3 stage A ~11min + 27s + 校准 → v2 LoRA 90-120min → calib + 冒烟 = **~2.5h**，前置 = dataeng 晋升；**deveng "50min 窗口内 LoRA 不可行"误判已由 pm 勘正**——窗口不约束工作）；sysdesign ~00:16（末记忆 ~05:00：v0.3.17 落地 fddc562 后死；**勘正 schema 现役 = v0.3.17** 非 0.3.14+81——81 基线已被 arch 语境裁定取代，锚点 checked 3,039/t4 0/t5 0/revoked 0/context_released 0；检面三件待命）；arch（末记忆 ~04:50-05:00：Lead ADR-2 FREEZE 确认六决策零否决后；**ADR-2 处置完毕 commit b24d0f4**——盘上 56 行 vs 记忆零分歧，ADR-2/adr-1b/task-10 报告三交付物 untracked 死亡中断已一并提交 384 行；抽验口径不变；**13 项观察清单确认**（arch ①-⑧ + qa ⑨-⑬）。
  **arch 待审一项（不阻塞链）**：deveng 死亡前 7082d30（OOD suppression_mode=strong-too 可选模式）触碰 ADR-1 §8 语义（强带不可抑制）——已核实默认 two-band 不变 + v1-2 回归 sha 逐字节同 + 34 测试绿 = 能力增量非行为变更；**v2 runpoint 是否启用 strong-too 待架构裁定**（预判：D-15 T4 语境学习是 OOD 门主修路径，数据修复后 two-band 默认大概率够用；等 v2 读数 ⑪ 项实证后裁，不链前预设）。
  **链恢复排期**：D-d + build + 晋升（→~00:50）→ v1-3（~01:05）→ v2 LoRA（→~02:35-03:05）→ calib + 冒烟（~03:25）→ 读数（~04:15）——overnight 达成。**纪律照旧：三方复验门 / GPU §9 登记 / git 时间戳锚。**
- ~00:30 qa **ADR-2 观察清单读数映射确认**（pm 汇编用）：⑨ T4 spans 语境条件化→G2/G3 T4 双门（per-row spans 明细，benign PII span fire 可数）｜⑩ T1-T3 分离度→G1 表+CI｜⑪ 强带 OOD 抑制→G4 + **suppression_mode A/B**（two-band vs strong-too 双 runpoint——arch 待审 7082d30 的实证面）｜⑫ B 族→G5 红队族表（v1-2 基线 0/8、0/7、0/4 对照）｜⑬ calib 过拟合→双运行点对照列（完整 dev 13,239 行 QA 点 vs calib，dev→heldout 迁移衰减）。arch 侧涉 qa：⑤ 饱和区计数（calibration 旁车自动出）⑥ T1 FPR CI ⑦ op 位移（v1-3 select-op 对比）⑧ 两段效应分解（v1-3/v2 各自完整读数，harness --tag 区分）。**流程全就绪**：v1-3 出→先读效应分解基线段；v2 出→主读数。
- ~00:32 sysdesign **恢复后契约面就绪**：①缺口期产物托管校验完成（v1/v1-1/v1-2 calib 对现役 schema 零违规；缺口期仓库演进认知重建）；②**ADR-2 D-16 threshold_space 落地（v0.3.18，commit d44c59f——恢复令后首件）**：m6-thresholds +threshold_space（logit|score）+ if/then 强制（声明 logit ⟹ T1-T5 必带 *_logit 键，T6 softmax 豁免；消费者硬失败优于静默换轨）；三态咬合测试过；v1-2 calib 已带 logit 键、v2 声明即过；ood.suppression 拓宽 {two-band, strong-too}（7082d30 对齐）；SYS-1 §12 D-n 编号空间注记；③v2 链消费面就绪：数据波→m6_h6_audit 四层（union 白名单/projection_gate 键/scope 硬边界/泄漏锁内容级复验 per Lead 注记）+ SYS-1 偏差登记；v1-3→check_response 过检；v2 LoRA+calib→check_response + threshold_space 消费验证。schema 链 0.3.0→0.3.18 全登记。〔其"等 deveng 认领 task-11"微滞后——deveng rev3 认领有效，链 gate = dataeng 晋升〕
- ~00:53 dataeng **v2 数据波交付完成（970764a）** + deveng **v1-3 链开跑**：波 D-a~e 全量落地（恢复后续跑 ~35min，ETA 兑现）；自审三绿（GATES/isolation/schema）+ 泄漏 exact 0；manifest 98,287→108,075（+9,788，8 新家族，challenge-mirror +150）。deveng loader 验证：train 61,162（+4,894）/ dev 12,768（+150 mirror）/ 投影优先级 3,102 精确生效 / 零内容分歧——**v1-3 stage A + 训练 + 校准 ~11min 开跑**（提前于投影 01:05；GPU 仅 WDDM 桌面进程）。**排序注记（pm）**：dataeng 口径"arch 抽验 + sysdesign 四层两道绿后可排"，deveng 以晋升 + 自审绿 + loader 零分歧先行 v1-3（11min 便宜可重跑，接受）；**v2 LoRA（90-120min 贵步骤）硬门 = 双绿 + v1-3 读数守卫注入**——已钉 deveng + 追两绿。数据侧下一动作：等 v1-3 读数反馈（某族仍 miss → 构念解释迭代，不翻套件）。〔manifest +9,788 vs loader +4,894 ≈ 半——疑双键/投影族 per-file 重复计数，请 arch 抽验时顺手裁〕
- ~00:58 qa **GPU 时隙申请（v12-qaop2 补跑 13min）裁定：拒，排入 v2 读数段**。三理由：①**态势已变**（qa 前提滞后：波已晋升 970764a、deveng v1-3 已在 GPU ~00:53 起——非空闲窗）；②**02:16 前例正是"条件时隙 + kill 让路"模式**（v0 全量与 v1 相撞根因）；LoRA 硬门双绿时点不可预测，绿落即 kill = 废跑；③**⑬ 列（v1-2 heldout 交叉列）无 LoRA 前消费者**——读数段一起跑关键路径零成本。已预排：v2 读数段 = 主读数 + qaop2 补跑 + ⑨-⑬ 全流程。
- ~01:00 arch **抽验门：绿（LoRA 硬门 1/2 关闭）**：四项全过——①8 新家族 × 9 heldout 套件内容级 0 重合 ②规模门六任务精确一致 ③投影 3,102 中 high-risk=0（收紧纪律跨波存活）④伪造族 700/700 双键 + T4 良性负例 800+150 落位；Lead 内容级注记满足。**数字口径裁定：非重复计数 bug，是 §6.11 孪生结构重现**——9,788/4,894 = 2.0002 ≈ 精确 2.0（每新行 train 侧任务视图一次 + pool 孪生一次，loader 按 id 去重消费一份；§6.11 当时比率 1.72，本波新行全量孪生化故 2.0）。**建议入案（非阻塞）**：manifest 增双数键 file_rows + unique_ids（dataeng/sysdesign 5min）——口径教训契约化。v1-3 先行认可（便宜可重跑口径正确）。
- 00:23-00:26 sysdesign **四层审计全 PASS（2068a1b，证据 h6-audit-v2wave.txt）——LoRA 硬门 2/2 关闭**：①行契约 26 文件 invalid=0（全量滚）②规模门 6/6（train T2 pos 2,970 / T6 pos 4,050——forged-auth 双键 + toolout 轨迹 + jb-variant 全入账）③eval_family 全覆盖（challenge-mirror 1,100→1,250，lawful-pii 150 一致）④manifest 0 违规 + 23 条目对数吻合。**过程披露：首跑 28 fails → 全绿**（kind=document 1,800 行 / role=tool 2,769 行 / projection_gate.note 键三类全 = **schema 滞后非数据违规**，v0.3.19 吸收 ADR-2 D-18 后重跑全绿）。**交叉互证**（Lead 泄漏锁内容级口径 = dataeng 五断言 + L4 对数覆盖）：结构计数 **3,102 投影 ids（0 diverged）= projection_gate.checked 精确一致**；scope {conditional:1603, safe:1499} 硬边界（high-risk 零出现）；union 白名单四维零违规；ADR-2 D-17 契约栈全链落地。SYS-1 D-14 登记。
- 00:26 dataeng **双数键落地（89f5a55，即时兑现）+ v2 数据窗口终态**：manifest 每文件 entry 增 file_rows + unique_ids（§6.11 孪生口径教训契约化）；终态 commits = 970764a（D-a~e 波）+ f18fef9（inventory v3）+ 89f5a55（双数键）+ 前置 a6a8fc9/f247fcc/01e4c07；train_rows 108,075 / 8 新家族 / 投影 3,102（三道独立对账一致）/ 乙醇红线 0 重合实证。**数据侧三道链全绿闭环**（arch 抽验 ✓ + sysdesign 四层 ✓ + dataeng 自审 ✓）。数据侧待命（等 v1-3 读数反馈）。
- **【时钟校正·第三次（~30-40min 膨胀）】**上两条及更早 ~00:30-01:02 段标签膨胀；git 锚实测：arch ADR-2 **b24d0f4=00:15:36** / sysdesign v0.3.18 **d44c59f=00:17:39** / dataeng 波 **970764a=00:18:12** / pm 68ce17f=00:21:08 / sysdesign 四层绿 **2068a1b=00:23:05** / **turn35 锚=00:23:17**。deveng v1-3 开跑实际 **~00:21**（其"00:53"标签同膨胀）→ **v1-3 ETA ~00:32**；LoRA 投影 ~00:35-40 起 → ~02:05-02:40 完 → calib + 冒烟 → 读数（含 qaop2 补跑 + ⑨-⑬）→ **全链 ~03:10-04:00 完**（原"~04:15"基于膨胀标签）。

## 9. GPU 占用登记（单卡 24GB 严格串行）

**预锁窗口（Lead 01:13 批准）**：v1 训练 H7-H9｜v2 数据增补 H10-H12｜v2 训练 H12-H15｜验收全量 H20-H21。计划外占用先向 pm 登记，冲突升级 Lead。**【~02:00 Lead 预裁】v1 训练允许提前于 H7-H9 开跑**：四条件全绿即可放行，pm 直接执行；开跑时窗口标注"实际提前，理由=四条件全绿"。**【~02:28 协议升级（qa 建议、pm 采纳）】GPU 时隙预约制**：关键 GPU 步骤由 pm 在本表显式分配时隙，执行方按登记时隙启动（**查空闲 ≠ 获得时隙**）；H7 后关键步骤（v1/v2 验收读数、acceptance 全量等）一律走分配制。**【~04:25 Lead 预授权】v2 训练允许早于 H12-15 预锁窗开跑**：两机械条件（task-10 报告落盘 + GPU 空闲）全绿即开（v1 四条件门先例）；no-later-than 语义不变；开跑时窗口标注"实际提前，理由=两条件全绿"；附则——§16 判据执行结果必须进 task-10 报告（未触发但启动需注"判据外主动迭代"依据）+ qa 复核走 CPU/GPU 分离。

| 时间 | 占用方 | 步骤 | 时长 | 纪律 |
|------|--------|------|------|------|
| 01:07–02:10 | deveng-m6 | 特征探针 ×2（各 ~6s）、训练 smoke ×2（12s/17s）、推理 smoke ×3（各 ~1s） | 累计 <1min | 每次前查 nvidia-smi；无遗留进程；已全部结束，当前空闲 |
| ~01:40（task-7 轮） | deveng-m6 | smoke 训练 ×4（9-17s/次，fp16 缓存后 2-7s）+ 推理 smoke ×8（~1-6s/次） | 累计 <2.5min | 全部已结束；当前空闲；下一窗口 task-8 v1 训练 H7-H9 预锁不变 |
| ~01:50 | qa-m6 | 冻结套件 1770 行基线 v0 | 755s | 已完成结束，无遗留 |
| 02:00–~02:13（已终止） | qa-m6 | 基线 v0 全量首跑 | ~13min | **已 kill**（qa 裁决 A 变体，~02:13）：dev 读到中间态（13,108 vs 新 12,313）+ L1 修复未完（470 残留），避免废跑 |
| 02:16–~02:20（已让路终止） | qa-m6 | v0 全量重跑首启 | ~4min | **与 deveng v1 相撞（双进程 21GB/84%），qa 主动 kill 让路**——排程失误：启动前只查 nvidia-smi 空闲、未与 deveng 对时序（无预先协调） |
| 02:43–03:17（**已完成**） | qa-m6 | v0 终态对照全量：热修后干净标签 + 全六切分（heldout 14,263/challenge 1,500/ood 500/红队 170/冻结 1,770）；challenge/ood/redteam 旧预测沿用（行集未变），dev 8,139/heldout 新行集重推 | ~34min | **完成 03:17:22（机器戳）**；报告 qa-baseline-v0-full.md（03:20:17）：五门全挂 = v1-2 对照锚点 |
| ~03:22–~04:15（已完成） | deveng-m6 | **v1-2 链**：remap 2% 抽样逮到真内容漂移（216/1053 同 id 行文本被改，NFKC/参数化——id 重用不安全，fail-closed 正确触发）→ **stage A 全量重提取**（56,268 train + 12,618 dev）→ stage B（30s）→ 重训 → 校准 → 验证 | ~50min | arch 预批准 +22min 分支；"测量而非断言"实证（否则 1/5 陈旧特征入模）；实际 ~04:03-05 完成（快于 04:15 ETA） |
| ~04:12–~04:50（已完成） | qa-m6 | **v1-2 套件读数**（H10 正式数字）：run-v12-041243（04:12:43）→ 双运行点报告 + sensitivity + per-item ×2 | ~40min | **verdict=FAIL 两点一致**（首迭代预期姿态）；读数全落盘；task-9 板面 complete ~04:50 |
| ~04:50（**中断——全队死亡**） | — | 原 v2 链计划（数据波 → v1-3 → LoRA → 读数）死亡时未产出 | — | 死亡窗口 ~04:50；恢复令 00:12 后重排（见下行） |
| ~00:53 起（执行中·恢复模式） | deveng（主） | **v2 GPU 链（恢复令）**：v1-3 head-only 刷新（stage A + 27s + 校准 ~11min，~00:53 开跑——提前于投影 01:05；loader 验证：train 61,162 +4,894 / dev 12,768 +150 mirror / 投影 3,102 生效 / 零内容分歧）→ 【**硬门**：arch 抽验 + sysdesign 四层双绿 + v1-3 读数守卫注入】→ v2 LoRA r16（90-120min）→ calib + 冒烟 → qa 读数 | ~2.5h 链 | dataeng 波已晋升 **970764a**（manifest 98,287→108,075 +9,788 / 8 新家族 / challenge-mirror +150 / 自审三绿 + 泄漏 exact 0）；投影 ~03:30-04:15 全链完 |
| 02:18–02:41（已完成） | deveng-m6 | **v1 训练全量**：m6_train --config m6-v1.yaml | 23min 实跑（预算 35-50min） | 完成：ep2 macroR@zeroFP=0.7988；撞卡期 OOM 警告恢复后正常；产物 9de9718（82MB force-add）+ feat_cache 3.4GB 本地可再生 |
