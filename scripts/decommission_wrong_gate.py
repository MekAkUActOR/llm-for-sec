# -*- coding: utf-8 -*-
"""拆除上一轮装错的门：
  1) `scripts/audit_s1_families.py` 改为**弃用转发**到 `audit_s1_training_files.py`
     （原版审的是评测集 data/heldout/v0.5-topup-families ✗）；
  2) `reports/m3-launch-runbook.md` 步骤 2.0b 的命令与期望值改为指向真文件审计，
     并删去"补不含契约的负样本"这条**错误处方** ✗；
  3) 给 `reports/s1-three-families-structural-audit.md` 顶部加**更正横幅**。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")

DEPRECATED = '''# -*- coding: utf-8 -*-
"""★已弃用（2026-10-06 晚）——请用 `scripts/audit_s1_training_files.py`。

本脚本原先审的是 `data/heldout/v0.5-topup-families/*.jsonl`（27–30 条的**评测集**），
**不是入训文件** ✗。真正的入训文件是 `data/sft/m2.5-staging/*.jsonl`
（1,200–1,500 行、3.4–4.9 MB）。

且原版的**机制诊断是错的**：它把"目标 100% 含 VERDICT"判为共模缺陷，
但 `scripts/check_prompt_contract_mandate.py` 证明三族的 **prompt 侧 100% 要求
"以 VERDICT 行结尾"** ⇒ 目标 100% 合规是**正确行为**；
真根因是**目标长度（中位 697–1,035）远超部署预算 450** ✗。
详见 `reports/rootcause-corrected-length-not-contract.md` 与 docs/01 §11.35 规则 36（更正版）。

本文件保留为**转发入口**，以保证任何仍在调用它的地方拿到正确结果。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"J:\\Projects\\llm_for_sec")

def main() -> int:
    print("[deprecated] audit_s1_families.py → 转发到 audit_s1_training_files.py")
    print("[deprecated] 原因：原版审的是评测集而非入训文件；且机制诊断有误。")
    target = ROOT / "scripts" / "audit_s1_training_files.py"
    return subprocess.call([sys.executable, str(target)])

if __name__ == "__main__":
    raise SystemExit(main())
