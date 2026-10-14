# -*- coding: utf-8 -*-
r"""区分两种原因：文件**没被扫到** ✓ 还是**扫到了但载体行数为 0** ✗。

★上一版 fail-closed 的报错把二者混为一谈 ✗（"files 里一个都没有" 是我写死的措辞），
  这种**误导性诊断**本身也是缺陷 ✗ —— 它会把我引向错误的方向 ✓。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "cco", str(ROOT / "scripts" / "check_carrier_ontology.py"))
cco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cco)

M4 = "data/dpo-remediation-staging/dpo_m4_final.jsonl"
M3 = "data/lf/dpo_m3_final.jsonl"


def main() -> int:
    print("=== 1. 该路径是否被 scan_glob 扫到 ===")
    for label, rel in (("m4 暂存", M4), ("m3 活文件", M3)):
        blk = cco.scan_glob(rel)
        found = list(blk.keys())
        print(f"  {label}: scan_glob('{rel}') -> {len(found)} 个文件 {found[:3]}")
        for k, v in blk.items():
            cr = v.get("carrier_rows") or {}
            print(f"    {k}: carrier_rows={dict(cr)}  keys={sorted(v.keys())[:8]}")

    print("\n=== 2. 两者在 extract 层面看起来一样吗 ===")
    for label, rel in (("m4", M4), ("m3", M3)):
        p = ROOT / rel
        rows = p.read_text(encoding="utf-8").splitlines()
        print(f"  {label}: 行数={len([r for r in rows if r.strip()])}  "
              f"首行前 120 字符 = {rows[0][:120]}")

    print("\n=== 3. scope 展开是什么 ===")
    for label, pat in (("dpo_remediation_staging", "data/dpo-remediation-staging/*.jsonl"),
                       ("dpo_m3_final", "data/lf/dpo_m3_final.jsonl"),
                       ("lf_total", "data/lf/*.jsonl")):
        exp = cco._expand(pat)
        print(f"  {label}: _expand -> {len(exp)} 个")
        for e in list(exp)[:2]:
            print(f"    {e}")
    print("\nDISTINGUISH-DIAG=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
