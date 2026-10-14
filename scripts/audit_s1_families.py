# -*- coding: utf-8 -*-
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

ROOT = Path(r"J:\Projects\llm_for_sec")

def main() -> int:
    print("[deprecated] audit_s1_families.py → 转发到 audit_s1_training_files.py")
    print("[deprecated] 原因：原版审的是评测集而非入训文件；且机制诊断有误。")
    target = ROOT / "scripts" / "audit_s1_training_files.py"
    return subprocess.call([sys.executable, str(target)])

if __name__ == "__main__":
    raise SystemExit(main())
