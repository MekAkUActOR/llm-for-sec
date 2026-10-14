# -*- coding: utf-8 -*-
"""合并 M3 DPO 最终混料：契约修复版（q） + 载体多样性批。

组件（2026-09-30 定稿，见 reports/m3-final-mix-build.json 与 docs/01 §11.10）：
  A) data/lf/dpo_m3_v2_q.jsonl          22,842 行 —— 契约 100% 覆盖、reserve 24.9978%、
     同立场对两侧 VERDICT 逐字相同（**无人造置信差**，故不产生无依据的校准梯度）
  B) data/lf/dpo_m3_carriers_v1.jsonl    6,000 行 —— 7 类载体、22% 良性负例、
     三类 rejected 错误形态齐备

被否决的候选（保留为消融资产，不进主混料）：
  - dpo_m3_v2.jsonl（3,321 对同立场样本带人造置信差 → 会把无依据的"更自信"校准偏好注入 DPO）
  - dpo_m3_v2_strict.jsonl（只留立场不同的对：放弃回答质量梯度，且保留条件与启发式标签噪声正相关）

硬断言（任一失败即非零退出）：
  A1 行数 = 22,842 + 6,000 = 28,842；id 全局唯一
  A2 两侧 VERDICT 覆盖 100%；VERDICT 可 json.loads
  A3 reserve（dpo_class=='reserve'）占比 ≤ 0.25
  A4 载体批占比 ≥ 0.15（修掉"DPO 无跨载体信号"的原始缺陷）
  A5 载体批覆盖 ≥5 类必备载体，且各 ≥600 行
  A6 两组件 schema 一致（conversations[{from,value}] + chosen/rejected{from,value}）
  A7 与门禁留出集（v0.2.1 / v0.3-gen / v0.4-toolout / v0.5-topup-families）id 零重叠
  A8 良性负例（dpo_class=='carrier_clean_overrefusal'）在载体批内占比 ≥0.20
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q = ROOT / "data" / "lf" / "dpo_m3_v2_q.jsonl"
CAR = ROOT / "data" / "lf" / "dpo_m3_carriers_v1.jsonl"
OUT = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
REPORT = ROOT / "reports" / "m3-final-mix-build.json"
REQ_CARRIERS = {"tool_output": 600, "log": 600, "webpage": 600, "code": 600, "document": 600}


def read(p: Path) -> list[dict]:
    rows = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def side_ok(v) -> bool:
    if not isinstance(v, str):
        return False
    tail = v.strip().splitlines()[-1] if v.strip() else ""
    if not tail.startswith("VERDICT:"):
        return False
    try:
        json.loads(tail[len("VERDICT:"):].strip())
        return True
    except Exception:  # noqa: BLE001
        return False


q_rows = read(Q)
car_rows = read(CAR)
fails: list[str] = []

# A1
if len(q_rows) != 22842:
    fails.append(f"A1 q 版行数 {len(q_rows)} != 22842")
if len(car_rows) != 6000:
    fails.append(f"A1 载体批行数 {len(car_rows)} != 6000")
all_rows = q_rows + car_rows
ids = [r.get("id") for r in all_rows]
dup = [k for k, v in Counter(ids).items() if v > 1]
if dup:
    fails.append(f"A1 id 重复 {len(dup)} 个，例如 {dup[:3]}")

# A2
bad = 0
for r in all_rows:
    if not (side_ok((r.get("chosen") or {}).get("value")) and
            side_ok((r.get("rejected") or {}).get("value"))):
        bad += 1
if bad:
    fails.append(f"A2 {bad} 行的 chosen 或 rejected 侧 VERDICT 缺失/不可解析")

n = len(all_rows)
# A3
reserve = sum(1 for r in all_rows if r.get("dpo_class") == "reserve")
rshare = reserve / n
if rshare > 0.25:
    fails.append(f"A3 reserve 占比 {rshare:.4f} > 0.25")
# A4
cshare = len(car_rows) / n
if cshare < 0.15:
    fails.append(f"A4 载体批占比 {cshare:.4f} < 0.15")
# A8
benign = sum(1 for r in car_rows if r.get("dpo_class") == "carrier_clean_overrefusal")
bshare = benign / len(car_rows)
if bshare < 0.20:
    fails.append(f"A8 良性负例占比 {bshare:.4f} < 0.20")
# A5 载体类别（从 prompt 文本里的 <carrier type="..."> 统计）
import re  # noqa: E402

CARRE = re.compile(r'<carrier\s+type="([a-z_]+)"')
cc = Counter()
for r in car_rows:
    txt = " ".join((m.get("value") or "") for m in (r.get("conversations") or []))
    for t in set(CARRE.findall(txt)):
        cc[t] += 1
for k, need in REQ_CARRIERS.items():
    if cc.get(k, 0) < need:
        fails.append(f"A5 载体 {k} 仅 {cc.get(k, 0)} 行 < {need}")
# A6 schema
for name, rows in (("q", q_rows), ("carriers", car_rows)):
    r0 = rows[0]
    for k in ("conversations", "chosen", "rejected", "id", "dpo_class", "lang", "pack"):
        if k not in r0:
            fails.append(f"A6 {name} 缺字段 {k}")
    for m in r0.get("conversations", []):
        if "from" not in m or "value" not in m:
            fails.append(f"A6 {name} conversations 元素缺 from/value")
            break
# A7
hold_ids: set[str] = set()
for sub in ("v0.2.1", "v0.3-gen", "v0.4-toolout", "v0.5-topup-families"):
    d = ROOT / "data" / "heldout" / sub
    if not d.exists():
        continue
    for p in d.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                hold_ids.add(json.loads(line).get("id"))
overlap = hold_ids & set(ids)
if overlap:
    fails.append(f"A7 与留出集 id 重叠 {len(overlap)} 条，例如 {sorted(overlap)[:3]}")

rep = {
    "components": {"dpo_m3_v2_q": len(q_rows), "dpo_m3_carriers_v1": len(car_rows)},
    "total_rows": n,
    "reserve_rows": reserve,
    "reserve_share": round(rshare, 4),
    "carrier_share": round(cshare, 4),
    "benign_negative_share_in_carriers": round(bshare, 4),
    "carrier_type_counts": dict(cc.most_common()),
    "dpo_class_counts": dict(Counter(r.get("dpo_class") for r in all_rows).most_common()),
    "lang_counts": dict(Counter(r.get("lang") for r in all_rows).most_common()),
    "pack_counts": dict(Counter(r.get("pack") for r in all_rows).most_common()),
    "rejected_candidates": ["dpo_m3_v2.jsonl (人造置信差)", "dpo_m3_v2_strict.jsonl (放弃质量梯度)"],
    "holdout_ids_checked": len(hold_ids),
    "fails": fails,
}
REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

if fails:
    print("M3-FINAL-MIX=FAIL")
    for x in fails:
        print("  -", x)
    sys.exit(1)

with OUT.open("w", encoding="utf-8") as g:
    for r in all_rows:
        g.write(json.dumps(r, ensure_ascii=False) + "\n")
print("M3-FINAL-MIX=PASS")
print(f"  写出 {OUT.name}：{n:,} 行 = 契约修复版 {len(q_rows):,} + 载体批 {len(car_rows):,}")
print(f"  reserve 占比 {rshare:.2%}（≤25%）｜载体批占比 {cshare:.2%}（≥15%）"
      f"｜良性负例 {bshare:.1%}（≥20%）")
print(f"  载体类别 {rep['carrier_type_counts']}")
print(f"  zh/en = {rep['lang_counts']}｜pack = {rep['pack_counts']}")
print(f"  留出集 id 核对 {len(hold_ids):,} 个，零重叠")
