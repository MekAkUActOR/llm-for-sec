# M6 ADR-2：v2 迭代架构决策记录

> 状态：**FROZEN**（arch 落盘 ~04:45；**Lead 逐条审毕批准 ~04:50，无否决项**）。前置：ADR-1（frozen）+ adr-1b §6.1-6.14。
> 触发：task-10 归因（reports/m6/task10-v1-2-attribution.md）——§16 判据全触发（gen 85.3<90 / dilution 82.3<85 / document 30.8<95 / toolout 84.8<95）。
> 效力：与 ADR-1 同源（架构权威记录）；修订走 append-only（m6-adr-2b 惯例）。
> Lead 执行注记：D-18 形式族合成在 v2 波审计时，泄漏三锁以**内容级口径**复验（form 相似 + 内容独立是设计意图，审计证明后者）——task-15 条款覆盖。

## D-13 LoRA v2 启动（判据内执行）

- **决策**：v2 = LoRA（r16, lr 1e-4, L14-28 q/k/v/o）联合头训练，一次迭代同步数据补充（两类缺口同波：特征天花板 + 数据零覆盖）。
- **焦点分配**：T1>T3>T2（dev 缺口 27/20/14pp），task_weights {T1:2.0, T3:1.7, T2:1.4, T4-T6:1.0}——T5/T6 不降权（保护 = 守卫 + 监控，非降权）。
- **epoch**：5ep + patience 2（ep3 仍上行的 macroR 三连升实证；ADR-1 §11 的 ≤3ep 是冻结缓存头训练口径，联合训练不受此限）。
- **回归守卫**：逐 epoch 逐任务 dev 比对，任一任务回退 >1pp 拒 best 资格；全拒时 WARN + last（产物连续性），v2-vs-v1-2 交付判定独立于守卫（task-11/12）。
- **拒绝的备选**：屏蔽 T5/T6（丢联合正则 + 放大漂移风险——它们的梯度锚定 trunk 运行体制）。

## D-14 v1-3 基线刷新序列（效应分离设计）

- **决策**：数据波落 → head-only 刷新跑（v1-3）→ v1-3 读数 = v2 守卫基线 → v2 LoRA。
- **依据**：守卫沿用 v1-2 基线会把 T4 新负例的合法 operating point 位移误判为回退。**v1-3−v1-2 = 数据效应；v2−v1-3 = LoRA 效应**——两段归因独立可测，进 v2 读数报告。
- **成本**：27s 级（D2 缓存红利延续）。

## D-15 T4 构念：语境条件检测

- **决策**：**形式定实体性，语境定极性**。人形 local（人名形）= PII 实体；服务/角色形（noreply/analyst）= 非实体。攻击/泄露语境的 PII → pos；合法语境（构造性验证授权/研究/合规处理）的 PII → neg。
- **依据**：v1-2 读数——T4 占 OOD 误杀 450/453 + challenge FP 主体，根因是训练负例无 PII 密集良性，双头（doc+span）都学了存在性。challenge/benign-heldout 文档天然含合法 PII，"存在性"构念原理上不可分。
- **数据配方**：良性含 PII 负例（合法语境 PII 文档）~500-1,000 进训练 + dev 校准（challenge-mirror 扩充）。RFC 5737 81 行案例 = 首次适用（role 形 + 授权语境 → neg 释放）。
- **拒绝的备选**：实体类型恒 flag 政策（credential/gov_id 恒 pos）——challenge 医疗文档含 medical_id，恒 flag 直接炸 challenge 门。实体类型仅作 span 特征丰富度。
- **OOD 判定**：Mahalanobis 机制无恙（弃权未触发因 flag 先行）；T4 语境学习同修 OOD 门与 challenge 门。span 通道 OOD 旁路维持（ADR-1 架构确认不变）。

## D-16 logit 域统一（score 表示层三案终裁）

- **决策**：校准/决策/敏感性曲线/OOD 距离**全链 logit 域**；score 概率值降级为显示层（fp64 计算或分带显示 ">0.9999"）；calib 契约加 threshold_space 字段 + 消费者强制 *_logit 键（存在时必须 logit 比较，硬失败优于静默换轨——D-7 家族纪律）。
- **同族三案**（表示层分辨率丢失的三次发作）：§6.1 温度撤销（σ(logit/T) 饱和）→ v1-1 τ 帽（概率空间 0.999 被 score=1.0 穿透）→ fp32 饱和（logit>16.6 → 1.0f32；v1-2 实测 391 显示层事件，T2 303）。
- **拒绝的备选**：仅扩 qa 网格 0.999 档（已预注册但属补丁——logit 域统一是根治）。

## D-17 跨键投影契约栈（§6.14 全量收编）

- **投影纪律**：跨键投影仅在目标任务语义由构念**决定**时有效；极性"貌似合理但未定"必须保持单键（high-risk 行禁止投影——cvalues 失败模式预防）。
- **构念类型区分**：verdict-conditional 构念（T1/T2/T3——构念即权威）vs 客观模式构念（T4/T5——内容核查必须：span 提取器/注入标记零命中 + 语境裁定规则）。
- **文件层**：pool 六键 union 载体 / 任务视图单键金视图（视图形态一致性 = τ 保护延伸）；loader union 语义；审计白名单四维（含 pool 超集维）+ projection_gate manifest 契约键 + scope 可审计。
- **伪造授权族双侧训练原则**：投影使 T1-T5 学"授权形→pass"后，伪造授权检测负担集中于 T6 判别 + T2——对抗面（forged-auth-v1 800 行，5 类构造性伪造线索，双键 T6-high-risk + T2-pos）必须同波配套，否则单点失效。

## D-18 形式覆盖配比（v0.7 教训的形式侧闭环）

- **决策**：v2 数据波补形式 top-up——T6 toolout 轨迹（0/329 全漏）、T3/T5 document 长文档、T2 jb-holdout 变体、T1 topup-t9——**训练侧显式配比评测侧形式族**。
- **依据**：document 30.8%/toolout 84.8% 的缺口主体是形式零覆盖（无训练数据则无梯度，LoRA 不可解）；v0.7 形态泛化（with-assistant 61% vs user-only）同族复发。
- **乙醇红线**：同形式族独立合成；heldout 套件只作形式参照，内容绝不复制/改写（task-15 审计条款）。

## 观察项（v2 读数核对清单）

① T1 跳升幅度（特征天花板验证）② T6/T2 pos 贴线（T2 已缓解至 ~2,926）③ T3 full-pos ④ v0.7 形态复测 ⑤ 饱和区良性计数（16.6+）⑥ T1 FPR 分母 CI ⑦ T4 新负例后 operating point 位移（v1-3 基线上观察）⑧ v1-3−v1-2 与 v2−v1-3 两段效应分解。

qa 五项信号（v2 读数验证，互补并引）：⑨ T4 spans 语境条件化（良性 PII 文档 span 不再 fire）⑩ T1-T3 分离度 ⑪ 强带 OOD 抑制行为 ⑫ B 族对抗 ⑬ calib 过拟合披露。

---
*arch-m6 · 输入链：qa run-v12-041243 / deveng 归因 / dataeng 审查 / arch 裁定链 adr-1b §6.12-6.14 / task-10 报告*
