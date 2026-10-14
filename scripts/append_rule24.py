# -*- coding: utf-8 -*-
"""追加 §11.24 = 规则 24（"未见载体"必须按被评产物索引），并在 §10.3 加口径要求。"""
from pathlib import Path

p = Path("docs/01-engineering-definition.md")
t = p.read_text(encoding="utf-8")
assert "### 11.24" not in t, "已追加过"

RULE = r"""### 11.24 规则 24 — "未见载体"必须**按被评产物索引**；全局暴露数字会误导（2026-09-30 晚实证）

**病例（本晚发现，代价是一次差点发错的门禁）**：载体本体论一度记"document 已入训（5,200 行）"，
据此推断 document 门禁只能声称"未见机理"。字节级普查推翻了它，并暴露**更根本的建模错误**：
"载体暴露"被当成了**全局量**，而它实际是**按产物不同**的：

| 训练文件 | 状态 | document 条数 |
|---|---|---|
| `sft_m25.jsonl`（m25-full） | 活 | **0** |
| `sec_sft_needlefix.jsonl`（`soup-a050` 的一半） | 活 | **0** |
| **`dpo_m3_final.jsonl`（M3 DPO）** | **活** | **1,000** |
| `sec_sft_topup.jsonl`（C 路 top-up） | **权重已废弃** | 1,200 |

⇒ 同一个载体，对 `soup-a050` 是**完全未见**（可支撑未见载体泛化），对 M3 是**正在训练**
（只能支撑未见机理）。**"未见载体"这句话不指明被评产物就没有意义。**

**规则**：
1. 任何"未见载体 X"的表述**必须绑定一个被评产物**，并给出该产物**所见**该载体的条数与来源文件。
2. 载体的"已训/未见"状态**不得**由全局统计或备料目录推断：
   - 备料目录（如 `data/sft/m2.5-staging/`）**不等于**已训数据——本晚实测 10/14 族 100% 已在终混，
     而 `doc_structure` 等 3 族 0% 在终混（`reports/staging-manifest-reconciliation.md` §6）；
   - **废弃分支的数据不算暴露**：C 路 top-up 的权重已登记 `discarded`，
     其数据对任何活产物**不构成暴露**（但须在文档里显著登记，以免再次被误当已训）。
3. **门禁集的载体构成必须与训练暴露交叉校验**（发射前必跑）：本晚已落
   `scripts/check_m3_gate_leak.py`——它对 M3 给出
   "v0.3-gen 258 条 = av_metadata 132 + image_metadata 126，与 `dpo_m3_final.jsonl` 重叠 **0**，
   且 DPO 数据**不含** image/av metadata" ⇒ MUST-A 的未见载体 claim **未被污染**。
   **这类交叉校验必须在每次门禁发射前跑，并把结果贴进裁定报告。**
4. **JSONL 里的载体信封引号被转义**（实际形态 `<carrier type=\"X\" ...>`）。
   按裸 `<carrier>` 或未转义 `type="` 匹配都会得 0 —— 本晚因此在两个脚本上连续误判。
   **体检口径：`<carrier type=\"` 在 `sft_m25.jsonl` 的出现次数应 = 13,981**
   （与 docs/01 §10.2 登记的信封总数逐位吻合），**不一致就说明匹配写错了**。

"""
anchor = "## 12. 未决问题"
i = t.find(anchor)
assert i > 0
t = t[:i] + RULE + t[i:]

NOTE = r"""
> **★口径要求（2026-09-30 晚，规则 24）**：本节的"留出载体"必须**按被评产物**说明。
> 例：`image_metadata`/`av_metadata` 对**本项目全部活产物**（含 M3）都是 0 次暴露
> （`dpo_m3_final.jsonl` 载体分布里不含二者）⇒ 可支撑未见载体泛化；
> 而 `document` 对 `soup-a050` 是 0 次、对 M3 是 **1,000 次** ⇒ 对 M3 只能声称未见**机理**。
> 交叉校验脚本：`scripts/check_m3_gate_leak.py`、`scripts/census_carriers_authoritative.py`。
"""
a2 = "### 10.3 轮换规则（硬规则）"
assert a2 in t
t = t.replace(a2, NOTE.strip() + "\n\n" + a2, 1)
p.write_text(t, encoding="utf-8")
print(f"✅ 已追加 §11.24（规则 24）并在 §10.3 前加入口径要求")
print(f"   行数 = {len(t.splitlines())}")
