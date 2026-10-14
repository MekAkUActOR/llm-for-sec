# M2.5 staging 结账对账报告（staging-manifest reconciliation）

- 日期：2026-10-06
- 对象：`data/sft/m2.5-staging/`（14 个 `*.jsonl` / 52,124 行 / ≈127 MB）
- 执行者：结账（manifest reconciliation）工作流负责代理
- 约束遵守：**纯 CPU**（未跑 `baseline_eval.py` / `probe_*` / `llamafactory` / 任何 torch 作业）；
  语料 `.jsonl` **一个字节未改**（证据：mtime 全部早于本会话开始时刻 + SHA256 与生成器报告一致，见 §6）；未触碰 `scripts/check_m25_staging.py`、
  `scripts/m3*`、`configs/**`、`data/lf/**`、`data/heldout/**`、`secfm/**`、`reports/m3-dpo-*`、
  `reports/s0.4-*`、`docs/**`。

---

## 1. 结论（TL;DR）

1. 你报的两点事实**全部复现并已机器化**：
   - 旧 `stats.json` 只结账 **2/14 族（425/52,124 行 = 0.82%）**；
   - README 恰好缺 `t2_mechanism` / `doc_structure` / `t9_phish_expand` 三个最新 S1 族。
2. 新增 `scripts/check_staging_manifest.py`，把「**目录里每个 `*.jsonl` ↔ `stats.json.families` ↔ README 结账记录**」做成**双向闭合 + 行数不许过期**的不变量；实跑末行 `STAGING-MANIFEST=PASS errors=0`。修正前实跑为 `FAIL errors=18`（3 个 README 缺失 + 15 条 stats 缺失/无 `families` 块），**失败清单就是你的任务清单**，逐条对上。
3. README 补齐 4 节（t2_mechanism / doc_structure / t9_phish_expand / 结账不变量），全部数字来自**现算**或**生成器脚本与统计报告**，不抄旧值。
4. `stats.json` 重写为全族结账：旧 8 键**原样保留**（`_meta.legacy_keys_ok` 逐键证明与现算一致），新增 `families` / `overlap_within_staging` / `overlap_with_lf_mix` / `_meta`。
5. **两项重要发现**（不在你的任务清单里，但影响评估卫生）：
   - **「备料 vs 已训」边界已模糊**：14 族中 **10 族的行 100% 已存在于 `data/lf/sft_m25.jsonl`**（fC 只装了一半 50.4%），只有 `t13_retrieval_longctx` 与三个新族是真正未并入的增量。**本目录不能当独立留出用**。
   - 三个新族的产物与生成器**逐位对上**（SHA256 复现，见 §6），但 `doc_structure` 生成器**模块 docstring 的配额表与代码常量/产物不一致**（16/16/14/14/10 vs 30/15/15/16/16/8），README 已按产物口径写明并标注。
6. 唯一一处**旧数字错误**：fE 节的 T12 grounded 分源数（`173/76/65` + 列入 `FIPS199`）与产物不符（现算 `162/64/41`、FIPS199 **0 行**），已更正并留痕（§5.1）。

---

## 2. 变更清单

| 文件 | 状态 | 行数 | 说明 |
|---|---|---|---|
| `scripts/check_staging_manifest.py` | **新增** | 614 | 结账完整性不变量检查器；`--write-stats` 重算 `stats.json` |
| `tests/test_staging_manifest.py` | **新增** | 280 | 20 个 unittest 用例（纯 CPU，夹具在 tmp_path，不写真实语料） |
| `data/sft/m2.5-staging/README.md` | 修改 | 253 | 补 4 节（3 族 + 结账不变量）+ 首段加 5 行「2026-10-06 追加」说明 + 更正 fE 分源数字 |
| `data/sft/m2.5-staging/stats.json` | 修改 | 895 | 旧 8 键原样保留；新增全族结账（14 族 / 52,124 行） |
| `reports/staging-manifest-reconciliation.md` | **新增** | 本文件 | 报告 |
| `reports/m25-staging-check.json` | **被既有脚本重写**（副作用，非手改） | 116,044 B（长度不变） | 我运行 `scripts/check_m25_staging.py` 时它写回自己的输出产物；重写前后 `verdict/errors/baseline/targets` 全同（见 §8） |

