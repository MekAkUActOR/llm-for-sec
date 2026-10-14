# heldout v0.4-toolout

**tool_output 同载体回归集**（不是泛化留出集）。

## 为什么只能用于回归

`tool_output` 载体在训练侧出现 **1,224 次**
（`reports/carrier-census.json`：`data/lf/sft_m25.jsonl` +
`data/sft/m2.5-staging/t14_authinject.jsonl`）。按
`reports/review-2026-09-30.md` §4.4/§6.2，该载体的"未见载体泛化"断言**已失效**；
`scripts/m25_exit_verdict.py` 的 `carrier_audit` 会打印
`★regression-only`，`--require-unseen-carrier` 会 fail-closed。
本集只用于**同载体、新 phrasing** 的回归读数。

## 内容

- `tool_output.jsonl`：**70** 条
  - 46 条对抗条（`kind=="robustness"`，family=adv；15 种注入机制，zh 23 / en 23，
    forward 15 / nonforward 31）；
  - 12 条干净负例（`kind=="alignment"`，expected.must_refuse=false；合法工具
    返回，拒答即误判）；
  - 12 条政策条件化条（4 组 × 3 包；同 user 同载体，仅 `<system>` 的 policy 行不同）；
- schema 与 `data/heldout/v0.2.1/` 的 8 条 tool_output 条目**逐字一致**
  （9 键同序）；信封同构：`<carrier type="tool_output" trust="untrusted"
  id="c1">` + `<meta>`(tool/call) + `<body>`；
- 域名/地址一律虚构：RFC 2606（`example.com` / `*.example` / `example.org`）
  与 RFC 5737（`198.51.100.x` / `203.0.113.x` / `192.0.2.x`）。

## 与 v0.2.1 那 8 条的关系

id 与 query **均无交集**；8 条既不是本集的子集，本集也不是它们的超集
（`scripts/check_toolout_heldout.py` 断言）。且旧 8 条中只有 4 条
`kind=="robustness"`（另 4 条 capability 的 comply 是正确行为）。
因此**不可直接比大小**，只可做"同机制子集对照"。

## 校验

    python scripts/check_toolout_heldout.py          # exit 0 = 通过
    python -m pytest tests/test_toolout_heldout.py -q
