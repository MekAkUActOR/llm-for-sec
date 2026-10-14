# -*- coding: utf-8 -*-
r"""★★★★★★★ 量化『同句反标』缺陷 ✓ —— 载体正文在两侧**逐字相同**却有相反 chosen。

## 为什么这是决定性的

样本已证实：
- `dpoCAR-000859`（干净支 ✓ chosen=`answer`）的正文首行
  `[管道备注] 本告警与 OPS-2231 重复——已关联供参考。` ✓
- `dpoCAR-000002`（注入支 ✗ chosen=`report`）的正文首行**一字不差** ✓

**⇒ 对同一段文本，训练同时给「报告」和「不报告」两个相反的偏好** ✗✓
**⇒ DPO 无法同时满足 ⇒ 只能落到一侧 ⇒ 实测落到了 `answer`** ✗✓

**★ 这就是第 19 轮推论 41.5 要求"同句/异境硬负样本"的原因** ✓ —— 而数据违反了它 ✓。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")
CLS = ("carrier_clean_overrefusal", "carrier_inject_obedient",
       "carrier_inject_hollow")


def h_of(r: dict) -> str:
    return next((str(c.get("value") or "") for c in (r.get("conversations") or [])
                 if c.get("from") == "human"), "")


def body_of(h: str) -> str:
    m = re.search(r"<body>(.*?)</body>", h, re.S)
    return m.group(1) if m else h


def side(s) -> str:
    return str(s.get("value") or "") if isinstance(s, dict) else str(s or "")


def act_of(s) -> str:
    m = ACT.search(side(s))
    return m.group(1) if m else "(无)"


def norm(b: str) -> str:
    """正文规范化：去空白 ✓、去纯结构行 ✓（保留括号标注行 ✓）。"""
    ls = [re.sub(r"\s+", " ", l).strip() for l in b.splitlines()]
    return "\n".join(l for l in ls if l)


def main() -> int:
    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    sel = [r for r in rows if str(r.get("dpo_class")) in CLS]
    print(f"=== 参与比对的载体条目 = {len(sel)}（三类 ✓）===")

    # ① 整段正文逐字相同、但 chosen 动作不同 ⇒ ★硬矛盾
    bybody: dict[str, list] = defaultdict(list)
    for r in sel:
        bybody[norm(body_of(h_of(r)))].append(r)
    conflict = {b: rs for b, rs in bybody.items()
                if len({act_of(r.get("chosen")) for r in rs}) > 1}
    n_conf = sum(len(rs) for rs in conflict.values())
    print(f"\n=== ① ★整段正文逐字相同、chosen 动作却不同 ⇒ 直接矛盾 ===")
    print(f"  不同的正文 = {len(bybody)}")
    print(f"  ★其中**存在反标**的正文 = {len(conflict)}")
    print(f"  ★涉及条目数 = {n_conf} / {len(sel)} = {n_conf/len(sel):.1%} ✗✓")

    print(f"\n=== ② 反标正文的样本（正文不同类、chosen 相反 ✓）===")
    k = 0
    for b, rs in sorted(conflict.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  --- 正文（前 90 字）= {b[:90]!r} ---")
        for r in rs[:4]:
            print(f"      {r.get('id'):<18} {r.get('dpo_class'):<28} "
                  f"chosen={act_of(r.get('chosen')):<8} "
                  f"rejected={act_of(r.get('rejected'))}")
        print(f"      （共 {len(rs)} 条）")
        k += 1
        if k >= 5:
            break

    # ③ 逐行（标注行）层面的反标 ⇒ 更细的尺度 ✓
    print(f"\n=== ③ ★逐【行】尺度的反标（标注行 ✓）===")
    BRL = re.compile(r"^\s*[\[【][^\]]{0,24}[\]】]")
    linecls: dict[str, dict[str, Counter]] = defaultdict(
        lambda: defaultdict(Counter))
    for r in sel:
        cls = str(r.get("dpo_class"))
        act = act_of(r.get("chosen"))
        for l in body_of(h_of(r)).splitlines():
            l = re.sub(r"\s+", " ", l).strip()
            if BRL.match(l):
                linecls[l][cls][act] += 1
    yes = no = 0
    samples = []
    for l, cs in linecls.items():
        acts = {a for c in cs.values() for a in c}
        if len(acts) > 1:
            yes += 1
            samples.append((l, cs))
        else:
            no += 1
    print(f"  不同的标注行 = {yes + no}")
    print(f"  ★**同一行在两侧带相反 chosen 动作** = {yes} "
          f"（{yes/max(yes+no,1):.1%} ✗✓）")
    print(f"\n  样本：")
    for l, cs in samples[:6]:
        print(f"\n    {l[:100]!r}")
        for c, ac in cs.items():
            print(f"        {c:<30} {dict(ac)}")

    print(f"\n★判读：")
    print(f"  · 整段逐字相同却反标 = **{n_conf} 条（{n_conf/len(sel):.1%}）** ✗")
    print(f"  · 单行尺度反标 = **{yes} 种标注行** ✗")
    print("  ⇒ 数据**同时教两个相反偏好** ⇒ DPO 无解 ⇒ 落到一侧 ⇒ 实测落到 `answer` ✗✓")
    print("  ⇒ **修法**：① 两侧不得共享载体正文 ✓；② 若必须共享，")
    print("     则**注入侧必须有额外的、可判别的 AI 面向指令** ✓（推论 41.5 ✓）")
    print("\nLABEL-CONTRADICTION=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
