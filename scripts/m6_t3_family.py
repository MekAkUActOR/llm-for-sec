# -*- coding: utf-8 -*-
"""T3 heldout 族分解（arch 裁定：v2 验收的 T3 以 heldout 平面读数为准，按族细分）。

族映射（id 前缀）：
  m6-t3-legacy -> r9-paired（legacy 池）
  m6-t3m       -> multiturn
  m6-t3l       -> longctx
  m6-doclong   -> doc-intent
"""
import json
import sys
from pathlib import Path

FAMILY = {
    "m6-t3-legacy": "r9-paired",
    "m6-t3m": "multiturn",
    "m6-t3l": "longctx",
    "m6-doclong": "doc-intent",
}


def fam_of(rid: str) -> str:
    for p, f in FAMILY.items():
        if rid.startswith(p + "-"):
            return f
    return "other"


def main(run_dir: str) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from m6_acceptance import parse_infer_output, load_m6_splits, attach_preds

    snap = Path(run_dir) / "labels-heldout.jsonl"
    if snap.exists():  # run 时快照优先（行集与该 run 的推理一致；D 波扩容后旧 run 用旧行集）
        ho = [json.loads(l) for l in snap.open(encoding="utf-8") if l.strip()]
    else:
        ho = load_m6_splits(Path("data/m6"))["heldout"]
    preds = parse_infer_output(Path(run_dir) / "out-heldout.jsonl")
    attach_preds(ho, preds)

    fams = {}
    for r in ho:
        if r["labels"].get("T3") != 1:
            continue
        f = fam_of(r["id"])
        fams.setdefault(f, {"n": 0, "det": 0})
        fams[f]["n"] += 1
        # 口径对齐 G1（flag-only：m6_infer 注入 θ 后的 logit 域判定）
        fams[f]["det"] += 1 if r["pred"]["tasks"]["T3"]["flag"] else 0
    print(f"T3 heldout 族分解（flag-only，G1 口径）：")
    for f, d in sorted(fams.items(), key=lambda x: -x[1]["n"]):
        print(f"  {f:12s} {d['det']:4d}/{d['n']:4d} = {d['det']/d['n']*100:.1f}%")
    tot = sum(d["det"] for d in fams.values()), sum(d["n"] for d in fams.values())
    print(f"  {'合计':12s} {tot[0]:4d}/{tot[1]:4d} = {tot[0]/tot[1]*100:.1f}%")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
