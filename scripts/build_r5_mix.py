# -*- coding: utf-8 -*-
"""配方 R5 混料：needlefix 修复混料 + 载体正向回放切片。

设计原则（"加法不伤泛化"的机制假设）：
  实测法则——训练在**载体贫乏**的数据上会侵蚀跨载体鲁棒性（m2calib 6/168 →
  needlefix 24/168 → m25full 36/168）。故本配方**不动 needle/契约的每行剂量**
  （长上下文 3,724 行、契约回放 2,024 行各自仍被看一遍），**只额外加入 6,000 行
  载体正向回放**（"载体内容即数据、报告发现、政策接地裁决"，含 22% 良性负例），
  直接训练使命主轴。

代价：总行数 5,748 → 11,748，1 epoch 的步数 360 → 734（eff-batch 16），
      预计 55 分钟（4.5 s/步）。契约**占比** 35.2% → 17.2%（绝对剂量不变 2,024 行）。

门禁完整性：只用 tool_output/log/webpage/code/document/email/text；
v0.3-gen 只含 image_metadata/av_metadata（训练普查中 0 次）⇒ 不污染"未见载体"主张。

硬断言：
  A1 总行数 = 5,748 + 6,000 = 11,748；id 全局唯一
  A2 长上下文行数仍为 3,724（T13-retrieval 1,500 + T10-multiturn 2,224）
  A3 契约回放行数仍为 2,024（绝对剂量不变）
  A4 全部 11,748 行末尾 assistant 含 VERDICT（规则 11 的格式前提）
  A5 与 sft_v0_eval300 及四套留出仪器 id 零重叠
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDLE = ROOT / "data" / "lf" / "sec_sft_needlefix.jsonl"
CARRIER = ROOT / "data" / "lf" / "carrier_sft_slice.jsonl"
OUT = ROOT / "data" / "lf" / "sec_sft_needlefix_carrier.jsonl"
REPORT = ROOT / "reports" / "r5-mix-build.json"
LC_PREFIX = ("T13-retrieval", "T10-multiturn")


def read(p: Path):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


nf = read(NEEDLE)
cr = read(CARRIER)
rows = nf + cr
fails = []

# A1
if len(rows) != 11748:
    fails.append(f"A1 总行数 {len(rows)} != 11748")
ids = [r.get("id") for r in rows]
dup = [k for k, v in Counter(ids).items() if v > 1]
if dup:
    fails.append(f"A1 id 重复 {len(dup)}：{dup[:3]}")

# A2 / A3
lc = [r for r in nf if str(r.get("task", "")).startswith(LC_PREFIX)]
ct = [r for r in nf if r not in lc]
if len(lc) != 3724:
    fails.append(f"A2 长上下文行数 {len(lc)} != 3724")
if len(ct) != 2024:
    fails.append(f"A3 契约回放行数 {len(ct)} != 2024")
fam = Counter(str(r.get("task", "")).split(":")[0] for r in lc)
if fam.get("T13-retrieval", 0) != 1500 or fam.get("T10-multiturn", 0) != 2224:
    fails.append(f"A2 长上下文族分布异常 {dict(fam)}")

# A4
bad = [r["id"] for r in rows
       if "VERDICT" not in (r.get("messages") or [{}])[-1].get("content", "")]
if bad:
    fails.append(f"A4 {len(bad)} 行末条 assistant 缺 VERDICT，例如 {bad[:3]}")

# A5
hold = set()
hold.add("__none__")
ev = ROOT / "data" / "lf" / "sft_v0_eval300.jsonl"
if ev.exists():
    hold |= {r.get("id") for r in read(ev)}
for sub in ("v0.2.1", "v0.3-gen", "v0.4-toolout", "v0.5-topup-families"):
    d = ROOT / "data" / "heldout" / sub
    if d.exists():
        for p in d.glob("*.jsonl"):
            hold |= {json.loads(x).get("id") for x in
                     p.read_text(encoding="utf-8").splitlines() if x.strip()}
ov = hold & set(ids)
if ov:
    fails.append(f"A5 与留出集 id 重叠 {len(ov)}：{sorted(ov)[:3]}")

share = {
    "long_context": round(len(lc) / len(rows), 4),
    "contract_replay": round(len(ct) / len(rows), 4),
    "carrier_replay": round(len(cr) / len(rows), 4),
}
rep = {
    "total_rows": len(rows),
    "abs_dose": {"long_context": len(lc), "contract_replay": len(ct),
                 "carrier_replay": len(cr)},
    "share": share,
    "steps_at_eff16": len(rows) // 16,
    "task_family_counts": dict(Counter(str(r.get("task", "")).split(":")[0]
                                       for r in rows).most_common()),
    "lang_counts": dict(Counter(r.get("lang") for r in rows).most_common()),
    "pack_counts": dict(Counter(r.get("pack") for r in rows).most_common()),
    "holdout_ids_checked": len(hold) - 1,
    "note": "绝对剂量不变（长上下文 3,724 / 契约 2,024 各看一遍），只额外加 6,000 载体行；"
            "契约占比降到 17.2% 是稀释的必然结果，但绝对回放剂量与参照 run 完全相同",
    "fails": fails,
}
REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
if fails:
    print("R5-MIX=FAIL")
    for x in fails:
        print("  -", x)
    sys.exit(1)
with OUT.open("w", encoding="utf-8") as g:
    for r in rows:
        g.write(json.dumps(r, ensure_ascii=False) + "\n")
print("R5-MIX=PASS")
print(f"  写出 {OUT.name}：{len(rows):,} 行 = 长上下文 {len(lc):,} + 契约 {len(ct):,} + 载体 {len(cr):,}")
print(f"  占比 {share}；1 epoch 步数 {len(rows)//16}（eff-batch 16）")
print(f"  留出 id 核对 {len(hold)-1:,} 个，零重叠")
