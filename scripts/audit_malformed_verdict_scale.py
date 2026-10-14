# -*- coding: utf-8 -*-
"""量化 toolout 仪器对"畸形 VERDICT 恢复"（`action recovered`）的依赖度。

背景（本脚本回答的问题）：`reports/s0.4-g1-instrument-repair.md` §8 把
"判分器对畸形 VERDICT 的恢复逻辑（`action recovered`）误判率**未被任何人审标定**"
登记为**S0.4 修复最大的残留不确定性**。在审计它之前，先量出它**管多少条读数**。

判分器在 `note` 里写 `malformed VERDICT, action recovered`、在 `evidence` 里写
`recovered action=<action>`；即该条目的 `label` **不是**由模型输出的规范 VERDICT 决定，
而是由恢复逻辑决定的。

用法：python scripts/audit_malformed_verdict_scale.py [--dump N]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--dump", type=int, default=0,
                help="额外导出 N 条样本（含响应正文）到 reports/malformed-verdict-sample.json 供人审")
a = ap.parse_args()


def is_recovered(r):
    return ("malformed" in str(r.get("note", "")).lower()
            or "recovered" in str(r.get("evidence", "")).lower())


rows = []
for f in sorted((ROOT / "reports").glob("scored-chat-to-*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    rs = [r for r in d.get("items", []) if r.get("responded")]
    rob = [r for r in rs if r.get("kind") == "robustness"]
    rec = [r for r in rob if is_recovered(r)]
    k = sum(1 for r in rob if r.get("derived", {}).get("attack_success"))
    krec = sum(1 for r in rec if r.get("derived", {}).get("attack_success"))
    rows.append((f.name, len(rob), k, len(rec), krec))

tag = lambda n: n.replace("scored-chat-to-", "").replace("-v2.json", "")  # noqa: E731
print(f"{'tag':<12} {'鲁棒n':>6} {'顺从k':>6} {'恢复条数':>9} {'其中顺从':>9} {'恢复占比':>9}")
for n, nr, k, nrec, krec in rows:
    print(f"{tag(n):<12} {nr:>6} {k:>6} {nrec:>9} {krec:>9} "
          f"{nrec / max(nr, 1) * 100:>8.0f}%")

tot_n = sum(r[1] for r in rows)
tot_rec = sum(r[3] for r in rows)
tot_k = sum(r[2] for r in rows)
tot_krec = sum(r[4] for r in rows)
print(f"\n合计：鲁棒性条目 {tot_n}，其中**依赖恢复逻辑** {tot_rec} "
      f"（{tot_rec / max(tot_n, 1) * 100:.0f}%）")
print(f"      全部顺从 {tot_k} 条，其中**来自恢复条目** {tot_krec} "
      f"（{tot_krec / max(tot_k, 1) * 100:.0f}%）")
print("\n⇒ 判读：恢复条目占比越高，ASR 读数越由**恢复逻辑的准确率**而非模型行为决定。")

if a.dump:
    samp = []
    for f in sorted((ROOT / "reports").glob("scored-chat-to-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d.get("items", []):
            if r.get("responded") and r.get("kind") == "robustness" and is_recovered(r):
                samp.append({"tag": tag(f.name), "id": r.get("id"),
                             "label": r.get("label"), "note": r.get("note"),
                             "evidence": r.get("evidence"),
                             "attack_success": r.get("derived", {}).get("attack_success")})
    out = ROOT / "reports" / "malformed-verdict-sample.json"
    out.write_text(json.dumps(samp[:a.dump], ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n已导出 {min(len(samp), a.dump)} 条到 {out.relative_to(ROOT)}")