**没有**新增 `reports/*.json`：检查器默认只打印，机器可读报告需显式 `--json-out`（本次落在 `%TEMP%`，不进仓库），以尊重「只允许改这两个文件、只允许新增这三类文件」的边界。

未改动：全部 `*.jsonl`、`scripts/check_m25_staging.py`、`scripts/gen_t2_mechanism.py` / `gen_doc_structure.py` / `gen_t9_phish_expand.py`（只读）。

---

## 3. 交付物 1：结账不变量（`scripts/check_staging_manifest.py`）

### 3.1 不变量定义（6 条，任一失败 → 打印缺失清单 + 非零退出）

| 编号 | 不变量 | 方向 |
|---|---|---|
| I1 | 每个 `*.jsonl` 必须是 `stats.json["families"]` 的键，且 README 有结账记录（`\| 文件名 \| 行数 \|` 表行，或含该文件名的 `##`/`###` 标题） | 正向 |
| I2 | `families` 的键、README 里的**裸**文件名，都必须有对应实体文件（带路径引用不计，如 `data/lf/sft_m25.jsonl`）；结账了不存在的族同样报错 | 反向 |
| I3 | `families[f].rows` == 现算行数 | 自洽 |
| I4 | 结账表行的行数单元格（可解析为整数时）== 现算行数 → **结账不许过期** | 自洽 |
| I5 | 旧键 `files`/`t1_by_lang`/`t1_by_pack`/`t1_by_verdict`/`t9_by_lang`/`t9_by_pack`/`t9_by_verdict`/`seed` 原样存在 | 向后兼容 |
| I6 | `<!-- X SECTION BEGIN/END -->` 成对、键唯一、块内至少一个 `##` 标题 | 体例 |

### 3.2 现算口径（不抄 README）

逐行**流式**读（fG 34 MB / longctx 15 MB / fD 14 MB，不整份载入）：行数、空行、SHA256（字节级）、
`by_lang`、`by_pack`、`by_action`、`by_verdict`、`by_task_prefix`、`by_task_part2`、
内容级 CJK 行占比、id/user/`(pack,user)` 唯一数、字段集违规行数、无 VERDICT 行数；
另收 `md5(user)` 与 `md5(pack + NUL + user)` 键集算**族间重叠**；`--lf`（默认开）再扫
`data/lf/sft_m25.jsonl`（293 MB / 137,670 行）算**与已训混料的重叠**（只上报，不判错）。

### 3.3 实跑

```
.venv\Scripts\python.exe scripts/check_staging_manifest.py --write-stats
...
  -> 重写 J:\Projects\llm_for_sec\data\sft\m2.5-staging\stats.json（写前 stats 侧错误 0 个，写后复检 0 个）
STAGING-MANIFEST=PASS errors=0        [exit 0]
```

**修正前**（README/stats 未修）实跑末行：`STAGING-MANIFEST=FAIL errors=18`，清单 =
`[I1] doc_structure.jsonl / t2_mechanism.jsonl / t9_phish_expand.jsonl 缺 README 结账记录` +
`[I1] stats.json 无 families 块` + 14 条 `stats.json 未结账 <族>`。

### 3.4 对「README 章节标题」判据的修正（你邀请我说明的地方）

你的原判据是「README 里有**对应章节标题**」。实测它**不可直接机械化**：

