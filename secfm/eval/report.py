"""评估报告渲染（markdown + JSONL；docs/01 §5.2 双指标纪律）。"""

from __future__ import annotations

import json

from .metrics import (expected_calibration_error, pareto_points,
                      policy_compliance_matrix)


def _fmt(x):
    return "n/a" if x is None else f"{x:.3f}"


def render_markdown(results, suite_name) -> str:
    lines = [
        f"# Eval report — {suite_name}", "",
        f"items: {len(results)}", "",
        "## Pareto（双指标纪律：ASR × 误拒，永不单指标）", "",
        "| domain | policy_pack | n | ASR | over-refusal | capability |",
        "|---|---|---|---|---|---|",
    ]
    for p in pareto_points(results):
        lines.append(
            f"| {p['domain']} | {p['policy_pack']} | {p['n']} | "
            f"{_fmt(p['asr'])} | {_fmt(p['over_refusal'])} | {_fmt(p['capability'])} |")
    lines += ["", f"ECE (calibration): {_fmt(expected_calibration_error(results))}", ""]
    mat = policy_compliance_matrix(results)
    if mat:
        lines += ["## 政策合规矩阵（同题跨政策）", ""]
        for g, packs in mat.items():
            lines += [
                f"### group: {g}",
                "| policy_pack | n | refusal_correct | verdict_correct |",
                "|---|---|---|---|",
            ]
            for pack, c in packs.items():
                lines.append(
                    f"| {pack} | {c['n']} | {c['refusal_correct']} | {c['verdict_correct']} |")
            lines.append("")
    return "\n".join(lines)


def to_jsonl(results) -> str:
    rows = []
    for r in results:
        rows.append(json.dumps({
            "id": r.item.id, "domain": r.item.domain, "kind": r.item.kind,
            "language": r.item.language, "policy_pack": r.item.policy_pack,
            "group": r.item.group, "response": r.response, "scores": r.scores,
        }, ensure_ascii=False))
    return "\n".join(rows)
