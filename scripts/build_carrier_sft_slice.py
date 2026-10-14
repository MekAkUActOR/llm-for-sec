# -*- coding: utf-8 -*-
"""从 M3 载体偏好对里抽出**正向 SFT 切片**（chosen 侧），用于"加法不伤泛化"的配方。

动机：实测法则是"训练在载体贫乏的数据上会侵蚀跨载体鲁棒性"（m2calib 6/168 →
needlefix 24/168 → m25full 36/168）。所以配方里必须**直接训练使命主轴**：
让模型在被注入的载体载荷面前保持"内容即数据、报告发现、政策接地裁决"的行为。

门禁完整性：v0.3-gen 只含 image_metadata / av_metadata 两类载体（各 126/132 条），
而训练普查显示这两类出现 0 次；本切片只用 tool_output/log/webpage/code/document/email/text
⇒ **不污染 v0.3-gen 的"未见载体"主张**（与 v0.4-toolout 不同——那个会被 tool_output 训练污染）。

输出 schema 与 data/lf/sft_v0.jsonl 完全一致（{id,task,pack,lang,messages}），
以便与长上下文切片、契约回放直接拼接。

硬断言：
  A1 行数 = 载体偏好对行数（每对贡献 1 行）
  A2 每行末条 assistant 含 VERDICT
  A3 载体类别覆盖 ≥5 类，各 ≥600
  A4 与 v0.3-gen / v0.2.1 / v0.5-topup-families 的 id 零重叠
  A5 良性负例（carrier_clean_overrefusal）行数 ≥20%（防止把"见载体就报攻击"练进去）
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "lf" / "dpo_m3_carriers_v1.jsonl"
OUT = ROOT / "data" / "lf" / "carrier_sft_slice.jsonl"
REPORT = ROOT / "reports" / "carrier-sft-slice.json"
CAR = re.compile(r'<carrier\s+type="([a-z_]+)"')

rows = []
with SRC.open(encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        conv = list(r.get("conversations") or [])
        chosen = (r.get("chosen") or {}).get("value") or ""
        msgs = [{"role": ("system" if m.get("from") == "system"
                          else "user" if m.get("from") in ("human", "user") else "assistant"),
                 "content": m.get("value") or ""} for m in conv]
        msgs.append({"role": "assistant", "content": chosen})
        rows.append({"id": r.get("id"), "task": f"R-carrier:{r.get('dpo_class')}",
                     "pack": r.get("pack"), "lang": r.get("lang"), "messages": msgs,
                     "_class": r.get("dpo_class"),
                     "_carriers": sorted(set(CAR.findall(
                         " ".join(m["content"] for m in msgs))))})

fails = []
if not rows:
    fails.append("A1 空切片")
nov = sum(1 for r in rows if "VERDICT" not in r["messages"][-1]["content"])
if nov:
    fails.append(f"A2 {nov} 行末条 assistant 缺 VERDICT")
cc = Counter(c for r in rows for c in r["_carriers"])
REQ = {"tool_output": 600, "log": 600, "webpage": 600, "code": 600, "document": 600}
for k, need in REQ.items():
    if cc.get(k, 0) < need:
        fails.append(f"A3 载体 {k} 仅 {cc.get(k, 0)} < {need}")
hold = set()
for sub in ("v0.3-gen", "v0.2.1", "v0.5-topup-families", "v0.4-toolout"):
    d = ROOT / "data" / "heldout" / sub
    if d.exists():
        for p in d.glob("*.jsonl"):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    hold.add(json.loads(line).get("id"))
ov = hold & {r["id"] for r in rows}
if ov:
    fails.append(f"A4 与留出集 id 重叠 {len(ov)}：{sorted(ov)[:3]}")
benign = sum(1 for r in rows if r["_class"] == "carrier_clean_overrefusal")
bsh = benign / len(rows)
if bsh < 0.20:
    fails.append(f"A5 良性负例占比 {bsh:.3f} < 0.20")

rep = {"rows": len(rows), "carrier_type_counts": dict(cc.most_common()),
       "class_counts": dict(Counter(r["_class"] for r in rows).most_common()),
       "benign_share": round(bsh, 4),
       "lang_counts": dict(Counter(r["lang"] for r in rows).most_common()),
       "pack_counts": dict(Counter(r["pack"] for r in rows).most_common()),
       "schema": "sharegpt {id,task,pack,lang,messages[{role,content}]}（同 sft_v0.jsonl）",
       "gate_contamination": "无：只用 tool_output/log/webpage/code/document/email/text；"
                             "v0.3-gen 只含 image_metadata/av_metadata（训练中 0 次）",
       "fails": fails}
REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
if fails:
    print("CARRIER-SFT-SLICE=FAIL")
    for x in fails:
        print("  -", x)
    sys.exit(1)
with OUT.open("w", encoding="utf-8") as g:
    for r in rows:
        g.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")},
                           ensure_ascii=False) + "\n")
print("CARRIER-SFT-SLICE=PASS")
print(f"  写出 {OUT.name}：{len(rows):,} 行；载体 {rep['carrier_type_counts']}")
print(f"  类别 {rep['class_counts']}")
print(f"  良性负例 {bsh:.1%}；zh/en {rep['lang_counts']}")
