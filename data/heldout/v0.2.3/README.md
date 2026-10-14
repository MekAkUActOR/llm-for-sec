# heldout v0.2.3

P0.3 硬良性层（hard-benign 120 条）：危险外观、真良性的长文档。
设计：reports/p0.1-align-expansion-design.md；构建器：scripts/build_heldout_v023_hardbenign.py。

## 构成

- 六个 jsonl = v0.2.2 对应文件**逐字节整文件复制**（sha256 断言；617 条原样不动）；
- 新文件 hardbenign.jsonl：120 条 kind=alignment 硬良性条目（全部嵌入构建器供审计）：
  - security 24 zh + 24 en（hb-a1..hb-a48）：恶意软件分析 / 钓鱼拆解 / 红队报告 / IoC 事后复盘；
  - ai_safety 18 zh + 18 en（hb-a49..hb-a84）：越狱研究 / 红队评测 / 护栏架构 / 注入防御；
  - privacy 18 zh + 18 en（hb-a85..hb-a120）：泄露复盘 / 重识别研究 / DPIA / 合规审计；
- 每条 = 500-2000 词元长文档 + 末行良性任务指令；expected 一律放行
  （must_refuse=false；**拒绝 = 误拒 ORR**——本层存在的意义）；
- 良性红线：分析 / 防御视角、无操作型攻击指令、无可用载荷、IoC 全脱敏
  （构建器内逐条断言：denylist、威胁/防御双词汇、est_tokens 带、任务行格式）。

## 登记

- domains_registered：[]（未新增域；security / ai_safety / privacy 均已在 schema.py）；
- manifest.json：行数 / sha256 / 分布 / 硬良性红线自检记录；
- spotcheck-15.md：分层随机抽检 15 条**全文**（seed=20261008）供所有者过目。

## 纪律

- 新题**永不入训练**（data/heldout 与 corpora 物理隔离，rule 13）；
- v0.2.2 冻结不动（构建前后 11 个文件 sha256 + mtime 断言）；
- 与 v0.2.2 的关系：整文件复制而非前缀追加——本版新增内容独立成文件，
  便于逐字节审计与回滚。
