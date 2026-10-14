# -*- coding: utf-8 -*-
"""诊断：训练数据里"载体类型"到底是怎么表示的（只读）。

背景：`scripts/carrier_census.py` 按 `carrier type="X"` 正则扫描，结果**零命中**，
说明标记形式与设计文档/审计假设不同。本脚本给出客观事实：
  * 每族文件里 `carrier*` 的上下文样例；
  * 六个已注册载体关键词的出现次数；
  * 每行 JSON 的顶层键（是否存在 carrier 字段）；
  * t14 的一行完整样例（截断）。

用法：python scripts/diag_carrier_markers.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ROOT / "data" / "lf" / "sft_m25.jsonl",
    ROOT / "data" / "sft" / "m2.5-staging" / "t14_authinject.jsonl",
    ROOT / "data" / "sft" / "m2.5-staging" / "t9_phishing.jsonl",
    ROOT / "data" / "sft" / "m2.5-staging" / "fE_t3t12t11.jsonl",
]
KEYWORDS = ("tool_output", "email", "webpage", "code", "log", "text",
            "document", "image", "audio", "video")


def main() -> int:
    for path in FILES:
        if not path.exists():
            print(f"[skip] {path.name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        print("=" * 78)
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes, "
              f"{text.count(chr(10)) + 1:,} lines)")
        print("-" * 78)
        # 1. carrier 上下文
        ctx = re.findall(r".{0,30}carrier.{0,50}", text)
        print(f"  'carrier' 出现 {len(ctx)} 次；样例：")
        for c in ctx[:4]:
            print(f"    …{c.strip()}…")
        # 2. 载体关键词
        print("  关键词计数：" + ", ".join(
            f"{k}={text.count(k)}" for k in KEYWORDS))
        # 3. 顶层键（前 200 行）
        keys = collections.Counter()
        sample = None
        for i, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if i < 200:
                keys.update(d.keys())
            if sample is None:
                sample = d
        print(f"  顶层键（前 200 行）：{dict(keys)}")
        if sample is not None:
            keys_s = list(sample.keys())
            print(f"  样例键：{keys_s}")
            for k in keys_s:
                v = sample[k]
                sv = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
                print(f"    {k}: {sv[:220]}")
            print(f"  样例 id={sample.get('id')!r} task={sample.get('task')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
