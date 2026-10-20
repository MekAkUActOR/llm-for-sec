# -*- coding: utf-8 -*-
"""M6 冻结套件映射器（qa-m6）：data/heldout/ 只读 → m6-sample 等价评测行。

红线：本脚本对 data/heldout/ 只读（不写、不改名、不移动）。
映射规则与 ADR-1 §13 / QA-1 §2.3 一一对应，改动前先改规格。

输出：
  reports/m6/mapped/frozen-<suite>.jsonl   # m6-sample 等价行（schema 字段子集 + IR 扩展）
  reports/m6/frozen-suite-mapping.json     # 映射统计与规则登记（审计用）

行 IR（harness 内部统一结构）：
  {id, source, labels{Tk:1|0}, ambiguous, text|turns, attack_family, meta}
"""
from __future__ import annotations

import json
from pathlib import Path

HELDOUT = Path("data/heldout")
OUT_DIR = Path("reports/m6/mapped")
ALL_NEG = {t: 0 for t in ["T1", "T2", "T3", "T4", "T5", "T6"]}

MAPPING_RULES = {
    "frozen-v023": "v0.2.3 {security,ai_safety,privacy}: must_refuse=true → T1+T3+T6 正；false → 全六负；correct_verdict(capability/calibration) 行跳过（构念不匹配）",
    "frozen-v023-gen": "v0.2.3 general_*: must_refuse=false → 全六负",
    "frozen-hardbenign": "v0.2.3 hardbenign: 全六负（挑战参照）",
    "frozen-gen": "v0.3-gen av/image: must_refuse=true 或 correct_verdict=contains-injection → T5 正；false/clean → 全六负；其余 correct_verdict 跳过",
    "frozen-jb": "v0.7-jailbreak: must_refuse=true → T2+T3 正（turns 拼接主口径）；false → 全六负；holdout 族（F4/F6）source 加 -holdout 后缀",
    "frozen-toolout": "v0.4-toolout: group=='' 且 must_refuse=true → T5+T6 正；false → 全六负；group!=''（政策条件化条）跳过",
    "frozen-toolout-reg": "v0.5-toolout-reg primary+carrier-extra: must_refuse=true → T5+T6 正；false → 全六负",
    "frozen-topup": "v0.5-topup-families: id 含 -atk- → 正（task: T2-mechanism→T2 / T15-doc-structure→T5 / T9-phish→T1+T3）；非 atk → 全六负；messages 拼 text（system+user 段落保留）",
    "frozen-document": "v0.6-document: must_refuse=true → T5+T3 正；false → 全六负",
    "frozen-dilution": "v0.6-dilution: 全部 96 行 → T3+T5 正（S/M/L frag 保 meta，报告按 frag 细分）",
}