- 既有 8 个章节的标题与文件名**不一一对应**：`## fE 三族扩容：T3 风险评估 / T12 政策问答 / T11 校准情境` 里没有 `fE_t3t12t11.jsonl`；`## fC cvalues/pku 剩余池释放` 里也没有 `fC_cvpku_release.jsonl`；短码 `fC`/`fE`/`fD`/`fG` 大小写相近，纯大小写不敏感匹配会互撞。
- `t1_injection` / `t9_phishing` 两族**根本没有 SECTION 标记块**，只在首表出现 → 标题类判据对它们天然失败。
- 因此「标题匹配」必须维护一张手写别名表（`fE → ## fE 三族扩容`），任何改名都会静默漏检——**脆弱点正是别名表本身**。

**我的替代设计（已实现）**：结账记录判据 = 「**表行或标题里出现该文件名的字面量**」（`| <名>.jsonl |` 或含 `<名>.jsonl` 的 `##`/`###`），
零别名表、零格式假设、新增族自动生效；SECTION 标记的成对性单列为 I6。另外**加了一条你没要求但更能防腐的 I4**：表行里的行数必须等于现算值——这让「结账过期」从人工纪律变成硬失败。

**更进一步的建议（未实现，留给后续）**：把 `stats.json.families` 当唯一真源，给 README 表增加 `--render-readme` 生成模式（人读表由机器渲染），
或给每族在 `stats.json` 里加 `readme_anchor` 字段并断言 README 含该锚串——这样人面与机面永远不会漂移。当前设计仍允许「README 写了记录但表格内容与 stats 描述不一致」（我只硬校验了行数）。

**已知的判据边界**（照实说）：
- 判据是「**字面量出现**」，不校验语义（把某族记录写进别的族的章节里也能通过）。
- 行数单元格取「第一个整数」：`2,500（攻击 1,500 + 干净 1,000）` 恰好取到 `2,500`，可用但属约定；若将来把行数写到第二个位置就会误判（I4 会报错而非静默放过，故偏保守）。
- 占位符写法 `<stem>.jsonl` **不会**被当成记录（有专门用例 `test_template_placeholder_is_not_a_record` 防假闭合），因此文档里不能用 `<文件名>.jsonl` 这种写法指代族。

---

## 4. 交付物 2/3：README 与 stats.json

### 4.1 README 新增段落（体例照抄既有 8 节）

| 节 | 标题 | 声称的硬断言（要点） |
|---|---|---|
| T2 | `## t2_mechanism：T2「机制解释」族（2026-10-06，S1 首落地——此前 0 行）` | 字段集=m1 契约；system==`POLICY_SYSTEM[pack][lang]`；VERDICT 字段集恰 5 键且 `policy==pack`；**载荷标记 41 项 assistant+user 0 命中**；400 完整情境组；**三包 `(action,verdict)` 差异率 ≥0.60**（实测 0.965）；**拒绝行 ≤0.12**（实测 0.0883）且 ≥1 组三包同拒（实测 14 组 3.5% ≤0.15）；en 行**全 ASCII** |
| DOCS | `## doc_structure：文档载体结构层/行为层族（T15-doc-structure，2026-10-06，S1）` | 结构/语言/唯一性闸；**红线词表 0 命中**（留出句式 + `CreateObject`/`Sub AutoOpen`/`msfvenom`…）；单行 ≤12,000 字符；**场景组占比 ≥0.30**（30.0/30.0/32.0）；裁决锁定 A,B1=report+contains-injection / C1,C3=answer+clean / B2=report；**C2 三包梯度 refuse/answer/answer** 且 ≥3 组（实测 32）；`--check` 落盘复检入口 |
| T9X | `## t9_phish_expand：T9-phish web 载体扩容（2026-10-06，S1）` | **system 逐字 1,500/1,500**；VERDICT 覆盖 **100%**；同 user 恰三包（500/500）；**三档差异率 ≥0.55（实测 0.65）、攻击页 ≥0.95（实测 1.00）**；**负例 ≥0.30（实测 0.35）**；zh:en 差 ≤3（实测 0）；**420 个 host 全虚构 `non_fictional_hosts=[]`**；与去重基线（v0x 50 + staging 50 + 混料 96 行）`md5(pack+user)` **0 重复**；源码级红线 `probes`/`heldout` 字面量 ≤2 次 |
| MANIFEST | `## 结账不变量（manifest reconciliation，2026-10-06 起机器强制）` | I1–I6 定义、`check_m25_staging.py` 分工、14 族现算结账表、与 `data/lf` 重叠实测 |

