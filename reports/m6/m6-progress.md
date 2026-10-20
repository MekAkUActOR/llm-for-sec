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
| H1 | 10-21 02:30 | 设计冻结：ADR-1（task-1）+ 数据映射 DATA-1（task-3） | ✅ ~01:18 达成 | 运行时钟提前 ~72min（自报 02:05；时钟源声明见 §8） |
| H1.5 | 10-21 03:30 | SYS-1 系统规格 + schema 契约（task-2）+ QA-1 验收规格冻结 | 🔶 3/5 | task-2 ✅ ~01:42（SYS-1 v1.0.0 + schema v0.3.0 + 自检 14/14）+ U3 收口；剩 QA-1 冻结确认 + arch 咬合审查 |
| H6 | 10-21 07:00 | 数据冻结：六任务五切分 + manifest + 泄漏审计（task-4/5/6） | ⏳ | v1 训练硬前置 |
| H10 | 10-21 11:00 | v1 模型 + 首轮评测读数（task-8/9） | ⏳ | 训练窗口 H7-H9（GPU 预锁） |
| H16 | 10-21 17:00 | v2 模型迭代（task-11） | ⏳ | 数据增补 H10-12 / 训练 H12-15（GPU 预锁） |
| H20 | 10-21 21:00 | 验收轮：acceptance harness 全量（task-12） | ⏳ | 验收窗口 H20-H21（GPU 预锁） |
| H23 | 10-22 00:00 | 报告/上传/交接收尾（task-13/14） | ⏳ | 窗口 01:04 关闭 |

### H1.5 冻结验收清单（pm 维护，02:30 闹钟轮仪器）

1. task-2 板上 complete（SYS-1 系统规格 + schema 契约冻结）
2. SCHEMAS.md + 七份 schema 定稿（U3 字段名正式收口，deveng 锁 infer 输出 schema）
3. QA-1 冻结版落盘（三大读数纪律 LOCKED 已确认；T4 两层措辞入冻结版）
4. task-7/task-9 双解锁 → deveng claim task-7（预研就绪，claim 后即冲 complete）；qa 正式 claim task-9
5. arch 咬合审查结论（SYS-1 与 ADR-1/1b 接口一致）记录在案

### H6 数据冻结验收清单（pm 维护，07:00 检查点仪器）

1. task-4 train/dev 落盘：六任务正例覆盖全部子类，规模达配比与功效要求（U5：heldout 正例 ≥200/任务、benign 负例 ≥1000）
2. m4 勘误已应用（adr-1b §3）：标签一律取 chosen VERDICT + 每 dpo_class 极性分布断言通过（防 bt330 1,904 / carrier_inject_obedient 2,360 正例误入负例侧）
3. T4 自建 span 级 heldout 落盘（data/m6/t4，adr-1b §4；冻结套件无 span 级 PII 正例，v0.2.3 privacy 仅参照）
4. 挑战集（≥1200，含"全任务负例"复制行）+ OOD 集（≥300）落盘，qa 会审通过
5. manifest 全量（文件/行数/来源/六任务标签分布/切分指纹）+ U4 dev 难负例标记落实
6. 泄漏审计零泄漏（sha256 精确交集空 + 5-gram 可疑对逐对解释），qa 复核签字
7. arch 六项 pool schema 要求落实（六维标签向量 / T6 三类 / 信封多样化 / reveal_turn / PII risk 映射 / T4 主门）

## 3. WBS 任务板镜像（权威状态看 team_task_list；依赖已由 Lead 硬化 11 条边，readiness 门禁生效）

