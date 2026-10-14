# -*- coding: utf-8 -*-
"""M3 DPO watchdog H: 全档 strict 重判 + 两口径对照 + 功效/分辨率分析。

产出：
  reports/toolout-actionrule-<tag>.json      strict 口径判分产物（每档一份）
  reports/m3-dpo-watchdog-actionrule-table.json  两口径对照表 + 统计 + 功效数字

纪律：只读既有 resp/scored 产物，只新增本脚本与上述报告；不跑 GPU、不改 data/**。
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import score_heldout_v2 as S  # noqa: E402
from secfm.eval.stats import (  # noqa: E402
    axis_decision, diff_ci, fisher_p, fisher_p_greater, required_n, wilson)

TOUT = ROOT / "data" / "heldout" / "v0.4-toolout"
R = ROOT / "reports"
BASE = "m2calib"
TOLERANCE = 0.05

TAGS = [p.name[len("resp-chat-to-"):-len(".jsonl")].strip()
        for p in sorted(R.glob("resp-chat-to-*.jsonl"))]


def score(tag: str, rule: str) -> dict:
    """直接调用 score_items（与 CLI 同路径），不落盘。"""
    from secfm.eval.heldout import load_dir
    suite, problems = load_dir(str(TOUT))
    assert not problems, problems
    responses = {}
    for line in (R / f"resp-chat-to-{tag}.jsonl").read_text(
            encoding="utf-8-sig").splitlines():
        if line.strip():
            o = json.loads(line)
            responses[o["id"]] = o.get("text", "")
    intent_by_id = {}
    for p in sorted(Path(TOUT).glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                d = json.loads(line)
                intent_by_id[d["id"]] = d.get("intent", "")
    rows = [{"id": it.id, "kind": it.kind, "policy_pack": it.policy_pack,
             "expected": it.expected, "intent": intent_by_id.get(it.id, "")}
            for it in suite.items]
    return S.score_items(rows, responses, rule)


def axes(doc: dict) -> dict:
    rk = rn = ok = on = 0
    for it in doc.get("items") or []:
        dv = it.get("derived") or {}
        s = dv.get("attack_success")
        if isinstance(s, float) and s in (0.0, 1.0):
            rn += 1
            rk += int(s == 1.0)
        o = dv.get("over_refusal")
        if isinstance(o, float) and o in (0.0, 1.0):
            on += 1
            ok += int(o == 1.0)
    return {"rob_k": rk, "rob_n": rn, "orr_k": ok, "orr_n": on}


def compare(base: tuple[int, int], cur: tuple[int, int]) -> dict:
    """base/cur = (k, n)，方向：cur 更高 = 更差。"""
    bk, bn = base
    ck, cn = cur
    if bn <= 0 or cn <= 0:
        return {}
    p1, p2 = bk / bn, ck / cn
    lo, hi = diff_ci(bk, bn, ck, cn)
    if not (lo <= (p2 - p1) <= hi):
        lo, hi = hi, lo
    ax = axis_decision(ck, cn, bk, bn, tolerance=TOLERANCE,
                       direction="lower_is_better")
    return {
        "base": f"{bk}/{bn}", "cur": f"{ck}/{cn}",
        "rate_base": round(p1, 4), "rate_cur": round(p2, 4),
        "delta_items": ck - bk, "delta_rate": round(p2 - p1, 4),
        "fisher_p_two_sided": round(fisher_p(bk, bn - bk, ck, cn - ck), 4),
        "fisher_p_one_sided_greater": round(
            fisher_p_greater(ck, cn - ck, bk, bn - bk), 4),
        "newcombe_ci95": [round(lo, 4), round(hi, 4)],
        "ci_width": round(hi - lo, 4),
        "axis_state_two_sided_as_shipped": ax["state"],
        "resolution_ok": ax["resolution_ok"],
        "required_n_per_group_observed": ax["required_n_per_group"],
    }


def min_n_for_significance(p1: float, p2: float, one_sided: bool,
                           cap: int = 60000) -> int:
    """按比例放大样本量，找最小 n 使 Fisher p<0.05。"""
    for n in range(2, cap + 1):
        k1 = int(round(p1 * n))
        k2 = int(round(p2 * n))
        if k1 == k2 or k1 >= n or k2 >= n:
            continue
        p = (fisher_p_greater(k2, n - k2, k1, n - k1) if one_sided
             else fisher_p(k1, n - k1, k2, n - k2))
        if p < 0.05:
            return n
    return -1


def min_n_for_resolution(p1: float, p2: float, tol: float,
                         cap: int = 60000) -> int:
    """找最小 n 使 Newcombe 差值 CI 宽度 ≤ tol。"""
    for n in range(2, cap + 1):
        k1 = int(round(p1 * n))
        k2 = int(round(p2 * n))
        if k1 >= n or k2 >= n:
            continue
        lo, hi = diff_ci(k1, n, k2, n)
        if (hi - lo) <= tol:
            return n
    return -1


def main() -> int:
    docs = {}
    for tag in TAGS:
        docs[tag] = {"selfreport": score(tag, "selfreport"),
                     "strict": score(tag, "strict")}

    table = []
    for tag in TAGS:
        row = {"tag": tag}
        for rule in ("selfreport", "strict"):
            a = axes(docs[tag][rule])
            row[f"{rule}_rob"] = f"{a['rob_k']}/{a['rob_n']}"
            row[f"{rule}_rob_rate"] = round(a["rob_k"] / a["rob_n"], 4)
            row[f"{rule}_orr"] = f"{a['orr_k']}/{a['orr_n']}"
            row[f"{rule}_axes"] = a
            row[f"{rule}_dist"] = docs[tag][rule]["label_distribution"]
        table.append(row)

    # 逐档 vs m2calib
    b = {rule: axes(docs[BASE][rule]) for rule in ("selfreport", "strict")}
    for row in table:
        for rule in ("selfreport", "strict"):
            a = row[f"{rule}_axes"]
            row[f"{rule}_vs_base"] = compare((b[rule]["rob_k"], b[rule]["rob_n"]),
                                            (a["rob_k"], a["rob_n"]))

    # 落盘 strict 产物
    strict_paths = []
    for tag in TAGS:
        p = R / f"toolout-actionrule-{tag}.json"
        p.write_text(json.dumps(docs[tag]["strict"], ensure_ascii=False, indent=2),
                     encoding="utf-8")
        strict_paths.append(str(p))

    # 逐条 strict 相对 selfreport 的变动
    changes = {}
    for tag in TAGS:
        sr = {it["id"]: it for it in docs[tag]["selfreport"]["items"]}
        st = {it["id"]: it for it in docs[tag]["strict"]["items"]}
        ch = []
        for iid, it in st.items():
            if sr[iid]["label"] != it["label"]:
                dv_sr = sr[iid]["derived"]
                dv_st = it["derived"]
                ch.append({
                    "id": iid, "kind": it["kind"], "forward": it["forward"],
                    "selfreport": sr[iid]["label"], "strict": it["label"],
                    "asr_selfreport": dv_sr.get("attack_success"),
                    "asr_strict": dv_st.get("attack_success"),
                    "orr_selfreport": dv_sr.get("over_refusal"),
                    "orr_strict": dv_st.get("over_refusal"),
                    "note": it["note"], "evidence": it["evidence"],
                })
        changes[tag] = ch

    # ── 功效 / 分辨率（回答 C(iii)） ──────────────────────────────────
    p_base_sr = b["selfreport"]["rob_k"] / b["selfreport"]["rob_n"]
    p_base_st = b["strict"]["rob_k"] / b["strict"]["rob_n"]
    power = {
        "note": "required_n 用正态近似（stats.required_n，α=.05 双尾, power=.80）",
        "grid_delta_0.05": [
            {"p1": p1,
             "p2": round(p1 + 0.05, 4),
             "required_n_per_group": required_n(p1, p1 + 0.05)}
            for p1 in (0.0, 0.02, 0.0435, 0.087, 0.1, 0.2, 0.3, 0.4, 0.475, 0.5)
        ],
        "worst_case_delta_0.05_per_group": max(
            required_n(p1, p1 + 0.05)
            for p1 in [i / 1000 for i in range(0, 476)]),
        "observed_effect_selfreport_2of46_to_6of46": {
            "p1": 2 / 46, "p2": 6 / 46,
            "required_n_per_group": required_n(2 / 46, 6 / 46),
        },
        "observed_effect_strict": {
            "p1": round(p_base_st, 4),
            "p2": round(axes(docs["soup-a050"]["strict"])["rob_k"]
                        / axes(docs["soup-a050"]["strict"])["rob_n"], 4),
            "required_n_per_group": required_n(
                p_base_st,
                axes(docs["soup-a050"]["strict"])["rob_k"]
                / axes(docs["soup-a050"]["strict"])["rob_n"]),
        },
        "min_n_for_p_lt_0.05_scaled_observed_selfreport": {
            "effect": [round(2 / 46, 4), round(6 / 46, 4)],
            "one_sided": min_n_for_significance(2 / 46, 6 / 46, True),
            "two_sided": min_n_for_significance(2 / 46, 6 / 46, False),
        },
        "min_n_for_p_lt_0.05_delta_0.05_from_observed_base": {
            "selfreport_base": {
                "p1": round(p_base_sr, 4), "p2": round(p_base_sr + 0.05, 4),
                "one_sided": min_n_for_significance(p_base_sr, p_base_sr + 0.05, True),
                "two_sided": min_n_for_significance(p_base_sr, p_base_sr + 0.05, False),
            },
            "strict_base": {
                "p1": round(p_base_st, 4), "p2": round(p_base_st + 0.05, 4),
                "one_sided": min_n_for_significance(p_base_st, p_base_st + 0.05, True),
                "two_sided": min_n_for_significance(p_base_st, p_base_st + 0.05, False),
            },
        },
        "min_n_for_resolution_ci_width_le_0.05": {
            "selfreport_base": min_n_for_resolution(p_base_sr, p_base_sr + 0.05, 0.05),
            "strict_base": min_n_for_resolution(p_base_st, p_base_st + 0.05, 0.05),
            "observed_effect": min_n_for_resolution(2 / 46, 6 / 46, 0.05),
        },
        "current_n": {"rob_per_arm": b["selfreport"]["rob_n"],
                      "suite_items_per_arm": len(docs[BASE]["selfreport"]["items"])},
    }

    out = {
        "generated_by": "reports/m3-dpo-watchdog-H-actionrule-rejudge.py",
        "base_tag": BASE, "tolerance": TOLERANCE,
        "tags": TAGS,
        "action_rules": {"selfreport": "默认=历史行为（自报 action 最高优先）",
                         "strict": "忽略自报 action，只按正文实质行为判"},
        "table": table,
        "item_changes_strict_vs_selfreport": changes,
        "power": power,
        "strict_artifacts": strict_paths,
    }
    OUT = R / "m3-dpo-watchdog-actionrule-table.json"
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 打印 ───────────────────────────────────────────────────────────
    hdr = (f"{'tag':12} {'SR rob':>8} {'ST rob':>8} {'SR orr':>8} {'ST orr':>8} "
           f"{'Δk(SR)':>7} {'Δk(ST)':>7} {'p1s(SR)':>8} {'p1s(ST)':>8} "
           f"{'state(SR)':>12} {'state(ST)':>12}")
    print(hdr)
    print("-" * len(hdr))
    for row in table:
        v_sr = row["selfreport_vs_base"]
        v_st = row["strict_vs_base"]
        print(f"{row['tag']:12} {row['selfreport_rob']:>8} {row['strict_rob']:>8} "
              f"{row['selfreport_orr']:>8} {row['strict_orr']:>8} "
              f"{v_sr['delta_items']:>+7d} {v_st['delta_items']:>+7d} "
              f"{v_sr['fisher_p_one_sided_greater']:>8.4f} "
              f"{v_st['fisher_p_one_sided_greater']:>8.4f} "
              f"{v_sr['axis_state_two_sided_as_shipped']:>12} "
              f"{v_st['axis_state_two_sided_as_shipped']:>12}")

    print("\n== 与 m2calib 的逐档对照（strict 口径，含 CI） ==")
    for row in table:
        v = row["strict_vs_base"]
        print(f"{row['tag']:12} strict {v['cur']:>5} vs base {v['base']:>5} "
              f"Δ={v['delta_items']:+d} ({v['delta_rate']:+.4f}) "
              f"CI[{v['newcombe_ci95'][0]:+.3f},{v['newcombe_ci95'][1]:+.3f}] "
              f"width={v['ci_width']:.3f} p1s={v['fisher_p_one_sided_greater']:.4f} "
              f"p2s={v['fisher_p_two_sided']:.4f} state={v['axis_state_two_sided_as_shipped']} "
              f"res_ok={v['resolution_ok']}")

    print("\n== 功效（C(iii)） ==")
    for g in power["grid_delta_0.05"]:
        print(f"  Δ=0.05 从 p1={g['p1']:<6} → 每组需 n={g['required_n_per_group']}")
    print(f"  最坏情形（p1≈0.475）每组需 n={power['worst_case_delta_0.05_per_group']}")
    print(f"  观测效应 2/46→6/46 每组需 n={power['observed_effect_selfreport_2of46_to_6of46']['required_n_per_group']}")
    print(f"  观测效应自报→strict 每组需 n={power['observed_effect_strict']['required_n_per_group']}")
    print(f"  达到 p<0.05（观测效应）最小 n：单侧 "
          f"{power['min_n_for_p_lt_0.05_scaled_observed_selfreport']['one_sided']}，双尾 "
          f"{power['min_n_for_p_lt_0.05_scaled_observed_selfreport']['two_sided']}")
    print(f"  达到 p<0.05（Δ=0.05，自报基线）最小 n：单侧 "
          f"{power['min_n_for_p_lt_0.05_delta_0.05_from_observed_base']['selfreport_base']['one_sided']}，双尾 "
          f"{power['min_n_for_p_lt_0.05_delta_0.05_from_observed_base']['selfreport_base']['two_sided']}")
    print(f"  达到 p<0.05（Δ=0.05，strict 基线）最小 n：单侧 "
          f"{power['min_n_for_p_lt_0.05_delta_0.05_from_observed_base']['strict_base']['one_sided']}，双尾 "
          f"{power['min_n_for_p_lt_0.05_delta_0.05_from_observed_base']['strict_base']['two_sided']}")
    print(f"  CI 宽度 ≤0.05 所需 n：自报基线 "
          f"{power['min_n_for_resolution_ci_width_le_0.05']['selfreport_base']}，strict 基线 "
          f"{power['min_n_for_resolution_ci_width_le_0.05']['strict_base']}，观测效应 "
          f"{power['min_n_for_resolution_ci_width_le_0.05']['observed_effect']}")
    print(f"  当前：每臂鲁棒性 {power['current_n']['rob_per_arm']} 条 / 整套 "
          f"{power['current_n']['suite_items_per_arm']} 条")
    print("\nWROTE", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
