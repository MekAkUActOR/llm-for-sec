# M3 后评测链：新代码的产物命名预检（2026-09-30 晚，父代理）

**目的**：本轮改了 `scripts/topup_verdict.py`（新增 `contract_rate` / `contract_items` /
`orr_items` / `paired_diff`）与 `secfm/eval/stats.py`（端点重排）。链的第 7 步会调用该脚本，
若命名不吻合，M3 的裁定会**静默退化成 PENDING**（而 PENDING 看起来像 "没测到"，不像 bug）。
故在训练完成前逐条核对。

**链的实际参数**（`scripts/eval_m3_post.ps1`）：`$Tag='m3-dpo'`、`$Baseline='soup-a050'`；
第 7 步 = `topup_verdict.py --variant m3-dpo --baseline soup-a050 --family-base m15 --needle-format chat`。

| 我的新代码读取 | 生产者 | 实测命名 | 结论 |
|---|---|---|---|
| `resp-chat-gen-<tag>.jsonl` | `eval_needlefix.ps1` L47 `--dump-responses` | `resp-chat-gen-$Tag.jsonl` | ✅ 逐字一致 |
| `scored-chat-gen-<tag>-v2.json` | `eval_needlefix.ps1` L53 `--out` | `scored-chat-gen-$Tag-v2.json` | ✅ 逐字一致 |
| `scored-chat-<tag>-v2.json`（ORR，v0.2.1） | `eval_needlefix.ps1` L82 | `scored-chat-$Tag-v2.json` | ✅ |
| `longctx-<tag>-chat.json` | `eval_needlefix.ps1` L60 `$nfName` | L59 注释明写"chat ⇒ `longctx-<Tag>-chat.json`（与 `topup_verdict --needle-format chat` 一致）" | ✅ |

⇒ 四条产物族在 `$Tag='m3-dpo'` 下分别成为
`resp-chat-gen-m3-dpo.jsonl` / `scored-chat-gen-m3-dpo-v2.json` / `scored-chat-m3-dpo-v2.json` /
`longctx-m3-dpo-chat.json`，**全部落在新代码的读取路径上** ✅。

**基线条**：`soup-a050` 的前两条**已存在**（实测 `contract_rate('soup-a050')=70/168`、
`orr_items('soup-a050')` → 9/54 ✓）；`longctx-soup-a050-chat.json` 由链的**第 0 步**产出
（`eval_m3_post.ps1` L44-61，`-DecisiveOnly`，约 4 min）⇒ 基线侧齐备 ✅。

**预期后果（可证伪的预测，留给下一轮核对）**：
在此之前 `soup-a050` 的裁定一直停在
`PENDING 阻断项=['缺 needle 报告（m2calib/soup-a050，口径=chat）']`。
第 0 步落地后，**M3 的裁定应不再因"缺 needle 报告"而 PENDING**；
若它仍报该阻断项，则说明第 0 步失败或命名有第三种约定 —— **那是需要立刻查的 bug，不是"未测"**。

**未做**：未实测整条链（GPU 被 M3 占用，链的第 1 步起即 `exit 2`），
故本预检只覆盖**命名与调用参数**，不覆盖运行时行为。