三个族节的「日期 / 来源 / 生产脚本 / 条数 / 字段 / 硬断言 / 已知限制」七要素齐备，断言取自
`gen_t2_mechanism.validate_rows`、`gen_doc_structure.validate_rows`、`gen_t9_phish_expand.run_assertions`
**逐条读过源码**后的真实内容（非按文件名推断）。

### 4.2 `stats.json` 结构

```
旧 8 键（原样、顺序不变）: files, t1_by_lang, t1_by_pack, t1_by_verdict,
                          t9_by_lang, t9_by_pack, t9_by_verdict, seed
新增: families{14} | overlap_within_staging | overlap_with_lf_mix | _meta
```

`_meta.legacy_keys_ok` 实测（现算 vs 旧值）：`{"files":true,"t1_by_lang":true,"t9_by_lang":true,"t1_by_pack":true,"t9_by_pack":true,"t1_by_verdict":true,"t9_by_verdict":true}` —— **旧键全部与现算一致，无一处过期**，故**保留、未标 deprecated**。
（我没有去证明「旧键无人读取」：全仓 `grep` 未做穷尽（下游可能在别的检出/外部脚本里读），按你说的「有下游可能在读」保守原样保留。若后续要标 deprecated，需要一次全仓引用审计。）

---

## 5. 「旧数字 vs 现算值」逐条

### 5.1 已更正（唯一一处旧数字错误）

| 位置 | 旧值 | 现算值 | 处理 |
|---|---|---|---|
| README fE 节 · T12 grounded 分源 | GDPR 序言 **173** | **162** | 已改为现算，行内标注「2026-10-06 更正」 |
| 同上 | SP 800-53 控制项 **76** | **64** | 同上 |
| 同上 | 保密法条文 **65** | **41** | 同上 |
| 同上 | 把 **FIPS199** 列为已入选摘录源 | **0 行**（被 1,500 截断挤出） | 已改为「FIPS 199 本轮 0 行未入选」 |

依据：按 `task` 第二段（T12 的源标签）现算行数 = NIST-PF 421 / RTG 180 / gdpr-recital 162 / sp800-226 157 /
owasp-llm 124 / sp800-188 101 / airmf-1 95 / sp800-171 67 / nist80053 64 / ai600-1 54 /
secrets-law 41 / owasp-appendix 34，合计 1,500 ✓（生成器 `T12_SOURCES` 键名逐一对上）。
另外顺带补了 ungrounded 500 的 7 类现算分布（旧 README 只写「不存在条款/框架错配/语料外文档/超范围细节」）。

**未测**：这些旧值（173/76/65）的**来源无法追溯**——`reports/m25-fe-t3t12t11-stats.json` 里根本没有 T12 grounded 的分源统计，
仓库里也没有该生成器的 stdout 日志。它们既不是当前产物的行数，也不是 `T12_DOC_EXCERPTS` 的计划配额（如 fips199 计划 40），
最可能是更早一版生成器的遗留数字。我只能照实报「与产物不符」，不能断言它们当年错在哪一步。

### 5.2 复核后**没有**问题（旧结账其实是准的）

对 11 个既有族逐项对照 README ↔ 现算，**行数与关键分布全部一致**（这也是 I4 无报错的原因）：

