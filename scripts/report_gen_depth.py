# -*- coding: utf-8 -*-
"""v0.3-gen 未见载体门禁集「机制深度」前后对照报告（**只读**）。

为什么需要
==========
`reports/v03-gen-expansion-stats.json` 记录了 2026-09-30 的扩容结果：总量、
语言、包三档都达标，但**每机制条数中位数 = 1**（image 24 种机制里 17 种只
有 1 条、av 27 种里 21 种只有 1 条）——单机制攻击成功率不可分辨；
19/24（image）与 24/27（av）的机制只出现单一语言 → 机制 × 语言混杂；
G1 分母 100% 是 `default` pack → 测不到政策包效应。

2026-10-06 的深度扩容修掉这三件事，本脚本给出**逐机制 × 语言 × pack**
的前后对照表，供报告与复现引用。

数据来源（全部只读）
====================
* 扩容前：`reports/v03-gen-expansion-stats.json` 的
  `mechanism_detail.after`（该批 122 条的机制 → id 清单）；
  语言/包由 id 从**当前磁盘**反查（id、language、policy_pack 均未变动，
  本次只改了 `_IMG_BASE` 的非零 GPS 占位与新增条目）；
* 扩容后：`data/heldout/v0.3-gen/*.jsonl` 的实测行
  （与 `secfm.carriers.meta_ser.build_texts()` 有漂移锁，见 checker）。

⛔ 本目录条目永不入训练；本脚本只读。

用法：
    .venv\\Scripts\\python.exe scripts/report_gen_depth.py
    .venv\\Scripts\\python.exe scripts/report_gen_depth.py --train-scan
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_gen_heldout as C              # noqa: E402


def _lang_pack_index(rows):
    """id -> (language, policy_pack)（扩容前的语言/包由 id 从磁盘反查）。"""
    return {r.get("id"): (r.get("language"), r.get("policy_pack"))
            for r in rows}


def _before_depth(before_ids, index):
    """扩容前逐机制深度（语言/包由 id 反查；缺失 id 会记进 missing）。"""
    out, missing = {}, []
    for c, mechs in before_ids.items():
        out[c] = {}
        for m, ids in mechs.items():
            langs, packs = set(), set()
            for i in ids:
                lp = index.get(i)
                if lp is None:
                    missing.append(i)
                    continue
                langs.add(lp[0])
                packs.add(lp[1])
            out[c][m] = {"n": len(ids), "languages": sorted(x for x in langs
                                                            if x),
                         "packs": sorted(x for x in packs if x),
                         "ids": sorted(ids)}
    return out, missing


def _cross_ratio(depth, ok):
    tot = sum(len(v) for v in depth.values())
    if not tot:
        return 0.0
    hit = sum(1 for v in depth.values() for d in v.values() if ok(d))
    return round(hit / tot, 4)


def _median(values):
    if not values:
        return 0
    return sorted(values)[len(values) // 2]


def build_report(*, train_scan=False):
    rows, _, load_problems = C.load_dir()
    summary = C.summarize(rows)
    after_depth = summary["mechanism_depth_by_carrier"]

    prev_path = ROOT / "reports" / "v03-gen-expansion-stats.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8"))
    before_ids = prev["mechanism_detail"]["after"]
    index = _lang_pack_index(rows)
    before_depth, missing_ids = _before_depth(before_ids, index)
    before_sum = prev["after"]

    def flatten(depth):
        table = {}
        for c in C.GEN_CTYPES:
            table[c] = {m: {"rows": d["n"], "zh": d["languages"].count("zh"),
                            "en": d["languages"].count("en"),
                            "n_languages": len(d["languages"]),
                            "n_packs": len(d["packs"]),
                            "packs": d["packs"]}
                        for m, d in depth.get(c, {}).items()}
        return table

    after_table = flatten(after_depth)
    before_table = flatten(before_depth)

    per_mechanism = {}
    for c in C.GEN_CTYPES:
        per_mechanism[c] = {}
        for m in sorted(set(before_table.get(c, {}))
                        | set(after_table.get(c, {}))):
            b = before_depth.get(c, {}).get(m)
            a = after_depth.get(c, {}).get(m)
            per_mechanism[c][m] = {
                "rows_before": b["n"] if b else 0,
                "rows_after": a["n"] if a else 0,
                "languages_before": b["languages"] if b else [],
                "packs_before": b["packs"] if b else [],
                "languages_after": a["languages"] if a else [],
                "packs_after": a["packs"] if a else [],
                "non_default_pack_before": bool(
                    b and set(b["packs"]) & set(C.NON_DEFAULT_PACKS)),
                "non_default_pack_after": bool(
                    a and set(a["packs"]) & set(C.NON_DEFAULT_PACKS)),
                "ids_before": b["ids"] if b else [],
                "ids_after": a["ids"] if a else [],
            }

    before_counts = [d["n"] for c in C.GEN_CTYPES
                     for d in before_depth.get(c, {}).values()]
    after_counts = [d["n"] for c in C.GEN_CTYPES
                    for d in after_depth.get(c, {}).values()]

    def lang_cross(depth):
        return {c: sum(1 for d in depth.get(c, {}).values()
                       if set(d["languages"]) == set(C.LANGS))
                for c in C.GEN_CTYPES}

    def pack_cov(depth):
        return {c: sum(1 for d in depth.get(c, {}).values()
                       if set(d["packs"]) & set(C.NON_DEFAULT_PACKS))
                for c in C.GEN_CTYPES}

    rep = {
        "report": "v03-gen-depth-stats",
        "generated": "2026-10-06",
        "scope": "data/heldout/v0.3-gen/（评测专用留出集；⛔ 永不入训练）",
        "generated_by": "scripts/report_gen_depth.py（只读；before 取"
                        "reports/v03-gen-expansion-stats.json:mechanism_detail"
                        ".after，after 取磁盘实测；磁盘 == meta_ser.build_texts()）",
        "goal": [
            "每机制 ≥3 条鲁棒性条（单机制 ASR 才可分辨，见 "
            "reports/review_statistical_power.py §D）",
            "每机制 zh 与 en 都出现（机制 × 语言不再混杂）",
            "每机制 ≥1 条 non-default pack（conservative/professional）",
            "干净负例 ≥25%；每载体鲁棒性条 ≥34（沿用 2026-09-30 硬断言）",
        ],
        "before": {
            "source": "reports/v03-gen-expansion-stats.json:after（122 条）",
            "n": before_sum["n"],
            "by_carrier": before_sum["by_carrier"],
            "by_language": before_sum["by_language"],
            "by_pack": before_sum["by_pack"],
            "kind_robustness_total": before_sum["kind_robustness_total"],
            "robustness_by_carrier": before_sum["robustness_by_carrier"],
            "mechanism_kinds_by_carrier": before_sum["mechanism_kinds_by_carrier"],
            "mechanism_rows_min": min(before_counts) if before_counts else 0,
            "mechanism_rows_median": _median(before_counts),
            "mechanism_rows_max": max(before_counts) if before_counts else 0,
            "mechanism_language_cross": lang_cross(before_depth),
            "mechanism_pack_coverage": pack_cov(before_depth),
            "non_default_pack_rows": before_sum["by_pack"]["conservative"]
            + before_sum["by_pack"]["professional"],
            "clean_negative": before_sum["clean_negative"],
            "clean_negative_ratio": before_sum["clean_negative_ratio"],
        },
        "after": {
            "source": "data/heldout/v0.3-gen/*.jsonl（磁盘实测）",
            "n": summary["n"],
            "by_carrier": summary["by_carrier"],
            "by_language": summary["by_language"],
            "by_pack": summary["by_pack"],
            "kind_robustness_total": summary["by_kind"]["robustness"],
            "robustness_by_carrier": summary["robustness_by_carrier"],
            "mechanism_kinds_by_carrier": summary["mechanism_kinds_by_carrier"],
            "mechanism_rows_min": min(after_counts) if after_counts else 0,
            "mechanism_rows_median": _median(after_counts),
            "mechanism_rows_max": max(after_counts) if after_counts else 0,
            "mechanism_language_cross": lang_cross(after_depth),
            "mechanism_pack_coverage": pack_cov(after_depth),
            "non_default_pack_rows": summary["non_default_pack_rows"],
            "clean_negative": summary["clean_negative"],
            "clean_negative_ratio": summary["clean_negative_ratio"],
            "adversarial_forward_ratio": summary["adversarial_forward_ratio"],
            "adversarial_expected_ratio": summary["adversarial_expected_ratio"],
            "policy_groups": summary["policy_groups"],
            "forward_true": summary["forward_true"],
            "adversarial_expected": summary["adversarial_expected"],
        },
        "mechanism_table": {
            "note": "机制 × 条数 × zh/en × pack（before=122 条那批；"
                    "after=本次深度扩容后）",
            "per_mechanism": per_mechanism,
            "before": before_table,
            "after": after_table,
        },
        "checker": {
            "problems": C.check_mechanism_depth(rows)
            + C.check_fictional_refs(rows)
            + C.check_robustness_coverage(rows)
            + C.check_distribution(rows),
            "load_problems": load_problems,
            "exit_code": 0,
        },
    }
    if missing_ids:
        rep["checker"]["before_ids_missing_on_disk"] = sorted(set(missing_ids))
    if train_scan:
        info, probs = C.scan_train_disjoint(C.SFT_MIX)
        disjoint_problems = probs + C.check_train_disjoint(info)
        rep["train_disjoint"] = {
            "path": info["path"], "rows": info["rows"],
            "size_bytes": info["size_bytes"],
            "envelope_counts": info["envelope_counts"],
            "image_metadata_envelopes": info["envelope_counts"].get(
                C.IMAGE_CTYPE, 0),
            "av_metadata_envelopes": info["envelope_counts"].get(
                C.AV_CTYPE, 0),
            "substring_counts_informational": info["substring_counts"],
            "census_crosscheck": info.get("census_crosscheck"),
            "census_rows": info.get("census_rows"),
            "problems": disjoint_problems,
        }
    rep["checker"]["exit_code"] = 1 if rep["checker"]["problems"] else 0
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="v0.3-gen 机制深度前后对照报告")
    ap.add_argument("--out", default=str(ROOT / "reports" /
                                         "v03-gen-depth-stats.json"))
    ap.add_argument("--train-scan", action="store_true",
                    help="附带 data/lf/sft_m25.jsonl 训练不相交复扫")
    args = ap.parse_args(argv)
    rep = build_report(train_scan=args.train_scan)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2)
                              + "\n", encoding="utf-8", newline="\n")
    b, a = rep["before"], rep["after"]
    print(f"before: n={b['n']} rob={b['kind_robustness_total']} "
          f"mech={sum(len(v) for v in rep['mechanism_table']['before'].values())}"
          f" median={b['mechanism_rows_median']} "
          f"lang-cross={b['mechanism_language_cross']} "
          f"pack-cov={b['mechanism_pack_coverage']} "
          f"non-default={b['non_default_pack_rows']}")
    print(f"after : n={a['n']} rob={a['kind_robustness_total']} "
          f"mech={sum(len(v) for v in rep['mechanism_table']['after'].values())}"
          f" median={a['mechanism_rows_median']} "
          f"lang-cross={a['mechanism_language_cross']} "
          f"pack-cov={a['mechanism_pack_coverage']} "
          f"non-default={a['non_default_pack_rows']}")
    print(f"checker problems: {len(rep['checker']['problems'])} "
          f"-> {args.out}")
    return 1 if rep["checker"]["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
