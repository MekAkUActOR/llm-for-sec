# M6 最终报告——v2 链交付（Lead 终裁：选项 A）

> **交付物**：`checkpoints/m6-v2-4dt` @ **19eaaba**（dual-trunk 复合 + span 长度门），operating point = **QA 点**
> **终裁**：Lead 2026-10-22 21:17 选项 A 接受（依据 + 裁量权五项追认见 §11）
> **主笔**：pm-m6 汇编；arch / qa / deveng / dataeng / sysdesign 素材回填
> **证据骨架**：`reports/m6/task13-final-adjudication.md`（5685fa4，十节终裁材料——本报告以其为主表引用）

---

## 0. 摘要

M6 使命 = 在 `qwen3-06b-sec-m5a-dpo-r5`（0.6B / 28 层 / hidden 1024）上实现六任务统一检测（①内容审核 ②越狱/直接注入 ③恶意意图含多轮诱导与长上下文注入 ④PII ⑤间接注入 ⑥高危指令注入），**单次推理输出全部六任务结果**。原始 24h 窗口以诚实 FAIL 记录关闭（final-20261022-0104.md）；恢复链连夜执行，经 **v0→v1-2→v1-3→v2→v2.4→v2.4-dt 六代迭代**（macro 0.681→0.935，全零 FP），Lead 终裁接受 **v2.4-dt @ 19eaaba（QA 点）** 为窗口交付。四验收线诚实计分：**G1/G5 过线，G2 五头过线（T4 差 4.9x），G3 全差（3.3-21x），G4 差 2.7x**——全部差距面已归因到机制并给出 post-window 修复路径。

---

## 1. 使命达成度声明（诚实计分）

| 验收线 | 结果 | 计分 |
|---|---|---|
| **G1** recall >95%（六任务） | **六头全过**：T1 100 / T2 99.7 / T3 97.3 / T4 100 / T5 100 / T6 100（CI95 下界>95，QA 点） | ✅ **过线** |
| **G2** FPR <0.5% | T1/T2/T3/T5/T6 = 0.000-0.021%（三代零 FP）；**T4 = 2.333%（4.9x）** | ⚠️ 五头过线，T4 差 4.9x |
| **G3** 挑战 FPR <0.1% | T1 1.13%（11.3x）/ T4 0.78%（7.8x）/ T2/T3/T5/T6 0.67-2.13%（6.7-21x）；样本级 1.04%（calib 链六代 41.3→1.04） | ❌ 全差（特征化） |
| **G4** OOD 放过 ≥95% | 35.4%（2.7x 差额） | ❌ 差 2.7x（双向量归因） |
| **G5** 红队 ≥90% | **92.4%（157/170，WEAK 旗清零）** | ✅ **过线** |
| 参照 | 挑战正例召回 100%（345/345，六代持续） | ✅ |

**结论**：单推理六结果架构目标达成；检测面（G1/G5/召回）过线；误报面（G2-T4/G3）与 OOD 面（G4）为已知差距，全部归因到机制（§6）并有修复路线（§7）。

## 2. v0 基线对照（架构决定性验证）

v0 = m5a-r5 原样模型套六任务口径。**探针架构（冻结主干 + 多头探针）交付了原样模型不具备的检测能力**（Lead 终裁确认：探针架构 68-98% vs 原样 0-2% 的决定性验证）——六代轨迹的起点即探针基线（T1 13 / T3 37 / 红队 34.7），随表示学习（v2 LoRA）与监督数据弧（v2.1 波）逐代抬升。**架构选型（D-13：主干冻结 + head-only 起步 → LoRA 表示学习 → 确定性后处理复合）被六代弧完整实证。**

## 3. 架构与迭代链（六代弧）

**macro 弧（dev 平面，全零 FP）**：v1-2 0.681 → v1-3 0.818 → v2 0.866 → v2.4 0.910 → **v2.4-dt 0.935**

