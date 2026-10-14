# -*- coding: utf-8 -*-
"""探针 v0.4 组装：两个域换源重建 + 其余六域字节复制（保纵向可比）。

- general_en：严格互补重建（scripts/gen_probes_v04_general_en.py，哈希补集 + 8-gram 三重复核）
- privacy   ：换源重建（scripts/gen_probes_v04_privacy.py，ICO 指导页 + 单元级预筛）
- ais/aisafety/content/general_zh/malware/sec：从 v0.3 **字节复制**（SHA256 记录），
  使这六域的 base/c1-full/m15/m2*/m25 纵向读数与历史完全可比。

输出：data/probes/v0.4/*.jsonl + README.md + reports/probes-v04-build.json
用法：python scripts/assemble_probes_v04.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V03 = ROOT / "data" / "probes" / "v0.3"
V04 = ROOT / "data" / "probes" / "v0.4"
REPORT = ROOT / "reports" / "probes-v04-build.json"
COPY = ["ais.jsonl", "aisafety.jsonl", "content.jsonl", "general_zh.jsonl",
        "malware.jsonl", "sec.jsonl"]
REBUILT = ["general_en.jsonl", "privacy.jsonl"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def count(p: Path) -> tuple[int, int]:
    n = chars = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n += 1
            chars += len(json.loads(line)["text"])
    return n, chars


def main() -> int:
    V04.mkdir(parents=True, exist_ok=True)
    rep: dict = {"version": "v0.4", "dir": str(V04), "copied": {}, "rebuilt": {}}
    for name in COPY:
        src, dst = V03 / name, V04 / name
        s = sha256(src)
        if not dst.exists() or sha256(dst) != s:
            shutil.copyfile(src, dst)
        n, c = count(dst)
        rep["copied"][name] = {"rows": n, "chars": c, "sha256": sha256(dst),
                              "byte_identical_v03": sha256(dst) == s}
    for name in REBUILT:
        p = V04 / name
        if not p.exists():
            print(f"!! missing {p}")
            return 1
        n, c = count(p)
        rep["rebuilt"][name] = {"rows": n, "chars": c, "sha256": sha256(p)}
    # 断言：两域重建体量不低于旧版（可比性下限）
    old = {n: count(V03 / n)[0] for n in REBUILT}
    for n in REBUILT:
        new = rep["rebuilt"][n]["rows"]
        rep["rebuilt"][n]["v03_rows"] = old[n]
        if new < old[n]:
            print(f"!! {n}: v0.4 rows {new} < v0.3 rows {old[n]}")
            return 1
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
