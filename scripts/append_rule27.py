# -*- coding: utf-8 -*-
"""追加规则 27 到 docs/01。"""
from pathlib import Path

p = Path("docs/01-engineering-definition.md")
t = p.read_text(encoding="utf-8")
assert "规则 27" not in t, "已追加过"

BLOCK = """
### 11.27 规则 27 — 方向相关的统计代码必须**按方向自证**：端点要重排，`b` 要放在"更差"一侧（2026-09-30 晚实证，两处方向 bug）

**背景**：为补齐 objective ① 的"verdict 输出 n/CI/p"，把 MUST-B/C 接到
`secfm/eval/stats.py::axis_decision` 上。接入过程**连续暴露两个方向相关的 bug**，
其中一个存在于库里、另一个是我接线时犯的。

**实证一（库内，潜在 fail-open）**：`axis_decision` 原为
`lo_s, hi_s = sign * lo, sign * hi`（只翻符号、**不重排端点**）。
`direction="higher_is_better"` ⇒ `sign = -1` ⇒ 必然 `lo_s > hi_s`，**区间端点反序**。
配对路径更严重：`width = hi_p - lo_p` 变成**负数** ⇒
`resolution_ok = width <= tolerance` **假为 True** ⇒ 又一个 fail-open。
**为何长期未暴露**：此前所有调用都用默认的 `lower_is_better`（`sign=+1`）。
**是"契约保留率（越高越好）"这个 FIRST 的 `higher_is_better` 用法首次触发。**

**实证二（我接线时犯错）**：`paired_diff()` 返回的 `n01 = 基线 0 → 变体 1`。
在"越低越好"的轴上它是"更差"；在"越高越好"的轴上它是"**更好**"。
我按固定顺序把 `(n01, n10)` 传给 `discordant` ⇒ 方向传反 ⇒
p 由正确的 **0.0407** 变成 **0.978**（保守 24 倍）。
`axis_decision` 的契约是 `discordant=(b, c)` 其中 **`b` 必须是"更差"那一边**。

**本规则（三条，可机械检验）**：

1. **符号变换后必须重排端点**：`if lo > hi: lo, hi = hi, lo`。
   任何"翻转差值符号"的统计输出（`axis_decision` 一类）都属此列；
   **反序的区间是 fail-open**，因为它会让"宽度"变成负数而通过一切"宽度足够小"的检查。
2. **配对检验的 `b` 必须放在"更差"一侧，而"更差"由判据的 `direction` 决定**。
   同一个 `paired_diff` 的字段在相反方向的轴上**含义相反**，因此
   **`discordant` 的构造必须显式依赖 `direction`**，不得按固定顺序传。
3. **每个方向都必须有测试**。只测默认方向等于只测一条路径。
   *检验*：`tests/test_stats_direction.py` 断言
   （a）`higher_is_better` 下 CI 端点正序且 `width > 0`；
   （b）同一对 (b,c) 在两种方向下给出的 p **互补**（一侧显著则另一侧不显著）；
   （c）配对路径的 `resolution_ok` 在端点反序被修好后不再假为 True。

**与规则 20/25/26 的关系**：规则 20 要求"同批条目必须配对"，规则 25 要求"名称与测量对象一致"，
规则 26 要求"每个 MUST 门有会失败的证据"，本规则补上**"方向"这一维**——
配对做对了、名字起对了、门也活着，**方向传反仍然会把结论翻过来**。
"""

p.write_text(t.rstrip() + "\n" + BLOCK, encoding="utf-8")
print(f"✅ 已追加；行数 = {len(p.read_text(encoding='utf-8').splitlines())}")
