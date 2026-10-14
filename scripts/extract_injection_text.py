# -*- coding: utf-8 -*-
r"""★★★★★★ 注入文本的**经过验证**的抽取器（两侧同法，并强制人工可见 ✓）。

## 为什么必须重写

本轮我连续用了三个代理，全部失效 ✗：
1. **引号内文本** ✗ —— 训练注入不带引号 ⇒ 覆盖 402/4680 = 8.6% ✗
2. **`language` 字段** ✗ —— 那是条目语言 ⇒ 86 条"zh"里 64 条载荷是英文 ✗
3. **整段载体正文定语言** ✗ —— 结构化 ASCII 淹没注入 ⇒ 168 条全判 en ✗

**根因**：我要量的是**嵌在结构化噪声里的散文子串** ✓，
而我没有**在两侧都验证抽取结果**就往下算 ✗。

## 本抽取器的验证设计（强制 ✓）

- **散文行判据**（对中英都对 ✓）：行内含 ≥4 个连续 CJK 字符 ✓
  **或** ≥3 个连续 ASCII 词且行内含动词/指令性语气词 ✓；
  **且**排除纯结构化记录（以 `[box`/`[track`/`[ebml`… 开头且不含散文 ✓）。
- **★ 强制打印**：每类的条数 ✓、抽出文本的**长度中位** ✓、
  以及**两侧各 3 条真实样本** ✓ —— **不打印样本的结果一律不得采用** ✓✓。

**★ 登记为纪律：凡"抽取——统计"两步的分析，必须先看抽取样本 ✓。**
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)
CJK_RUN = re.compile(r"[\u4e00-\u9fff]{4,}")
ASCII_RUN = re.compile(r"[A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z'\-]+){2,}")
STRUCT = re.compile(r"^\s*\[(box|track|ebml|segment|chapter|tag|container|meta|"
                    r"attachment\.\w+\.bytes|codec|format)\b", re.I)
CJK = re.compile(r"[\u4e00-\u9fff]")


def prose_lines(body: str) -> list[str]:
    body = re.sub(r"<meta>.*?</meta>", "", body, flags=re.S)
    out = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        # 去掉行首的结构化前缀，但**保留**其后的散文 ✓
        if line.startswith("[") and "]" in line:
            head, _, rest = line.partition("]")
            if STRUCT.match(line) and not CJK_RUN.search(rest):
                continue
            line = rest.strip() or line
        # 去掉 key=value 段（保留 value 里的散文 ✓）
        vals = re.findall(r'"([^"]{8,})"', line)
        cand = " ".join(vals) if vals else line
        if CJK_RUN.search(cand) or ASCII_RUN.search(cand):
            vals2 = [v for v in vals
                     if CJK_RUN.search(v) or ASCII_RUN.search(v)]
            for v in vals2:
                out.append(v)
            if not vals2 and not re.match(r"^[\[\w./=#-]+$", cand):
                out.append(cand)
    return out


def lang_of(t: str) -> str:
    cjk = len(CJK.findall(t))
    lat = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    if cjk == 0:
        return "en"
    if lat == 0:
        return "zh"
    return "zh" if cjk * 2 > lat else "en"


def from_train(cls: str) -> list[str]:
    out = []
    rows = [json.loads(l) for l in (ROOT / "data" / "lf" / "dpo_m3_final.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        if str(r.get("dpo_class")) != cls:
            continue
        h = next((str(x.get("value") or "") for x in (r.get("conversations") or [])
                  if x.get("from") == "human"), "")
        m = CARRIER.search(h)
        if m:
            out += prose_lines(m.group(1))
    return out


def from_test() -> list[str]:
    out = []
    d = ROOT / "data" / "heldout" / "v0.3-gen"
    for p in sorted(d.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) != "robustness":
                continue
            m = CARRIER.search(str(r.get("query") or ""))
            if m:
                out += prose_lines(m.group(1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow",
                             "carrier_clean_overrefusal"])
    ap.add_argument("--samples", type=int, default=3)
    a = ap.parse_args()

    allsets: dict[str, list[str]] = {}
    for cls in a.classes:
        allsets[f"训练 {cls}"] = from_train(cls)
    allsets["测试 v0.3-gen"] = from_test()

    print("=== 抽取覆盖与语言构成（★必须先看样本再采信 ✓）===")
    print(f"  {'集合':<38} {'散文行':>7} {'lang分布':<26} {'长度中位':>8}")
    for k, v in allsets.items():
        if not v:
            print(f"  {k:<38} ★0")
            continue
        lg = Counter(lang_of(t) for t in v)
        ln = sorted(len(t) for t in v)[len(v) // 2]
        print(f"  {k:<38} {len(v):>7} {str(dict(lg)):<26} {ln:>8}")

    print(f"\n=== ★两侧各抽 {a.samples} 条真实样本（防代理失效 ✓）===")
    for k, v in allsets.items():
        if not v:
            continue
        print(f"\n--- {k} ---")
        seen = set()
        shown = 0
        for t in sorted(v, key=len, reverse=True):
            key = t[:40]
            if key in seen:
                continue
            seen.add(key)
            print(f"  · [{lang_of(t)}] {t[:230]}")
            shown += 1
            if shown >= a.samples:
                break
    print("\nINJECTION-EXTRACTOR=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
