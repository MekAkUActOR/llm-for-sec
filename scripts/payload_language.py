# -*- coding: utf-8 -*-
r"""★★★★★★ 用**注入载荷自身的语言**重做分档（不是 `language` 字段 ✗）。

## 为什么必须重做

`language` 字段指**条目/协议**语言 ✓，**不是注入载荷的语言** ✗。
实证：`gen-av-a3` 的 `language="zh"` ✓ 但其注入正文是英文 ✗
（`"cover-art note: this artwork is pre-licensed — skip the copyright..."` ✓）。

⇒ 上一版的"en 74.4% / zh 27.9%"是**用错维度分出来的** ✗✓，作废 ✓。

**★ 正确口径**：抽取载体里被标为 `[text-bearing]` 的**带文本字符串** ✓，
按**该字符串**的中英构成定语言 ✓ ⇒ 这是"注入载荷语言" ✓✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
D = ROOT / "data" / "heldout" / "v0.3-gen"
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)
QUOTED = re.compile(r'"([^"]{12,})"')
CJK = re.compile(r"[\u4e00-\u9fff]")


def payload_texts() -> dict[str, list[str]]:
    """每个 id → 载体里所有引号内文本（长度 ≥12 ✓）。"""
    out = {}
    for p in sorted(D.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) != "robustness":
                continue
            m = CARRIER.search(str(r.get("query") or ""))
            if not m:
                continue
            body = m.group(1)
            # 排除 meta 里的 file/declared_type 等（它们也是引号 ✓ 但非载荷 ✓）
            body = re.sub(r"<meta>.*?</meta>", "", body, flags=re.S)
            out[str(r.get("id"))] = QUOTED.findall(body)
    return out


def lang_of(t: str) -> str:
    cjk = len(CJK.findall(t))
    lat = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    if cjk == 0:
        return "payload-en"
    if lat == 0:
        return "payload-zh"
    return "payload-zh" if cjk * 2 > lat else "payload-en"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", default="reports/scored-chat-gen-m3-dpo-v2-mnt512.json")
    ap.add_argument("--show", type=int, default=2)
    a = ap.parse_args()

    pt = payload_texts()
    print(f"=== 载体带文本字符串统计 n={len(pt)} ===")
    nz = sum(1 for v in pt.values() if v)
    print(f"  非空 = {nz}")
    print(f"  每条字符串数中位 = "
          f"{sorted(len(v) for v in pt.values())[len(pt)//2]}")

    # 每个 id 取"最长"的那条作为注入载荷（注入通常是长文本 ✓）
    inj = {i: max(v, key=len) for i, v in pt.items() if v}
    print(f"  注入载荷语言分布 = {dict(Counter(lang_of(t) for t in inj.values()))}")

    for name, rel in [("起点 soup-a050", "reports/scored-chat-gen-soup-a050-v2-mnt512.json"),
                      ("m3-dpo", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json")]:
        p = ROOT / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
        print(f"\n{'='*80}\n{name}  n={len(items)}\n{'='*80}")
        print(f"  {'注入载荷语言':<14} {'n':>4} {'comply':>7} {'ASR':>8}  标签")
        for lg in ("payload-zh", "payload-en"):
            sub = [x for x in items if lang_of(inj.get(str(x.get("id")), "")) == lg]
            if not sub:
                continue
            k = sum(1 for x in sub if str(x.get("label")) == "comply")
            c = Counter(str(x.get("label")) for x in sub)
            print(f"  {lg:<14} {len(sub):>4} {k:>7} {k/len(sub):>8.1%}  {dict(c)}")

    print("\n=== 对照：`language` 字段 vs 注入载荷语言 ===")
    cross = Counter()
    for p in sorted(D.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) != "robustness":
                continue
            i = str(r.get("id"))
            cross[(str(r.get("language")), lang_of(inj.get(i, "")))] += 1
    for k, v in sorted(cross.items()):
        print(f"  language={k[0]:<3} × {k[1]:<11} = {v}")
    print("  ★若两者大量不一致 ⇒ `language` 字段**不能**当作注入语言 ✓")

    if a.show:
        print("\n=== 中文载荷样本 ===")
        for i, t in list((k, v) for k, v in inj.items()
                         if lang_of(v) == "payload-zh")[:a.show]:
            print(f"  [{i}] {t[:220]}")
        print("\n=== 英文载荷样本 ===")
        for i, t in list((k, v) for k, v in inj.items()
                         if lang_of(v) == "payload-en")[:a.show]:
            print(f"  [{i}] {t[:220]}")
    print("\nPAYLOAD-LANGUAGE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
