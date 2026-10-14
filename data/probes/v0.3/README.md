# 探针集 v0.3

来源隔离的固定文本样本（M1.5 知识注入观测）。**永不入训练语料**。

## 构成

| 域 | 条数 | 来源 |
|---|---|---|
| ais | 500 | v0.1.1 字节复制（ais 为 ais-500 已验证版；其余四域纵向可比） |
| aisafety | 144 | arXiv 同域互补类目（cs.CY/SE/PL/soc.SI），三层排除 vs 训练语料（详见 scripts/fetch_probes_v03.py 设计文档） |
| content | 263 | arXiv 同域互补类目（cs.CY/SE/PL/soc.SI），三层排除 vs 训练语料（详见 scripts/fetch_probes_v03.py 设计文档） |
| general_en | 297 | v0.1.1 字节复制（ais 为 ais-500 已验证版；其余四域纵向可比） |
| general_zh | 500 | v0.1.1 字节复制（ais 为 ais-500 已验证版；其余四域纵向可比） |
| malware | 78 | arXiv 同域互补类目（cs.CY/SE/PL/soc.SI），三层排除 vs 训练语料（详见 scripts/fetch_probes_v03.py 设计文档） |
| privacy | 173 | v0.1.1 字节复制（ais 为 ais-500 已验证版；其余四域纵向可比） |
| sec | 500 | v0.1.1 字节复制（ais 为 ais-500 已验证版；其余四域纵向可比） |

组装时间：2026-09-25 09:58
ais-500 验证态：{"data\\corpora\\clean\\c0_arxiv-cscr.jsonl": {"sha256": "655b7621e0eca363", "docs": 2000}, "data\\corpora\\clean\\c1_arxiv_full.jsonl": {"sha256": "9c1fddf3131f3d36", "docs": 50384}, "data\\corpora\\clean\\c2_aisafety_arxiv.jsonl": {"sha256": "86d5e4386bf116fd", "docs": 18880}, "data\\corpora\\clean\\c2_privacy_arxiv.jsonl": {"sha256": "18ed7c3d2b9ba1a0", "docs": 2680}}
