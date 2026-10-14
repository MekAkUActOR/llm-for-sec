# -*- coding: utf-8 -*-
"""把 v0.6-document 登记进 data/ontology/carriers.json（用户裁决：选项 B，按模型分角色）。

做法是**外科式合并**而非整体替换：
  - `instruments`：只按现算结果更新被检查的键（rows/kind/lang/per_carrier/
    per_carrier_robustness/untagged_rows/role），并为 v0.6-document 新增条目；
  - 每个载体的 `gate_items`：按现算补齐/更新各 scope 计数（含新增的 v0.6-document）；
  - `coverage_matrix.cells`：更新被检查的列（n/basis/robustness_n），
    **保留**本体里计算不出的额外字段（如 train_all_lf_basis_lf_total 及其 warning）；
  - `coverage_matrix.columns`：补上新列标签。

幂等：连跑两次结果一致。
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_carrier_ontology as C  # noqa: E402

P = ROOT / "data" / "ontology" / "carriers.json"
CHECKED_INST_KEYS = ("rows", "kind", "lang", "per_carrier",
                     "per_carrier_robustness", "untagged_rows", "role")


def main() -> int:
    onto = json.loads(P.read_text(encoding="utf-8"))
    facts = C.collect_facts()
    finst = facts.get("instruments") or {}
    fcm = facts.get("coverage_matrix") or {}
    fgate = facts.get("gate_items") or {}

    changed = []

    # --- 1. instruments ---
    o_inst = onto.setdefault("instruments", {})
    for name, want in finst.items():
        got = o_inst.get(name)
        if not isinstance(got, dict):
            o_inst[name] = dict(want)
            changed.append(f"instruments+{name}")
            continue
        for k in CHECKED_INST_KEYS:
            if got.get(k) != want.get(k):
                got[k] = want.get(k)
                changed.append(f"instruments.{name}.{k}")
        # 便于消费的附加字段（不参与校验，缺失也可）
        for k in ("role_by_model", "role_merged"):
            if k in want and got.get(k) != want.get(k):
                got[k] = want.get(k)
    for name in sorted(set(o_inst) - set(finst)):
        # 本体有、现算无 ⇒ 校验会报 instrument_unknown；这里直接删掉并记录
        del o_inst[name]
        changed.append(f"instruments-{name}")

    # --- 2. 每个载体的 gate_items ---
    for car in onto.get("carriers", []):
        cid = car.get("id")
        want = fgate.get(cid) or {}
        gi = car.setdefault("gate_items", {})
        for name in C.GATE_SCOPES:
            w = want.get(name, 0)
            if gi.get(name) != w:
                gi[name] = w
                changed.append(f"gate_items.{cid}.{name}")
        for name in sorted(set(gi) - set(C.GATE_SCOPES)):
            del gi[name]
            changed.append(f"gate_items-{cid}.{name}")

    # --- 3. coverage_matrix.cells（合并，不整体替换）---
    cm = onto.setdefault("coverage_matrix", {})
    cells = cm.setdefault("cells", {})
    for cid, wcols in fcm.items():
        got = cells.setdefault(cid, {})
        for col, wcell in wcols.items():
            g = got.get(col)
            if not isinstance(g, dict):
                got[col] = dict(wcell)
                changed.append(f"cells.{cid}.{col}+")
                continue
            for k, v in wcell.items():
                if g.get(k) != v:
                    g[k] = v
                    changed.append(f"cells.{cid}.{col}.{k}")

    # --- 4. coverage_matrix.columns ---
    cols = cm.setdefault("columns", {})
    for col, spec in C.MATRIX_COLUMNS.items():
        lab = spec["label"]
        if cols.get(col) != lab:
            cols[col] = lab
            changed.append(f"columns.{col}")

    if not changed:
        print("ONTOLOGY-REGISTER=SKIP（无需改动，幂等）")
        return 0

    bak = P.with_suffix(".json.bak-before-v06-document")
    if not bak.exists():
        bak.write_text(P.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"备份 -> {bak.name}")
    P.write_text(json.dumps(onto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ONTOLOGY-REGISTER=APPLIED 改动 {len(changed)} 处：")
    for c in changed[:30]:
        print(f"    {c}")
    if len(changed) > 30:
        print(f"    … 另有 {len(changed)-30} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
