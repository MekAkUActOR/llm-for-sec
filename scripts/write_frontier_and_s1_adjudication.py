# -*- coding: utf-8 -*-
"""把 α–toolout 前沿的完成结果写入 s0.4 报告（替换原 §6 的计划），并写 S1 本体论裁决。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "reports"

# ---------- 1) 替换 s0.4 报告的 §6（原为"待执行"的计划） ----------
p = R / "s0.4-g1-instrument-repair.md"
txt = p.read_text(encoding="utf-8")
old_head = "## 6. 后续（M3 训练结束后执行，需 GPU 串行）"
i = txt.find(old_head)
assert i > 0, "找不到 §6 锚点"
j = txt.find("\n## 7.", i)
assert j > i, "找不到 §7 锚点"
NEW6 = r"""## 6. α–toolout 前沿：**已执行，结论是决定性的否定**

（本节原为"待执行"的计划；2026-09-30 晚用户裁定"先测 α–toolout 前沿再选起点"，故已执行。）

仪器：`scripts/sweep_alpha_toolout.py`（逐档跑 v0.4-toolout，2.5 min/档，严格串行）。
起点 `m2calib` = **2/46**，SHOULD-4 门槛 = **≤4/46**。

| α | 档 | toolout 顺从（鲁棒性 46 条） | 判 |
|---|---|---|---|
| 0.00 | m2calib（起点） | **2/46** | PASS |
| 0.20 | soup-a020 | **7/46** | FAIL |
| 0.35 | soup-a035 | **6/46** | FAIL |
| 0.38 | soup-a038 | **6/46** | FAIL |
| 0.40 | soup-a040 | **6/46** | FAIL |
| 0.42 | soup-a042 | **6/46** | FAIL |
| 0.45 | soup-a045 | **6/46** | FAIL |
| 0.50 | soup-a050 | **6/46** | FAIL |
| 0.65 | soup-a065 | **7/46** | FAIL |

**结论 1（决定性）**：劣化在 **α=0.20 就饱和**，α 从 0.20 到 0.65 全程停在 6–7/46。
**不存在**同时满足 A（needle ≥0.75，需 α≳0.38）与 SHOULD-4（≤4/46）的 α
⇒ **"降 α 把 toolout 买回来"这条路被否证**；用户裁定执行的前沿扫描给出了一个**否定答案**，
而这正是它该给出的东西（比继续猜好）。
完整的五轴联合表见 `reports/alpha-frontier.json` 与 `scripts/alpha_frontier.py`。

**结论 2（★★ 我先前把证据说重了）**：SHOULD-4 在 n=46 下**原理上不可判**。
`scripts/judge_alpha_toolout.py` 实测：a050 vs m2calib 为 2/46 → 6/46，
Δ=+0.087，**单侧 Fisher p=0.120**，**Newcombe 95%CI = [−0.043, +0.210]（含 0）**；
而分辨 2/46→6/46 需 **161/组**（power 0.8，`secfm/eval/stats.py:required_n`），
CI 宽 0.25 ≫ 容差 0.05。按项目自己的三态教义（`secfm/eval/stats.py` 文档：
"差异不可区分时，判定应写**未达可区分**，而不是通过/不通过"），
**该轴的正确标签是 `undecidable`（仪器欠功效），而不是 FAIL**。
本文 §3/§8 原先据"FAIL"把 `soup-a050` 由"C 路成立"降为"C 路有条件成立"，
**该降级依据不足，应改回"C 路成立 + toolout 轴未达可区分（欠功效）"**，
并把该轴作为**待扩容的可判化任务**（见下）而不是已成立的失败。
点估计口径仍守约（0.087 > 0.05），故两种读法**都保留登记**，不藏。

**结论 3（仍然稳健、应当保留的那一条）**：**所有 α>0 档都比 m2calib 差 3–5 条**，
且 α 之间只差 1 条（**小于同一位看门狗独立测得的 ±2 条仪器噪声**）
⇒ 可以说"needle 修复的权重增量在 toolout 顺从轴上带来了一致的（但未达可区分的）偏移"，
**不可以**据此在 α 之间排序。看门狗另以三条独立判读口径复算，方向一致（Δ=+4 条上下）。

**结论 4（可判化任务）**：项目教义明确要求"**需扩容而不是反复重测**"。
故已并行启动 `data/heldout/v0.5-toolout-reg/`（同 schema 扩容套件，鲁棒性 ≥200 条起、
第一期目标可分辨 Δ≈0.087，完整目标 ~400/组可分辨 Δ=0.05）
与判分器加固（自报 `action` 双向短路问题的修法，见 `reports/m3-dpo-watchdog.md` §3.9）。
在该套件落地前，SHOULD-4 的读数**只能作方向性参考**。
"""
p.write_text(txt[:i] + NEW6 + txt[j + 1:], encoding="utf-8")
print(f"已替换 {p.relative_to(ROOT)} 的 §6（{len(NEW6)} 字符）")

# ---------- 2) S1 本体论裁决 ----------
ADJ = r"""# S1 载体本体论 — 父代理裁决与事实性更正登记

日期：2026-09-30 ｜ 依据：`docs/08-carrier-ontology.md`、`reports/carrier-ontology-report.md`
（子代理交付，`CARRIER-ONTOLOGY-CHECK=PASS errors=0`、`Ran 37 tests ... OK`）

## 1. 交付验收

| 交付物 | 状态 |
|---|---|
| `docs/08-carrier-ontology.md`（383 行，§1–§7） | **接受** |
| `data/ontology/carriers.json`（781 行，机器可校验本体） | **接受** |
| `scripts/check_carrier_ontology.py`（638 行） | **接受**（末行 `CARRIER-ONTOLOGY-CHECK=PASS errors=0`） |
| `tests/test_carrier_ontology.py`（362 行 / 37 tests） | **接受**（`Ran 37 tests in 60.162s` / `OK`） |
| `reports/carrier-ontology-report.md`（190 行） | **接受** |

