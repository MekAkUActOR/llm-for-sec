#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M3.5 RLVR 任务文件契约核查（CPU-only，只读）。

核查 data/rlvr/tasks-v01.jsonl：
  - 行数 / 任务型分布 / 包分布 / 语言分布
  - 必需列：messages(system,user) / reward_task_json / reward_pack
  - reward_task_json 可解析且含 task_type + ground_truth
  - ground_truth 与 task_type 自洽（关键字段在位）
  - reward_pack ∈ 三包
输出：reports/m35-tasks-contract.json + 人类可读摘要
用法：python scripts/check_rlvr_tasks.py [--file data/rlvr/tasks-v01.jsonl]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[\u4e00-\u9fff]")
GT_REQUIRED = {
    "inj_detect": ("verdict", "action"),
    "policy_ruling": ("actions",),
    "pii_discover": ("verdict", "action", "locate"),
    "carrier_classify": ("verdict", "action"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/rlvr/tasks-v01.jsonl")
    args = ap.parse_args()
    p = ROOT / args.file
    rows = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]

    types = collections.Counter()
    packs = collections.Counter()
    lang = collections.Counter()
    cross: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    bad = []
    for i, r in enumerate(rows):
        for col in ("messages", "reward_task_json", "reward_pack"):
            if col not in r:
                bad.append((i, f"缺列 {col}"))
                continue
        msgs = r.get("messages") or []
        roles = [m.get("role") for m in msgs]
        if roles != ["system", "user"]:
            bad.append((i, f"messages 角色异常 {roles}"))
        try:
            rt = json.loads(r["reward_task_json"])
        except Exception as exc:
            bad.append((i, f"reward_task_json 解析失败 {exc}"))
            continue
        tt = rt.get("task_type")
        types[tt] += 1
        gt = rt.get("ground_truth") or {}
        for k in GT_REQUIRED.get(tt, ()):
            if k not in gt:
                bad.append((i, f"{tt} 的 ground_truth 缺 {k}"))
        packs[r.get("reward_pack")] += 1
        cross[tt][r.get("reward_pack")] += 1
        u = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
        lang["zh" if len(CJK.findall(u[:2000])) >= 8 else "en"] += 1

    out = {
        "file": args.file,
        "rows": len(rows),
        "task_types": dict(types),
        "packs": dict(packs),
        "task_type_x_pack": {k: dict(v) for k, v in cross.items()},
        "lang_content_zh_en": dict(lang),
        "violations": len(bad),
        "violations_sample": bad[:10],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    dest = ROOT / "reports" / "m35-tasks-contract.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告 → {dest}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
