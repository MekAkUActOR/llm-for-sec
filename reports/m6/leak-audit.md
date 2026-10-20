# M6 H6 泄漏审计（data/m6/ vs data/heldout/）

- 审计范围：训练侧 127579 行（t*/train+dev、pool/train+dev、dev-mirror）vs 冻结套件 1401 行（v0.2.3 / v0.3-gen / v0.4-toolout / v0.5-toolout-reg / v0.5-topup / v0.6-document / v0.6-dilution / v0.7-jailbreak）
- A 精确匹配：规范化文本 sha16 交集 = **0**
- B1 近似（含 system 模板，8-gram 覆盖率>30%）= 14 —— 全部为 v0.5-topup 的 policy-pack 系统提示模板共祖（pack 声明头部为渲染器脚手架，两侧语料共有），详见 B2
- B2 近似（剥离 system 模板，正文级 8-gram 覆盖率>30%）= **0**
- 乙醇纪律：data/heldout/ 全程只读（本审计为 task-6 治理用途），未复制任何内容进训练侧

## 结论

**PASS** — 零泄漏：正文级无任何精确或近似重合；B1 命中全部归因为共享渲染器模板（policy pack 声明头），非查询内容泄漏。

### B1 命中清单（模板共祖归因）

- B1 32.3% v0.5-topup-families/ptp-T15-006-tracked_change-atk-en-professional（模板头部重叠）
- B1 30.6% v0.5-topup-families/ptp-T15-012-form_placeholder-atk-en-professional（模板头部重叠）
- B1 34.7% v0.5-topup-families/ptp-T15-016-n_footnote-neg-en-conservative（模板头部重叠）
- B1 35.3% v0.5-topup-families/ptp-T15-018-n_formula-neg-en-professional（模板头部重叠）
- B1 34.1% v0.5-topup-families/ptp-T15-020-n_annotation-neg-en-conservative（模板头部重叠）
- B1 34.3% v0.5-topup-families/ptp-T15-200-link_tip-pola-en-conservative（模板头部重叠）
- B1 30.1% v0.5-topup-families/ptp-T15-201-link_tip-pola-en-default（模板头部重叠）
- B1 35.6% v0.5-topup-families/ptp-T15-202-link_tip-pola-en-professional（模板头部重叠）
- B1 31.1% v0.5-topup-families/ptp-T2-026-lru_evict-neg-en-conservative（模板头部重叠）
- B1 31.2% v0.5-topup-families/ptp-T2-028-dns_ttl-neg-en-professional（模板头部重叠）
- B1 30.7% v0.5-topup-families/ptp-T9-018-mfa_fatigue_approve-atk-en-conservative（模板头部重叠）
- B1 32.8% v0.5-topup-families/ptp-T9-020-b_ticket_closed-neg-en-default（模板头部重叠）
- B1 41.1% v0.5-topup-families/ptp-T9-022-b_invoice_paid-neg-en-conservative（模板头部重叠）
- B1 35.3% v0.5-topup-families/ptp-T9-024-h_invoice_promo-neg-en-professional（模板头部重叠）

### 方法与复现

- 命令：`.venv\Scripts\python.exe -X utf8 scripts\m6\audit_leak.py`
- 精确：norm_text（NFKC→小写→空白折叠）sha16；近似：whitespace 8-gram shingle，行覆盖率阈值 30%
- B2 剥离规则：heldout 侧行取 query 字段（无模板）；训练侧排除 input.system（policy pack 模板所在）

## 终态与复核链

- qa 复检证书：reports/m6/audit/leak-check-h6-final.json（overall=PASS：L1 train↔eval 精确/NFKC 0/0、L2 冻结套件 0、L3 红队 0、L5 实体 642/0、L4 披露层）
- 与 data/m6 终态（commit d5f65df）对齐：content-only 锁（qa L1 协议口径）后六任务 train↔heldout 与 dev↔heldout 内容重合 0；isolation 断言含 content_overlap_qa_l1=0

### Process 惯例（qa 建议，已采纳）

本轮"断言≠实测"两次的共性 = 断言视图与评测协议视图不一致（pool vs 任务视图、pack 锁 vs content 口径）。终态修复把评测方口径直接固化为数据方断言（isolation.content_overlap_qa_l1 与 t4_entity_overlap 即 qa L1/L5 协议的机器化）。"评测方口径进数据方断言"保留为 M6 后续轮次与 M7 的惯例。
