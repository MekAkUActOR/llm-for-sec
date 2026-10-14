# -*- coding: utf-8 -*-
"""r4 门禁链命令重构：剩余脚本 argparse + jb 产物结构。"""
import json
import re
import io

# 1) argparse: score_heldout_v2 / topup_verdict
for f in ("scripts/score_heldout_v2.py", "scripts/topup_verdict.py"):
    src = io.open(f, encoding="utf-8", errors="replace").read()
    print("===", f)
    for m in re.finditer(r"add_argument\((.*?)\)\n", src, re.S):
        blob = m.group(1)
        names = re.findall(r"[\"'](--[a-z0-9-]+)[\"']", blob)
        d = re.search(r"default=([\"']?[^,)]+)", blob)
        print("   ", ",".join(names), "| default:", d.group(1)[:70] if d else "-")

# 2) jb-scored 结构（r3）
d = json.load(open(r"reports/jb-scored-m5a-dpo-r3-v0.7-full-v2.json", encoding="utf-8"))
print("=== jb-scored keys:", list(d.keys())[:15])
for k, v in d.items():
    if isinstance(v, (str, int, float, bool)):
        print("   ", k, "=", str(v)[:80])

# 3) jb-resp 头两行（字段名）
with open(r"reports/jb-resp-m5a-dpo-r3-v0.7-full.jsonl", encoding="utf-8") as f:
    line = json.loads(f.readline())
print("=== jb-resp fields:", list(line.keys()))

# 4) heldout 数据目录（v023/gen 用哪个目录、score 的输入口径）
for p in ("reports/scored-chat-v023-m5a-dpo-r3-v2-mnt512.json",
          "reports/scored-chat-gen-m5a-dpo-r3-v2-mnt512.json",
          "reports/scored-chat-to-m5a-dpo-r3-v2-mnt512.json"):
    d = json.load(open(p, encoding="utf-8"))
    print("===", p)
    for k, v in list(d.items())[:14]:
        if isinstance(v, (str, int, float, bool)) and len(str(v)) < 90:
            print("   ", k, "=", v)