**路径转折（本窗口最重要的架构结论）**：
1. **v2 LoRA**（e2a758c）：D-13 head-only 四案例 = 冻结特征能力极限 → LoRA 表示学习是共同解（longctx 26.7→100 / A3 0→8/8 / 红队 52.9→90.6 全验证）。ep2-best 定版（macroR 0.866；T1 -12.1pp = 监督负例缺失）。
2. **联合训练结构性关闭**：v2.1 三试 + v2.2 四增量 = 5 轨迹 4 次 ep2 良性饱和盆地复发（17.7k T1-neg 平衡 × 头 lr 的结构性不稳；bf16/cuDNN 非确定性 = 盆地彩票）。**arch 关闭联合路径**。
3. **确定性后处理转向**（F-1 头级投递保基质）：Branch A 阴性（表示级损伤实锤）→ Branch B 部分阳性（T1 线性探针 0.949）→ **v2.4 外科复合**（f7a580a：v2 probe + fresh T1/T3 on frozen v2 trunk-MLP，T1 0.899 / τ 8.5 / 零饱和）——T1 修复的活性成分是监督数据而非表示重塑。
4. **v2.4-dt**（19eaaba）：dual-trunk 组装（trunkA v2 服务 T1/T2/T3/T5/T6 + trunkB 服务 T4doc：T4 0.797→0.949；单一骨干前向保持）+ span 长度门（min_len=2，-51% T4 FP，decode 侧零扰动）+ 从属化 NO-GO（金标：9% TP 承重 + 2.3% 收益份额，双重否定）。
5. **T6 配对性**（F-3）：微观退化域仅 v2 精确 trunk+head 对可用——T6 对保持原样。

## 4. 数据配方

- **基础映射**：data/m4-run 28,842 风险对按六任务标签空间重映射 + 跨任务负例共享（良性池对所有头为负例）。
- **D 波**（v1-3）：near-miss 边界 + 数据效应 +13.7pp（macroR 0.818）。
- **t1-lawful 波**（v2.1/v2.2）：t1-lawful 700 + T1-neg 跨视图投影 7,947——T1 数据弧闭环（挑战 FP 23.0→0.33/1.13%）。
- **T4 staging**（v2.2）：labeled 13,702→15,002，lawful-pii mirror 双硬 T1/T4 平面。
- **终态**：train 64,070 / dev 12,768（manifest sha 482986 波）；chmirror 1,550（v2.4 起含 lawful-pii 300）。
- **冻结行集**（只读评测）：heldout 16,263（D 波后）/ challenge 1,500 / ood 500 / redteam 170。
- **乙醇纪律**：全程无违规（§10 审计链）。

## 5. 验收对照（主表）

**主表 = task13-final-adjudication.md §1**（门卡全表：3 通过族 + 4 差距面 + 六代轨迹，commit 5685fa4）。要点：G1 六头全过（QA 点）、G2 五头零 FP、G5 92.4%、挑战召回 345/345；差距面 T4-G2 4.9x / G3-T1 11.3x / G3-T4 7.8x / G3 其余 6.7-21x / G4 2.7x。双运行点读数存档（qa-report-v24dt{,-qaop}.md + eval×2）；⑬ 终答 = QA 点（calib 点 G1 多头破地板，门计数 6✓ vs 0-2✓）。

## 6. 已知局限（差距面归因，deveng §5 + arch §3）

1. **T4-G2/G3**：span 驱动残余 FP（门后 dev 1,005 行域；heldout benign span 份额 2.3%）——语境盲提取 × lawfully-benign 行；context 门 = post-window。
2. **G4 双向量**：is_ood 塌陷（4.6% vs v1-3 9.2%，LoRA 吸收 OOD 分离度——几何级）× span 强带旁路（310/500 OOD 行 ≈ 98% of fails）。v2→v2.4 遥测增益 = 平面重校准 100%（三层依赖 474168c 逐位证明）；几何赤字原封。
3. **T4 dev recall 0.949 骑 trunkB**（branch-B ep3-least-bad 选择）；验收面 G1 已验证（T4 100% heldout-held）。
4. **span 通道承重结构**：heldout 9% T4 正例 span-only 依赖（27/300）——defense-in-depth 实证 + 结构脆弱性并存。

