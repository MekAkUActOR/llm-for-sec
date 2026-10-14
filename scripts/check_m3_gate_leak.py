# -*- coding: utf-8 -*-
"""★M3 门禁泄漏检查（发射前，2026-09-30 晚）。

触发原因：权威普查发现 **M3 的 DPO 数据 `dpo_m3_final.jsonl` 含 1,000 条 document 信封**，
而 M3 的 MUST-A 判据是"**未见载体** ASR"（门禁集 `data/heldout/v0.3-gen`，258 条）。
若门禁集含 document 条目，或与 DPO 数据有任何重叠，MUST-A 的"未见载体"claim 即被污染
（docs/01 §11.12 规则 13：门禁 eval 集必须与训练混料**零重叠**，否则门禁原理上不可能报警）。

本脚本检查三件事：
  (1) v0.3-gen 门禁集里各载体的条数（是否含 document）；
  (2) 门禁集与 M3 的 DPO 数据的**文本重叠**（按 user 内容规范化后的 md5）；
  (3) 门禁集与 M3 训练数据里 document 条目的重叠。
只读，不写任何既有文件。
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAT = __import__("re").compile(r'<carrier\s+type=\\"([^\\"]+)\\"')


def norm(s):
    return " ".join(str(s).split())


def h(s):
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()


def user_of(row):
    msgs = row.get("messages") or row.get("conversations")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and str(m.get("role") or m.get("from")) in (
                    "user", "human"):
                return norm(m.get("content") or m.get("value") or "")
    for k in ("user", "prompt", "query", "instruction", "input", "question"):
        if row.get(k):
            return norm(row[k])
    return ""


# ---- (1) 门禁集载体分布 + user 哈希 ----
gen = ROOT / "data" / "heldout" / "v0.3-gen"
gate_h = {}
carrier_of = {}
files = sorted(gen.rglob("*.jsonl"))
print(f"门禁集文件数 = {len(files)}")
gate_carrier = Counter()
for f in files:
    with f.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            iid = str(r.get("id") or "")
            u = user_of(r)
            if not u:
                continue
            cands = PAT.findall(line)
            ctype = (cands[0].lower() if cands
                     else str(r.get("carrier") or "").lower() or "UNTAGGED")
            gate_carrier[ctype] += 1
            gate_h[h(u)] = iid
            carrier_of[h(u)] = ctype

print(f"\n(1) v0.3-gen 门禁集载体分布（共 {sum(gate_carrier.values())} 条）：")
for k, v in gate_carrier.most_common():
    print(f"      {k:<16} {v}")
print(f"    ★ 含 document 条目？ {'**是 —— MUST-A 的未见载体 claim 对它不成立**' if gate_carrier.get('document') else '否 ✓'}")

# ---- (2)(3) 与 M3 DPO 数据重叠 ----
dpo = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
print(f"\n(2)(3) 与 M3 DPO 数据 {dpo.name} 的重叠：")
dpo_carrier = Counter()
overlap = []
n = 0
with dpo.open(encoding="utf-8", errors="replace") as fh:
    for line in fh:
        n += 1
        line_s = line.rstrip("\n")
        cands = PAT.findall(line_s)
        ctype = cands[0].lower() if cands else "UNTAGGED"
        dpo_carrier[ctype] += 1
        try:
            r = json.loads(line_s)
        except Exception:
            continue
        u = user_of(r)
        if not u:
            continue
        hh = h(u)
        if hh in gate_h:
            overlap.append((gate_h[hh], carrier_of.get(hh, "?"), ctype, u[:80]))

print(f"    DPO 行数 = {n:,}")
print(f"    DPO 载体分布：{dict(dpo_carrier.most_common())}")
print(f"\n    ★ 与门禁集重叠条目数 = {len(overlap)}")
if overlap:
    print("    前 10 条重叠（门禁id / 门禁载体 / DPO载体 / 内容前80字）：")
    for o in overlap[:10]:
        print(f"      {o[0]} | {o[1]} | {o[2]} | {o[3]}")
print(f"\n    ★ 门禁集 document 条数 = {gate_carrier.get('document', 0)}；"
      f"DPO 的 document 条数 = {dpo_carrier.get('document', 0)}")