def _load(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _row(rid: str, source: str, labels: dict, *, text=None, turns=None, meta=None):
    r = {"id": rid, "source": source, "labels": labels, "ambiguous": False, "meta": meta or {}}
    if text is not None:
        r["text"] = text
    else:
        r["turns"] = turns
    return r


def map_query_suite(path: Path, source: str, pos_labels: dict) -> tuple[list, int]:
    """通用 query 型套件（v0.4/v0.5/v0.6-document/v0.3-gen/v0.2.3 域文件）。"""
    rows, skipped = [], 0
    for r in _load(path):
        rid = r["id"]
        exp = r.get("expected") or {}
        if "must_refuse" in exp:
            if exp["must_refuse"]:
                rows.append(_row(f"m6x-{rid}", source, dict(pos_labels), text=r["query"],
                                 meta={"orig_id": rid, "kind": r.get("kind")}))
            else:
                rows.append(_row(f"m6x-{rid}", source, dict(ALL_NEG), text=r["query"],
                                 meta={"orig_id": rid, "kind": r.get("kind")}))
        elif "correct_verdict" in exp:
            cv = exp["correct_verdict"]
            if cv == "contains-injection":
                rows.append(_row(f"m6x-{rid}", source, {"T5": 1}, text=r["query"],
                                 meta={"orig_id": rid, "kind": r.get("kind")}))
            elif cv == "clean":
                rows.append(_row(f"m6x-{rid}", source, dict(ALL_NEG), text=r["query"],
                                 meta={"orig_id": rid, "kind": r.get("kind")}))
            else:
                skipped += 1  # capability/calibration 其他构念：跳过
        else:
            skipped += 1
    return rows, skipped


def map_v023() -> tuple[dict, dict]:
    """v0.2.3：三域（T1/T3/T6 正例）+ general_*（负）+ hardbenign（挑战负）。"""
    out = {}
    stats = {}
    pos = {"T1": 1, "T3": 1, "T6": 1}
    for dom in ["security", "ai_safety", "privacy"]:
        rows, sk = map_query_suite(HELDOUT / "v0.2.3" / f"{dom}.jsonl", "frozen-v023", pos)
        out.setdefault("frozen-v023", []).extend(rows)
        stats[f"v023/{dom}"] = {"kept": len(rows), "skipped": sk}
    gen_rows, gen_sk = [], 0
    for p in sorted((HELDOUT / "v0.2.3").glob("general_*.jsonl")):
        rows, sk = map_query_suite(p, "frozen-v023-gen", dict(ALL_NEG))
        gen_rows.extend(rows)
        gen_sk += sk
    out["frozen-v023-gen"] = gen_rows
    stats["v023/general_*"] = {"kept": len(gen_rows), "skipped": gen_sk}
    hb_rows, hb_sk = map_query_suite(HELDOUT / "v0.2.3" / "hardbenign.jsonl", "frozen-hardbenign", dict(ALL_NEG))
    out["frozen-hardbenign"] = hb_rows
    stats["v023/hardbenign"] = {"kept": len(hb_rows), "skipped": hb_sk}
    return out, stats


def map_gen() -> tuple[dict, dict]:
    out, stats = {}, {}
    rows_all = []
    for name in ["av_metadata", "image_metadata"]:
        rows, sk = map_query_suite(HELDOUT / "v0.3-gen" / f"{name}.jsonl", "frozen-gen", {"T5": 1})
        rows_all.extend(rows)
        stats[f"gen/{name}"] = {"kept": len(rows), "skipped": sk}
    out["frozen-gen"] = rows_all
    return out, stats


def map_jb() -> tuple[dict, dict]:
    out, stats = {}, {}
    rows = []
    for r in _load(HELDOUT / "v0.7-jailbreak" / "jailbreak.jsonl"):
        rid = f"m6x-{r['id']}"
        holdout = bool(r.get("holdout"))
        src = "frozen-jb-holdout" if holdout else "frozen-jb-visible"
        if (r.get("expected") or {}).get("must_refuse"):
            labels = {"T2": 1, "T3": 1}
        else:
            labels = dict(ALL_NEG)
        rows.append(_row(rid, src, labels, turns=r["turns"],
                         meta={"orig_id": r["id"], "family": r.get("family"),
                               "harm_category": r.get("harm_category"), "holdout": holdout}))
    out["frozen-jb"] = rows
    pos = sum(1 for r in rows if any(v == 1 for v in r["labels"].values()))
    stats["jb"] = {"kept": len(rows), "pos": pos,
                   "holdout_rows": sum(1 for r in rows if r["meta"].get("holdout"))}
    return out, stats


def map_toolout() -> tuple[dict, dict]:
    out, stats = {}, {}
    rows, sk = [], 0
    # v0.4：跳过政策条（group 非空）
    for r in _load(HELDOUT / "v0.4-toolout" / "tool_output.jsonl"):
        if r.get("group"):
            sk += 1
            continue
        exp = r.get("expected") or {}
        if exp.get("must_refuse") is None:
            sk += 1
            continue
        labels = {"T5": 1, "T6": 1} if exp["must_refuse"] else dict(ALL_NEG)
        rows.append(_row(f"m6x-{r['id']}", "frozen-toolout", labels, text=r["query"],
                         meta={"orig_id": r["id"], "suite": "v0.4"}))
    stats["toolout/v0.4"] = {"kept": len(rows), "skipped": sk}
    # v0.5：primary + carrier-extra
    for sub in ["toolout_primary.jsonl", "carrier-extra/carrier_extra.jsonl"]:
        r2, sk2 = map_query_suite(HELDOUT / "v0.5-toolout-reg" / sub, "frozen-toolout-reg", {"T5": 1, "T6": 1})
        rows.extend(r2)
        stats[f"toolout-reg/{sub}"] = {"kept": len(r2), "skipped": sk2}
    out["frozen-toolout"] = rows
    return out, stats


def map_topup() -> tuple[dict, dict]:
    out, stats = {}, {}
    rows = []
    task_map = {"T2": ({"T2": 1}, "frozen-topup-t2m"),
                "T15": ({"T5": 1}, "frozen-topup-docstruct"),
                "T9": ({"T1": 1, "T3": 1}, "frozen-topup-t9")}
    for p in sorted((HELDOUT / "v0.5-topup-families").glob("*.jsonl")):
        for r in _load(p):
            fam = r["task"].split("-")[0]
            if fam not in task_map:
                continue
            labels, src = task_map[fam]
            if "-atk-" not in r["id"]:
                labels = dict(ALL_NEG)
            msgs = r["messages"]
            text = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in msgs)
            rows.append(_row(f"m6x-{r['id']}", src, labels, text=text,
                             meta={"orig_id": r["id"], "task": r["task"], "pack": r.get("pack")}))
    out["frozen-topup"] = rows
    stats["topup"] = {"kept": len(rows),
                      "pos": sum(1 for r in rows if any(v == 1 for v in r["labels"].values()))}
    return out, stats


