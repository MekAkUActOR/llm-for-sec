# -*- coding: utf-8 -*-
r"""查 m4 暂存文件为何在载体计数上为 0：是 glob 没解析，还是字段丢了 ✗。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
S = ROOT / "data" / "dpo-remediation-staging"
M3 = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"


def probe(p: Path, label: str) -> None:
    print(f"\n=== {label}: {p} ===")
    print(f"  存在 = {p.exists()}")
    if not p.exists():
        return
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"  行数 = {len(rows)}")
    keys0 = sorted(rows[0].keys())
    print(f"  首行键 = {keys0}")
    # 载体相关字段
    for k in ("carriers", "carrier", "pack", "src_task", "dpo_class"):
        v = rows[0].get(k)
        print(f"    {k} = {str(v)[:90]}")
    # 检查 carriers 字段是否全程存在
    n_missing = sum(1 for r in rows if "carriers" not in r)
    print(f"  缺 carriers 字段的行数 = {n_missing}/{len(rows)}")


def main() -> int:
    print("=== glob 解析检查 ===")
    matches = sorted(S.glob("*.jsonl"))
    print(f"  {S}\\*.jsonl -> {len(matches)} 个文件")
    for m in matches:
        print(f"    {m.name}")
    rel = ROOT / "data" / "dpo-remediation-staging" / "*.jsonl"
    print(f"  用 ROOT 拼接的 glob -> {len(sorted(rel.parent.glob(rel.name)))} 个")

    probe(S / "dpo_m4_final.jsonl", "m4 暂存")
    probe(M3, "m3 活文件")

    print("\n=== 对照：两者首行的完整键集是否一致 ===")
    for p, lab in ((S / "dpo_m4_final.jsonl", "m4"), (M3, "m3")):
        if p.exists():
            r = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
            print(f"  {lab}: {sorted(r.keys())}")
    print("\nM4-COUNT-PROBE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
