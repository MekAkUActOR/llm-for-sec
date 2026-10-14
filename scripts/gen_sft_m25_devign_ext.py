# -*- coding: utf-8 -*-
"""M2.5 fG：devign 深池 en 侧扩容（T6 代码漏洞定位，纯 en × 三包）。

背景：devign 清洗语料 10,039 条，fD 仅释放前 1,167 条（× 3 包 = 3,501 行）。
全局 zh 配比压力（新族偏 zh：fA 64.8% / t14 69.6% / fC 57.1%）需要 en 侧增量，
而 T6 代码漏洞定位是任务最相关的安全能力之一 → 释放 [1167:5167) 4,000 条
记录 × 3 包 = 12,000 行**纯 en** 行。

同源纪律：
- 与 fD 共用同一 filter 与同一洗牌种子（RNG_SHUFFLE=20260929），切片
  [1167:5167) 与 fD 的 [0:1167) 零重叠；
- 与 m1 零同文（m1 的 T6 源为 GTFOBins/LOLBAS，本族为 devign）；
- 代码含 CJK 注释的记录跳过（维持 en 行纯 ASCII 结构闸）。

用法：python scripts/gen_sft_m25_devign_ext.py
输出：data/sft/m2.5-staging/fG_t6_devign_ext.jsonl（12,000 行预期）
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_m25_t6 import (  # noqa: E402
    PACKS, RNG_SEED, SRC_DEVIGN, classify, parse_devign, verdict)
from gen_sft_v0 import build_sample  # noqa: E402

OUT = ROOT / "data" / "sft" / "m2.5-staging" / "fG_t6_devign_ext.jsonl"
M1 = ROOT / "data" / "lf" / "sft_m1.jsonl"
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
START, STOP = 1167, 5167          # 与 fD 切片不重叠
_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")


def main() -> int:
    rng = random.Random(RNG_SEED)
    recs = []
    with SRC_DEVIGN.open(encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)["text"]
            if not (100 < len(t) < 8000):
                continue
            p = parse_devign(t)
            if not (p and 1 <= len(p[3]) <= 4):
                continue
            project, commit, code, vuln_lines = p
            if _CJK.search(code):        # en 行纯 ASCII 结构闸
                continue
            recs.append(p)
    rng.shuffle(recs)                # 与 fD 同一 RNG_SEED → 同序
    taken = recs[START:STOP]

    rows = []
    n = 0
    for project, commit, code, vuln_lines in taken:
        lines_str = ", ".join(str(x) for x in vuln_lines)
        n_str = f"{len(vuln_lines)} line(s)"
        _, en_pat = classify([code.split("\n")[i - 1] for i in vuln_lines])
        user = (f"The following function is from the open-source project "
                f"{project}. Locate the vulnerable lines: give line numbers "
                f"and explain the defect pattern (analysis use).\n\n{code}")
        body = {
            "conservative": f"Vulnerable lines: {lines_str} ({n_str}). "
                            f"Pattern: {en_pat[0]}.",
            "default": (f"Vulnerable lines: {lines_str} ({n_str}).\n"
                        f"Pattern: {en_pat[0]}.\n"
                        f"Cause & impact: {en_pat[1]}\n"
                        f"Fix direction: {en_pat[2]}"),
            "professional": (f"Vulnerable lines: {lines_str} ({n_str}).\n"
                             f"Pattern: {en_pat[0]}.\n"
                             f"Cause & impact: {en_pat[1]}\n"
                             f"Fix direction: {en_pat[2]}\n"
                             f"Verification: {en_pat[3]}"),
        }
        for pack in PACKS:
            n += 1
            assistant = body[pack] + "\n" + verdict(
                "answer", "contains-vulnerability", 0.9,
                [f"devign-ext:{project}:{commit[:8]}"], pack)
            rows.append(build_sample(
                f"sft-T6E-{n:05d}",
                f"T6-code:devign-ext:{project}:{commit[:8]}",
                pack, "en", user, assistant))

    # ---------- 断言 ----------
    assert len(rows) == 3 * len(taken), "三包展开不齐"
    assert len(rows) >= 11000, f"行数 {len(rows)} < 11,000（池不足）"
    packs = {}
    for r in rows:
        packs[r["pack"]] = packs.get(r["pack"], 0) + 1
        assert r["lang"] == "en"
        assert "VERDICT: " in r["messages"][2]["content"]
        assert not _CJK.search(r["messages"][1]["content"])
        assert not _CJK.search(r["messages"][2]["content"])
    pv = list(packs.values())
    assert max(pv) - min(pv) <= 3, f"包不均 {packs}"
    seen = set()
    for p in [M1] + sorted(STAGE.glob("*.jsonl")):
        if p.name == OUT.name:
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                j = json.loads(line)
                for m in j.get("messages", []):
                    if m.get("role") == "user":
                        seen.add(hashlib.md5(
                            (j.get("pack", "") + "\x00"
                             + m["content"]).encode("utf-8")).hexdigest())
    hit = sum(1 for r in rows if hashlib.md5(
        (r["pack"] + "\x00" + r["messages"][1]["content"]).encode("utf-8")
    ).hexdigest() in seen)
    assert hit == 0, f"{hit} 行与 m1/staging 撞行"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"total": len(rows), "records": len(taken),
                      "packs": packs, "collision": hit, "out": str(OUT)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