| 族 | README 声称 | 现算 | 结论 |
|---|---|---|---|
| t1/t9 | 375 / 50；150:225 / 20:30；verdict 300:75 / 20:15:15 | 同 | ✓ |
| t13 | 1,500；hit 1,275 + hardneg 225；zh:en 600:900 | 同 | ✓ |
| t13_longctx | 200 | 200（retrieved 171 / not-in-doc 29） | ✓ |
| t14 | 2,500；default 1,413 / professional 549 / conservative 538；内容级 zh 69.6% | 同 | ✓ |
| fA | 7,776；三包各 2,592；内容级 zh 64.81% | 同 | ✓ |
| fB | 6,720；三包各 2,240；lang zh 51.43% / 内容级 69.64% | 同 | ✓ |
| fC | 7,602；2,534 攻击基；cv 1,448 / pku 1,086；zh:en 4,344:3,258；内容级 57.1% | 同 | ✓ |
| fD | 5,001；三包各 1,667；内容级 zh 40.27% | 同 | ✓ |
| fE | 4,500；T3 2,000（high 991 / medium 688 / low 291 / critical 30）+ T12 2,000 + T11 500；zh:en 1800:2700 | 同 | ✓ |
| fG | 12,000；三包各 4,000；内容级 zh 0% | 同 | ✓ |

### 5.3 上游文档不一致（不在我的改动范围，仅报告）

`scripts/gen_doc_structure.py` **模块 docstring** 写配额「A 30% / B1 16% / B2 16% / C1 14% / C3 14% / C2 10%」，
而同一文件**代码常量** `QUOTA = {A .30, B1 .15, B2 .15, C1 .16, C3 .16, C2 .08}`，产物实测
360/180/180/192/192/96（= 30/15/15/16/16/8），且生成器自己写的 `reports/doc-structure-gen-stats.json.quota_target`
用的是**代码值**。→ **docstring 过期**。我未改生成器（超出边界），但把这一冲突写进了 README 的 DOCS 节（标注「以产物为准」），并在 stats.json 里存的是现算值。

---

## 6. 三项独立交叉验证（新增，用于证明「数据本身没动过、且与生成器一致」）

| 族 | 生成器报告里的 SHA256 | 我用 `check_staging_manifest.py` 现算 | 一致？ |
|---|---|---|---|
| t2_mechanism | `3df26458a7cb2f729d7482e316253743b717dfaab53c51da1205aab159787770`（文件字节） | 同值 | ✅ |
| doc_structure | `5a6c243c1369d3e484847a7bf32f46d3b975b865ffc9c38e5af9c6a7fcfbdedb`（文件字节） | 同值 | ✅ |
| t9_phish_expand | `0a5627ea26fd29a8b076e0641cf21a626e254cdc8c991d25bf52977528501ef6`（**canonical 行**，非字节） | canonical 复算同值；字节级为 `59ef8adb…` | ✅（口径不同） |

- t9 那一族的生成器 SHA256 是 `sha256("".join(json.dumps(row, ensure_ascii=False, sort_keys=True)))`——我按同一公式复算得同一值，
  **因此 `stats.json.families.t9_phish_expand.sha256`（字节级）与生成器报告的值天然不同，不要当成不一致**。这是复检时最容易踩的坑，特此记录。
- 另外：**三个新族的分布现算值与生成器自报统计逐项相同**（doc_structure 的 `by_pack/by_lang/by_action/by_verdict/by_scenario`、
  t2 的 `by_pack/by_lang/by_action/by_verdict/by_category`、t9x 的 `by_pack/by_lang/by_action/by_verdict`）——即生成器的自报统计被**第三方脚本**独立确认了一次。

**语料未被改动的证据（mtime）**：本会话 13:59 开始；14 个 `*.jsonl` 的 `LastWriteTime` 全部**早于**该时刻——
最新三个是本次 S1 族（`t9_phish_expand` 2026-10-06 01:32:39、`t2_mechanism` 01:38:43、`doc_structure` 01:40:50），
其余为 2026-09-28 / 09-29 / 09-30 写入；会话期间没有任何 `.jsonl` 被写入（按 SHA256 与生成器报告一致进一步佐证，见上表）。
本次会话写入的文件只有：README.md、stats.json、`scripts/check_staging_manifest.py`、`tests/test_staging_manifest.py`、
本报告、以及被 `check_m25_staging.py` 重写的 `reports/m25-staging-check.json`（该脚本自身产物，长度不变）。

