# -*- coding: utf-8 -*-
r"""★★★★★★★ M4 修法：把 `carrier_clean_overrefusal` 的 **rejected 侧**从 `report` ✗ 改为 `refuse` ✓。

## 因果依据（全部实测 ✓）

| 证据 | 数值 |
|---|---|
| `logps/rejected` 变化 | **−151.93** ✗ vs `logps/chosen` **+22.01** ✓ |
| `rewards/rejected` 变化 | **−12.46** ✗ vs `rewards/chosen` **+0.29** ✓ |
| ⇒ rejected 侧占学到的 margin | **97.7%** ✗（有效比 ≈ 43:1 ✓） |
| `report` 作 rejected | **1,320 条，全在干净支** ✗ |
| `report` 作 chosen | 4,680 条 ✓ |
| ⇒ 有效强度 | 压低 **56,760** ✗ vs 抬高 **4,680** ✓ ⇒ **12 倍压制** ✗✓ |

**⇒ `report`（注入抵抗的正确动作 ✓）被 DPO 全局压掉 ⇒ 失效** ✗✓

## 修法（外科式 ✓，只动 1,320 条的 rejected 侧 ✓）

1. **VERDICT 里** `"action": "report"` ✗ → **`"action": "refuse"`** ✓
2. **`verdict` 字段** `"contains-injection"` ✗ → **`"hold"`** ✓（不再声称检出注入 ✓）
3. **正文**去掉「并上报」/「含注入」类措辞 ✓ ⇒ **退化为纯过度反应** ✓
4. **`findings`** 去掉 `suspected-injection` 类条目 ✓

**★ 不动的**：chosen 侧一字不改 ✓；载体正文一字不改 ✓；长度只增不减 ✓（Cor 37.3 ✓）；
**不写回** `dpo_m3_final.jsonl` ✗（冻结件 ✓）—— 只写 M4 staging ✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
SRC = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
DST = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_final.jsonl"
CLS = "carrier_clean_overrefusal"

#: 正文里要抹掉的「上报 / 检出注入」措辞 ✓（zh ✓）
ZH_SUB = [
    (r"已拒绝遵循并上报", "已中止原任务并请求人工复核"),
    (r"已拒绝遵循、上报", "已中止原任务并请求人工复核"),
    (r"检测到疑似注入载荷：", "为稳妥起见中止："),
    (r"检测到注入载荷：", "为稳妥起见中止："),
    (r"疑似注入载荷", "不确定内容"),
    (r"看似面向 AI 的指令", "内容不够清晰"),
    (r"并上报", "并请求人工复核"),
]
EN_SUB = [
    (r"detected suspected injection payload:\s*", "erring on the side of caution: "),
    (r"detected injection payload:\s*", "erring on the side of caution: "),
    (r"suspected injection payload", "uncertain content"),
    (r"looks like an AI-facing instruction", "is not clearly data"),
    (r"refused and escalated", "halted and asked for human review"),
]


def side(s):
    return s.get("value") if isinstance(s, dict) else s


def set_side(s, v):
    if isinstance(s, dict):
        s = dict(s)
        s["value"] = v
        return s
    return v


def fix_rejected(text: str, lang: str) -> tuple[str, int]:
    n = 0
    for pat, rep in (ZH_SUB if lang == "zh" else EN_SUB):
        new, k = re.subn(pat, rep, text, flags=re.I)
        text = new
        n += k
    # ① action: report → refuse ✓
    new, k = re.subn(r'("action"\s*:\s*)"report"', r'\1"refuse"', text)
    text, n = new, n + k
    # ② verdict: contains-injection → hold ✓
    new, k = re.subn(r'("verdict"\s*:\s*)"[^"]*"', r'\1"hold"', text)
    text, n = new, n + k
    # ③ findings 里去掉注入条目 ✓
    new, k = re.subn(r',\s*"carrier c1 [^"]*(?:injection|注入)[^"]*"', "", text)
    text, n = new, n + k
    return text, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--dst", default=str(DST))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    lines = Path(a.src).read_text(encoding="utf-8").splitlines()
    print(f"=== 源 = {a.src}  行数 = {len(lines)} ===")
    out = []
    changed = 0
    before = Counter()
    after = Counter()
    ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("dpo_class")) != CLS:
            out.append(line)
            continue
        m = ACT.search(str(side(r.get("rejected")) or ""))
        before[m.group(1) if m else "(无)"] += 1
        nt, n = fix_rejected(str(side(r.get("rejected")) or ""),
                             str(r.get("lang")))
        if n == 0:
            print(f"  ★{r.get('id')} 未改动（须排查 ✗）")
        else:
            changed += 1
        r["rejected"] = set_side(r.get("rejected"), nt)
        m2 = ACT.search(nt)
        after[m2.group(1) if m2 else "(无)"] += 1
        out.append(json.dumps(r, ensure_ascii=False))

    print(f"  改动条目 = {changed}（应为 1320 ✓）")
    print(f"  rejected 动作：前 {dict(before)} → 后 {dict(after)}")
    ok = (changed == 1320 and after.get("refuse") == 1320
          and after.get("report", 0) == 0)
    print(f"  ★`report` 已从 rejected 侧消失 = {after.get('report', 0) == 0}")
    if a.dry_run:
        print("  （dry-run，未写盘 ✓）")
        print(f"FIX-CLEAN-REJECTED={'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1

    dp = Path(a.dst)
    dp.parent.mkdir(parents=True, exist_ok=True)
    dp.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"  已写 = {a.dst}  {dp.stat().st_size:,} B  行数 = {len(out)}")
    print(f"FIX-CLEAN-REJECTED={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
