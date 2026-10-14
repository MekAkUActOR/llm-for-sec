# M1 探针集 v0.1.1

来源隔离的固定文本样本，仅用于逐 checkpoint PPL 对比（docs/05 §7）。**永不入训练语料**。

## 与 v0.1 的差异（2026-09-25，去污版本化）

**唯一变更：ais 域 200 → 193 条**，剔除 7 条与 C1 训练语料
（`data/corpora/clean/c1_arxiv_full.jsonl`，cs.CR 全历史）重叠的
cs.AI×cs.CR 双列目摘要。其余四域（privacy/sec/general_en/general_zh）
与 v0.1 **字节相同**（直接复制）。

**原因**：v0.1 的 ais 探针抓取时，训练集排除正则
`arXiv:(\d{4}\.\d{4,5})` 在 c0_arxiv-cscr.jsonl 文本中从未匹配
（C0 文本不嵌 id）——排除形同虚设。cs.CR 全历史扩展入库后按规范化
标题匹配复核，发现 7 条双列目（探针=训练污染，PPL 虚低）。

**证据与清单**：`reports/probe-ais-overlap-arxiv-full.json`
（overlap_count=7，含 arXiv id 与标题）。

**剔除的 7 条**（arXiv id，均为 cs.AI 主列 + cs.CR 跨列）：

| arXiv id | 标题 |
|---|---|
| 2609.27452 | Issuer-Sovereign Agentic Payments |
| 2609.27311 | Multi-View Fusion for Encrypted C2 Detection: A Leakage-Controlled Measurement Study of Evaluation Pitfalls |
| 2609.27155 | The Like Trap: Multi-Stage Poisoning against Agents in Similarity-based Recommendation Systems |
| 2609.27124 | When Clients Are Orchestrated: Strategic Gradient Manipulation to Defeat Federated Learning Servers with Efficient Defense |
| 2609.26990 | Topological Signatures of Cyber-Attack Classes in Natural Visibility Graph Representations of Network Traffic |
| 2609.26900 | Ajar: Measuring Open Privilege in Agent Defenses |
| 2609.26860 | Comparative Evaluation of Static Embedding Models for HTTP Request Anomaly Detection |

v0.1 原目录保留不动（审计轨迹）。

## 域清单（v0.1.1）

- privacy: 173 docs
- ais: 193 docs
- general_en: 297 docs
- general_zh: 500 docs
- sec: 500 docs
