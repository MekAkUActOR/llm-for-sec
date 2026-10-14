# -*- coding: utf-8 -*-
r"""★★★★★★ 验证 `dpo_m4_capfix.jsonl` ✓ —— 修法是否精确、是否只动了该动的 ✓。

## 必须全绿的断言

| # | 断言 | 为什么 |
|---|---|---|
| 1 | 行数 = 28,842 ✓ | 不得丢行 ✗ |
| 2 | **`report` 不再出现在任何 rejected 侧** ✓✓ | **这正是修法的目的** ✓ |
| 3 | `carrier_clean_overrefusal` 的 rejected 全是 `refuse` ✓ | 精确改动 ✓ |
| 4 | **除该族外，其余 27,522 行与源**逐字相同**** ✓✓ | 外科式 ✓，不误伤 ✓ |
| 5 | `length_matched_from` 保留 6,540 条 ✓ | 长度修法未被破坏 ✓ |
| 6 | `report` 作 chosen 仍为 4,680 ✓ | 抵抗信号未被削弱 ✓ |
| 7 | 长度：新 rejected 中位 ≥ 源 × 0.95 ✓ | 不引入长度混杂 ✓（Cor 37.3 ✓） |
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
ST = ROOT / "data" / "dpo-remediation-staging"
#: ★源已改名以避开本体论作用域 glob（`*.jsonl` ✓）——
#:   否则同目录两个版本会被**双计** ✗（实测 `computed` 恰为 ontology 的 2× ✗✓）。
A = ST / "dpo_m4_lenmatch.jsonl.superseded"   # 源（长度匹配版 ✓，已退役）
B = ST / "dpo_m4_capfix.jsonl"                # 产物（长度匹配 + capfix ✓，唯一活候选）
CLS = "carrier_clean_overrefusal"
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")


def side(s):
    return s.get("value") if isinstance(s, dict) else s


def act(s) -> str:
    m = ACT.search(str(side(s) or ""))
    return m.group(1) if m else "(无)"


def main() -> int:
    ra = [json.loads(l) for l in A.read_text(encoding="utf-8").splitlines() if l.strip()]
    rb = [json.loads(l) for l in B.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = {}

    ok["1 行数一致"] = len(ra) == len(rb) == 28842
    print(f"  ① 行数 源 {len(ra)} / 产物 {len(rb)}  ⇒ {ok['1 行数一致']}")

    rep_rj = sum(1 for r in rb if act(r.get("rejected")) == "report")
    ok["2 report 不再作 rejected"] = rep_rj == 0
    print(f"  ② `report` 作 rejected 的条目 = {rep_rj}（须 0 ✓）⇒ "
          f"{ok['2 report 不再作 rejected']}")

    cc = [r for r in rb if str(r.get("dpo_class")) == CLS]
    cacts = Counter(act(r.get("rejected")) for r in cc)
    ok["3 干净支 rejected 全为 refuse"] = (len(cc) == 1320
                                          and cacts.get("refuse") == 1320)
    print(f"  ③ 干净支 {len(cc)} 条 rejected 动作 = {dict(cacts)} ⇒ "
          f"{ok['3 干净支 rejected 全为 refuse']}")

    # ④ 其余行逐字相同 ✓
    diff = 0
    for x, y in zip(ra, rb):
        if str(x.get("dpo_class")) == CLS:
            continue
        if json.dumps(x, ensure_ascii=False, sort_keys=True) != \
           json.dumps(y, ensure_ascii=False, sort_keys=True):
            diff += 1
    ok["4 其余行逐字相同"] = diff == 0
    print(f"  ④ 非干净支中被改动的行 = {diff}（须 0 ✓）⇒ {ok['4 其余行逐字相同']}")

    lm = sum(1 for r in rb if r.get("length_matched_from"))
    ok["5 长度匹配标记保留"] = lm == 6540
    print(f"  ⑤ `length_matched_from` = {lm}（须 6540 ✓）⇒ "
          f"{ok['5 长度匹配标记保留']}")

    rep_ch = sum(1 for r in rb if act(r.get("chosen")) == "report")
    ok["6 report 作 chosen 仍 4680"] = rep_ch == 4680
    print(f"  ⑥ `report` 作 chosen 的条目 = {rep_ch}（须 4680 ✓）⇒ "
          f"{ok['6 report 作 chosen 仍 4680']}")

    la = [len(str(side(r.get("rejected")) or "")) for r in ra
          if str(r.get("dpo_class")) == CLS]
    lb = [len(str(side(r.get("rejected")) or "")) for r in rb
          if str(r.get("dpo_class")) == CLS]
    ratio = st.median(lb) / max(st.median(la), 1)
    ok["7 未缩短 rejected"] = ratio >= 0.95
    print(f"  ⑦ rejected 长度 源中位 {int(st.median(la))} / 产物中位 "
          f"{int(st.median(lb))}  比 {ratio:.2f}（≥0.95 ✓）⇒ "
          f"{ok['7 未缩短 rejected']}")

    print(f"\n  另：`report` 作 chosen = {rep_ch}，作 rejected = {rep_rj} "
          f"⇒ **天平已从 1,320:4,680 的压制转为纯 4,680 提升** ✓✓")
    allok = all(ok.values())
    print(f"\nCAPFIX-VERIFY={'PASS' if allok else 'FAIL'}")
    for k, v in ok.items():
        if not v:
            print(f"  ✗ 未通过：{k}")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