'''


def fix_audit_script() -> bool:
    p = ROOT / "scripts" / "audit_s1_families.py"
    if not p.exists():
        print("  audit_s1_families.py 不存在，跳过")
        return True
    src = p.read_text(encoding="utf-8")
    if "已弃用（2026-10-06 晚）" in src:
        print("  audit_s1_families.py 已是转发入口（幂等）")
        return True
    bak = p.with_suffix(".py.bak-wrongtarget-20261006")
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
        print(f"  备份 -> {bak.name}")
    p.write_text(DEPRECATED, encoding="utf-8")
    print("  audit_s1_families.py -> 弃用转发入口")
    return True


def fix_runbook() -> bool:
    p = ROOT / "reports" / "m3-launch-runbook.md"
    txt = p.read_text(encoding="utf-8")
    if not txt:
        return False
    changed = []

    # (a) 命令改名
    if "scripts\\audit_s1_families.py" in txt:
        txt = txt.replace("scripts\\audit_s1_families.py",
                          "scripts\\audit_s1_training_files.py")
        changed.append("命令")
    # (b) 期望值
    if "AUDIT-S1-FAMILIES=PASS" in txt:
        txt = txt.replace("AUDIT-S1-FAMILIES=PASS", "AUDIT-S1-TRAINING=PASS")
        changed.append("期望值")

    # (c) 替换整段"背景/禁止发射"叙述为更正版
    old_start = "> ### ★★ 步骤 2.0b"
    if old_start in txt:
        i = txt.index(old_start)
        j = txt.find("\n\n", i)
        if j == -1:
            j = len(txt)
        new_block = (
            "> ### ★★ 步骤 2.0b（**强制门**）：S1 入训三族结构审计"
            "（规则 36 更正版 / docs/01 §11.35）\n"
            ">\n"
            "> **★2026-10-06 晚更正**：本步原先指向 `data/heldout/v0.5-topup-families/`"
            "（**评测集**）✗，\n"
            "> 且给出的处方（\"补不含契约的负样本\"）**是错的** ✗✗。\n"
            "> 真入训文件是 **`data/sft/m2.5-staging/*.jsonl`**；\n"
            "> `scripts/check_prompt_contract_mandate.py` 证明三族 prompt 侧 "
            "**100.00% 要求\"以 VERDICT 行结尾\"**\n"
            "> ⇒ 目标 100% 合规是**正确行为**，不是共模缺陷；\n"
            "> **真根因是长度**：`t2_mechanism` 目标中位 **1,035**、"
            "`doc_structure` **697**，\n"
            "> 而部署预算只有 **450** 字符 ⇒ 部署时截断 ⇒ 尾部契约行丢失 ✗。\n"
            "> **★按旧处方加负样本会教模型违反 prompt 的格式指令，比现状更糟** ✗✗\n"
            "> 详见 `reports/rootcause-corrected-length-not-contract.md`。\n"
            ">\n"
            "> ```powershell\n"
            "> & 'J:\\Projects\\llm_for_sec\\.venv\\Scripts\\python.exe' `\n"
            ">     scripts\\audit_s1_training_files.py\n"
            "> # 期望：AUDIT-S1-TRAINING=PASS（rc=0）\n"
            "> # 若 rc≠0 ⇒ ★禁止发射★：把目标长度压进部署预算（推论 36.4），\n"
            "> #           并同时报告 prompt 要求率 / 合规率 / 长度-预算比（推论 36.3）。\n"
            "> # ★错误处方（勿用）：给三族加\"不含契约行\"的负样本 —— 契约是 prompt 强制的。\n"
            "> ```\n"
            ">\n"
            "> **★\"交付 ≠ 可入训\"**：docs/01 L260 记的 A5 欠账（\"T2 已交付 1,200 行"
            "但未入训\"）\n"
            "> 的**结清条件是\"压进长度预算\"，不是\"补足行数\"**。"
        )
        txt = txt[:i] + new_block + txt[j:]
        changed.append("2.0b 整段")
    if not changed:
        print("  runbook 无需改动（幂等）")
        return True
    p.write_text(txt, encoding="utf-8")
    print(f"  runbook 已更新：{changed}")
    return True


def banner_report() -> bool:
    p = ROOT / "reports" / "s1-three-families-structural-audit.md"
    if not p.exists():
        print("  S1 审计报告不存在，跳过")
        return True
    txt = p.read_text(encoding="utf-8")
    head = "> # ★★★ 本报告已被更正，请勿直接引用结论 ★★★\n>\n"
    if head in txt:
        print("  S1 报告已有更正横幅（幂等）")
        return True
    banner = (
        "> # ★★★ 本报告已被更正，请勿直接引用结论 ★★★\n"
        ">\n"
        "> **更正时间**：2026-10-06 晚。**更正报告**："
        "`reports/rootcause-corrected-length-not-contract.md`\n"
        ">\n"
        "> **本报告的两处错误**：\n"
        "> 1. **审错了文件**：本报告用的是 `data/heldout/v0.5-topup-families/*.jsonl`"
        "（**评测集**，27–30 条），\n"
        ">    而真正的入训文件是 `data/sft/m2.5-staging/*.jsonl`"
        "（**1,200–1,500 行**）✗。\n"
        "> 2. **机制诊断错误**：本报告把\"目标 100% 含 VERDICT\"判为**共模缺陷**，\n"
        ">    但 `scripts/check_prompt_contract_mandate.py` 证明三族 **prompt 侧 100.00% "
        "要求\"以 VERDICT 行结尾\"**\n"
        ">    ⇒ 目标 100% 合规是**正确行为** ✗。**真根因是长度**"
        "（中位 697–1,035 vs 部署预算 450）。\n"
        "> 3. **处方有害**：本报告建议\"补不含契约的负样本\"——"
        "**那会教模型违反 prompt 的格式指令** ✗✗。\n"
        ">\n"
        "> **数字仍然有效**（对真文件的复审见 "
        "`scripts/audit_s1_training_files.py`，结果同为 FAIL），\n"
        "> **但原因与修复方向完全不同**。规则 36 已按更正版重写。\n"
        ">\n"
        "---\n\n"
    )
    p.write_text(banner + txt, encoding="utf-8")
    print("  S1 报告已加更正横幅")
    return True


def main() -> int:
    print("=== 拆错门 + 加更正 ===")
    ok = all([fix_audit_script(), fix_runbook(), banner_report()])
    print(f"DECOMMISSION-WRONG-GATE={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