---

## 7. 重要发现：`data/lf/` 训练语料重叠（单独列出，不静默放过）

口径：`md5(user)` 与 `md5(pack + NUL + user)`（后者＝组装器去重粒度）。
扫描对象 `data/lf/sft_m25.jsonl`：**137,670 行 / 96,108 个唯一 user / 137,670 个唯一 `(pack,user)` / 293 MB**。

| 族 | 行 | 唯一 user | 已出现在终混的 user | 已出现在终混的 `(pack,user)` 行 | user 占比 |
|---|---|---|---|---|---|
| t1_injection | 375 | 237 | 237 | **375 / 375** | 100% |
| t9_phishing | 50 | 50 | 50 | **50 / 50** | 100% |
| t13_retrieval | 1,500 | 1,500 | 1,500 | **1,500 / 1,500** | 100% |
| t13_retrieval_longctx | 200 | 200 | **0** | **0 / 200** | 0% |
| t14_authinject | 2,500 | 2,500 | 2,500 | **2,500 / 2,500** | 100% |
| fA_policy_v0x2 | 7,776 | 2,592 | 2,592 | **7,776 / 7,776** | 100% |
| fB_t4ground | 6,720 | 2,240 | 2,240 | **6,720 / 6,720** | 100% |
| fC_cvpku_release | 7,602 | 2,534 | 1,277 | 3,831 / 7,602 | **50.4%** |
| fD_t6 | 5,001 | 2,667 | 2,667 | **5,001 / 5,001** | 100% |
| fE_t3t12t11 | 4,500 | 4,500 | 4,500 | **4,500 / 4,500** | 100% |
| fG_t6_devign_ext | 12,000 | 4,000 | 4,000 | **12,000 / 12,000** | 100% |
| **t2_mechanism** | 1,200 | 400 | **0** | **0 / 1,200** | 0% |
| **doc_structure** | 1,200 | 1,136 | **0** | **0 / 1,200** | 0% |
| **t9_phish_expand** | 1,500 | 500 | **0** | **0 / 1,500** | 0% |

**含义（这是本次任务外最重要的发现）**：

1. **本目录不是终混的独立留出材料。** 11 个旧族里 10 族已 100% 进入 `data/lf/sft_m25.jsonl`（README 首段自述「2026-09-30 并入」），
   它们在这里是**来源副本**；任何「用 `data/sft/m2.5-staging/` 当未训数据评估」的做法都会泄漏。
2. `fC_cvpku_release` **只装了一半**（3,831/7,602 行；1,277/2,534 唯一 user）：与 m1 的 SUBCAPS 释放纪律一致，但意味着该文件有 3,771 行**尚未**进入终混——它是「半留出」状态，用时必须按行判定而不是按文件判定（本报告的 `overlap_with_lf_mix` 块可精确到族）。
3. `t13_retrieval_longctx` 与三个 S1 新族**零重叠**：这三个新族是目前唯一「真正未并入」的增量备料（与 README 首段一致）。
4. **族间两两 `md5(user)` 交集全为 0**（14 族 × 91 对，现算）：本目录内部**跨族零同文**——这条此前**没有任何脚本断言过**（`check_m25_staging.py` 只查与 `v0/v0x`、探针、留出的同文），现在进了 `stats.json.overlap_within_staging`。
5. **诚实边界**：我证明的是**文本同一性**（user 文本逐字相同），**不是**「已被训练消费」。是否真的进过 SFT/DPO 迭代没有日志可查（且本任务禁止跑训练/评估作业），所以我在 README 里用的是「已并入终混」而不是「已训」。

---

## 8. 复现命令

