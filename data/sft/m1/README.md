# SFT M1（M2 全量组装首版）

由 `scripts/assemble_sft_m2.py` 生成（seed 固定，可复现）；
规格：docs/research/m2-data-assembly-plan.md（§9 实现摘要；
行配比以 §6 定稿为准）。**本目录不含 LF 注册**——`--register-lf`
显式触发后才写 data/lf/sft_m1.jsonl 并登记 `sec_sft_m1`。

## 组成

- 共 98339 条（转换 274129 → 去重后 204917 → 采样）
- zh:en = 35188:63151（36%:64%；目标 40:60）
- OR(误拒纪律):攻击 = 1.273（目标≈1.25:1）

| 行 | 采得 | 缺口 | 定标 |
|---|---|---|---|
| policy_pairs | 18564 | 24636 | 43200 |
| task_single | 12399 | 11601 | 24000 |
| injection_jailbreak | 10209 | 1291 | 11500 |
| multiturn | 5167 | 2533 | 7700 |
| general_recovery | 52000 | 0 | 52000 |

## 行定义（§6）
- policy_pairs：三包条件化政策行为（v0 政策对 + cvalues/pku
  攻击面三包拒绝 + trustllm 隐私意识三包）
- task_single：检测/审查任务（v0 注入/PII/校准 + trustllm 泄漏
  检测 + wgm 回复审查）
- injection_jailbreak：攻击识别与拒绝（adv/sr/mi/hb/wj/wgm/
  sp/trustllm/xstest-unsafe/or-toxic/beavertails/v0 注入）
- multiturn：多轮渐进（safemtdata 梯度 + hh 截断对话）
- general_recovery：良性恢复与误拒纪律（xstest/or-bench/exag/
  wgm-unharmful B 二包 + hh/sp/cvalues/pku 良性复用）

## 纪律
- 全部 assistant 以 VERDICT 行结尾（多轮仅末轮——§7）；
- 武器化响应永不入 assistant（neg/unsafe 侧整对进
 data/sft/dpo-reserve/，M3 偏好阶段用）；
- trustllm privacy_leakage 为反向设计：检测/分级不揭示，
 gt-* 不入任何训练文本；
- 工具输出载体族零生成（docs/06 §7 留出族）；
- 排除：reports/sft-exclusion-hashes.json（污染∪红线，内容
 哈希——生成器不接触评估路径）；
- 攻击意图池切分为规则版分类器（§1.14 降级方案）；实测与
 抽检见 reports/m2-pool-split-audit.json。

## VERDICT 词表扩展（v0.1 草案，校准跑定稿）
- 新增 verdict 值 `harmful-response`（wgm 回复审查任务：被审
  回复含应拦截的有害内容）与 `normal`（审查通过）。

## 自建扩容缺口（校准跑后回填）
自建扩容缺口（§6 列明、生成器尚未扩容）：政策配对 ~28K（A 扩容 10K+T4 场景 7K）、任务族 ~19K（T1/T3/T9 8K+T12 4K+B/C 扩容）、注入 ~3K（攻击词典 2.3K）、多轮 ~3.8K（走私构造 5K）——校准跑错误分析后按缺口回填
