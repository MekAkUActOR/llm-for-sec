# heldout v0.2.1

v0.2 的**只增不改**增量版（byte-prefix 保证：三域文件均以 v0.2 对应文件
字节为前缀，单测断言）。

## 增量原因

v0.2 载体五类（email/webpage/log/text/code）未覆盖**工具返回值载体**——
InjecAgent 型"工具结果内嵌注入"结构（User Instruction / Tool Parameters /
工具返回携带指令）需 `tool_output` 载体映射（docs/research/m2-sft-sources.md
§2.13 协议兼容性评估的盲区结论；secfm.carriers.base 已扩展该类型）。

## 增量内容

- security +4（sec-t1~t4）、ai_safety +4（ais-t1~t4）：共 8 条
  tool_output 载体注入条目；153 → 161 条；
- 每域 2 capability（correct_verdict=contains-injection）
  + 2 robustness（must_refuse=True，前瞻条目——判分器 v2 report_finding
  计为防御成功）；
- 载荷族：裁决固定、证据排除/发现压制、跳过检查、任务劫持+提示词外传、
  PII 数据外传；工具族：calendar/mail_archive/log_search/file_scan/
  web_fetch/translate/search/crm_lookup；
- 攻击条目模式级（零武器化），条目由 build_context 生成（train/infer
  同路径），注入嵌于工具返回内容。

## 版本纪律

- v0.2 保持冻结不动；v0.2.1 为独立目录（版本化目录纪律）；
- 与 v0.2 的对比读数：161 条全集或 153 条子集均可（byte-prefix 保证
  逐字对齐，纵向可比）。
