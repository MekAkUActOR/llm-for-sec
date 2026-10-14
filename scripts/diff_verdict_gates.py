# -*- coding: utf-8 -*-
"""列出 m25/topup 判定报告里的逐轴判定（用于"改判据后是否有回归"的审计）。

用法：
    python scripts/diff_verdict_gates.py reports/m25-exit-verdict-chat-m25full.json [...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def walk(o, prefix=""):
    """递归找所有含 'state' 的判定字典。"""
    if isinstance(o, dict):
        if "state" in o and ("diff" in o or "fisher_p" in o):
            yield prefix.rstrip("."), o
        for k, v in o.items():
            yield from walk(v, f"{prefix}{k}.")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{prefix}[{i}].")


args = sys.argv[1:]
files = [Path(a) if Path(a).is_absolute() else ROOT / a for a in args]
if not files:
    print(__doc__)
    raise SystemExit(2)
for f in files:
    if not f.exists():
        print(f"!! 缺文件 {f}")
        continue
    d = json.loads(f.read_text(encoding="utf-8"))
    print(f"\n===== {f.name}")
    print(f"  tag={d.get('tag')} suffix={d.get('suffix')!r} "
          f"verdict={d.get('verdict')}")
    print(f"  bases={d.get('bases')}")
    print(f"  passed={d.get('passed')}")
    print(f"  failed={d.get('failed')}  undecided={d.get('undecided')}")
    for path, v in walk(d):
        if path.endswith("decisions") or "decision" in path.lower() or True:
            print(f"    {path:52} state={v.get('state'):<12} "
                  f"diff={v.get('diff')} p={v.get('fisher_p')} "
                  f"tol={v.get('tolerance')} test={v.get('test')}")
