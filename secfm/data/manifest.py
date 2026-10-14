"""训练语料 manifest：入库登记与审计（docs/04 §3）。

- 一行一个已入库来源（JSONL）；planned 状态允许占位（对应 docs/04 来源表）；
- 校验：schema 完整性、id 唯一、tier/domain/lang 枚举、status 状态机；
- 统计：按 tier/domain 的 token 量（配比核对，docs/04 §2）。

用法：
    python -m secfm.data.manifest --file data/corpora/manifest.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

TIERS = ("public", "restricted", "quarantine")
DOMAINS = ("security", "privacy", "ai_safety", "general", "code")
STATUSES = ("planned", "downloading", "ingested", "quarantined", "dropped")
REQUIRED = ("id", "name", "tier", "domain", "lang", "status")


def load(path):
    rows, problems = [], []
    for ln, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"line {ln}: invalid JSON ({e})")
            continue
        missing = [k for k in REQUIRED if k not in d]
        if missing:
            problems.append(f"line {ln} ({d.get('id', '?')}): missing {missing}")
            continue
        rows.append(d)
    return rows, problems


def validate(rows):
    problems = []
    ids = [r["id"] for r in rows]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        problems.append(f"duplicate ids: {dupes}")
    for r in rows:
        if r["tier"] not in TIERS:
            problems.append(f"{r['id']}: tier {r['tier']!r} not in {TIERS}")
        if r["domain"] not in DOMAINS:
            problems.append(f"{r['id']}: domain {r['domain']!r} not in {DOMAINS}")
        if r["status"] not in STATUSES:
            problems.append(f"{r['id']}: status {r['status']!r} not in {STATUSES}")
        if r["status"] == "ingested" and not r.get("license"):
            problems.append(f"{r['id']}: ingested 但缺 license 字段（docs/04 许可核验）")
        if r["tier"] != "public" and r.get("files"):
            problems.append(
                f"{r['id']}: 非 public 层的文件路径 {r['files']} 不应出现在训练 "
                f"token 目录（restricted/quarantine 只进判断任务，docs/04 §0）")
    return problems


def stats(rows):
    by_tier = Counter()
    by_domain = Counter()
    ingested_tokens = 0
    for r in rows:
        if r["status"] in ("ingested",):
            tok = int(r.get("est_tokens", 0) or 0)
            by_tier[r["tier"]] += tok
            by_domain[r["domain"]] += tok
            ingested_tokens += tok
    return {"sources": len(rows), "ingested_tokens": ingested_tokens,
            "tokens_by_tier": dict(by_tier), "tokens_by_domain": dict(by_domain)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="语料 manifest 校验与统计")
    ap.add_argument("--file", default="data/corpora/manifest.jsonl")
    args = ap.parse_args(argv)
    path = Path(args.file)
    if not path.exists():
        print(f"manifest 不存在: {path}（首批入库时创建）")
        return 0
    rows, problems = load(path)
    problems += validate(rows)
    print(json.dumps(stats(rows), ensure_ascii=False, indent=2))
    if problems:
        print("\n".join("PROBLEM: " + p for p in problems))
        return 1
    print(f"OK: {len(rows)} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