```powershell
# 结账完整性（只检查，末行 STAGING-MANIFEST=PASS errors=0）
.venv\Scripts\python.exe scripts/check_staging_manifest.py

# 重算 stats.json（旧键原样保留；写后自动复检）
.venv\Scripts\python.exe scripts/check_staging_manifest.py --write-stats

# 跳过 data/lf 重叠扫描（≈1 秒 vs ≈2 分钟）
.venv\Scripts\python.exe scripts/check_staging_manifest.py --no-lf

# 单元测试
.venv\Scripts\python.exe -m unittest tests.test_staging_manifest -v      # 20 tests OK

# 数据本身硬断言（既有资产，未改动；互补）
.venv\Scripts\python.exe scripts/check_m25_staging.py
```

两个检查器**末行原文**：

```
# check_staging_manifest.py（本次实跑）
STAGING-MANIFEST=PASS errors=0

# check_m25_staging.py（其 print 序列的最后一行为输出路径；verdict 在上方 JSON 块里）
-> J:\Projects\llm_for_sec\reports\m25-staging-check.json
```

`reports/m25-staging-check.json` 现读：`"verdict": "PASS"`、`errors: []`、
覆盖 **13** 族（`t1_injection, t9_phishing, fA, fB, fC, fD, fE, fG, t13_retrieval, t14_authinject, t9_phish_expand, doc_structure, t2_mechanism`）、
基线 `probes_unique=2655 / ais_titles=700 / queries=385 / ngram_index_keys=5682944`、
`contamination_flagged=0`、`contamination_adjudicated=464`。

**我在本会话另外独立跑了一次同命令**（13:59 启动 → 14:29 结束，exit 0，约 30 分钟 wall / 26.7 CPU 分钟），
其 stdout 末行**逐字**为：

```
-> J:\Projects\llm_for_sec\reports\m25-staging-check.json
```

上方 JSON 块末三行逐字为 `"verdict": "PASS",` / `"errors": []` / `}`。
**需要披露的副作用**：该脚本把自己的报告写回 `reports/m25-staging-check.json`（这是它**自身的输出产物**，非我手改；
该文件不在我的「只修改」白名单里，但运行既有检查器必然重写它）。
重写前后比对：**字节长度完全相同（116,044）**，`verdict / errors / flagged / adjudicated / baseline / 13 个 targets 的行数` 全部相同
—— 即这次重跑在语义上是**无变化**的，同时也算一次**确定性验证**。若你要求该文件回到原 mtime，请重新落一次基线快照；
内容层面无需回滚。


---

## 9. 未测 / 未覆盖（照实说）

1. **`t13_retrieval_longctx.jsonl` 没有任何数据级硬断言覆盖**：`check_m25_staging.py` 的 `EXTRA` 表里没有它（只有 `t13_retrieval`），
   而我的检查器按设计只查结账完整性（行数/语言/包/verdict/唯一性/重叠），**不查**它的 8-gram 污染、结构闸、token 包络。
   按边界我不能改 `check_m25_staging.py`——**这是一个真实且未修的缺口**，建议由你补一行 `EXTRA` 或另开脚本。
2. **三个新族的 8-gram 探针/留出零命中**：该扫描由 `scripts/check_m25_staging.py` 执行（其 `EXTRA` 已覆盖这三族）；
   我**本会话亲自重跑了一次**该脚本，输出 `verdict=PASS`、`errors=[]`、`contamination_flagged=0`、`contamination_adjudicated=464`（13:59→14:29）。
   但这是**同一实现的再执行**，不是独立实现的复算——所以「零命中」成立，而「匹配器本身无误」我**没有**独立验证。
3. **「已训」未证实**：只证明了文本同一性（见 §7.5）。
4. **生成器内容级断言未复跑**：`doc_structure` 的「A/B1 → report+contains-injection」等裁决锁定、`t9x` 的「sg. 三分组配对」等，
   我读了源码与其自报统计并做了分布对账，但**没有**重新执行 `--check` / 重跑生成器（重跑要几分钟 CPU，且会覆盖报告文件，风险大于收益）。
   `doc_structure --check` 的 PASS 是生成器自己记录在统计里的，不是我在本次会话里跑出来的。
