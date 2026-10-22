# M6 乙醇纪律贯穿审计声明（task-15 · qa-m6 · 草稿 v2）

> 状态：草稿（待 deveng 两项确认后定稿）；随 T14 最终交付。
> 范围：data/heldout 冻结套件与 data/m6 评测资产（challenge/ood/heldout）从未用于训练/调参/阈值标定。

## 1. 泄漏审计（L1-L5，三次证书）

| 证书 | 时点 | 数据版本 | 结论 |
|---|---|---|---|
| leak-check-h1.json | ~01:50 | 首版 | L1 FAIL（472 精确重合：t1-legacy×130 + t3×343）→ dataeng 整改单 |
| leak-check-h6-recheck.json | ~02:2x | content-only 锁修复 | L5 实体级 PASS（642→0）；L1 仍 470 → 二轮整改 |
| leak-check-h6-hotfix1.json | ~03:1x | 热修 35943e2 终态 | **overall PASS**（L1 exact/NFKC 0-0、L2 冻结 0、L3 红队 0、L5 实体 0/644） |
| leak-check-d-wave-post-fix.json | 10-22 03:3x | v2 D 波（形式族 top-up 后，train 59,583 行） | **overall PASS**（内容级口径：L1/L2/L3=0、L5 实体 0；L4a 披露层形式相似） |

- L1-L3/L5 为硬门（精确/NFKC sha256 + span 实体子串）；L4 5-gram containment 为披露层（模板结构性相似，B2 正文级 8-gram=0 佐证）。
- 两次"断言≠实测"事件（pool 视图 vs 任务视图；pack 锁 vs content 口径）均已根因闭环，评测方口径（content_overlap_qa_l1）已固化进 dataeng build_all 断言。

## 2. 训练配置复核（v1/v1-2/v2）

- configs/m6-v1-2.yaml：train_splits=[train]、val_split=dev、early_stop 基于 dev ✓
- train_log.jsonl（v1-2）：逐 epoch 指标全部 dev split（n_pos/n_neg 与 dev 行集对应）✓
- **已确认 A**：eval.suites 字段 = 惰性外部约定清单，训练侧从未执行（deveng grep 证据：m6_train.py 无 suites 读取；训练全程指标只用 dev）——config 注释将标 inert
- **已确认 B**：v1-2 校准 dev = 热修后快照（12,618 行 union 口径，deveng 04:23 复测一致；T4 pos=688 为 union 口径 [t4-pii dev + pool 多键行]，qa 单视图口径 250——同一数据两种视图计数，非版本漂移）。v2 校准读运行时 manifest 保证一致

### v2.4 数据波复核（10-22 19:5x）

- leak-check-v24-wave.json：**overall PASS**（train 16,144 [t1-lawful + T4 staging 波后] vs eval 16,263 exact=0/NFKC=0；frozen 2,806 零；redteam 170 零；L5 实体 0/3,900）——L4a 形式相似披露层照旧（模板结构性，B2 正文级 8-gram=0 佐证）。
- v2.4 读数链的输入行集：emit v24（dev 13,389 / chmirror 1,550 含 lawful-pii mirror 硬化池 300）；manifest sha 482986…（16:45）与读数一致 ✓。

### v2 段（LoRA 终审，10-22 04:2x）

- configs/m6-v2.yaml：**无任何 heldout/challenge/ood 引用**（v1-2 的惰性 eval.suites 块在 v2 config 中已不存在——惯性问题自然消除）；manifest 驱动 + prefix_rows exclude；守卫基线 = qa v1-3 dev 读数注入（baseline_readings，D-14 裁定）✓
- **守卫平面注明（D-14 分工）**：baseline_readings 的 T3 0.747 是 dev 平面（multiturn+r9，零 longctx/doc-intent——arch §6.15 镜像漏洞）；deveng 的 epoch 回归守卫在 dev 平面防 LoRA 破坏已学边界，**heldout 族平面的验收以 qa 读数为准**（m6_t3_family.py 族分解）——设计分工已裁决，非违规
- config 瑕疵记录：notes 尾行"regression guard vs v1-2 baseline"为陈旧表述（实际 baseline_readings = v1-3，注释块正确）——已报 deveng，不影响审计结论

## 3. 阈值标定纪律

- QA harness 选点（mode select-op）：仅 dev + dev-mirror/challenge-mirror（可行域约束），预注册 25 档网格（v1.3.2，Lead 批准留痕）✓
- deveng calib.json：dev split（D8 零 FP 构造）✓
- heldout/challenge/ood 从未进入任何阈值标定路径 ✓（challenge-mirror 是 dev-mirror 内的定标镜像，非 challenge 本体）

## 4. 红线执行记录

- data/heldout/ 全程只读（m6_heldout_map.py 以只读模式扫描；qa 全部产物不含对 data/heldout 的写操作）
- data/m6/challenge、ood：仅推理消费（m6_infer 输入），无训练引用
- 历史事故与修复：GPU 单卡撞卡（02:17，qa 让路）；数据热修波两次重跑读数（v0×2、v1-1 弃）——均为流程事件，无红线违规

## 5. 结论

**乙醇纪律全程无违规**：冻结套件（data/heldout）从未进入训练/调参/阈值标定的任何代码路径；训练侧指标与校准全程 dev split；阈值标定仅 dev + dev-mirror。heldout/challenge/ood 在训练管线的引用仅为惰性外部约定（grep 证据留档）。

## 6. v2 波审计条款（arch/Lead 执行注记）

形式族合成数据（toolout 轨迹/jb 变体/document 长文/topup-t9）入池后，泄漏三锁以**内容级口径**复验（L1 精确/NFKC + L5 实体子串；形式同族的结构相似是设计意图，内容独立是审计要证明的命题）——qa leak-check 全口径重跑出证。

**执行记录（D 波 post-fix，10-22 03:3x）**：leak-check-d-wave-post-fix.json——train 59,583 行（D 波扩容后）vs eval 16,263（含 T2 heldout +42 jbvar 切分）+ frozen 2,806 + redteam 170：L1/L2/L3 exact=NFKC=0、L5 实体 hits=0（3,900 行）、L4b 红队 0；L4a 5-gram containment flag=241,244（披露层——形式同族的结构相似，正文级 8-gram 独立性由 L5 佐证）。**overall PASS**——形式参照与内容复制的区分成立，条款闭环。

## 7. 口径换算注记

dev 统计三口径：deveng union（t*/dev + pool 多键，12,618 行）/ qa 去重单视图（8,139）/ qa 完整合并（13,239 = 8,139 + pool 独有 5,100）。QA 选点以完整合并口径执行（operating-point-v2 刷新记录）。
