# -*- coding: utf-8 -*-
r"""诊断：为什么训练数据的载体抽取只覆盖 8.6%（402/4680）✗。"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)
QUOTED = re.compile(r'"([^"]{12,})"')

CLS = ("carrier_inject_obedient", "carrier_inject_hollow")


def main() -> int:
    rows = [json.loads(l) for l in (ROOT / "data" / "lf" / "dpo_m3_final.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    sel = [r for r in rows if str(r.get("dpo_class")) in CLS]
    print(f"=== 目标类 {len(sel)} 行 ===")
    print(f"  顶层键 = {sorted(sel[0].keys())}")

    c = Counter()
    for r in sel:
        convs = r.get("conversations") or []
        hum = [str(x.get("value") or "") for x in convs if x.get("from") == "human"]
        if not hum:
            c["无人回合"] += 1
            continue
        h = hum[0]
        if "<carrier" not in h:
            c["人回合无 <carrier"] += 1
        if CARRIER.search(h):
            c["CARRIER 正则命中"] += 1
        else:
            c["CARRIER 正则未命中"] += 1
        m = CARRIER.search(h)
        if m:
            body = re.sub(r"<meta>.*?</meta>", "", m.group(1), flags=re.S)
            if QUOTED.findall(body):
                c["且有引号文本(≥12)"] += 1
            else:
                c["但无引号文本(≥12)"] += 1
    for k, v in c.most_common():
        print(f"  {k:<26} {v}")

    print("\n=== 一个『CARRIER 命中但无引号文本』的样本 ===")
    for r in sel:
        h = next((str(x.get("value") or "") for x in (r.get("conversations") or [])
                  if x.get("from") == "human"), "")
        m = CARRIER.search(h)
        if not m:
            continue
        body = re.sub(r"<meta>.*?</meta>", "", m.group(1), flags=re.S)
        if not QUOTED.findall(body):
            print(f"  id={r.get('id')} dpo_class={r.get('dpo_class')}")
            print(f"  --- carrier（前 900 字）---\n{body[:900]}")
            break

    print("\n=== 一个『人回合无 <carrier』的样本 ===")
    for r in sel:
        h = next((str(x.get("value") or "") for x in (r.get("conversations") or [])
                  if x.get("from") == "human"), "")
        if h and "<carrier" not in h:
            print(f"  id={r.get('id')} dpo_class={r.get('dpo_class')}")
            print(f"  --- human（前 900 字）---\n{h[:900]}")
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