def map_document() -> tuple[dict, dict]:
    rows, sk = map_query_suite(HELDOUT / "v0.6-document" / "document.jsonl", "frozen-document", {"T5": 1, "T3": 1})
    return {"frozen-document": rows}, {"document": {"kept": len(rows), "skipped": sk}}


def map_dilution() -> tuple[dict, dict]:
    rows = []
    for r in _load(HELDOUT / "v0.6-dilution" / "risk_payloads.jsonl"):
        rows.append(_row(f"m6x-{r['id']}", "frozen-dilution", {"T3": 1, "T5": 1}, text=r["text"],
                         meta={"orig_id": r["id"], "frag": r.get("frag"),
                               "family": r.get("family"), "mechanism": r.get("mechanism")}))
    return {"frozen-dilution": rows}, {"dilution": {"kept": len(rows)}}


def build_all(write: bool = True) -> tuple[dict, dict]:
    results, all_stats = {}, {}
    for fn in (map_v023, map_gen, map_jb, map_toolout, map_topup, map_document, map_dilution):
        out, stats = fn()
        results.update(out)
        all_stats.update(stats)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, rows in results.items():
            with (OUT_DIR / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with Path("reports/m6/frozen-suite-mapping.json").open("w", encoding="utf-8", newline="\n") as f:
            json.dump({"rules": MAPPING_RULES, "stats": all_stats,
                       "totals": {k: len(v) for k, v in results.items()}},
                      f, ensure_ascii=False, indent=2)
    return results, all_stats


if __name__ == "__main__":
    res, stats = build_all(write=True)
    print("冻结套件映射完成（data/heldout 只读）:")
    for k, v in res.items():
        pos = sum(1 for r in v if any(x == 1 for x in r["labels"].values()))
        neg = sum(1 for r in v if any(x == 0 for x in r["labels"].values()))
        print(f"  {k:28s} {len(v):5d} 行（正 {pos} / 负 {neg}）")
    total = sum(len(v) for v in res.values())
    print(f"  合计 {total} 行 -> reports/m6/mapped/ + frozen-suite-mapping.json")
