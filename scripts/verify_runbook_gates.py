# -*- coding: utf-8 -*-
"""复核 runbook 的**三道**强制门都已接入（用 Python 读，避免 PS 5.1 的编码毁伤）。

★2026-10-06 第 16 轮：门由两道增为三道 —— 新增 **2.0c 规则 37**
  （偏好数据逐类 token 长度混杂），并把 2.0 的期望从"共模即缺陷"更正为
  "prompt 强制的共模不是缺陷"。本校验器同步登记这些字符串，
  使**后来者无法悄悄删掉新门或退回旧诊断**。
"""
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\reports\m3-launch-runbook.md")
txt = P.read_text(encoding="utf-8")
lines = txt.splitlines()
print(f"文件 = {P.name}  行数 = {len(lines)}  字符 = {len(txt)}")
need = [
    # --- 2.0 规则 33 门 ---
    "步骤 2.0（", "audit_dpo_discriminative_axes.py", "AUDIT-DPO-AXES=PASS",
    # --- 2.0c 规则 37 门（★第 16 轮新增，M3 真缺陷所在）---
    "步骤 2.0c", "audit_dpo_length_confounding.py", "AUDIT-DPO-LENGTH=PASS",
    "规则 37", "长度匹配", "推论 37.2",
    # --- 2.0b 规则 36 门 ---
    "步骤 2.0b", "audit_s1_training_files.py", "AUDIT-S1-TRAINING=PASS",
    "规则 36", "交付 ≠ 可入训",
    "check_prompt_contract_mandate.py",
    "推论 36.3", "推论 36.4",
    # ★第 16 轮：改指向 token 级报告（旧报告仍存在，但机制诊断已被取代）
    "token-level-rootcause-and-prescription.md",
    # ★第 16 轮：口径更正必须写明（字符 → token）
    "--budget-tokens", "规则 37.1",
]
#: 必须**不再出现**的旧内容（防回退）
forbid = [
    "audit_s1_families.py",              # 旧审计（审的是评测集）
    "s1-three-families-structural-audit.md",  # 旧报告（机制诊断错误）
    "--budget-chars 450 `",              # ★第 16 轮：字符口径判定已废弃（规则 37.1）
]
for n in need:
    cnt = txt.count(n)
    print(f"  {'OK ' if cnt else '★缺'}  {n!r}  ×{cnt}")
bad = [c for c in ("\ufffd", "锟斤拷") if c in txt]
print(f"\n乱码 = {bad or '无'}")
print("--- 必须不再出现的旧内容 ---")
leftover = []
for f in forbid:
    cnt = txt.count(f)
    print(f"  {'★残留' if cnt else 'OK  '}  {f!r}  ×{cnt}")
    if cnt:
        leftover.append(f)
ok = all(txt.count(n) for n in need) and not bad and not leftover
print(f"RUNBOOK-GATES={'PASS' if ok else 'FAIL'}")
