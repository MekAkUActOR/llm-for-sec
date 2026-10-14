# -*- coding: utf-8 -*-
r"""★★★★★★ 用**生成器标签**做全面交叉：`机制 × 语言 × 位置`（训练）vs `机制`（测试）。

## 为什么这才是对的测量

第 20 轮我自造了四个代理，全部失效 ✗。而生成器**自己**就在 `src_task` 里写了
`T1-injection:{载体}:{机制}:{位置}` ✓，在 `lang` 里写了载荷语言 ✓，
测试侧在 `intent` 里写了 `机制:[…]` ✓。

**⇒ 只在**这一层**做测量** ✓ —— 它没有我发明的任何假设 ✓。

**★ 要回答的问题**：训练与测试在**机制**上的覆盖是否齐？
以及——**每个机制内部**，模型的表现如何？（后者才是机制级归因 ✓）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TRAIN = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
HD = ROOT / "data" / "heldout" / "v0.3-gen"
MECH_T = re.compile(r"机制:\s*\[([^\]]+)\]")


def train_rows() -> list[dict]:
    return [json.loads(l) for l in TRAIN.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def parse_src(st: str) -> tuple[str, str, str]:
    """T1-injection:{carrier}:{mech}:{pos} → (carrier, mech, pos)。"""
    p = str(st).split(":")
    if len(p) >= 5 and p[0] == "T1-injection":
        return p[1], p[2], p[3]
    return "?", "?", "?"


def test_meta() -> dict[str, dict]:
    out = {}
    for f in sorted(HD.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) != "robustness":
                continue
            m = MECH_T.search(str(r.get("intent") or ""))
            out[str(r.get("id"))] = {
                "mech": m.group(1) if m else "?",
                "carrier": f.stem,
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inject-classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow"])
    ap.add_argument("--scored", default="reports/scored-chat-gen-m3-dpo-v2-mnt512.json")
    ap.add_argument("--base-scored",
                    default="reports/scored-chat-gen-soup-a050-v2-mnt512.json")
    a = ap.parse_args()

    rows = [r for r in train_rows()
            if str(r.get("dpo_class")) in a.inject_classes]
    print(f"=== 训练注入 {len(rows)} 条（生成器标签 ✓）===")
    tab: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        _, mech, _ = parse_src(r.get("src_task"))
        tab[mech][str(r.get("lang"))] += 1
    print(f"  {'机制':<22} {'合计':>6} {'zh':>6} {'en':>6}   {'位置(head/mid/tail)'}")
    pos_of: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        _, mech, pos = parse_src(r.get("src_task"))
        pos_of[mech][pos] += 1
    for mech in sorted(tab, key=lambda k: -sum(tab[k].values())):
        c = tab[mech]
        tot = sum(c.values())
        print(f"  {mech:<22} {tot:>6} {c.get('zh',0):>6} {c.get('en',0):>6}   "
              f"{dict(pos_of[mech])}")

    print("\n=== 测试侧机制分布（intent 的『机制:』✓）===")
    tm = test_meta()
    print(f"  n={len(tm)}  机制 = "
          f"{dict(Counter(v['mech'] for v in tm.values()).most_common(12))}")

    print("\n=== ★训练 ↔ 测试的机制覆盖差 ===")
    tr_m = {m for m in tab}
    te_m = {v["mech"] for v in tm.values()}
    def base(x: str) -> str:
        return re.sub(r"^(AV|IMG)-", "", x).lower()
    tr_b = {base(m) for m in tr_m}
    te_b = {base(m) for m in te_m}
    print(f"  测试有、训练没有（按名形比对）= {sorted(te_b - tr_b)}")
    print(f"  训练有、测试没有               = {sorted(tr_b - te_b)}")

    print(f"\n=== ④ m3-dpo 在每个测试机制上的 ASR（★机制级归因 ✓）===")
    d = json.loads((ROOT / a.scored).read_text(encoding="utf-8"))
    items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
    db = json.loads((ROOT / a.base_scored).read_text(encoding="utf-8"))
    bitems = {str(x.get("id")): x for x in (db.get("items") or [])
              if str(x.get("kind")) == "robustness"}
    by: dict[str, list] = defaultdict(list)
    for x in items:
        by[(tm.get(str(x.get("id"))) or {}).get("mech", "?")].append(x)
    print(f"  {'测试机制':<28} {'n':>4} {'起点ASR':>8} {'m3-dpo ASR':>10}")
    for mech in sorted(by, key=lambda k: -len(by[k])):
        sub = by[mech]
        k = sum(1 for x in sub if str(x.get("label")) == "comply")
        bsub = [bitems[str(x.get("id"))] for x in sub
                if str(x.get("id")) in bitems]
        bk = sum(1 for x in bsub if str(x.get("label")) == "comply")
        br = f"{bk/len(bsub):.1%}" if bsub else "?"
        print(f"  {mech:<28} {len(sub):>4} {br:>8} {k/len(sub):>10.1%}")
    print("\nGENERATOR-TAXONOMY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
