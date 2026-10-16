# -*- coding: utf-8 -*-
"""_tmp_m5a_r8_sha_check.py — M5A-R8 冻结仪器 sha 复验（一次性探针件）。

r8 门禁链启动前置门（run_m5a_r8_gates.ps1 Step 0 调用）：
  四件冻结仪器与 r6/r7 逐字节相同（判分/数据零漂移的机械保证）；
  本轮训练配置 configs/m5a-dpo-r8.yaml = r7 件复制 + 恰 2 行功能 diff
  （model_name_or_path → ModelScope 对齐底座本地快照、output_dir → r8；
  LoRA 块与数据/剂量全保留），其新 sha 7d4786f43ddd043e…5149a1c2 在此登记。
fail-closed：任一不符即 rc=1。
全文件整体重写（勘误纪律：不做字符串手术）。
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")

CHECKS = [
    # (相对路径, sha256 前 16 hex, 后 8 hex)
    ("scripts/probe_jailbreak.py", "6cd4390f7848719b", "20a6881b"),
    ("scripts/score_heldout_v2.py", "83d50c8bfb8a500e", "52bcb1da"),
    ("data/heldout/v0.7-jailbreak/jailbreak.jsonl", "cbad0fed25d3490b", "20f816cb"),
    ("data/heldout/v0.6-dilution/risk_payloads.jsonl", "c6eabceecdffa05f", "fd5ef09f"),
    # r8 训练配置（r7 复制 + 2 行 diff，见 configs/m5a-dpo-r8.yaml 头部登记）
    ("configs/m5a-dpo-r8.yaml", "7d4786f43ddd043e", "5149a1c2"),
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ok = True
    for rel, pre, suf in CHECKS:
        p = ROOT / rel
        if not p.is_file():
            print(f"[MISS] {rel}: 文件不存在")
            ok = False
            continue
        full = sha256_file(p)
        match = full.startswith(pre) and full.endswith(suf)
        print(f"[{'OK' if match else 'BAD'}] {rel}: {full[:16]}…{full[-8:]}")
        if not match:
            ok = False
    print("INSTRUMENT-SHA=" + ("PASS" if ok else "FAIL")
          + " (jb scorer / heldout scorer / jb suite / dilution pool / r8 config)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
