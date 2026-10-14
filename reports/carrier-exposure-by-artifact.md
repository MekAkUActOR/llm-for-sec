# 载体暴露必须**按产物索引**（2026-09-30 晚，S1 结构性更正）

> **一句话**：本项目此前把"载体是否已训"当成**全局量**，导致本体论记 document = 5,200 行"已入训"。
> 字节级普查证明它是**按产物不同**的：document 对 `soup-a050` 是 **0 次**（完全未见），
> 对 M3 是 **1,000 次**（正在训练）。⇒ **"未见载体"这句话不指明被评产物就没有意义。**
> 已固化为 `docs/01` §11.24 = 规则 24，并把本体论的判定基准从 `lf_total` 改为 `live_lineage`。

## 1. 怎么发现的（一条链路，每一步都推翻了上一步的假设）

1. **staging 结账**（`reports/staging-manifest-reconciliation.md` §6）报告一个刺眼的边界现象：
   `data/sft/m2.5-staging/` 的 14 族中 **10 族 100% 已在终混 `sft_m25.jsonl` 里**，
   零重叠的只有 4 个文件——而 `doc_structure` / `t2_mechanism` / `t9_phish_expand` **正是**其中三个。
   ⇒ 备料目录**不是**独立留出材料。
2. **追问**：那本体论说的"document 已入训（5,200 行，经 C 路 top-up 绑定）"还成立吗？
   按 user 文本哈希追踪（`scripts/trace_carrier_into_lineage.py`）：
   `doc_structure.jsonl` 的 1,136 条唯一 user **只**出现在 `sec_sft_topup.jsonl`，
   而该文件被 `m3base-topup{,-e1,-e2}.yaml` 消费——**全是已 FAIL 的 C 路**（权重 `discarded`）。
3. **第一次误判**：我据此推断"document 完全没入训"。**错**——见第 4 步。
4. **我的检测方法本身错了两次**：
   - 第 1 版正则用裸 `<carrier>` ⇒ 命中 0，而 docs/01 记 13,981 行带信封；
   - 第 2 版用未转义 `type="` ⇒ 仍命中 0；
   - **字节级检查**才查明真相：训练文件是 JSONL，信封引号被转义为 `\"`，
     实际形态是 `<carrier type=\"text\" trust=\"untrusted\" id=\"c1\">`。
     `<carrier type=\"` 在 `sft_m25.jsonl` 出现 **13,981** 次，与 docs/01 登记**逐位吻合**。
   ⇒ **教训已写进规则 24 第 4 条：体检口径 = 该计数必须等于 13,981，不一致就是匹配写错了。**
5. **真结论**（`scripts/census_carriers_authoritative.py`）：

| 训练文件 | 状态 | document |
|---|---|---|
| `sft_m25.jsonl`（m25-full） | 活 | **0** |
| `sec_sft_needlefix.jsonl`（`soup-a050` 的一半） | 活 | **0** |
| **`dpo_m3_final.jsonl`（M3 DPO，训练中）** | **活** | **1,000** |
| `sec_sft_topup.jsonl`（C 路 top-up） | **权重已废弃** | 1,200 |
| `data/sft/m2.5-staging/doc_structure.jsonl` | 备料（经哈希证明只进废弃分支） | 1,200 |

## 2. 根因：本体论的 `train` 列用了 `lf_total`

`data/ontology/carriers.json` 的 `coverage_matrix.cells[*].train` 原为
`basis: "lf_total"` = `data/lf/*.jsonl` **全部加总** ⇒ 把
(a) **从未被任何 config 消费**的文件（`sec_sft_needlefix_carrier`、`carrier_sft_slice`）、
(b) **已废弃分支**（C 路 `sec_sft_topup`）的数据
**都算成了"已训"**。9 个载体的 `train.n` 全部虚高：

