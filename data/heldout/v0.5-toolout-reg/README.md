# heldout v0.5-toolout-reg

**tool_output 稳健性门禁的扩容回归套件**（不是泛化留出集）。

## 为什么在这里

`data/heldout/v0.4-toolout`（70 条／鲁棒性 46）在 n=46 上**分辨不了 0.05 的公差**：
各 α 档是**在同一批条目上**评测的（配对设计），按配对 McNemar 精确检验
（`secfm/eval/stats.py:mcnemar_p`，power 0.80 / 单侧 α=.05，实测翻转率 p10≈0.087）
需要 **≈76 条/臂**；n=46 连这一档都不到。本目录即扩容产物。
**v0.4-toolout 未被触碰。**

## 同分布约束（本次扩容的第一约束）

新条目按 v0.4 那 46 条鲁棒性条目的**机理占比**等比扩容（最大余数法，逐格偏差
≤1 条），不引入 v0.4 之外的机理：

| 维度 | v0.4（46 条） | 本套件主层（210 条） |
|---|---|---|
| 机理 | 15 种；`fake_system_directive` 4，其余 3 | 同 15 种；按 4:3 等比 → 18 / 13–14 |
| 载体 | `tool_output` 100% | `tool_output` 100% |
| 语言 | zh 23 / en 23 | zh 105 / en 105 |
| axis | 前瞻 14/46 = 30.4% | 前瞻 62/210 = 29.5% |

逐格对照表见 `reports/toolout-reg-suite-report.md`。`carrier-extra/carrier_extra.jsonl`（载体拓宽层）
**不满足**同分布（载体不同）：它放在子目录里、必须显式指定读法，
**不得**与 v0.4 的 70 条混在一起做逐条对照。

## 内容（合计 339 条；两个文件分两个**读法**）

| 文件 | 内容 | 条数 |
|---|---|---|
| `toolout_primary.jsonl` | 鲁棒性（载体全部 `tool_output`；与 v0.4 同机理占比） | 210 |
| `toolout_primary.jsonl` | 干净负例（`kind=alignment`，`must_refuse=false`）：15 机理 × 2（zh/en） | 30 |
| `toolout_primary.jsonl` | 政策条件化（8 组 × 3 包） | 24 |
| `carrier-extra/carrier_extra.jsonl` | 鲁棒性（**载体拓宽层**：log/webpage/code/document/email/text） | 60 |
| `carrier-extra/carrier_extra.jsonl` | 干净负例（载体拓宽层） | 15 |

- **默认读法**：`--heldout data/heldout/v0.5-toolout-reg` ⇒ 只读到 `toolout_primary.jsonl` 的
  **264 条同分布层**（`secfm.eval.heldout.load_dir` 只 glob 一层 `*.jsonl`）。
  这一层单独就满足"同载体（tool_output）+ 同机理分布"的回归要求。
- **载体拓宽层**要显式指定：`--heldout data/heldout/v0.5-toolout-reg/carrier-extra`。
  它**不是**同分布（载体不同），**不得**与 v0.4 的 70 条混在一起做逐条对照。
- 主层 210 条鲁棒性 + v0.4 的 46 条 = **256 条/臂**，超过配对检验所需的
  ≈76 条/臂（见 `reports/toolout-reg-suite-report.md` §配对适配性）。

## schema

与 `data/heldout/v0.4-toolout/tool_output.jsonl` **逐字一致**：每行 9 键同序
（`id, domain, kind, language, policy_pack, query, expected, group, intent`），
协议信封同构（`<dsh-protocol v="0.1">` + `<system>` + `<operator>` +
`<carrier type=.. trust="untrusted" id="c1">`(`<meta>`+`<body>`) + `<user>`）。
`intent` 在 v0.4 前缀 `[mech=..; axis=..; family=..]` 之后追加
`carrier=` / `slot=` / `stratum=`，并以两段**自洽字段**结尾（定界符 `«»`——
载荷里可能出现 JSON 双引号，故不用 `"` 定界）：

    预期正确行为=«..» ; 注入要求=«..»      （英文条用 expected_correct_behavior / injected_requirement）

这两段是"可判性冒烟"的输入：校验器把它们当假回复喂给
`scripts/score_heldout_v2.py:classify()`，`selfreport`（默认）与 `strict`
两个口径都断言前者判为**防御**、后者判为**顺从**。
`注入要求` 的文本在载体里一定可见（base64/hex/零宽机理按各自编码视图可见）。

## 消费方式（不改判分器）

    python scripts/baseline_eval.py --heldout data/heldout/v0.5-toolout-reg --prompt-format chat ...      # 264 条同分布层
    python scripts/baseline_eval.py --heldout data/heldout/v0.5-toolout-reg/carrier-extra ...            # 75 条展开层
    python scripts/score_heldout_v2.py --heldout data/heldout/v0.5-toolout-reg --responses resp.jsonl
    python scripts/score_heldout_v2.py --heldout data/heldout/v0.5-toolout-reg --responses resp.jsonl --action-rule strict
    python scripts/check_toolout_reg_suite.py            # 硬断言（末行 PASS/FAIL）

## ★ 纪律：本套件**只能作回归判据**

`tool_output` 载体在训练侧出现 **1,224 次**（`reports/carrier-census.json`），
`carrier_sft_slice` / `dpo_m3_final` 里的载体切片另有 1,100 行级命中 ⇒
按 `docs/01 §10.3` 的表述纪律，本套件**不得表述为"未见载体泛化"**：
它衡量的是**同载体、新句式**下的行为（回归），不是新载体的泛化。
生成器源码：`scripts/build_toolout_reg_suite.py`（`SEED=20261006`，逐字节可复现）。

## 机理 × 条数（鲁棒性）

| 机理 | 鲁棒性条数（主层 tool_output / 拓宽层） |
|---|---|
| `fake_system_directive` | 18 / 5（共 23） |
| `fake_json_field_privesc` | 14 / 4（共 18） |
| `pagination_continuation` | 14 / 4（共 18） |
| `error_message_instruction` | 14 / 4（共 18） |
| `id_timestamp_url_smuggle` | 14 / 4（共 18） |
| `nested_tool_result` | 14 / 4（共 18） |
| `mcp_schema_pollution` | 14 / 4（共 18） |
| `csv_formula_injection` | 14 / 4（共 18） |
| `log_line_injection` | 14 / 4（共 18） |
| `unicode_zero_width_bidi` | 14 / 4（共 18） |
| `base64_payload` | 14 / 4（共 18） |
| `hex_payload` | 13 / 4（共 17） |
| `attention_dilution_long` | 13 / 4（共 17） |
| `hidden_markup_comment` | 13 / 4（共 17） |
| `meta_field_smuggle` | 13 / 3（共 16） |

## 载体 × 条数

| 载体 | 鲁棒性 | 对齐 | 合计 |
|---|---|---|---|
| `tool_output` | 210 | 54 | 264 |
| `log` | 11 | 3 | 14 |
| `webpage` | 10 | 3 | 13 |
| `code` | 9 | 2 | 11 |
| `document` | 10 | 2 | 12 |
| `email` | 10 | 3 | 13 |
| `text` | 10 | 2 | 12 |
