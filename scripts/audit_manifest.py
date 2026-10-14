#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""manifest.jsonl 完备性审计（M5 开放权重评审的记账体检，CPU-only）。

检查项：
  1. 必需字段缺失（id/name/url/license/tier/domain/lang/est_tokens/docs/
     status/files/notes）——逐行;
  2. status 与磁盘证据一致性：status='procured' 但 files 指向的文件/目录
     存在（= 实际已入库/已入训）→ 记为**记账滞后**待修正；反之
     status='ingested' 但文件全缺 → 记为**幽灵行**；
  3. ingested_at 缺失清单；
  4. tier 字段分布 + TIER_MAP（gen_datacard）覆盖差集。

用法：python scripts/audit_manifest.py [--json reports/manifest-audit.json]
退出码：0 = 无「幽灵行」（严重）；1 = 存在幽灵行。记账滞后只警告不改退出码。
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"

REQUIRED = ("id", "name", "url", "license", "tier", "domain", "lang",
            "est_tokens", "docs", "status", "files")


def evidence(paths: list[str]) -> list[dict]:
    """files 字段 → 磁盘证据（存在性 + 大小/条目数 + mtime）。"""
    out = []
    for raw in paths:
        p = ROOT / raw if not Path(raw).is_absolute() else Path(raw)
        if p.is_file():
            st = p.stat()
            out.append({"path": raw, "kind": "file", "bytes": st.st_size,
                        "mtime": datetime.datetime.fromtimestamp(
                            st.st_mtime).strftime("%Y-%m-%d %H:%M")})
        elif p.is_dir():
            n = sum(1 for _ in p.rglob("*"))
            st = p.stat()
            out.append({"path": raw, "kind": "dir", "entries": n,
                        "mtime": datetime.datetime.fromtimestamp(
                            st.st_mtime).strftime("%Y-%m-%d %H:%M")})
        else:
            out.append({"path": raw, "kind": "missing"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="审计报告落盘路径")
    args = ap.parse_args()

    rows = [json.loads(l) for l in MANIFEST.open(encoding="utf-8")
            if l.strip()]
    missing_fields: dict[str, list[str]] = collections.defaultdict(list)
    stale_procured, ghost_ingested, no_ingested_at = [], [], []
    for r in rows:
        for k in REQUIRED:
            if k not in r or r[k] in (None, "", []):
                missing_fields[k].append(r.get("id"))
        if not r.get("notes"):
            missing_fields["notes"].append(r.get("id"))
        if not r.get("ingested_at"):
            no_ingested_at.append(r.get("id"))
        ev = evidence(r.get("files") or [])
        present = [e for e in ev if e["kind"] in ("file", "dir")]
        status = r.get("status")
        if status == "procured" and present:
            stale_procured.append({"id": r.get("id"), "evidence": present,
                                   "est_tokens": r.get("est_tokens")})
        if status == "ingested" and not present:
            ghost_ingested.append({"id": r.get("id"), "files": r.get("files")})

    # TIER_MAP（数据卡生成器为唯一权威副本）覆盖差集
    tier_missing = []
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import gen_datacard as gd  # type: ignore
        tier_missing = sorted(r["id"] for r in rows
                              if r["id"] not in gd.TIER_MAP)
    except Exception as exc:  # pragma: no cover
        tier_missing = [f"<TIER_MAP 读取失败: {exc}>"]

    print(f"manifest 行数：{len(rows)}")
    print(f"status 分布：{dict(collections.Counter(r.get('status') for r in rows))}")
    print(f"tier 字段分布：{dict(collections.Counter(r.get('tier') for r in rows))}")
    print("\n--- 1) 必需字段缺失 ---")
    if not missing_fields:
        print("  无")
    for k, v in sorted(missing_fields.items()):
        print(f"  {k}: {len(v)} → {v}")
    print("\n--- 2) 记账滞后（status=procured 但磁盘有证据）---")
    if not stale_procured:
        print("  无")
    for item in stale_procured:
        ev = "; ".join(f"{e['path']}@{e['mtime']}"
                       f"({e.get('bytes', e.get('entries'))})"
                       for e in item["evidence"])
        print(f"  {item['id']:24s} est={item['est_tokens']/1e6:5.2f}M | {ev}")
    print("\n--- 3) 幽灵行（status=ingested 但文件全缺）---")
    if not ghost_ingested:
        print("  无")
    for item in ghost_ingested:
        print(f"  {item['id']}: {item['files']}")
    print(f"\n--- 4) 无 ingested_at：{len(no_ingested_at)} 行 ---")
    print("  " + (", ".join(no_ingested_at) if no_ingested_at else "无"))
    print(f"--- 5) TIER_MAP 未覆盖：{len(tier_missing)} ---")
    print("  " + (", ".join(tier_missing) if tier_missing else "无"))

    if args.json:
        out = ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "manifest_rows": len(rows),
            "missing_fields": {k: v for k, v in missing_fields.items()},
            "stale_procured": stale_procured,
            "ghost_ingested": ghost_ingested,
            "no_ingested_at": no_ingested_at,
            "tier_map_uncovered": tier_missing,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告 → {out}")

    return 1 if ghost_ingested else 0


if __name__ == "__main__":
    raise SystemExit(main())