| ID | 任务 | 负责人 | 依赖 | 截止 | 状态 |
|----|------|--------|------|------|------|
| task-1 | 架构 ADR：六任务统一检测设计 | arch-m6 | — | H1 02:30 | ✅ completed（板上 rev3；运行钟 ~01:22） |
| task-2 | 系统设计：推理协议/阈值/弃权 | sysdesign-m6 | — | H1.5 03:30 | ✅ completed（板上 rev3；SYS-1 v1.0.0 + schema v0.3.0，commits e95c012/bb18c37 待 Lead push） |
| task-3 | 数据映射：数据源映射与配比 | dataeng-m6 | — | H1 02:30 | in_progress（DATA-1 草案在盘 docs/m6/data-mapping.md） |
| task-4 | 数据构建：六任务 train/dev | dataeng-m6 | 3 | H6 07:00 | pending |
| task-5 | 数据构建：挑战集 + OOD 集 | dataeng-m6 | 3 | H6 07:00 | pending |
| task-6 | 数据治理：manifest + 泄漏审计 | dataeng-m6 | 4,5 | H6 07:00 | pending |
| task-7 | 工程：多任务训练+推理管线 | deveng-m6 | 1✓,2✓ | H1.5–H6 | ready（双解锁已确认；已催 deveng claim，预研就绪即冲 complete） |
| task-8 | 模型：v1 训练与 checkpoint | deveng-m6 | 4,6,7 | H10 11:00 | pending |
| task-9 | 评测：验收 harness + 基线读数 | qa-m6 | 1✓,2✓ | H9 10:00 | ready（双解锁已确认；已催 qa claim + QA-1 最终冻结确认） |
| task-10 | 分析：v1 归因 + v2 改进清单 | arch-m6 | 8,9 | ~H12 | pending |
| task-11 | 模型：v2 迭代训练与读数 | deveng-m6 | 10 | H16 17:00 | pending |
| task-12 | 验收：acceptance 全量轮 | qa-m6 | 11 | H20 21:00 | pending |
| task-13 | 终裁：验收结论材料汇编 | arch+qa（pm 汇编） | 12 | ~H22 | pending |
| task-14 | 交付：最终报告与交接 | pm（全员回填） | 13 | H23 00:00 | pending |
| task-15 | 合规：乙醇纪律贯穿审计 | qa-m6 | —（全程） | 随 T14 | in_progress |

## 4. 度量活表（按评测轮更新，qa-m6 供数）

### 4.0 基线 v0（m5a-r5 原样，六任务口径）——待 qa 落盘

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

（暂无）

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

### 未决裁决项（pm 跟踪，来源 QA-1 §9）

| # | 事项 | 提议 | 待决人 | 状态 |
|---|------|------|--------|------|
| U1 | OOD 放过率门数字（kickoff 仅定性"默认放过"） | qa：硬门 ≥95% + 目标 98% + 弃权率单独披露 | Lead | ✅ 01:16 终裁采纳 + 补充条款（OOD 放过率/攻击侧弃权率并列两列） |
| U2 | G3 挑战集主门口径：任务级 vs 样本级 | qa：任务级主门 + 样本级双报 | Lead | ✅ 01:16 终裁采纳 + 统计强化（点估计判定 + 精确二项 CI95 标红制） |
| U3 | m6_infer 输出字段名（六任务键、abstain） | — | sysdesign（SYS-1） | ✅ 正式收口（SYS-1 定稿；deveng 4 处更名：results→tasks / action→decision / ood.score 原始距离 / latency_ms 顶层） |
| U4 | dev 内难负例子集标记（chFPR 替代约束） | — | dataeng | 进行中 |
| U5 | data/m6 切分规模 vs 功效要求（heldout 正例≥200/任务、benign≥1000、challenge≥1200、ood≥300） | — | dataeng | 进行中 |

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

## 9. GPU 占用登记（单卡 24GB 严格串行）

**预锁窗口（Lead 01:13 批准）**：v1 训练 H7-H9｜v2 数据增补 H10-H12｜v2 训练 H12-H15｜验收全量 H20-H21。计划外占用先向 pm 登记，冲突升级 Lead。

| 时间 | 占用方 | 步骤 | 时长 | 纪律 |
|------|--------|------|------|------|
| 01:07–02:10 | deveng-m6 | 特征探针 ×2（各 ~6s）、训练 smoke ×2（12s/17s）、推理 smoke ×3（各 ~1s） | 累计 <1min | 每次前查 nvidia-smi；无遗留进程；已全部结束，当前空闲 |
