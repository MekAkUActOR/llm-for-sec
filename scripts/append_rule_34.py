# -*- coding: utf-8 -*-
"""把规则 34 追加到 docs/01-engineering-definition.md §11（§11.33）。

★Python 而非 PowerShell：docs/*.md 是无 BOM UTF-8，PS 5.1 会写坏（本会话已两次踩到）。
"""
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\docs\01-engineering-definition.md")

BLOCK = """
### 11.33 规则 34 — **指标的"可计算覆盖率"必须与数值同时报告**；覆盖率下降不得读成指标改善（2026-09-30 晚实证，M3 的 MUST-C）

**实证**：M3 的两个 MUST 门读同一批响应，**给出方向相反的结论**：

| 门 | 起点 soup-a050 | M3 m3-dpo | 表面结论 |
|---|---|---|---|
| MUST-B 契约保留率 | 70/168 | **20/168** | **FAIL**（崩塌） |
| MUST-C 误拒 ORR | 9/54 | **4/54** | **"PASS / 改善"** |

**但 MUST-C 的 PASS 是伪影**：其度量 `derived.over_refusal` 依赖**解析出响应的裁决内容**，
而 M3 恰恰**丢掉了裁决块** ⇒ 仪器失明：

| | soup-a050 | m3-dpo |
|---|---|---|
| 响应含可解析裁决 | **45/54 (83.3%)** | **12/54 (22.2%)** |
| 不可解析响应 | 9 | **42** |
| `over_refusal=True` | 9 (16.7%) | 4 (7.4%) |

**条件于可解析子集时结论反转**：soup-a050 **9/45 = 20.0%**，
m3-dpo **3/12 = 25.0%** ⇒ **M3 的过度拒绝率反而更高**。

**⇒ 同一模型的同一批响应，一个门说"崩了"，另一个门说"改善了"——
而后者只是因为门自己看不见了。**

**与既有三例的关系**（规则 32）：前三例是"门不动/不灵/无刻度"，
**本例是门给出方向相反的错误结论——最危险的一类**。

**要求**：
1. **任何门禁指标在报告数值时，必须同时报告"可计算覆盖率"**
   （成功解析/判读的条目数 ÷ 应判读条目数）。
2. **两臂覆盖率之差超过 10 个百分点 ⇒ 该比较判为 `undecidable`**，
   **不得**据其数值给出 PASS/FAIL。
3. **必须另报"条件于可计算子集"的对照**——覆盖率下降时，该读数常与表面结论相反。
4. **禁止**用"指标改善"表述一个伴随覆盖率下降的读数；正确表述是"**仪器可见性丧失**"。
5. **推论 34.1（门间依赖）**：任一门的**可计算性依赖另一个门所测的同一行为**时，
   **两门不得各自独立裁定**——必须先判定前者是否已使后者失明。
   （本例：MUST-B 测的裁决块，正是 MUST-C 赖以计算的前提 ⇒
   MUST-B 一不过，MUST-C 的读数即**自动失效**，不得再单独引用。）

**与规则 26/32 的关系**：规则 26 要求门要**活着**，规则 32 要求门要**有刻度**，
本规则要求门**在读数时看得见**。**三者齐备，门才可采信。**
"""


def main() -> int:
    txt = P.read_text(encoding="utf-8")
    if "### 11.33 规则 34" in txt:
        print("已存在 §11.33，跳过（幂等）")
        return 0
    if not txt.endswith("\n"):
        txt += "\n"
    before = len(txt.splitlines())
    P.write_text(txt + BLOCK, encoding="utf-8")

    back = P.read_text(encoding="utf-8")
    after = len(back.splitlines())
    marks = [m for m in ("浠讳綍", "缈昏浆", "鐨勭粺", "鈽", "娴佺▼") if m in back]
    print(f"✅ 已追加 §11.33：{before} 行 → {after} 行（+{after-before}）")
    print(f"   双重编码特征串 = {marks if marks else '无'} ✓")
    for k in ("### 11.33 规则 34", "可计算覆盖率", "推论 34.1"):
        print(f"   {'✓' if k in back else '✗'} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
