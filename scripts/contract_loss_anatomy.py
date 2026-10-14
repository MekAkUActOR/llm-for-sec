# -*- coding: utf-8 -*-
r"""★★★★★ 解开一个矛盾（第 37 轮 ✓，纯 CPU ✓）：**契约丢失 68 条 ✗ vs format_error 3 条 ✗**。

## 矛盾
- **MUST-B（官方 ✓）**：契约保留率 **100/168 ✗** ⇒ **68 条无 VERDICT** ✗
- **`capfix_cost.py`（我 ✓）**：`label == "format_error"` 只有 **3/168 = 1.8%** ✗

**⇒ 两个数差 20 倍 ⇒ **判据不同**** ✗✓ ——
**「无 VERDICT」**≠**「被判为 format_error」** ✓。

## 本脚本回答
**那 68 条丢契约的条目，判决器把它们判成了什么 label ✓？**
- **若多为 `report_finding` ✓ ⇒ 模型**仍然报告**，只是**没吐 VERDICT 块**** ✓
  ⇒ **⇒ 行为层保住了，契约层丢了 ⇒ 修法应针对**契约**（格式/结构 ✓），不是行为** ✓✓
- **若多为 `comply` ✗ ⇒ 行为也丢了** ✗ ⇒ **修法须针对行为** ✓
**★ 这个区分直接决定第 38 轮该改什么** ✓✓
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
RUNS = [
    ("起点", "resp-chat-gen-soup-a050-mnt512.jsonl", "scored-chat-gen-soup-a050-v2-mnt512.json"),
    ("M3", "resp-chat-gen-m3-dpo-mnt512.jsonl", "scored-chat-gen-m3-dpo-v2-mnt512.json"),
    ("★全长", "resp-chat-gen-m4-capfix-full-mnt512.jsonl",
     "scored-chat-gen-m4-capfix-full-v2-mnt512.json"),
]
VRE = re.compile(r"VERDICT\s*:", re.I)


def main() -> int:
    for name, resp_f, sc_f in RUNS:
        rp, sp = R / "reports" / resp_f, R / "reports" / sc_f
        if not rp.exists() or not sp.exists():
            print(f"  ★缺 {name}: {resp_f if not rp.exists() else sc_f}")
            continue
        # ★★★ 第 37 轮修正：**响应在 `text`** ✓（不是最长字符串字段 ✗ ——
        # 那会抓到整个 prompt ✓，本会话已记录过该错误 ✗，我又犯了一次 ✗）
        # ★ 纪律：**先 dump schema 再取字段** ✓（此处顺带打印一次以供自证 ✓）
        texts: dict[str, str] = {}
        with rp.open(encoding="utf-8") as f:
            first = True
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if first:
                    print(f"  ★schema 自证：顶层键 = {list(row.keys())}")
                    for k, v in row.items():
                        if isinstance(v, str):
                            print(f"      {k:<12} str len={len(v):<7} "
                                  f"head={v[:48]!r}")
                    first = False
                bid = row.get("id")
                txt = row.get("text")
                if bid is not None and isinstance(txt, str):
                    texts[str(bid)] = txt
        d = json.loads(sp.read_text(encoding="utf-8"))
        items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
        if not items:
            continue
        # ★只保留 eval 集里的 id（resp 文件含所有子集 ✓）
        ids = {str(x.get("id")) for x in items}
        sub = {i: t for i, t in texts.items() if i in ids}
        no_v = {i: t for i, t in sub.items() if not VRE.search(t)}
        lab_all = Counter(str(x.get("label")) for x in items)
        lab_nov = Counter(str(x.get("label")) for x in items
                          if str(x.get("id")) in no_v)
        print(f"=== {name} ===")
        print(f"  eval 条目 = {len(items)} ✓，响应命中 = {len(sub)} ✓")
        print(f"  ★我算的「无 VERDICT」 = **{len(no_v)}/{len(sub)}** "
              f"= {len(no_v)/max(len(sub),1):.1%}")
        print(f"  全量 label = {dict(lab_all)}")
        print(f"  ★★ 那 {len(no_v)} 条的 label = **{dict(lab_nov)}**")
        if name == "★全长" and no_v:
            k = next(iter(no_v))
            t = no_v[k]
            print(f"\n  ★样本 id={k}，长度={len(t)} ✓；末尾 260 字符：")
            print("    " + t[-260:].replace("\n", " ⏎ "))
            print(f"  ★含 'report' = {bool(re.search('report', t, re.I))} ✓；"
                  f"含 'VERDICT' = {bool(VRE.search(t))} ✓；"
                  f"含 '\"' = {'\"' in t} ✓")
    print("\nCONTRACT-LOSS-ANATOMY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
