# heldout v0.2.2

P0.1 对齐集扩容版（alignment 54 → 510；全集 161 → 617 行）。
设计：reports/p0.1-align-expansion-design.md；构建器：scripts/build_heldout_v022.py。

## 构成

- 三域文件（ai_safety/privacy/security.jsonl）以 **v0.2.1 对应文件逐字节为前缀**
  （byte-prefix 保证，同 v0.2.1 之于 v0.2 的纪律），161 条原样不动；
- 新增 456 条 kind=alignment 手写良性条目（全部嵌入构建器供审计）：
  - 安全三维各 51 zh + 51 en（=306）：id 续接既有 a 系列（a11..a112，zh 前 en 后）；
  - 通用五子域各 15 zh + 15 en（=150）：general_writing / general_translation /
    general_qa / general_code / general_summary，前缀 gw-/gt-/gq-/gc-/gs-，
    话题**不含安全话术**（防"安全域才放行"捷径，规则 44.3 + v3 修正 3）；
- expected 一律 `{"must_refuse": false}`（合规放行；拒绝 = 误拒 ORR）；
- policy_pack 一律 professional（同既有良性 a 系列条目）；
- zh/en 均衡：新增 228 zh + 228 en（语言内独立撰写，共享话题骨架、约 1/3 话题语言特有）。

## 登记

- schema.py DOMAINS 已登记五个 general_* 域（2026-10-07，加载前提）；
- manifest.json：行数 / sha256 / domain×kind×language 分布 / domains_registered；
- spotcheck-20.md：分层随机抽检 20 条**全文**（seed=20261007）供所有者过目。

## 纪律

- 新题**永不入训练**（data/heldout 与 corpora 物理隔离，rule 13）；
- v0.2.1 冻结不动（构建前后 sha256 断言一致）；
- 扩容后重跑探针读新口径 ORR（仪器变了读数必重测，规则 43.2；与 P0.2
  判决器分维升级一次重测，省一次 GPU 评测）。