关键设计（我认可并采纳为项目标准）：
- **J3 门禁效力下限 = 34**：鲁棒性分母 <34 的门禁**不得**写成可用（对声明值与现算值双向生效）。
  这条直接来自今天的教训（n=4 的子集被我当成 G1 的全部）——它把"欠功效门禁不得声称为门禁"
  变成了**机器强制**，而不是靠人记得。
- **J2 结论边界机器可读**：`claims.unseen_carrier_gate_carriers` 必须恰等于
  "训练 0 次 **且** 鲁棒性分母 ≥34"的集合 ⇒ **"我们能声称什么"由脚本现算，不能由人主张**。

## 2. 事实性更正（本体论交付中发现的、影响既有文档与我的报告）

| # | 位置 | 原表述 | 实测 | 处置 |
|---|---|---|---|---|
| **D1** | `reports/s0.4-g1-instrument-repair.md:13`、其引用链 | "70 条 / **17 机理**" | **15 种机理**（`reports/toolout-heldout-stats.json:adv.n_mechanisms=15`）；17 是 `axis=forward` 行数 | **已改**（2026-09-30） |
| **D2** | `docs/01 §10.2` | document "已注册·待入训（混料出现 0）" | 训练侧 **5,200 行**（含 `sec_sft_topup` 1,200 行，由 `configs/m3base-topup-e1.yaml:8` 绑定）⇒ **已入训** | **待批准修正**（本文即批准，见 §3 Q3） |
| **D3** | `docs/01 §10.2`、`§9.1` | image_metadata **26** / av_metadata **20** | **126 / 132**（鲁棒性 80 / 88）；26/20 是 122 条版本残影 | **待批准修正**（同上） |
| **D4** | 我的口径表述（多份报告） | "在训载体 ASR（v0.2.1 鲁棒性 64）" 被当作**载体级**仪器 | **v0.2.1 不是载体级仪器**：161 条中 **144 条无载体标签**，带标签仅 17 条（tool_output 8 / webpage 3 / email 3 / code 1 / text 1 / log 1）⇒ 任何"按载体读 v0.2.1"都在下界上做，最多 8 条 ≪ 底线 34 | **登记**：SHOULD-1 的措辞应改为"**在训语料整体** ASR"，不得表述为载体级；见 §4 |

## 3. 本体论提出的三项问题的裁决

**Q1｜是否为 document 建未见载体门禁集？→ 裁决：是，且优先级最高。**
理由：document 是**最裸露**的载体——训练侧 5,200 行、**0 条未见载体门禁、0 条在训载体回归**
（v0.2.1 = 0 条），只有 27 条"在分布"观测；而使命陈述**明确列出"文档"**。
现状等于"我们对文档载体做了大量训练，但对它能否泛化**没有任何仪器**"。
派发：新建 `data/heldout/v0.6-document/`（**留出机理**优先于留出载体：因 document 已入训，
"未见载体"不可得，唯有"未见机理/结构"才可声称泛化），并要求与训练语料零重叠断言。

**Q2｜是否把 image/av 元数据之一投入训练？→ 裁决：否（现阶段）。**
理由：image_metadata（126）与 av_metadata（132）是本项目**唯一两条有结论支撑的载体**
（训练 0 次 ⇒ 唯一成立的"未见载体泛化"证据）。把它们投入训练会**同时作废这两条断言**，
而当前**没有替代的未见载体仪器**。正确顺序是：**先为其它载体造出达标的未见载体/未见机理门禁，
再谈消费这两条**。本裁决与 docs/01 §11 规则 4（不得用 discarded/失效基线）同源。

**Q3｜`docs/01 §10.2`/`§9.1` 的 D2/D3 修正由谁批准？→ 裁决：本报告批准，我来改。**
（当时 `docs/01` 正被另一条工作流编辑，故本体论作者无权改动是对的处置。）

## 4. 需要连带修正的口径（承接 D4）

1. **SHOULD-1 改名**：由"在训载体 ASR"改为"**在训语料 ASR（v0.2.1 鲁棒性 64，非载体级）**"，
   并在裁定输出里带 `instrument_caveat` 字段，避免下游把 64 条当成载体级证据。
2. **`docs/01 §10.2` 的载体-门禁矩阵**应以 `docs/08` §4 的覆盖矩阵为准（机器可校验、现算）。

## 5. 本体论作者登记的三点不确定性 — 我的处置

1. "`lf_total` 里有多少真被训练过"：`carrier_sft_slice`(6,000) 与 `sec_sft_needlefix_carrier`(11,748)
   在 `configs/` 里找不到 `dataset:` 引用 ⇒ 标"训练绑定未验证"**是正确的**。
   我确认：`sec_sft_needlefix_carrier.jsonl` 是**为 R5 配方预备但尚未入训**（M3 走的是 DPO 路线），
   `carrier_sft_slice.jsonl` 同理未入训。该结论文本已按"未验证"登记，无需改。
2. document"已入训"缺 run→sha256 直接绑定：**接受该保留**；由 Q1 的新门禁集与未来的绑定产物补齐。
3. "训练行数是出现次数而非 token 占比"：**接受为已知限制**，已在本体论文档写 caveat。
   后续若要按载体做**配比**结论，需要 token 级口径 —— 列为 S2 待办。
"""
(R / "s1-ontology-adjudication.md").write_text(ADJ, encoding="utf-8")
print(f"写出 {(R / 's1-ontology-adjudication.md').relative_to(ROOT)}（{len(ADJ)} 字符）")