| 载体 | 旧（lf_total） | 新（live_lineage） |
|---|---|---|
| text | 27,076 | **11,873** |
| email | 10,484 | **3,493** |
| tool_output | 5,624 | **2,324** |
| log | 4,713 | **1,338** |
| webpage | 5,607 | **1,332** |
| code | 4,718 | **1,343** |
| **document** | **5,200** | **1,000** |
| image_metadata | 0 | **0** |
| av_metadata | 0 | **0** |

### 修法与验证
- `data/ontology/carriers.json`：`train.n` 改 basis = `live_lineage`（旧值保留在
  `train_all_lf_basis_lf_total` 并标注"不得用于未见载体判定"）；
  新增顶层 `carrier_exposure_by_lineage`（文件 × 载体 × 状态）；
  逐载体 `train_rows["live_lineage"]`；`claim_rule` 增补规则 24 的口径。
- `scripts/check_carrier_ontology.py`：新增 **`live_lineage` scope**（多 glob 并集，
  = `sft_m25` + `sec_sft_needlefix` + `dpo_m3_final`），并把 `train` 列的 scopes 从
  `["lf_total"]` 改为 `["live_lineage"]`。`lf_total` 保留但标注"仅作面量参考"。
- **验证**：`CARRIER-ONTOLOGY-CHECK=PASS errors=0` ✓（9 类载体 / 扫描 72 个 jsonl）。
  检查器**自己重算**并与本体论逐格比对，故这是独立的机器确认，不是自证。

## 3. 关键的**好消息**：三条未见载体门禁中的两条被加固，第三条被发现

- `claims.unseen_carrier_gate_carriers` 现在是**机器推导**的：按 live_lineage 暴露为 0 且
  门禁鲁棒性分母 ≥34 ⇒ 仍为 **`image_metadata` / `av_metadata`**（二者在本项目**全部**活产物，
  含 M3，暴露均为 0）。
- **M3 门禁泄漏检查**（`scripts/check_m3_gate_leak.py`，发射前必跑）：
  `data/heldout/v0.3-gen` 的 258 条 = **av_metadata 132 + image_metadata 126**，
  与 `dpo_m3_final.jsonl` 的文本重叠 = **0**，且 DPO 数据的载体分布**不含** image/av metadata
  ⇒ **M3 的 MUST-A"未见载体"claim 未被污染** ✓（同时反证了我此前的 Q2 裁决
  "不要训 image/av 元数据"是对的：训了就会毁掉仅有的两条支撑断言）。
- **第三条门禁的机会**：document 对 `soup-a050` 是 0 次暴露 ⇒ 在**未训 document 的产物**上，
  document 门禁可以**合法声称未见载体泛化**——那会是本项目**第三条**达标门禁，
  且是**第一条文本类**的（现有两条都是元数据类）。已把这一点发给 document 门禁工作流：
  其 `claims` 必须**按被评产物分列**（对 M3 = 仅未见机理；对 soup-a050 = 未见载体 + 未见机理）。

## 4. 我这次错在哪（供审计）

| # | 我的错误 | 性质 | 怎么发现的 |
|---|---|---|---|
| 1 | 据 user 哈希追踪断定"document 完全没入训" | **结论跳得太快**：只查了一个来源文件，未普查全部活文件的载体分布 | 表驱动普查（逐文件 `type=\"...\"`） |
| 2 | 两版正则（裸 `<carrier>`、未转义 `type="`）都得 0，我却先怀疑"事实"而非"方法" | **方法错当成事实错** | 字节级 `data.count(b'<carrier type=\\"')` |
| 3 | 一度把结论写成"该载体只在废弃分支里出现过"（基于错误的方法得 0） | 由 #2 派生 | 同上 |
| 4 | 本体论修正脚本里改名 `lf_total` → 制造未知 scope，检查器报 18 错 | 未先读检查器的联动校验约定 | 实跑检查器 |

**共性**：**每次都是"实跑"救的场**——这与今晚其余 5 次（`fisher_p_greater` 缺 import、
`axis_decision` 缺 import、`--heldout` 传文件而非目录、引号 6 次、BOM）同型。
⇒ 本节最有价值的产出可能不是 document 的数字，而是"**任何'事实'结论在被机器复核前都不算成立**"这一条。
