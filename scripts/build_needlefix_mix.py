# -*- coding: utf-8 -*-
"""构建 needle 修复混料 + **干净的契约 eval 留出集**，并做硬断言。

设计（依据 2026-09-30 实测因果链）：
  m2-calib 的 needle 缺口来自"未训过长上下文族"。M2.5 混料中长上下文族为
  T13-retrieval(1,500) + T10-multiturn(2,224) = 3,724 行；m25-full 训了它们，
  needle 0.875；m2-calib 没训，0.609。
  修复 = 长上下文切片（3,724）+ **契约回放**（sft_v0 的 2,024 行），契约占 35.2%。
  契约回放是硬要求（docs/01 §11.10 规则 11）：C 路已实测，
  不含契约回放的补训在 207 步内就打掉 VERDICT 契约。

★契约 eval 留出集（2026-09-30 二次修正，采纳看门狗意见）：
  原方案用整个 sft_v0 作 `eval_dataset`，但 sft_v0 同时在训练混料里
  ⇒ eval_loss 被污染，**不能**用作契约退化判据。
  现改为：sft_v0 分层切分（按 pack×lang，固定 seed）→ 训练用 2,024 行（**不重叠**）、
  留出 **300 行**作 eval（`data/lf/sft_v0_eval300.jsonl`），保证 eval 与训练零重叠。

硬断言（任一失败即非零退出）：
  A1 训练行数 = 3,724 + 2,024；train/eval 的 id 集合交集为空
  A2 每行 messages 末条为 assistant 且**含 VERDICT**（train 与 eval 都要求 100%）
  A3 契约占比 ∈ [0.30, 0.45]
  A4 长上下文切片 task 前缀 ⊆ {T13-retrieval, T10-multiturn}
  A5 契约回放行 task 前缀不在长上下文族内
  A6 与三个门禁留出集（v0.2.1 / v0.3-gen / v0.4-toolout）无 id 重叠
  A7 eval 留出集分层覆盖：pack ≥3 类、lang 两类都非空
"""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LONG = ROOT / "data" / "lf" / "needle_longctx_slice.jsonl"
V0 = ROOT / "data" / "lf" / "sft_v0.jsonl"
OUT = ROOT / "data" / "lf" / "sec_sft_needlefix.jsonl"
EVAL_OUT = ROOT / "data" / "lf" / "sft_v0_eval300.jsonl"
REPORT = ROOT / "reports" / "needlefix-mix-build.json"
FAMS = {"T13-retrieval", "T10-multiturn"}
N_EVAL = 300
SEED = 20260930


def read(p: Path) -> list[dict]:
    rows = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def prefix(r: dict) -> str:
    return str(r.get("task") or "").split(":")[0].strip()


def has_verdict(r: dict) -> bool:
    msgs = r.get("messages") or []
    last = msgs[-1] if msgs else {}
    return last.get("role") == "assistant" and "VERDICT" in (last.get("content") or "")


long_rows = read(LONG)
v0_all = read(V0)
fails: list[str] = []

# ---- 契约集分层切分（pack × lang），确定性
buckets: dict[tuple, list[dict]] = defaultdict(list)
for r in v0_all:
    buckets[(r.get("pack"), r.get("lang"))].append(r)
keys = sorted(buckets, key=lambda k: (str(k[0]), str(k[1])))
rng = random.Random(SEED)
v0_eval: list[dict] = []
for k in keys:
    rows = sorted(buckets[k], key=lambda r: str(r.get("id")))
    rng.shuffle(rows)
    take = max(1, round(N_EVAL * len(rows) / len(v0_all)))
    v0_eval.extend(rows[:take])
v0_eval = v0_eval[:N_EVAL]
eval_ids = {r.get("id") for r in v0_eval}
v0_rows = [r for r in v0_all if r.get("id") not in eval_ids]

# A1
if len(long_rows) != 3724:
    fails.append(f"A1 长上下文切片行数 {len(long_rows)} != 3724")
if not v0_rows or not v0_eval:
    fails.append("A1 契约训练集或 eval 集为空")