## 7. post-window 路线图（四杠杆定序，qa ② + arch ⑦）

| # | 杠杆 | 根因域 | 预期收益 | 性价比 |
|---|---|---|---|---|
| 1 | **T4 context-gate**（doc 语境化 span 有效性，"待语境裁"中间态） | 实现层 | G2 2.33→~0.1-0.3%；G3 同步受益 | 高 |
| 2 | **G3 校准策略复核**（选点协议 v2 / 非零 FP 容忍构造） | 阈值域（零训练成本） | G3 各任务 → 容差内（T5 calib 0.07% 已示范） | 高 |
| 3 | **G4 三候选层**：(a) 特征重估 / (b) 学习式 OOD 判别头（mirror 代理监督——原则性首选）/ (c) flagged-OOD 联合语义 | 几何域 | 边界邻接覆盖（23x 分离恢复也只值 40.2%——需学习式边界） | 中 |
| 4 | **span 承重结构加固**（正例池配额纪律 + doc 头长文 PII 教学） | 数据/架构域 | 降低单点依赖（防御性） | 中 |

## 8. 工艺教训（十一条，可迁移）

1. **分解先于归因**——三次防错（T3 分母 / T4-FPR 定性翻转 / span 例证误导）；金标 join 是终审
2. **init 健康性是特征相对量**（F-2）——"健康头"换特征分布即饱和陷阱
3. **盆地彩票意识**（F-8）——非确定性下重训 = 新抽样；结构性不稳转确定性路径
4. **运行结束即刻提交**（run2 最优组合丢失教训）
5. **平面版本纪律**——跨代比较必注校准平面；OOD 几何量三层依赖（F-4）
6. **时敏审批直达申请人**（pm/qa 20min 窗口损失）
7. **测量域与判定域一致性系统化检查**（D-16 家族四次发作——fp32 sigmoid 饱和伪 0.0；守卫/校准一律 logit/log-P 域，F-7）
8. **fallback 语义须考虑非单调轨迹**（D-13 last-fallback 单调崩塌保最差 epoch → least-bad 字典序 24b759b）
9. **对活跃编辑中的代码库跑诊断 = 撞中途态**
10. **投影外推须全阶段核验放大因子**（8.6x 只外推到提取未核 fwd+bwd；4.4x 提速仅评测路径）
11. **工程产物不入 git 主链**（Lead 收口实证）——feat_cache/训练快照类可再生二进制应走 .gitignore + HF/制品库；本窗收口被 GitHub 单文件 100MB / 单推 ~2GB 硬限卡住 ~3h（116 commit 含 14.4GB 特征缓存，三次整推失败 → filter-branch 裁剪 `main-delivery` 分支[109 条哈希映射存 `reports/m6/remote-delivery-curation.md`，本地 main 完整历史不动]）

## 9. 团队与过程记录

**编制**：扁平敏捷团队（lead / arch / sysdesign / dataeng / deveng / qa / pm），任务板 15 项流转（task-1..14 全闭环中 + task-15 随本报告收口）。

**关键过程纪律**：
- **GPU 单卡 24GB 严格串行**：§9 登记制（先登记后作业；仲裁权 pm；一次 kill 先例[未登记+被取代+阻塞三要件]）；全窗口零物理撞卡
- **乙醇纪律**：冻结套件 vs 训练 = 0 泄漏（五次证书）；阈值标定全程 dev/chirror 域
- **时钟纪律**：40 个锚点采样；五次膨胀校正（git/机器戳为准）
- **停报纪律**：两次正确触发（不同失败模式 = 新信息）

**中断与恢复**：原始窗口末全员进程死亡（~04:50）→ Lead 恢复令（"窗口约束的是报告不是工作"）→ v2 链连夜执行；Lead 侧两次 api 中断恢复（其终裁通报载明）；会话压缩多次无信息损失。

**冲突消解记录**：qa 未登记占用 kill 仲裁（01:27-01:30，全程留档）；诊断槽与发射时序协调（16:45-17:0x，编辑中途态放弃）；催办与批准交叠（19:2x，流程教训 #6）。

