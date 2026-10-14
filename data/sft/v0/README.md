# M2 SFT 自建数据 v0

生成管线 `scripts/gen_sft_v0.py`（seed=20260926，确定性可复算）。
**未注册 dataset_info**（M2 校准跑时注册）；**未接触任何评估集/探针集**（隔离断言见 tests/test_gen_sft_v0.py）。

## 构成

| 文件 | 条数 |
|---|---|
| policy_pairs.jsonl | 1644 |
| injection_pairs.jsonl | 500 |
| pii_synthetic.jsonl | 108 |
| calibration.jsonl | 72 |
| **合计** | **2324** |

## 分布

- 按包：{'conservative': 548, 'default': 1228, 'professional': 548}
- 按语言：{'zh': 1516, 'en': 808}
- 按 action：{'refuse': 1216, 'answer': 628, 'report': 480}

## VERDICT 词表 v0

T1: contains-injection/clean/suspicious-pattern；T4: allow/refuse/conditional/out-of-scope；T7: contains-pii/clean、high/medium/low-risk、sufficiently-masked/insufficient；T8: injection/jailbreak-pattern/normal；T9: phishing/benign/suspicious；T11: sufficient/insufficient-context。（T3/T6/T12 随调研回填）

## 红线审计

- 攻击内容仅模式级入输入侧；响应模板零武器化（professional 放行目标=裁决+授权框架+结构大纲，无操作载荷）；
- PII 全合成：身份证虚构区号 99xxxx（ISO 7064 校验位真实）、手机 160-165 虚拟段、SSN 900 无效系列、IBAN mod-97 校验位真实——合成性可审计（单测断言格式构造）；
- T7 无去保护方向样本（还原类拒绝教学在 policy_pairs 方向性案例中）；
- assistant 一律以 VERDICT 行结尾（判分器 v2 严格模板层可解析——闭环单测）。
