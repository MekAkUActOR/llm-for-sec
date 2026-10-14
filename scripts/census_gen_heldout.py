# -*- coding: utf-8 -*-
"""v0.3-gen 门禁留出集的构成普查：条目类型、载体、语言、包。

用途：判定"用哪些载体的数据做 SFT 回放"会污染该门禁。
已训练载体（sft_m25 普查）：text 10,239 / email 1,768 / tool_output 1,224 /
log 250 / webpage 250 / code 250；document、image_metadata、av_metadata = 0。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "heldout" / "v0.3-gen"
CAR = re.compile(r'<carrier\s+type="([a-z_]+)"')

rows = []
for p in sorted(D.glob("*.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            r["_file"] = p.name
            rows.append(r)

print(f"v0.3-gen 共 {len(rows)} 条")
print("\n按文件:")
for k, v in Counter(r["_file"] for r in rows).most_common():
    print(f"  {k:34} {v:>5}")

keys = Counter()
for r in rows:
    keys.update(k for k in r if not k.startswith("_"))
print("\n字段:", dict(keys))

for field in ("kind", "task", "family", "lang", "language", "pack", "axis", "category",
              "carrier", "carrier_type", "modality"):
    vals = Counter(str(r.get(field)) for r in rows if r.get(field) is not None)
    if vals:
        print(f"\n{field}: {dict(vals.most_common(10))}")

# 从 prompt 文本里挖载体标记（含各种可能形态）
print("\n--- prompt 文本里的载体信号 ---")
pats = {
    "carrier type=...": CAR,
    "image/av 关键词": re.compile(r"image|图片|EXIF|GPS|帧|frame|音频|audio|video|视频", re.I),
}
msgkey = "messages" if rows and "messages" in rows[0] else "conversations"
for name, pat in pats.items():
    hit = 0
    per = Counter()
    for r in rows:
        txt = json.dumps(r.get(msgkey) or r, ensure_ascii=False)
        m = pat.findall(txt)
        if m:
            hit += 1
            if name == "carrier type=...":
                for x in set(m):
                    per[x] += 1
    print(f"  {name:20} 命中 {hit}/{len(rows)}")
    if per:
        print(f"     逐载体: {dict(per.most_common())}")

# 一条样例（截断）
if rows:
    r = dict(rows[0])
    msgs = r.get(msgkey) or []
    print(f"\n--- 样例 id={r.get('id')} ---")
    for m in msgs[:2]:
        v = (m.get("content") or m.get("value") or "")
        print(f"  [{m.get('role') or m.get('from')}] {v[:400]}")
    print(f"  ...(共 {len(msgs)} 轮)")
