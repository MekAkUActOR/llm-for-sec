# -*- coding: utf-8 -*-
"""查清 carrier 标记在训练文件里的**实际存储形态**（我的 `<carrier>` 直搜得 0，与普查的
13,981 行矛盾 ⇒ 必须先弄清口径，否则任何"document=0"的结论都不可靠）。
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "data" / "lf" / "sft_m25.jsonl"

print("=== 1. 原始文本里的 'carrier' 出现情况（前 3 处上下文）===")
hits = 0
with p.open(encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        low = line.lower()
        if "carrier" in low:
            hits += 1
            if hits <= 3:
                j = low.find("carrier")
                print(f"  行{i}: …{line[max(0, j - 90):j + 90]}…")
        if hits >= 50 and i > 200_000:
            break
print(f"  （扫描中命中 'carrier' 的行数 = {hits}）")

print("\n=== 2. 首行的 JSON 结构（字段名）===")
with p.open(encoding="utf-8", errors="replace") as f:
    first = json.loads(f.readline())
print(f"  顶层字段 = {list(first)}")
for k, v in first.items():
    s = json.dumps(v, ensure_ascii=False)[:110] if not isinstance(v, str) else v[:110]
    print(f"    {k}: {s}")

print("\n=== 3. 统计若干行的字段出现频次（判断载体信息存在哪个字段）===")
cnt = Counter()
with p.open(encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        if i >= 5000:
            break
        try:
            r = json.loads(line)
        except Exception:
            continue
        for k in r:
            cnt[k] += 1
print("  " + "  ".join(f"{k}={v}" for k, v in cnt.most_common(12)))
