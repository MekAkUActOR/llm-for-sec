# 自建数据 v0x（回填批）

上游 v0 契约（POLICY_SYSTEM/VERDICT 闭环/载体协议）。生成器：`scripts/gen_sft_v0x.py`（seed=20260928 确定性）。

| 语料 | 行 | 内容 |
|---|---|---|
| policy_expansion.jsonl | 5016 |
| t4_grounding.jsonl | 1236 |
| attack_dict.jsonl | 1860 |
| t1_injection.jsonl | 375 |
| t3_risk.jsonl | 1400 |
| t9_phish.jsonl | 50 |
| t12_policyqa.jsonl | 804 |
| t6_code.jsonl | 954 |
| pii_expansion.jsonl | 216 |
| smuggle_multiturn.jsonl | 387 |
| **合计** | **12298** |

## VERDICT 词表 v0.1 扩展（首填，校准跑定稿）

- T3 风险等级：critical / high（KEV 实测分布；medium/low 随非 KEV 情报源回填）
- T12 接地：grounded（未接地查询的 ungrounded 负例随校准回填）
- T4 法条：allow / conditional / refuse / out-of-scope

## 纪律

- 类目体系（31 L2）仅作话题种子，外部查询文本零复制；
- KEV/GTFOBins/LOLBAS/法规条文为公开防御性内容，输出仅检测/评估/引用侧；
- PII 全合成（虚构区号/虚拟段/无效系列）；
- 多轮走私：升级轮拒绝即止，末轮 VERDICT；此前轮良性应答；
- zh:en 全批约 3:1（全局配比拉回设计）。
