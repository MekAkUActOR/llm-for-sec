# -*- coding: utf-8 -*-
"""把 2026-09-30 晚新学到的四条工程规则追加进 docs/01 §11（插入到 §12 之前）。

插入位置：`## 12. 未决问题` 之前。不重写任何既有内容。
"""
from pathlib import Path

p = Path("docs/01-engineering-definition.md")
txt = p.read_text(encoding="utf-8")
anchor = "## 12. 未决问题"
i = txt.find(anchor)
assert i > 0, "找不到 §12 锚点"
assert "### 11.20" not in txt, "已追加过，勿重复"

NEW = r"""### 11.20 规则 20 — **单向门禁必须用单侧检验；同批条目上的对照必须用配对检验**（2026-09-30 实证，两处 fail-open 的根因）

**病例 A（单向门禁用双尾 ⇒ 偏宽）**：本项目三处门禁把**单向**命题（"不得**显著劣于**起点"、
"不得**上升**超 X"）交给**双尾** Fisher 检验，p 约被翻倍 ⇒ **门禁偏宽（fail-open）**。实测：
- `scripts/topup_verdict.py` 的 MUST-A 另有一处**签名误用**（把 `(k, n)` 当 2×2 单元格传入）
  叠加双尾，使有效阈值比冻结口径宽 **1 次试验**：变体 `15/168` 在原实现下 p=0.0716（放过），
  正确单侧 p=0.0346（应判劣化）；而冻结口径 `reports/criterion_b_table.py` 推的正是 **max_k=14**。
- `secfm/eval/stats.py:axis_decision` 同样在单向门槛里用双尾，实测把 `soup-a020`/`soup-a065`
  由 `worse` 误降为 `undecidable`。

**病例 B（同批条目用非配对检验 ⇒ 欠功效）**：本项目行为门禁几乎都是**变体 vs 基线跑在同一批条目**
（α 网格 9 档**全部**在 `data/heldout/v0.4-toolout` 同一批 46 条上评测）⇒ 应作**配对**检验；
非配对 Fisher 丢掉配对信息，实测配对比非配对 p 小 **2.1–2.5 倍**。同一批数据下
`a020`/`a065`（不一致对 b=5, c=0）在配对 McNemar 下 **p=0.03125 ⇒ 已证劣化**，非配对则会误判"不可区分"。

**规则**：
1. 命题是单向的 ⇒ 用**单侧**检验（`secfm.eval.stats.fisher_p_greater`），"更差"组放**第一行**。
2. 两侧跑在**同一批条目**上 ⇒ 用**配对**检验（`mcnemar_p(b, c)` / `axis_decision(..., discordant=)`）。
   配对所需的逐条不一致对数由 `secfm.eval.scored.discordant_pairs()` 现算；
   **两侧条目 id 集合不一致时该函数返回 `None`（fail-closed），调用方必须退回非配对并标注口径。**
3. 报告必须带 `test` 字段（`fisher(one-sided)` / `mcnemar(paired,one-sided)`）与不一致对数，
   使读者能看出用的是哪种检验。
4. **四套判读口径在同一批样本上一致 ≠ 显著**：那是**稳健性**证据，**不提供独立统计功效**。
   不得据"多口径都同向"宣称"结论稳健/已证"。

**复算入口**：`scripts/verify_fisher_fix.py`、`scripts/verify_stats_axis_fix.py`。

### 11.21 规则 21 — 门禁仪器的**口径**必须与其判据一致；不同口径的读数**禁止混比**（2026-09-30 实证）

needle 探针（`scripts/probe_longctx.py`）自 M1 起**只有 raw（裸续写）口径**，而 needle 是
MUST-1/SHOULD-2 的仪器 ⇒ 与规则 1（"raw 口径读数不得作为放大依据"）冲突，且
`soup-a050` 之所以成为 M3 起点，其 needle 读数（52/64=0.812）正是 raw 口径。

**规则**：
1. 任何门禁仪器都必须支持**部署格式（chat）**，并与 `secfm/eval/promptfmt.py` 共用**同一渲染源**
   （政策包**动态加载** `scripts/gen_sft_v0.py::POLICY_SYSTEM`，取不到即抛错，**不得复制字面量**）。
2. 裁定器必须以**单一开关同时决定两侧读哪份文件**（本项目：`topup_verdict.py --needle-format {raw,chat}`
   ⇒ chat 读 `longctx-<tag>-chat.json`），并在报告自述口径与要求不符或缺文件时
   **fail-closed 进 blockers**（与规则 15 联动）。**从构造上杜绝混比**，而不是靠人记得。
3. 新增口径**不得**覆盖既有口径的产物（chat 报告名带 `-chat` 后缀），以保证历史读数可复现。

### 11.22 规则 22 — DPO 的组成感知观测量：`λ_level` 与 chosen 绝对水平；**其阈值不得由本次 run 反推**（2026-09-30 实证）

DPO 的失败模式里，`rewards/margins`、`acc`、`loss` **都是合成分、组成盲**：
- `margins = rewards/chosen − rewards/rejected` ⇒ **只要 rejected 持续下压，margins 就机械上升**；
- `loss ≥ log2·(1 − accuracy)`（本项目实测 **100/100 个 logging 点成立**，⇒ `accuracy` 是真实逐样本计数），
  故 `loss` 与"剩余项"都只是 margin 的函数 ⇒ **loss 一路下降不能区分"抬 chosen"与"压 rejected"**。
- `logps/*` **不可用**（整条回复的绝对 log 概率和，含长度依赖 + 每点随机 batch 平均不同；
  实测 step 200 的 `rewards/chosen=+4.02` 而同步 `logps/chosen` 比 step 5 低 84 nats，**符号相反**）。
  ⇒ **正确观测量是 `rewards/chosen` 与 `rewards/rejected`**（已逐样本减掉参考模型）。

**组成感知观测量**：`λ_level = C/(C+|R|)`（窗口均值版，C=chosen、R=rejected），
**必须与 C 并列报告**（λ 是 2 维量的 1 维投影，端点差分版会爆成 ±20 以上而不可用）。
建议触发式：`λ_level(W) ≤ Λ` **且** `C(W) ≤ 0`（缺一不可）。

**规则**：
1. **阈值 Λ 与窗口长度 k 不得由当次 run 的读数反推**——那是结果驱动调参。
   必须由**行为学锚定**：在另一条配方/种子上刻意过训 DPO，同时测 λ/C 与门禁，
   取"门禁开始失败"的 C 再留边距；或改用尺度无关的形状判据。
2. 预注册的早停规则可能**可行域为空**（本项目实例：acc≥0.97 只可能在饱和后达线，
   而"margins 同期翻倍"只可能在饱和前发生 ⇒ 两条件时间上互斥，76 个滑窗**0 个**同时满足）
   ⇒ **触发区与病症区不相交，该规则原理上抓不到目标病症**。预注册前应先检验
   "规则的可行域是否非空"。
3. acc/margins/chosen/rejected **都是训练对均值**，而"空心拒答"是**行为学命题**
   ⇒ 训练期标量只能做**早期预警**，**不能**做空心化判定；仲裁者只能是行为学门禁。

### 11.23 规则 23 — 判据修复的**方向必须可审计**：收紧可事后做，放宽须重走预注册

本晚共修 7 处判据统计缺陷（3 处单向门禁用双尾、1 处非配对丢配对、1 处阻断项不改决策、
1 处基线默认值为废弃产物、1 处口径混比无守卫）。**全部方向为收紧或增强功效**，
且**没有任何一处**发生在"看到被测对象的行为学结果之后"（当时 M3 的行为学读数尚不存在）
⇒ 不可能为结果服务。

**规则**：修判据时必须同时登记 **(a) 修复方向**（收紧 / 放宽 / 仅增强功效）、
**(b) 相对被测对象行为学读数的时间顺序**、**(c) 验证方式**（哪条命令、哪个数字）。
**放宽方向或"修改阈值"的修复一律不得事后进行**，必须回到预注册流程。
本表见 `reports/s0-measurement-layer-status.md` §8。

"""
p.write_text(txt[:i] + NEW + txt[i:], encoding="utf-8")
print(f"已插入 §11.20–§11.23（{len(NEW)} 字符）到 {p}")
new = p.read_text(encoding="utf-8")
print(f"新行数 = {len(new.splitlines())}（原 {len(txt.splitlines())}）")
