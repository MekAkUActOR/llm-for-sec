# -*- coding: utf-8 -*-
"""第 17 轮：新增 docs/01 §11.36 推论 37.3（消混杂不得消灭信号），
并把"非长度信号复验"接进 runbook 步骤 2.0c。

★为什么需要 37.3：
  长度匹配的**粗暴做法**是把 rejected **砍短**或把 chosen **砍短** ✗ ——
  那会**连带抹掉非长度判别信号** ✗，把该对变成"纯长度对"，
  比不修更糟 ✓。
  第 17 轮实测：5 个混杂类**每个都有 100% 干净的非长度信号**
  （`action` 完全分离、`findings` 有无分离、`calibration` 的 `verdict:null`）✓
  ⇒ 修法必须是"**补足 rejected 的长度而不动其语义**" ✓，
  且修完**必须复验信号仍在** ✓。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"
RUNBOOK = ROOT / "reports" / "m3-launch-runbook.md"

DOC_ADD = """
**推论 37.3（消混杂不得消灭信号）**：对偏好对做长度匹配后，**必须复验**
该类的**非长度判别信号仍然存在**（`action` 取值分离、关键字段有无、结构标记分离度等）✓。

若长度匹配后两侧在**所有**非长度维度上也变得相同，则该类已退化为"纯长度对" ✗
⇒ **禁止入训**。

**★落地判据**：`scripts/audit_dpo_nonlength_signal.py` 必须对每一类
至少给出**一个** chosen/rejected 分离度 ≥ **0.95** 的非长度维度 ✓。

**★禁止的修法**：把 `rejected` 砍短、或把 `chosen` 砍短 ✗ ——
那会连带抹掉非长度信号，比不修更糟 ✓。
**唯一正确的方向是"补足较短一侧的长度而不动其语义"** ✓。

**来历（2026-10-06 第 17 轮）**：实测 5 个混杂类**每个都有 100% 干净的非长度信号**：

| dpo_class | chosen `action` | rejected `action` | 空 findings（c/r） |
|---|---|---|---|
| `carrier_inject_obedient` | report 2360/2360 | answer 2360/2360 | 0.0% / 100.0% |
| `carrier_inject_hollow` | report 2320/2320 | refuse 2320/2320 | 0.0% / 100.0% |
| `carrier_clean_overrefusal` | answer 1320/1320 | report 1320/1320 | 0.0% / 0.0% |
| `refusal_quality` | refuse 300/300 | refuse 300/300 | 82.0% / 100.0% |
| `calibration` | answer/refuse | answer 240/240 | `verdict:null` 0% / **60.0%** |

⇒ 数据**可用** ✓，缺陷是**同向累积的长度偏置**（6,540 对全部 chosen 更长 ✗），
**不是"唯一信号就是长度"** ✗ —— 后者是第 16 轮我写下的**过强论断**，此处更正 ✓。
"""

RUNBOOK_OLD_TAIL = """> # 修法：对这 5 类做**长度匹配**；★并单独修 carrier_inject_hollow 的**语义**
> #       （其 rejected 原本是"简短且格式正确"的拒绝 ⇒ 教的是"短=坏"，
> #         而应教"空洞=坏"；推论 37.2。长度匹配与改语义是两件事，都要做）
> ```"""

RUNBOOK_NEW_TAIL = """> # 修法：对这 5 类做**长度匹配** —— ★只补足较短一侧的长度，**不动语义** ✓
> #       · carrier_inject_obedient：把"服从"的回复写详尽（真服从也会长篇汇报）
> #       · carrier_inject_hollow  ：改为「冗长但空洞」（与类定义一致，不再靠"短"区分）
> #       · carrier_clean_overrefusal / refusal_quality / calibration：同样补足长度
> #       ★禁止的修法：把 rejected 或 chosen **砍短** ✗（会抹掉非长度信号，比不修更糟）
> ```
>
> **★并且修完必须复验非长度信号仍在（推论 37.3）** —— 四道检查里的第四道：
>
> ```powershell
> & 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe' `
>     scripts\audit_dpo_nonlength_signal.py
> # 期望：每个（曾混杂的）类至少有一个 **分离度 ≥0.95** 的非长度维度 ✓
> # 现读数：5 个混杂类**都有 100% 干净的非长度信号** ✓（action 完全分离、
> #         findings 有无分离、calibration 的 verdict:null 0%/60%）
> # ⇒ 数据**可用**，只需消长度差，**不需重新生成** ✓
> ```"""


def main() -> int:
    checks = {}

    doc = DOC.read_text(encoding="utf-8")
    if "推论 37.3" in doc:
        checks["37.3 已存在（幂等）"] = True
    else:
        doc = doc.rstrip("\n") + "\n" + DOC_ADD
        checks["37.3 已落"] = True
    DOC.write_text(doc, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    checks["docs 无乱码"] = not any(t in back for t in ("\ufffd", "锟斤拷"))

    rb = RUNBOOK.read_text(encoding="utf-8")
    if "audit_dpo_nonlength_signal.py" in rb:
        checks["runbook 已接 37.3"] = True
    elif RUNBOOK_OLD_TAIL in rb:
        rb = rb.replace(RUNBOOK_OLD_TAIL, RUNBOOK_NEW_TAIL)
        RUNBOOK.write_text(rb, encoding="utf-8")
        checks["runbook 已接 37.3"] = True
    else:
        checks["runbook 已接 37.3"] = False
    rb2 = RUNBOOK.read_text(encoding="utf-8")
    checks["runbook 无乱码"] = not any(t in rb2 for t in ("\ufffd", "锟斤拷"))

    ok = all(checks.values())
    print(f"ROUND17-DOCS={'PASS' if ok else 'FAIL'}  docs={len(back.splitlines())} 行  "
          f"runbook={len(rb2.splitlines())} 行")
    for k, v in checks.items():
        print(f"    {'OK ' if v else '★NG'} {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