## 10. 交接清单

| 类别 | 资产 |
|---|---|
| **checkpoint** | `checkpoints/m6-v2-4dt`（交付，19eaaba，determinism 97f2860a / 契约 0 / 35 测试绿）；`m6-v2`（lineage，e2a758c）；`m6-v2-4`（f7a580a） |
| **数据** | `data/m6/`（train 64,070 / dev 12,768，manifest 可一键重建）；challenge 1,500 / ood 500（自建评测资产）；`data/heldout/` 冻结套件（只读，从未入训练） |
| **生成器/工具** | `scripts/m6_train.py`、`m6_infer.py`、`m6_acceptance.py`、`m6_emit_dev.py`、`m6_t3_family.py`、`m6_leak_check.py` + 诊断工具集（_tmp_v24{,dt}.py / _tmp_t4decomp.py / _tmp_subord_final.py / _tmp_t1sat.py 等——复现记录完整性） |
| **配置** | `configs/m6-v2-4dt.yaml`（span_gate.min_len: 2，config 暴露可调可逆） |
| **审计链** | 五次泄漏证书（h1→h6×2→D 波→v2.4 波，全 PASS）+ 乙醇声明 FINAL（`reports/m6/audit/ethanol-statement.md`：全程无违规） |
| **评测/读数** | 六代读数链全档（qa-report-v12/v13/v2/v24/v24dt{,-qaop}-final.md）；per-item 预测快照 `reports/m6/preds/run-*/`（无重跑复算） |
| **报告索引** | task13-final-adjudication.md（终裁材料）→ 本报告；ADR-2/2b（架构决策链 b24d0f4…560758e）；deveng-findings-summary.md（8511b29）；qa-task13-materials.md；task13-arch-sections.md（6098276） |
| **复现** | 命令/种子/行集口径 = qa-task13-materials.md §③（训练 seed=42；选点网格枚举；推理 determinism 97f2860a） |
| **远端交付** | `main-delivery` 裁剪分支（1.58GB / 最大文件 90.3MB，116 commit 信息/作者/日期/交付内容原样，仅剔除 6 个可再生缓存路径；109 条哈希映射 `reports/m6/remote-delivery-curation.md`；本地 main 完整历史不动）+ qa 终读证据收编（4 preds 目录 + h6 协议文档，d4a3a59） |

**遗留问题** = §6 已知局限 + §7 路线图（post-window 执行域）。

## 11. 终裁记录与收尾

**Lead 终裁（21:17，选项 A）**：接受 v2.4-dt @ 19eaaba（QA 点）为 M6 窗口交付。依据：三通过族 + 全差距面特征化；选项 B 排除正确（无本窗杠杆 + 联合训练结构性关闭）；选项 C 排除正确（calib 点破地板）；六代 macro 弧 = 窗口方法论完整实证。**裁量权五项全部追认**：dual-trunk 组装（组装域）/ span 长度门（flag_rule 语义变更）/ 从属化 NO-GO（金标定谳）/ T1 权重变更（记录为未验证）/ 三跑框架（过程裁定）。

**各角色收尾 commit**：deveng 5d2f7fc（门态一致性 + 诊断工具入库）✓；qa 乙醇声明 FINAL + 终稿链 ✓；arch sections db0a34e（hash 同步）✓；pm 本报告 + 进度文档全档 ✓；dataeng 波次 manifest ✓。

**交付双备份**：①HF 公库 `howwhenRaw/m6-security-detector-v2-4dt`（9 文件：probe-heads.pt / ood_centers.json / calib / config / head_structure / metrics / build_manifest + 模型卡）✅ ②本地完整链 + `main-delivery` 远端推送（22:54 起在途，落地即窗口终闭）。

---

—— pm-m6 主笔，2026-10-22 21:3x 初稿 / 22:5x 增补（教训 #11 + 远端交付 + 双备份；第四十锚点系 22:54:02）。M6 窗口交付收口。
