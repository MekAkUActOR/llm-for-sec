# -*- coding: utf-8 -*-
"""基线 v0 读数汇总（qa-m6）：baseline 输出 → 套件/红队指标 → markdown。

用法：m6_baseline_report.py --out reports/m6/qa-baseline-v0-<scope>.md \
         [--inputs frozen|dev|heldout|...]（预测文件按 reports/m6/preds/baseline-<x>-out.jsonl）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m6_metrics as M  # noqa: E402
from m6_acceptance import load_redteam, load_mapped, parse_infer_output, render_report  # noqa: E402

TASKS = M.TASKS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="frozen", help="frozen / full")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_path = Path(args.out) if args.out else Path(f"reports/m6/qa-baseline-v0-{args.scope}.md")

    groups: dict[str, list[dict]] = {}
    # 冻结套件 + 红队
    rt = load_redteam(Path("reports/m6/redteam/redteam-v1.jsonl"))
    fz = load_mapped()
    preds_fz = parse_infer_output(Path("reports/m6/preds/baseline-v0-out.jsonl"))
    # baseline-v0-out.jsonl 覆盖 红队+frozen 两个组（同一次跑）
    import m6_acceptance as A
    A.attach_preds(rt, preds_fz)
    A.attach_preds(fz, preds_fz)
    groups["redteam"] = rt
    groups["frozen"] = fz
    counts = {"redteam": len(rt), "frozen": len(fz)}

    # data/m6 各切分（若输出存在）
    for split in ["heldout", "challenge", "ood"]:
        p = Path(f"reports/m6/preds/baseline-{split}-out.jsonl")
        if p.exists():
            from m6_acceptance import load_m6_splits
            sp = load_m6_splits(Path("data/m6"))
            rows = sp.get(split, [])
            preds = parse_infer_output(p)
            A.attach_preds(rows, preds)
            groups[split] = rows
            counts[split] = len(rows)

    M.check_score_sanity(sum(groups.values(), []))
    g5 = M.gate_redteam(groups["redteam"])
    suite_ref = M.suite_reference(groups.get("frozen", []))
    g1 = M.gate_recall(groups.get("heldout", []))
    g2 = M.gate_fpr(groups.get("heldout", []))
    g3 = M.gate_challenge(groups.get("challenge", []))
    g4 = M.gate_ood(groups.get("ood", []), attack_rows=groups.get("heldout", []))
    vers = M.make_verdict(g1, g2, g3, g4, g5)

    extra = {"g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5,
             "suite_ref": suite_ref, "sensitivity": {}, "theta": {},
             "notes": [
                 "基线 v0 = m5a-r5 原样模型 logprob 判别（无探针头、无 OOD 抑制、abstain 恒 false）",
                 "score = softmax([logP(YES), logP(NO)])；flag 以 θ=0.5 参考切（正式对照用 dev 选点后读数）",
                 "判断模板冻结于本文件附录（双语，按行 lang 选择）；渲染与 M6 同管线（m6_render r5 chat_template）",
                 "模板附录：T1 内容风险/T2 越狱直接注入/T3 整体恶意意图/T4 PII 存在/T5 载体间接注入/T6 高危操作（详见 scripts/m6_baseline_v0.py JUDGE_EN/JUDGE_ZH 常量，冻结）",
                 "数值噪声披露：批内 bf16 前向的 padding 模式差异引入 score ~±0.03 不确定度（θ 边际样本 flag 可能翻转；对照线用途可接受，主验收门不受影响——M6 探针头无此问题）",
             ]}
    report = render_report(vers, tag=f"baseline-v0-{args.scope}",
                           model_head="checkpoints/qwen3-06b-sec-m5a-dpo-r5（基线 v0）",
                           stub=False, runpoint=None, counts=counts, extra=extra)
    out_path.write_text(report, encoding="utf-8", newline="\n")
    print(f"verdict={vers['verdict']} -> {out_path}")


if __name__ == "__main__":
    main()
