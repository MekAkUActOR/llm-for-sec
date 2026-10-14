# -*- coding: utf-8 -*-
r"""★★★★★ 训练注入的**模板多样性** vs 测试 —— 判定"背模式 vs 学能力"。

## 假说

训练里英文注入占 **50%** ✓（2,340/4,680 ✓），但若它们只是**少数几个模板** ✗
（同一句话换字段名重复几百遍 ✓）⇒ 模型背下的是**那几个模板** ✗
⇒ 遇到测试里**措辞不同**的英文注入就失效 ✗✓。

**★ 度量**：注入文本的**去重后条数 / 总条数**（模板率 ✓），
以及去重后的**平均模板复用次数** ✓。**测试侧用同一把尺子量** ✓。
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
QUOTED = re.compile(r'"([^"]{12,})"')
CJK = re.compile(r"[\u4e00-\u9fff]")
#: 把数字/十六进制/邮箱等**可变槽位**归一，以看模板骨架 ✓
SLOT = re.compile(r"[0-9a-fA-F]{4,}|[\w.+-]+@[\w.-]+|\b\d+\b")


def norm(t: str) -> str:
    return SLOT.sub("<N>", t).strip()


def lang_of(t: str) -> str:
    cjk = len(CJK.findall(t))
    lat = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    if cjk == 0:
        return "en"
    if lat == 0:
        return "zh"
    return "zh" if cjk * 2 > lat else "en"


def payloads(path: Path, kind: str | None = None) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if kind and str(r.get("kind")) != kind:
            continue
        src = r.get("query")
        if not isinstance(src, str):
            src = next((str(c.get("value") or "") for c in (r.get("conversations") or [])
                        if c.get("from") == "human"), "")
        m = CARRIER.search(src or "")
        if not m:
            continue
        body = re.sub(r"<meta>.*?</meta>", "", m.group(1), flags=re.S)
        q = QUOTED.findall(body)
        if q:
            out.append(max(q, key=len))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/lf/dpo_m3_final.jsonl")
    ap.add_argument("--classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow"])
    a = ap.parse_args()

    rows = [json.loads(l) for l in (ROOT / a.data).read_text(
        encoding="utf-8").splitlines() if l.strip()]
    print("=== ① 训练注入的模板多样性（按 dpo_class）===")
    print(f"  {'dpo_class':<28} {'n':>5} {'lang':<4} {'去重后':>7} {'复用倍数':>9} "
          f"{'最高频模板出现次数':>18}")
    for cls in a.classes:
        texts = []
        for r in rows:
            if str(r.get("dpo_class")) != cls:
                continue
            hum = next((str(c.get("value") or "") for c in (r.get("conversations") or [])
                        if c.get("from") == "human"), "")
            m = CARRIER.search(hum)
            if not m:
                continue
            q = QUOTED.findall(re.sub(r"<meta>.*?</meta>", "", m.group(1), flags=re.S))
            if q:
                texts.append(max(q, key=len))
        for lg in ("zh", "en"):
            sub = [t for t in texts if lang_of(t) == lg]
            if not sub:
                continue
            uniq = Counter(norm(t) for t in sub)
            top = uniq.most_common(1)[0][1] if uniq else 0
            print(f"  {cls:<28} {len(sub):>5} {lg:<4} {len(uniq):>7} "
                  f"{len(sub)/max(len(uniq),1):>9.1f} {top:>18}")

    print("\n=== ② 测试注入（v0.3-gen）的同一度量 ===")
    tst = payloads(ROOT / "data" / "heldout" / "v0.3-gen" / "av_metadata.jsonl",
                   "robustness")
    tst += payloads(ROOT / "data" / "heldout" / "v0.3-gen" / "image_metadata.jsonl",
                    "robustness")
    for lg in ("zh", "en"):
        sub = [t for t in tst if lang_of(t) == lg]
        if not sub:
            continue
        uniq = Counter(norm(t) for t in sub)
        print(f"  {'测试 v0.3-gen':<28} {len(sub):>5} {lg:<4} {len(uniq):>7} "
              f"{len(sub)/max(len(uniq),1):>9.1f} "
              f"{(uniq.most_common(1)[0][1] if uniq else 0):>18}")

    print("\n★判读：")
    print("  · 训练 ↔ 测试的『复用倍数』差得远 ⇒ **训练是模板化背诵** ✗✓")
    print("    ⇒ 修法：**提高注入措辞多样性**（不是加量 ✗）✓✓")
    print("  · 两边接近 ⇒ 多样性不是主因，须继续查 ✗")
    print("\nTEMPLATE-DIVERSITY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