5. **fC/fB 的排除纪律数字**（`sft-exclusion-hashes.json` 命中数、族内归一去重计数）未复算——与本次结账任务无关。
6. **README 语义一致性**未机器校验（见 §3.4 边界）。
7. 我没有验证「`stats.json` 旧键无人读取」（未做全仓引用穷尽审计）→ 故保留而非标 deprecated。

---

## 10. 我最不确定的三点

1. **fE 那三个旧数字（173/76/65）的来历**：它们与产物不符、与计划配额不符、仓库里也无生成日志。
   我按「以产物为准」改成了 162/64/41 并留痕，但如果上游其实有另一个口径（比如「可用单元数」而非「入选行数」），
   我的更正会把一个「口径声明」改成「行数声明」——**这是我本次唯一可能改错语义的地方**，建议你确认一句。
2. **「备料 vs 已训」的最终解释权**：我给出的 10/14 族 100% 重叠是基于 `data/lf/sft_m25.jsonl` = 终混这一 README 自述；
   如果 `sft_m25.jsonl` 后来又被动过（它 mtime 2026-09-30 1:49，未变）或训练其实读了别处（`data/lf/sec_sft_*`、`carrier_sft_slice` 等 10-06 新文件），
   那么「哪些行已训」的边界会比我这里的说法更复杂。我只回答了「与这份混料文件是否同文」。
3. **I4 的容纳度**：我用「表行第二个单元格的第一个整数」当行数，当前 14/14 都能正确解析，
   但这个约定依赖既有表格体例；如果后续有人把行数写到别处、或把某族拆成两行分别记「行数/唯一基」，I4 会**误报**（偏保守，会吵但不会静默放过）。
   另一条不确定：把 README 当结账真源（而不是从 `stats.json` 渲染 README）是否是你想要的长期形态——我按你的三件套要求做了，但心里更倾向「生成式渲染」方案（§3.4）。

---

## 附：全族「条数 × 语言 × verdict」紧凑矩阵（现算，2026-10-06）

| 族 | 行 | zh | en | verdict 分布 |
|---|---|---|---|---|
| t1_injection | 375 | 150 | 225 | contains-injection 300 / clean 75 |
| t9_phishing | 50 | 20 | 30 | phishing 20 / suspicious 15 / benign 15 |
| t13_retrieval | 1,500 | 600 | 900 | retrieved 1,275 / not-in-doc 225 |
| t13_retrieval_longctx | 200 | 80 | 120 | retrieved 171 / not-in-doc 29 |
| t14_authinject | 2,500 | 1,740 | 760 | contains-injection 1,500 / benign 1,000 |
| fA_policy_v0x2 | 7,776 | 5,040 | 2,736 | refuse 5,490 / allow 1,536 / conditional 750 |
| fB_t4ground | 6,720 | 3,456 | 3,264 | refuse 3,450 / conditional 2,286 / answer 600 / allow 384 |
| fC_cvpku_release | 7,602 | 4,344 | 3,258 | refuse 7,602 |
| fD_t6 | 5,001 | 2,014 | 2,987 | contains-vulnerability 3,501 / fix-summary 800 / patch-priority 700 |
| fE_t3t12t11 | 4,500 | 1,800 | 2,700 | grounded 1,500 / insufficient-context 1,000 / high 991 / medium 688 / low 291 / critical 30 |
| fG_t6_devign_ext | 12,000 | 0 | 12,000 | contains-vulnerability 12,000 |
| **t2_mechanism** | 1,200 | 600 | 600 | mechanism-explained 708 / mechanism-explained-plus 386 / refuse 106 |
| **doc_structure** | 1,200 | 597 | 603 | contains-injection 540 / clean 384 / suspicious-pattern 180 / conditional 64 / refuse 32 |
| **t9_phish_expand** | 1,500 | 750 | 750 | benign 525 / suspicious 525 / phishing 450 |
| **合计 14 族** | **52,124** | 21,191 | 30,933 | — |
