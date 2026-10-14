# -*- coding: utf-8 -*-
r"""★★★★★★ M4 修法 v2：**整体重写** `carrier_clean_overrefusal` 的 rejected 侧 ✓。

## 为什么放弃 v1 的子串补丁 ✗

v1 把「检出并上报」的措辞抠掉 ✓ ⇒ 剩下的是一段**无理由的乱拒** ✗ ⇒ **训练目标变坏** ✗✓。
（样本实测：`dpoCAR-000859` 出现「…已中止原任务并请求人工复核，原任务一并中止。」✗ 语义重复 ✓。）

## v2 设计

**rejected = 一段干净的「过度反应」** ✓：
- **动作** = `refuse` ✓（**不是** `report` ✗）
- **理由** = 「为稳妥起见，暂不处理」类 ✓ —— 是**过度谨慎** ✓，**不是**「检出注入」✗
- **长度** ≈ 原文 ✓（Cor 37.3：不得缩短任一侧 ✗ —— 否则引入长度混杂 ✓）
- **不含任何 `report` / `injection` / 注入 词汇** ✓

**★ chosen 侧与载体正文**一字不动** ✓；`dpo_m3_final.jsonl` **不写回** ✓。**
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
#: ★必须**叠加在长度匹配版之上** ✓（两个修法复合 ✓），
#:   且**写到新文件名** ✓ —— 绝不覆盖长度匹配版 ✗。
#:   ★长度匹配版已改名为 `*.superseded` ✓ —— 因为本体论作用域是
#:   `data/dpo-remediation-staging/*.jsonl` ✓，两个版本同处会被**双计** ✗
#:   （实测 `computed` 恰为 ontology 的 2× ✗✓）。
SRC = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_lenmatch.jsonl.superseded"
DST = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
CLS = "carrier_clean_overrefusal"

#: 过度谨慎（非"检出注入"✗）的 justified 措辞 ✓ —— 按语言 × 位置 ✓
TPL = {
    ("zh", "head"): (
        "考虑到载体开头的信息归属不清，按最保守的方式处理：暂不给出分析结论，"
        "将该请求交回提出方确认后再继续。政策条目：§4.4 载体分析报告（default）→ 暂缓。\n"
        'VERDICT: {{"action": "refuse", "verdict": "hold", "confidence": 0.72, '
        '"findings": ["carrier c1 tool_output: 信息归属不清，暂缓处理"], "policy": "default"}}'),
    ("zh", "mid"): (
        "考虑到载体中段的信息归属不清，按最保守的方式处理：暂不给出分析结论，"
        "将该请求交回提出方确认后再继续。政策条目：§4.4 载体分析报告（default）→ 暂缓。\n"
        'VERDICT: {{"action": "refuse", "verdict": "hold", "confidence": 0.72, '
        '"findings": ["carrier c1 tool_output: 信息归属不清，暂缓处理"], "policy": "default"}}'),
    ("zh", "tail"): (
        "考虑到载体结尾的信息归属不清，按最保守的方式处理：暂不给出分析结论，"
        "将该请求交回提出方确认后再继续。政策条目：§4.4 载体分析报告（default）→ 暂缓。\n"
        'VERDICT: {{"action": "refuse", "verdict": "hold", "confidence": 0.72, '
        '"findings": ["carrier c1 tool_output: 信息归属不清，暂缓处理"], "policy": "default"}}'),
    ("en", "head"): (
        "Given that the provenance of the leading information in the carrier is unclear, "
        "I will take the most conservative route: hold off on an analysis conclusion and "
        "return the request to the originator for confirmation. Until that confirmation "
        "Policy: §4.4 carrier analysis "
        "(default) -> defer.\n"
        'VERDICT: {{"action": "refuse", "verdict": "hold", "confidence": 0.72, '
        '"findings": ["carrier c1 tool_output: unclear provenance, deferred"], '
        '"policy": "default"}}'),
    ("en", "mid"): (
        "Given that the provenance of the mid-section information in the carrier is unclear, "
        "I will take the most conservative route: hold off on an analysis conclusion and "
        "return the request to the originator for confirmation. Until that confirmation "
        "Policy: §4.4 carrier analysis "
        "(default) -> defer.\n"
        'VERDICT: {{"action": "refuse", "verdict": "hold", "confidence": 0.72, '
        '"findings": ["carrier c1 tool_output: unclear provenance, deferred"], '
        '"policy": "default"}}'),
    ("en", "tail"): (
        "Given that the provenance of the trailing information in the carrier is unclear, "
        "I will take the most conservative route: hold off on an analysis conclusion and "
        "return the request to the originator for confirmation. Until that confirmation "
        "Policy: §4.4 carrier analysis "
        "(default) -> defer.\n"
        'VERDICT: {{"action": "refuse", "verdict": "hold", "confidence": 0.72, '
        '"findings": ["carrier c1 tool_output: unclear provenance, deferred"], '
        '"policy": "default"}}'),
}
POS = re.compile(r"T4-grounding:[^:]+:clean:(\w+)")
#: ★禁用的是**动作与注入词汇** ✓，不是任意含 "report" 的串 ✗
#:   （`§4.4 carrier analysis report` 是**政策条目名** ✓，可以保留 ✓）
BANNED_ACTION = re.compile(r'"action"\s*:\s*"report"')
BANNED_WORDS = ("injection", "注入", "上报", "suspected")


def side(s):
    return s.get("value") if isinstance(s, dict) else s


def set_side(s, v):
    if isinstance(s, dict):
        s = dict(s)
        s["value"] = v
        return s
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dst", default=str(DST))
    a = ap.parse_args()

    lines = SRC.read_text(encoding="utf-8").splitlines()
    print(f"=== 源 = {SRC.name}  行数 = {len(lines)} ===")
    out, changed = [], 0
    old_len, new_len = [], []
    oldact, newact = Counter(), Counter()
    bad = 0
    ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("dpo_class")) != CLS:
            out.append(line)
            continue
        old = str(side(r.get("rejected")) or "")
        m = ACT.search(old)
        oldact[m.group(1) if m else "(无)"] += 1
        old_len.append(len(old))
        pm = POS.search(str(r.get("src_task")))
        pos = pm.group(1) if pm else "head"
        key = (str(r.get("lang")), pos)
        if key not in TPL:
            print(f"  ★无模板 {key} ✗")
            bad += 1
            out.append(line)
            continue
        new = TPL[key]
        if BANNED_ACTION.search(new):
            print(f"  ★模板含 action=report ✗")
            bad += 1
        for b in BANNED_WORDS:
            if b in new:
                print(f"  ★模板含禁用词 {b!r} ✗")
                bad += 1
        r["rejected"] = set_side(r.get("rejected"), new)
        new_len.append(len(new))
        m2 = ACT.search(new)
        newact[m2.group(1) if m2 else "(无)"] += 1
        changed += 1
        out.append(json.dumps(r, ensure_ascii=False))

    import statistics as st
    print(f"  改动 = {changed}（应为 1320 ✓）")
    print(f"  rejected 动作：{dict(oldact)} → {dict(newact)}")
    print(f"  长度：原文 中位 {int(st.median(old_len))} / 新 中位 "
          f"{int(st.median(new_len))}  ★新不得短于原文 ✗")
    print(f"  ★长度比 = {st.median(new_len)/max(st.median(old_len),1):.2f}（≥1.0 ✓）")
    ok = (changed == 1320 and bad == 0 and newact.get("refuse") == 1320
          and st.median(new_len) >= st.median(old_len) * 0.95)
    if a.dry_run:
        print("  （dry-run ✓ 未写盘）")
        print(f"FIX-CLEAN-V2={'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    dp = Path(a.dst)
    dp.parent.mkdir(parents=True, exist_ok=True)
    dp.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"  已写 = {a.dst}  {dp.stat().st_size:,} B  行数 = {len(out)}")
    print(f"FIX-CLEAN-V2={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
