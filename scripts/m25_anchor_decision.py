# -*- coding: utf-8 -*-
"""M2.5 锚决策（用户保留项："measure-then-decide on PPL anchors"）。

背景（docs/research/m25-backfill-plan.md §触发矩阵）：
  M2 的失败画像里"通用门禁"与"32k 锚"两行同时命中——general PPL vs m15
  +13.4/+18.6%、32k（longctx PPL@32768）vs m15 +12.9/+16.4%，均超 +10% 线。
  当时的处置选项之一是 **PT 回放锚 pass**（估 5-10h GPU），用户改判为
  "不预付、待读数后权衡"。本脚本把该权衡量化，读数一落地即可决策。

口径：
  - 通用门禁 = 探针 v0.3 的 general_en / general_zh PPL vs m15（历史连续）
    附 v0.4 干净口径（privacy/general_en 换源，仅绝对幅度附注）。
  - 32k 锚 = longctx PPL@32768（en/zh）vs m15；needle 同步列出。
  - 三个选项与触发条件（脚本给量化判据，**决策权在人**）：
      A 接受漂移 + 用 v0.4 校正解读：32k 两语言 ≤ +15% 且行为门禁 G1 过。
      B 跑 PT 回放锚 pass（5-10h GPU）：32k 任一语言 > +15%，或 needle < 9/12。
      C 改锚口径（把 +10% 线改为 v0.4 相对口径）：v0.4 显示漂移主要来自探针
        污染而非能力退化（即 v0.3 幅度显著大于 v0.4 幅度）。

用法：python scripts/m25_anchor_decision.py [--tag m25full]
输出：reports/m25-anchor-decision.json / .md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "reports"


def load(name: str):
    p = R / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def needle_count(doc) -> int | None:
    ns = (doc or {}).get("needle_success")
    if not ns:
        return None
    return int(round(sum(round(f * 3) for lens in ns.values() for f in lens.values())))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="m25full")
    args = ap.parse_args()
    tag = args.tag

    base_lc = load("longctx-m15.json")
    cur_lc = load(f"longctx-{tag}.json")
    m2_lc = load("longctx-m2full.json")
    rep: dict = {"tag": tag, "anchor": {}, "general_ppl": {}, "needle": {}}

    def anchor_block(lc):
        if not lc:
            return None
        return {lens: {lang: round(v["ppl"], 4) for lang, v in langs.items()}
                for lens, langs in lc["ppl"].items()}

    rep["anchor"] = {"m15": anchor_block(base_lc), "m2full": anchor_block(m2_lc),
                     tag: anchor_block(cur_lc)}
    for lens in ("16384", "32768"):
        for lang in ("en", "zh"):
            try:
                b = base_lc["ppl"][lens][lang]["ppl"]
                c = cur_lc["ppl"][lens][lang]["ppl"]
                rep["anchor"][f"delta_{lens}_{lang}_pct"] = round((c / b - 1) * 100, 2)
            except Exception:  # noqa: BLE001
                rep["anchor"][f"delta_{lens}_{lang}_pct"] = None

    for ver in ("v0.3", "v0.4"):
        b = load(f"ppl-m15-{ver}.json")
        c = load(f"ppl-{tag}-{ver}.json")
        if b and c:
            rep["general_ppl"][ver] = {
                k: {"m15": round(b["domains"][k]["ppl"], 4),
                    "cur": round(c["domains"][k]["ppl"], 4),
                    "delta_pct": round((c["domains"][k]["ppl"] /
                                        b["domains"][k]["ppl"] - 1) * 100, 2)}
                for k in ("general_en", "general_zh", "privacy")
                if k in b.get("domains", {}) and k in c.get("domains", {})}

    rep["needle"] = {"m15": needle_count(base_lc), "m2full": needle_count(m2_lc),
                     tag: needle_count(cur_lc), "line": 9}

    d32 = [rep["anchor"].get(f"delta_32768_{l}") for l in ("en", "zh")]
    d32_ok = all(d is not None and d <= 15.0 for d in d32)
    needle_ok = (rep["needle"][tag] is None) or rep["needle"][tag] >= 9
    v03 = rep["general_ppl"].get("v0.3", {})
    v04 = rep["general_ppl"].get("v0.4", {})
    shrink = bool(v03 and v04 and "general_en" in v03 and "general_en" in v04
                  and abs(v04["general_en"]["delta_pct"])
                  < abs(v03["general_en"]["delta_pct"]) * 0.6)
    rep["triggers"] = {
        "A_accept_plus_v04": {"need": "32k en/zh <= +15% 且 G1 过行为门禁",
                              "32k_ok": d32_ok,
                              "note": "G1 由 scripts/m25_exit_verdict.py 判定"},
        "B_anchor_pass": {"need": "32k 任一语言 > +15% 或 needle < 9/12",
                          "triggered": (not d32_ok) or (not needle_ok)},
        "C_reanchor_probes": {"need": "v0.4 幅度显著小于 v0.3（漂移主要来自探针污染）",
                              "triggered": shrink,
                              "v0.3_general_en": v03.get("general_en", {}).get("delta_pct"),
                              "v0.4_general_en": v04.get("general_en", {}).get("delta_pct")},
    }
    suffix = "" if tag == "m25full" else f"-{tag}"
    (R / f"m25-anchor-decision{suffix}.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    # MD 版（人类可读；docstring 一直声称有 .md 但代码从未写过 —— 2026-09-30 补）
    L = [f"# M2.5 锚决策（tag={tag}）", "",
         "> 决策权在人；本表只给量化判据。`32k 锚` 取自 `longctx-*.json` 的 "
         "`ppl@16384/32768`；`通用门禁` 取自 `ppl-*-v0.3/v0.4.json`。", "",
         "## 32k 锚（longctx PPL）", ""]
    anc = rep["anchor"].get(tag) or {}
    if anc:
        L += ["| 长度 | m15 | m2-full | " + tag + " | Δ vs m15 (en) | Δ vs m15 (zh) |",
              "|---|---|---|---|---|---|"]
        for lens in ("16384", "32768"):
            m15v = (rep["anchor"].get("m15") or {}).get(lens, {})
            m2v = (rep["anchor"].get("m2full") or {}).get(lens, {})
            cuv = anc.get(lens, {})
            de = rep["anchor"].get(f"delta_{lens}_en_pct")
            dz = rep["anchor"].get(f"delta_{lens}_zh_pct")
            f2 = lambda d: " / ".join(f"{d.get(k, float('nan')):.2f}"      # noqa: E731
                                      for k in ("en", "zh"))
            L.append(f"| {lens} | {f2(m15v)} | {f2(m2v)} | {f2(cuv)} | "
                     f"{'—' if de is None else f'{de:+.2f}%'} | "
                     f"{'—' if dz is None else f'{dz:+.2f}%'} |")
    else:
        L.append("（当前 tag 无 longctx 读数——评估链第 6 步尚未产出）")
    L += ["", "## 通用 PPL（general / privacy）", ""]
    for ver in ("v0.3", "v0.4"):
        blk = rep["general_ppl"].get(ver)
        L.append(f"**{ver}**" + ("" if blk else "（缺件）"))
        if blk:
            L += ["", "| 域 | m15 | " + tag + " | Δ% |", "|---|---|---|---|"]
            for k, v in blk.items():
                L.append(f"| {k} | {v['m15']:.4f} | {v['cur']:.4f} | "
                         f"{v['delta_pct']:+.2f}% |")
        L.append("")
    n = rep["needle"]
    L += ["## needle（水位线 9/12）", "",
          f"- m15: {n.get('m15')}  ·  m2-full: {n.get('m2full')}  ·  "
          f"{tag}: **{n.get(tag)}**", "", "## 三选项触发", ""]
    tr = rep["triggers"]
    L += [f"- **A 接受漂移 + v0.4 校正**：32k en/zh ≤ +15% → "
          f"`32k_ok={tr['A_accept_plus_v04']['32k_ok']}`（G1 由出口判定器给出）",
          f"- **B 跑 PT 回放锚 pass（5-10h GPU）**：`triggered="
          f"{tr['B_anchor_pass']['triggered']}`",
          f"- **C 改锚口径（v0.4 相对）**：`triggered="
          f"{tr['C_reanchor_probes']['triggered']}`"
          f"（v0.3 general_en {tr['C_reanchor_probes']['v0.3_general_en']}% vs "
          f"v0.4 {tr['C_reanchor_probes']['v0.4_general_en']}%）"]
    (R / f"m25-anchor-decision{suffix}.md").write_text("\n".join(L), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