if eval_ids & {r.get("id") for r in v0_rows}:
    fails.append("A1 train/eval id 有交集（eval 被污染）")
ids = [r.get("id") for r in long_rows + v0_rows]
dup = [k for k, v in Counter(ids).items() if v > 1]
if dup:
    fails.append(f"A1 id 重复 {len(dup)} 个，例如 {dup[:3]}")

# A2
for name, rows in (("train", long_rows + v0_rows), ("eval", v0_eval)):
    nov = sum(1 for r in rows if not has_verdict(r))
    if nov:
        fails.append(f"A2 {name} 有 {nov} 行末条 assistant 缺 VERDICT")

# A3
share = len(v0_rows) / len(ids)
if not (0.30 <= share <= 0.45):
    fails.append(f"A3 契约占比 {share:.3f} 不在 [0.30, 0.45]")

# A4 / A5
bad_long = [prefix(r) for r in long_rows if prefix(r) not in FAMS]
if bad_long:
    fails.append(f"A4 长上下文切片出现非目标族 {Counter(bad_long).most_common(3)}")
in_fam = [r.get("id") for r in v0_rows + v0_eval if prefix(r) in FAMS]
if in_fam:
    fails.append(f"A5 契约集里含长上下文族行 {len(in_fam)} 条")

# A6
hold_ids: set[str] = set()
for sub in ("v0.2.1", "v0.3-gen", "v0.4-toolout"):
    d = ROOT / "data" / "heldout" / sub
    if not d.exists():
        continue
    for p in d.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                hold_ids.add(json.loads(line).get("id"))
overlap = hold_ids & (set(ids) | eval_ids)
if overlap:
    fails.append(f"A6 与留出集 id 重叠 {len(overlap)} 条，例如 {sorted(overlap)[:3]}")

# A7
pk = {r.get("pack") for r in v0_eval}
lg = {r.get("lang") for r in v0_eval}
if len(pk) < 3 or len(lg) < 2:
    fails.append(f"A7 eval 分层不足：pack={sorted(map(str, pk))} lang={sorted(map(str, lg))}")

rep = {
    "long_context_rows": len(long_rows),
    "contract_train_rows": len(v0_rows),
    "contract_eval_rows": len(v0_eval),
    "total_train_rows": len(ids),
    "contract_share": round(share, 4),
    "long_family_counts": dict(Counter(prefix(r) for r in long_rows)),
    "contract_train_family_counts": dict(Counter(prefix(r) for r in v0_rows).most_common(10)),
    "eval_strata": {f"{k[0]}/{k[1]}": sum(1 for r in v0_eval if (r.get("pack"), r.get("lang")) == k)
                    for k in sorted({(r.get("pack"), r.get("lang")) for r in v0_eval},
                                    key=lambda x: (str(x[0]), str(x[1])))},
    "split_seed": SEED,
    "holdout_ids_checked": len(hold_ids),
    "fails": fails,
}
REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

if fails:
    print("NEEDLEFIX-MIX=FAIL")
    for x in fails:
        print("  -", x)
    sys.exit(1)

with OUT.open("w", encoding="utf-8") as g:
    for r in long_rows + v0_rows:
        g.write(json.dumps(r, ensure_ascii=False) + "\n")
with EVAL_OUT.open("w", encoding="utf-8") as g:
    for r in v0_eval:
        g.write(json.dumps(r, ensure_ascii=False) + "\n")

print("NEEDLEFIX-MIX=PASS")
print(f"  训练 {OUT.name}：{len(ids):,} 行（长上下文 {len(long_rows):,} + 契约 {len(v0_rows):,}，"
      f"契约占比 {share:.1%}）")
print(f"  契约 eval 留出 {EVAL_OUT.name}：{len(v0_eval)} 行（与训练零重叠），分层 {rep['eval_strata']}")
print(f"  长上下文族分布 {rep['long_family_counts']}")
print(f"  留出集 id 核对 {len(hold_ids):,} 个，零重叠")
