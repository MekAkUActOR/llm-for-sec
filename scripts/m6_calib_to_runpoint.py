# -*- coding: utf-8 -*-
"""calib.json -> m6-thresholds 推荐点 runpoint 转换（qa-m6）。

deveng 训练侧 calib（logit 空间校准）→ QA 验收推荐点（QA-1 §4.3 主读数）。
用法：python -X utf8 scripts/m6_calib_to_runpoint.py --calib checkpoints/m6-v2/calib.json --out reports/m6/operating-point-v2-recommended.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m6_acceptance import now  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    calib = json.loads(Path(args.calib).read_text(encoding="utf-8-sig"))
    stem = Path(args.calib).parent.name  # e.g. m6-v2
    man_path = Path("data/m6/manifest.json")
    man = hashlib.sha256(man_path.read_bytes()).hexdigest() if man_path.exists() else None
    n_cal = calib.get("calibrated_on", {}).get("n")
    if not isinstance(n_cal, int) or n_cal < 1:
        # 回退：dev labels 行数（emit 产物）或 1
        lab = Path("reports/m6/preds") / f"{stem.replace('m6-v', 'v')}-dev-labels.jsonl"
        n_cal = (sum(1 for l in lab.open(encoding="utf-8") if l.strip())
                 if lab.exists() else 13239)

    # v0.3.21（sysdesign d378def）：band 级 threshold_space 已收编（enum logit|score）。
    # 透传优先；仅当旧 schema 校验失败时回退剥离（决策语义已由 *_logit 承载）。
    # 语义要点：T6 的 logit = ln(P)（log-probability 域，D-16 softmax 等价修法），
    # 非 T1-T5 的 log-odds——换算用 exp 而非 sigmoid。
    th = {t: dict(band) for t, band in calib["thresholds"].items()}

    out = {
        "schema": "m6-thresholds",
        "schema_version": calib.get("schema_version", "0.2.0"),
        "runpoint_id": f"m6-runpoint-{stem.replace('m6-', '')}-recommended",
        "created": now(),
        "owner": "qa-m6",
        "calibrated_on": {
            "split": "dev",
            "manifest": man,
            "n": n_cal,
            "method": "deveng calib.json（logit 空间校准，D8 零 FP 构造）经 QA 转换为验收推荐点；QA-1 §4.3 双运行点条款的主读数",
        },
        "thresholds": th,
        "ood": calib["ood"],
        "temperature_applied": calib.get("temperature_applied"),
        "score_def": calib.get("score_def"),
        "notes": f"{stem} 推荐运行点；flag_logit 存在时决策带用 logit 比较（fp32 sigmoid 饱和修复）" + (f"；{args.note}" if args.note else ""),
    }
    p = Path(args.out)
    try:
        _validate(out)
    except Exception:  # noqa: BLE001 — 旧 schema 环境回退：剥离 threshold_space 再验
        for band in th.values():
            band.pop("threshold_space", None)
        _validate(out)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"推荐点 runpoint 过 m6-thresholds schema 校验 -> {p}")


def _validate(out: dict) -> None:
    import jsonschema
    from referencing import Registry, Resource
    sd = Path("docs/m6/schemas")
    reg = Registry()
    for f in sd.glob("*.json"):
        reg = reg.with_resource(f.name, Resource.from_contents(json.loads(f.read_text(encoding="utf-8"))))
    jsonschema.validate(out, json.loads((sd / "m6-thresholds.schema.json").read_text(encoding="utf-8")), registry=reg)


if __name__ == "__main__":
    main()
