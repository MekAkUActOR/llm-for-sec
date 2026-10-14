# -*- coding: utf-8 -*-
"""校验 runbook 插入段无乱码且关键字符串齐全（用 Python 读，不用 Get-Content）。"""
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\reports\m3-launch-runbook.md")
t = P.read_text(encoding="utf-8")
marks = [m for m in ("浠讳綍", "缈昏浆", "鐨勭粺", "鈽") if m in t]
print(f"行数 = {len(t.splitlines())}")
print(f"双重编码标记 = {marks if marks else '无'}")
for k in ("步骤 2.0", "audit_dpo_discriminative_axes.py", "AUDIT-DPO-AXES=PASS",
          "★禁止发射★", "规则 33"):
    print(f"  {'OK' if k in t else '✗MISSING'}  {k}")
