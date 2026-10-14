# -*- coding: utf-8 -*-
"""未见载体门禁集（v0.3-gen）的完整分析：两两对照 + 失败集中度。

为什么需要它：20 条时 m2full→m25full 是 p=0.0033，扩到 70 条后变成 p=0.081。
结论对仪器规模敏感，故必须给出**全对照 + 失败集中在哪些机制/载体**，
而不是只报一对数字。

用法：python scripts/analyze_gen_gate.py [--suffix chat-gen-] [--tags m2calib,m2full,m25full]
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from secfm.eval.stats import fisher_p, wilson          # noqa: E402
from secfm.eval.scored import robustness_axes          # noqa: E402

MECH_RE = re.compile(r"机制[:：]\s*\[([^\]]+)\]")
CARRIER_RE = re.compile(r'carrier\s+type=\\*"([A-Za-z_]+)\\*"')


def load(tag: str, suffix: str) -> dict | None:
    p = ROOT / "reports" / f"scored-{suffix}{tag}-v2.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_heldout_index() -> dict[str, dict]:
    """判分件只存 id/kind/label（不含 query/intent），故从 heldout 源按 id 关联。"""
    idx = {}
    d = ROOT / "data" / "heldout" / "v0.3-gen"
    for f in sorted(d.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                if j.get("id"):
                    idx[j["id"]] = j
    return idx


def fail_detail(doc: dict, idx: dict) -> list[dict]:
    out = []
    for it in doc.get("items", []):
        if it.get("kind") != "robustness" or not it.get("responded"):
            continue
        if it.get("label") == "comply":
            src = idx.get(it.get("id")) or {}
            q = src.get("query") or ""
            m = MECH_RE.search(src.get("intent") or "")
            c = CARRIER_RE.search(q)
            out.append({"id": it.get("id"),
                        "carrier": c.group(1) if c else "?",
                        "mechanism": m.group(1) if m else "(未标注)",
                        "lang": src.get("language"), "pack": src.get("policy_pack")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", default="chat-gen-")
    ap.add_argument("--tags", default="m2calib,m2full,m25full")
    a = ap.parse_args()
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    docs = {t: load(t, a.suffix) for t in tags}
    have = {t: d for t, d in docs.items() if d}
    idx = load_heldout_index()

    print("=" * 78)
    print(f"A. 未见载体鲁棒性轴（suffix={a.suffix!r}，仅 kind==robustness）")
    print("=" * 78)
    print(f"{'model':10} {'k/n':>9} {'rate':>7} {'95% CI':>18}")
    stats = {}
    for t, d in have.items():
        ax = robustness_axes(d)["all"]
        k, n = ax["success"], ax["n"]
        lo, hi = wilson(k, n)
        stats[t] = (k, n)
        print(f"{t:10} {f'{k}/{n}':>9} {k / n:>7.3f} "
              f"{f'[{lo:.3f}, {hi:.3f}]':>18}")

    print("\n" + "=" * 78)
    print("B. 两两对照（Fisher 精确检验）")
    print("=" * 78)
    for x, y in itertools.combinations(have, 2):
        k1, n1 = stats[x]
        k0, n0 = stats[y]
        p = fisher_p(k1, n1 - k1, k0, n0 - k0)
        d = k1 / n1 - k0 / n0
        tag = "可区分" if p < 0.05 else "★未达可区分"
        print(f"  {x:9} vs {y:9}: {k1}/{n1} - {k0}/{n0} = {d:+.3f}  "
              f"p={p:.4f}  {tag}")

    print("\n" + "=" * 78)
    print("C. 失败条目集中在哪些机制 / 载体（每模型）")
    print("=" * 78)
    for t, d in have.items():
        fails = fail_detail(d, idx)
        if not fails:
            print(f"  {t}: 无失败")
            continue
        by_mech = collections.Counter(f["mechanism"] for f in fails)
        by_carrier = collections.Counter(f["carrier"] for f in fails)
        print(f"  {t}: {len(fails)} 条失败 | 载体={dict(by_carrier)}")
        print(f"      机制 top: {dict(by_mech.most_common(6))}")
        print(f"      id: {', '.join(f['id'] for f in fails[:12])}"
              f"{' …' if len(fails) > 12 else ''}")

    # 逐载体对照
    print("\n" + "=" * 78)
    print("D. 逐载体（鲁棒性条）")
    print("=" * 78)
    for carrier in ("image_metadata", "av_metadata"):
        row = []
        for t, d in have.items():
            ids = {i["id"] for i in idx.values()
                   if CARRIER_RE.search(i.get("query") or "")
                   and CARRIER_RE.search(i["query"]).group(1) == carrier}
            sub = {"items": [i for i in d.get("items", []) if i.get("id") in ids]}
            ax = robustness_axes(sub)["all"]
            row.append(f"{t}={ax['success']}/{ax['n']}")
        print(f"  {carrier:16} " + "  ".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
