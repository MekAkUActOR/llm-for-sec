# heldout v0.6-dilution —— P0.6 稀释鲁棒性仪器的载荷池

**本目录是 P0.6 仪器的载荷池（组件），不是 `baseline_eval.py --heldout` 行为套件**
（`secfm.eval.heldout.load_dir` 不适用于本目录）；**唯一消费者是
`scripts/probe_dilution.py`**。

## 内容

- `risk_payloads.jsonl`：**96 条**风险载荷（2 lang × 3 frag × 8 机理 × 2 变体），
  行 schema（键序逐字固定）：`id / lang / frag / family / mechanism / variant / text`；
- `manifest.json`：机器可读 manifest（sha256 / 分维计数 / 机理→在训三族 mapping /
  grid 定义 / schema 契约）；
- `audit/`：`check_dilution_suite.py` 的验收结果快照（A1–A10）。

## 设计边界（摘要）

- 8 个机理全部映射**在训三族**（`gen_sft_v0.PAYLOADS`：ai_directive / policy_claim /
  hidden_text）——稀释轴单变量，不含 v0.3-gen / v0.6-document 的未见机理；
- 载荷 = 面向 AI 的注入指令（模式级、零武器化），句式全新仿写；与训练混料
  （`data/sft/**`、`data/lf/**`）及全部既有 heldout 的 8-gram 独立性由
  `scripts/check_dilution_suite.py`（A5）硬断言保证；
- 每条载荷的注入要求在某种视图下可读（m8 按编码/零宽视图）；
- S/M/L 片段 token 带宽：[24,40] / [112,144] / [480,544]（部署 tokenizer 实测）。

## 冻结与隔离

- **冻结 = 内容哈希**：`manifest.json` 的 sha256 登记后，任何修改 ⇒ 新开版本目录
  （如 `v0.6b-dilution`）并保留旧 manifest，**不得原地改**；
- **永不入训练**：载荷池、干草堆源（`data/probes/v0.1`）、生成的报告文件，
  一律只进评估管线；与 `data/corpora`、`data/lf` 物理分离；
- train-disjoint 不靠注释靠断言：`scripts/check_dilution_suite.py`（A5/A8）与
  `scripts/check_m25_staging.py`（HELDOUT_DIRS 已含本目录）。

设计文档：`reports/p0.6-dilution-instrument-design.md`；构建报告：
`reports/p0.6-dilution-build.md`。
