# v0.6-document 门禁集：验收、更正我的证据错误、以及一项需决策的登记

**时间**：2026-09-30 晚。子代理 `5076a80d` 交付完成并已停止。
**验收**：`BUILD-DOCUMENT-GATE=PASS items=80`、`DOCUMENT-GATE-CHECK=PASS errors=0`、
`TEST-DOCUMENT-GATE=PASS checks=all`、`CARRIER-ONTOLOGY-CHECK=PASS errors=0`（回归无漂移）✓

---

## 一、★更正我自己的证据错误（**我犯了我自己写的规则 25 所禁止的错误**）

我在 `reports/document-gate-overlap-adjudication.md` 里写过：

> "`shared_content_max = 8` 字节 ⇒ 最长只共享 8 字节"

**这是错的。** 子代理指出：该键存的是**判据常量** `SHARED_CONTENT_MAX`，
**不是测量值**——而这**正是 docs/01 §11.25 规则 25（指标命名必须与实际测量对象一致）
所要防的事故本身**。真实测量上界是 **`long_share_max_skeleton_bytes = 28`**。

- **我的结论方向仍然正确**（17,558 不是内容重叠），但**证据里的 8 必须换成 28**。
- **根因**：我读了一个**名字像测量值**的键，**没有去读它的赋值处**。
  这与本会话我另两次错误同源（把注释当事实、拿未被使用的配置文件当权威）
  ⇒ 共同模式：**我信任了"看起来像"的东西，而没有验证它的来源。**

**★子代理还给出比我手上更强的事实**（我原本没有）：
17,558 的 **100% 落在两个非活分支**——`sec_sft_topup.jsonl` 8,779 + `doc_structure.jsonl` 8,779；
`dpo_m3_final.jsonl` **0**；`carrier_sft_slice` / `sec_sft_needlefix_carrier` / `dpo_m3_carriers_v1` **0**。
**活谱系文件命中为 0**，因为**只有这两个非活分支带 `<meta>` 信封**
（活谱系与未用切片全是 `body_only`）。
⇒ **不需要改 manifest 的任何 claim** ✓，且结论比我原先的表述**更强**。

## 二、子代理逐条闭合了我登记的缺口

| 我登记的缺口 | 现状 |
|---|---|
| `split_site_directive` 无干净负例 | ✅ **已补 2 条**（zh+en，同结构位点无载荷）⇒ 对齐条 26→**28**；检查器新增 `b.no_clean_control` 强制"每机理 ≥1 条干净负例"，**8/8 全过** |
| `("raw_hits_long_content_share", 0)` 断言误名 | ✅ 已改为 6 条**真内容断言**（逐行 sha256 / 载体渲染文本 sha256 / 60B 内容窗口 / ≥8B 载荷片段整串包含 / 12B **散文层**窗口 / 与 7 个既有留出集三重比对 1,051 条）**全 0**；骨架桶改名为 `raw_hits_long_share_skeleton` 且**不设 0 阈值**（登记归属） |
| manifest 滞后于产物被报成"sha256 不一致" | ✅ **采纳我的诊断**：新增具名时序规则 `jsonl.mtime > manifest.mtime` ⇒ 报"**清单滞后于产物**" |
| 输出 109,781 条 / 58,384 行 | ✅ 聚合为"每类 ≤3 样例 + 计数 + 种类表"，明细写 `--stats-out` |
| `live_envelope` 8,800 vs 1,000 | ✅ 两个对象不同：`envelope_live_lineage_rows`=1,000 vs `envelope_candidate_pool_rows`=6,400；8,800 = 旧标签 `has_meta`(2400)+`has_dom`(2400)+`body_only`(4000) 而**前两者可同时命中同一行**；已改**互斥标签** |
| `_work` 体量 254 MB | ✅ **254 MB → 17.5 KB**（`overlap-full.json`）；只存计数+哈希+每桶 ≤20 条样例，**不含训练语料原文** |

**仪器改动登记**（7 条，逐条理由在 `reports/document-gate-report.md` §2.4）；
子代理自述：**除"把 1 条写错的断言换成 6 条真内容断言"与"分片 strip 口径"外未动任何断言，净效果更严** ✓。

## 三、★需决策：`v0.6-document` 的登记方式（我暂**不**擅自登记）

**子代理的关键提醒**：`check_carrier_ontology.py` 的 `GATE_SCOPES` / `INSTRUMENT_ROLES`
是**硬编码**，`v0.6-document` **不会**自动进覆盖矩阵；
**登记前本集不改变本体覆盖率结论**。

**难点**：子代理建议的角色是**按被评模型索引**的——
- `soup-a050`（`carrier_seen=false`）⇒ `unseen_carrier_gate`
- `m3-dpo`（`carrier_loaded=true` / 1000 行）⇒ `unseen_mechanism`

而现有 `INSTRUMENT_ROLES` 是**扁平映射（一个仪器一个角色）**，
**无法表达"同一仪器对不同模型扮演不同角色"** ⇒ **登记需要先改检查器的结构**。

且该套件自述的未见性范围是 **`unseen_mechanism_scope='structure_site_only'`**
（8 类结构位点与活谱系非零位点交集为 ∅，但**语义层只覆盖 6/8**）
⇒ **它不是全载体级未见性证据。**

### 三个选项

| 选项 | 做法 | 代价 / 风险 |
|---|---|---|
| **A（推荐，最保守）** | **暂不登记**。在 docs 记一行"本集已建成但**未纳入覆盖矩阵**，其结论不参与本体覆盖率"。 | 覆盖率结论**不变**（无风险）；代价是本集的白白建成一段时间 |
| **B** | 改 `INSTRUMENT_ROLES` 支持**按模型分列**，再按子代理建议登记两类角色。 | 结构性改动 + 需重算矩阵；**正确但工作量中等**，且要重新验证不破坏既有 4 列 |
| **C** | 按**单一角色**登记（只给 `unseen_carrier_gate` 或只给 `unseen_mechanism`）。 | 最省事，但**会掩盖"对 m3-dpo 它不是未见载体门"这一事实** ⇒ 有**过度声明**风险 |

**我的判断**：**B 是唯一无损的**，A 是可接受的临时态，**C 不可取**（它违反规则 24
"未见载体必须按被评产物索引"）。
**默认动作**：在本轮**保持 A**（不登记），把 B 作为下一项明确工作；
**不采用 C**。

## 四、子代理自述的三个不确定（照录，供后续取数）

1. **信封-OOD 未分离**：M3 活谱系 document 全为 `body_only`，门禁条带完整 `<meta>/<dom>`
   ⇒ **单个 M3 失败不能唯一归因到结构位点**。
2. **单机理样本量小**（5–6 条；`split_site_directive` 干净负例仅 2 条），
   逐机理读数**低于 §11.2 效力下限**，只能整体读。
3. **骨架行长共享 17,558 未清零**：清零需放弃 `<meta>` 信封设计
   （即放弃"信封未见性"这一声明），当前是**有意取舍**并已在 manifest/README 登记归属。
