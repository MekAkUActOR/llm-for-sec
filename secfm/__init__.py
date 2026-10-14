"""secfm —— 安全感知基座模型工具链。

M0 范围（docs/01 §7）：
- carriers  载体序列化 v0（email / webpage(DOM) / code / text）
- protocol  上下文协议 v0（构造/解析 + 注入防护转义）
- eval      评估骨架（双指标 Pareto、政策合规矩阵、ECE 校准）
- audit     底座审计工具（tokenizer fertility + 合成语料生成）

文档锚点：docs/00（问题定义）、docs/01（工程定义）、docs/02（M0 审计方案）。
"""

__version__ = "0.1.0"
