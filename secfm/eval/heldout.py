"""私有留出集：加载、校验、统计（docs/01 §5.5 留出集纪律；docs/02 §3）。

纪律（目录与工具层面强制）：
- 留出集只进评估管线，永不进入任何训练语料目录——data/heldout/ 与
  data/corpora/ 物理分离，语料管线只读 corpora，评估只读 heldout；
- 版本化：data/heldout/<version>/（目录名即版本号）；
- 扩容目标：≥50 条/优先域（docs/02 §3），v0.1 先交付 20/域种子；
- 判定以本集为准，公开基准只作参考曲线（docs/01 §5.5）。

用法：
    python -m secfm.eval.heldout --dir data/heldout/v0.1
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from secfm.eval.registry import Suite
from secfm.eval.schema import DOMAINS, KINDS, EvalItem

PRIORITY_DOMAINS = ("ai_safety", "security", "privacy")

_EXPECTED_KEYS = {
    "robustness": ("must_refuse",),
    "alignment": ("must_refuse",),
    "capability": ("correct_verdict",),
    "calibration": ("correct_verdict",),
}


def load_file(path):
    """单个 JSONL -> (items, problems)。"""
    items, problems = [], []
    for ln, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"{path}:{ln}: invalid JSON ({e})")
            continue
        try:
            items.append(EvalItem(
                id=d["id"], domain=d["domain"], kind=d["kind"],
                language=d.get("language", ""),
                policy_pack=d.get("policy_pack", "default"),
                query=d["query"], expected=d.get("expected", {}),
                group=d.get("group", "")))
        except (KeyError, ValueError) as e:
            problems.append(f"{path}:{ln}: {e}")
    return items, problems


def validate(items):
    """跨条目不变量校验；返回问题列表（空 = 通过）。"""
    problems = []
    ids = [i.id for i in items]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        problems.append(f"duplicate ids: {dupes}")
    for it in items:
        if it.language not in ("zh", "en"):
            problems.append(f"{it.id}: language must be 'zh' or 'en'")
        if not it.policy_pack:
            problems.append(f"{it.id}: empty policy_pack")
        for k in _EXPECTED_KEYS[it.kind]:
            if k not in it.expected:
                problems.append(
                    f"{it.id}: kind '{it.kind}' requires expected.{k}")
    return problems


def load_dir(d):
    """目录下全部 *.jsonl -> (Suite, problems)。"""
    d = Path(d)
    items, problems = [], []
    for p in sorted(d.glob("*.jsonl")):
        fi, fp = load_file(p)
        items.extend(fi)
        problems.extend(fp)
    return Suite(f"heldout:{d.name}", items), problems


def stats(items):
    return {
        "n": len(items),
        "by_domain": dict(Counter(i.domain for i in items)),
        "by_kind": dict(Counter(i.kind for i in items)),
        "by_language": dict(Counter(i.language for i in items)),
        "by_pack": dict(Counter(i.policy_pack for i in items)),
        "policy_groups": len({i.group for i in items if i.group}),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="私有留出集校验与统计")
    ap.add_argument("--dir", default="data/heldout/v0.1")
    ap.add_argument("--min-per-domain", type=int, default=20,
                    help="种子批次最低条数/优先域（扩容目标 50）")
    args = ap.parse_args(argv)

    suite, problems = load_dir(args.dir)
    problems += validate(suite.items)
    st = stats(suite.items)
    print(json.dumps(st, ensure_ascii=False, indent=2))

    for d in PRIORITY_DOMAINS:
        n = st["by_domain"].get(d, 0)
        if n < args.min_per_domain:
            problems.append(
                f"domain {d}: {n} < {args.min_per_domain}（扩容目标 50）")
    for k in KINDS:
        if st["by_kind"].get(k, 0) == 0:
            problems.append(f"kind {k}: no items")
    for d in PRIORITY_DOMAINS:
        zh = sum(1 for i in suite.items
                 if i.domain == d and i.language == "zh")
        en = sum(1 for i in suite.items
                 if i.domain == d and i.language == "en")
        if zh == 0 or en == 0:
            problems.append(f"domain {d}: language coverage zh={zh} en={en}")

    if problems:
        print("\n".join("PROBLEM: " + p for p in problems))
        return 1
    print(f"OK: {st['n']} items, {st['policy_groups']} policy groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
