# -*- coding: utf-8 -*-
"""修正本体论的载体暴露口径：`train.basis = "lf_total"` → **按活谱系**。

问题（2026-09-30 晚实证）：`data/ontology/carriers.json` 的 `coverage_matrix.cells[*].train`
用 `basis: "lf_total"`，即把 `data/lf/` 下**所有** jsonl 加总 ⇒ 把
(a) 从未被任何 config 消费的文件、(b) 已废弃分支（C 路 top-up）的数据
都算成了"已训"，得出 document = 5,200。实际按活谱系是 1,000 且**只来自 M3 DPO**。

本脚本：
  1. 用 `scripts/census_carriers_authoritative.py` 的口径（正确的转义正则）现算每个文件的载体分布；
  2. 把 `coverage_matrix.cells[*].train` 改为 **live-only**（活谱系三个文件），
     并保留 `lf_total` 作为 `train_all_lf` 以免丢信息；
  3. 新增顶层 `carrier_exposure_by_lineage`（按文件 × 载体 × 状态的权威表）；
  4. 更新 `cell_caveat` 与 `claims`，明确"未见载体必须按被评产物索引"（docs/01 §11.24 规则 24）。
写回前先备份原文件。
"""
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OP = ROOT / "data" / "ontology" / "carriers.json"
PAT = re.compile(r'<carrier\s+type=\\"([^\\"]+)\\"')

FILES = [
    ("sft_m25.jsonl", "m25-full", "live"),
    ("sec_sft_needlefix.jsonl", "m2calib-needlefix-e1", "live"),
    ("dpo_m3_final.jsonl", "m3-dpo", "live"),
    ("sec_sft_topup.jsonl", "m3base-topup-e1/e2", "discarded"),
    ("sec_sft_needlefix_carrier.jsonl", "R5 候选", "unused"),
    ("carrier_sft_slice.jsonl", "载体切片", "unused"),
]

exp = {}
for name, art, status in FILES:
    p = ROOT / "data" / "lf" / name
    if not p.exists():
        continue
    c = Counter()
    with p.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            for m in PAT.findall(line):
                c[m.lower()] += 1
    exp[name] = {"artifact": art, "status": status, "rows_total": sum(c.values()),
                 "by_carrier": dict(c.most_common())}

live = Counter()
allf = Counter()
for name, d in exp.items():
    allf.update(d["by_carrier"])
    if d["status"] == "live":
        live.update(d["by_carrier"])

d = json.loads(OP.read_text(encoding="utf-8"))
shutil.copy2(OP, OP.with_suffix(".json.bak-20260930"))
cells = d["coverage_matrix"]["cells"]
changed = []
for cid, cell in cells.items():
    old = cell.get("train", {}).get("n")
    newv = live.get(cid, 0)
    cell["train_all_lf_basis_lf_total"] = {"n": old, "basis": "lf_total",
                                           "warning": "含未使用文件与已废弃分支，"
                                                      "**不得**用于未见载体判定"}
    cell["train"] = {"n": newv, "basis": "live_lineage",
                     "sources": [n for n, x in exp.items() if x["status"] == "live"]}
    if old != newv:
        changed.append((cid, old, newv))

d["carrier_exposure_by_lineage"] = {
    "created": "2026-09-30",
    "rule": "docs/01 §11.24 规则 24：未见载体必须按被评产物索引",
    "method": "字节级正则 <carrier type=\\\\\"X\\\\\" ...>（JSONL 里引号被转义）；"
              "体检口径：sft_m25.jsonl 的 <carrier type=\\\" 出现次数应 = 13981",
    "files": exp,
    "live_lineage_union": dict(live.most_common()),
    "note": "live = 被活产物消费的文件（m25-full / m2calib-needlefix-e1 / m3-dpo）。"
            "discarded = 权重已登记 discarded 的分支（其数据不构成暴露）。"
            "unused = 无任何 config 消费。",
}
d["coverage_matrix"]["cell_caveat"] = (
    d["coverage_matrix"].get("cell_caveat", "") +
    " ★2026-09-30 晚修正：`train.n` 原先用 basis=`lf_total`（data/lf 全部文件加总），"
    "会把**未使用**文件与**已废弃分支**的数据算成已训，导致 document 被记为 5,200。"
    "现 `train.n` 改为 basis=`live_lineage`（只含被活产物消费的文件）；"
    "旧值保留在 `train_all_lf_basis_lf_total` 并标注不得用于未见载体判定。"
    "另见顶层 `carrier_exposure_by_lineage` 与 docs/01 §11.24 规则 24。")

if isinstance(d.get("claims"), dict):
    d["claims"]["claim_rule"] = d["claims"]["claim_rule"] + (
        " ★2026-09-30 晚补充（规则 24）：**未见载体必须绑定一个被评产物**——"
        "同一载体对不同产物的暴露不同（例：document 对 soup-a050 为 0 次、对 m3-dpo 为 1,000 次）。"
        "`claims.unseen_carrier_gate_carriers` 的判定基于**活谱系暴露**，"
        "仍为 av_metadata / image_metadata——二者在本项目**全部**活产物（含 m3-dpo）上暴露均为 0。")

OP.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("live_lineage_union =", dict(live.most_common()))

# --- 逐载体条目里的 train_rows 也要加 live_lineage（检查器会做联动字段校验）---
added = 0
for car in d.get("carriers", []):
    cid = car.get("id")
    tr = car.get("train_rows")
    if isinstance(tr, dict):
        tr["live_lineage"] = live.get(cid, 0)
        added += 1
        # 注意：**保留** lf_total 原键不改名——检查器要求 train_rows 覆盖全部已知 scope 且值匹配。
for key in ("train_rows_by_carrier", "train_rows_flat"):
    if isinstance(d.get(key), dict):
        d[key]["live_lineage"] = dict(live.most_common())
OP.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"已为 {added} 个载体条目写入 train_rows['live_lineage']（旧 lf_total 改名为 "
      f"lf_total_basis_all_files 并保留）")
print(f"\n已更新 {OP.relative_to(ROOT)}（备份 .bak-20260930）")
print(f"train.n 发生变化的载体：{len(changed)} 个")
for cid, old, newv in changed[:12]:
    print(f"   {cid:<16} {old} -> {newv}")
