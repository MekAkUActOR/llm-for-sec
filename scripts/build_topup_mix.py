# -*- coding: utf-8 -*-
"""C 路定向补齐混料构建器（2026-09-30 用户裁决 C）。

目的：以 m2-calib 为起点，用**低 LR/少步**补上 S1 交付的三族
（T2 机制解释 / document 载体结构行为层 / T9 钓鱼扩容），
**以未见载体门禁（v0.3-gen）为验收判据**——直击"续训侵蚀跨载体泛化"的诊断。

设计要点
--------
* 只收 S1 三族（不含 m1 基线、不含旧族）：补齐是"定向"的，不是又一次全量重跑；
* 三族均自带干净负例（T9 35% / T15 32% / T2 F5），故**不需要**额外注入抗误拒配重；
* 组内同 user × 三包的政策配对行**整体保留**（按 pack 分组裁剪会破坏梯度）；
* 全库 (id) 唯一、与 heldout 零同文由 `scripts/check_m25_staging.py` 负责，
  本脚本只做搬运与计数，不做内容改写。

用法
----
    python scripts/build_topup_mix.py [--out data/lf/sec_sft_topup.jsonl] [--dry-run]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "data" / "sft" / "m2.5-staging"

# (文件名, 任务前缀, 允许的 task 前缀元组)
SOURCES = [
    ("t2_mechanism.jsonl", "T2-mechanism", ("T2-mechanism",)),
    ("doc_structure.jsonl", "T15-doc", ("T15-doc",)),
    ("t9_phish_expand.jsonl", "T9-phish", ("T9-phish",)),
]
# 家族内条数上限（None = 全收）。T9 是 3 倍包配对，全收会占掉一半混料；
# 按页面组（同 user）整体抽样，保证三包不拆散。
MAX_ROWS = {"t9_phish_expand.jsonl": 900}


def uhash(row: dict) -> str:
    """内容级去重键：pack + 全部 messages 文本（与 check 脚本口径一致）。"""
    msgs = row.get("messages") or []
    blob = (str(row.get("pack")) + "\x00"
            + "\x00".join(f"{m.get('role')}:{m.get('content')}" for m in msgs))
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def is_zh(row: dict) -> bool:
    lang = str(row.get("lang") or "")
    if lang:
        return lang.startswith("zh")
    txt = "".join((m.get("content") or "") for m in (row.get("messages") or []))
    return any("\u4e00" <= c <= "\u9fff" for c in txt)


def _action(row: dict) -> str | None:
    msgs = [m for m in (row.get("messages") or []) if m.get("role") == "assistant"]
    if not msgs:
        return None
    c = msgs[-1].get("content") or ""
    if "VERDICT: " not in c:
        return None
    try:
        return json.loads(c.rsplit("VERDICT: ", 1)[1]).get("action")
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/lf/sec_sft_topup.jsonl")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = ROOT / a.out

    rows: list[dict] = []
    prov = []
    seen: set[str] = set()
    for fname, task, prefixes in SOURCES:
        p = STAGE / fname
        if not p.exists():
            print(f"[topup] MISSING {fname} -> 中止（缺件不得静默跳过）", file=sys.stderr)
            return 2
        taken = dup = bad = 0
        # 先按 user 文本分组（三包配对不可拆）
        groups: dict[str, list[dict]] = collections.OrderedDict()
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            t = str(r.get("task") or "")
            if not any(t.startswith(x) for x in prefixes):
                bad += 1
                continue
            key = hashlib.md5(("\x00".join(
                (m.get("content") or "") for m in (r.get("messages") or [])
                if m.get("role") == "user")).encode("utf-8")).hexdigest()
            groups.setdefault(key, []).append(r)
        cap = MAX_ROWS.get(fname)
        for key, grp in groups.items():
            if cap is not None and taken + len(grp) > cap:
                continue
            for r in grp:
                h = uhash(r)
                if h in seen:
                    dup += 1
                    continue
                seen.add(h)
                rows.append(r)
                taken += 1
        prov.append({"file": fname, "task_prefix": task, "file_rows": sum(
            len(g) for g in groups.values()), "group_rows_taken": taken,
            "groups": len(groups), "dup_dropped": dup,
            "prefix_mismatch_dropped": bad})
        print(f"[topup] {fname:26} groups={len(groups):>5} "
              f"taken={taken:>5} dup={dup:>4} bad={bad}")

    zh = sum(1 for r in rows if is_zh(r))
    acts = collections.Counter()
    for r in rows:
        ac = _action(r)
        if ac:
            acts[ac] += 1
    packs = collections.Counter(str(r.get("pack")) for r in rows)
    report = {
        "out": str(out.relative_to(ROOT)),
        "rows": len(rows), "zh": zh, "en": len(rows) - zh,
        "zh_pct": round(zh / len(rows) * 100, 1) if rows else None,
        "packs": dict(packs), "actions": dict(acts), "provenance": prov,
        "note": ("C 路定向补齐混料：仅 S1 三族；每族自带干净负例；"
                 "三包配对按 user 分组整体保留"),
    }
    if not rows:
        print("[topup] 未取到任何行 -> 中止", file=sys.stderr)
        return 2
    if a.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (ROOT / "reports" / "topup-mix-build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[topup] rows={len(rows)} zh={zh} ({report['zh_pct']}%) "
          f"packs={dict(packs)}")
    print(f"[topup] -> {out}")
    print(f"[topup] report -> reports/topup-mix-build.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
