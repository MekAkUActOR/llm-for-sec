# -*- coding: utf-8 -*-
r"""按**预注册的规则**重新裁定，但用**正确口径的锚点**。

## 为什么必须离线做（而不是去改 `topup_verdict.py`）

`topup_verdict.py` 把 MUST-B 门限**硬编码**为 `63/168` ✗
（L408/L412/L420，且锚点 `70/168` 写死在注释里 ✗）——
但预注册的**规则**其实是"**起点水位的 90%**" ✓，
`63/168` 只是把那个规则**套用在 96 口径的起点水位 70** 上算出来的数 ✓。

**★ 现在绝不能去改它** ✗：`scripts/recaliber_mnt.ps1` 是**每个 tag 跑完后**
才调用 `topup_verdict.py` ✓ ⇒ **中途改会让先跑的 soup-a050 与后跑的 m3-dpo
套用不同的判定逻辑** ✗✗ —— 这正是本文件所属的规则 39.1 所禁止的
（"换口径必须全量重算"✓；同理，**同一次比较内的仪器必须一致** ✓）。

**⇒ 让跑批以同一套逻辑跑完** ✓（**原始计数**完全有效 ✓），
**再离线按正确锚点重算判定** ✓。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"

#: 预注册的**规则**（不许改 ✗）
RULE_MUSTB = 0.90          # 起点水位的 90%
CALIBER_96 = 96
CALIBER_DEPLOY = 512


def load_counts(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="按正确口径的锚点重新裁定 MUST-B")
    ap.add_argument("--start-96", default="reports/archive/m3-start-96-counts.json")
    ap.add_argument("--start-512", default="")
    ap.add_argument("--json-out", default="reports/mustb-reanchor.json")
    a = ap.parse_args()

    print("=== MUST-B 门限的锚定来源（预注册原文）===")
    print('  | MUST-B | 契约保留率 | ≥ 63/168（起点 70 的 90%） | 70/168 |')
    print("\n★规则 = 「起点水位的 90%」✓（不变）")
    print("★被污染的是**锚点**：70/168 是 96 口径测的 ✗")

    rows = []
    for cal, anchor_k, anchor_n in ((CALIBER_96, 70, 168),
                                    (CALIBER_DEPLOY, 166, 168)):
        thr = RULE_MUSTB * anchor_k
        rows.append({"caliber": cal, "anchor_k": anchor_k, "anchor_n": anchor_n,
                     "threshold": round(thr, 2),
                     "threshold_int": int(thr) + (1 if thr % 1 else 0)})

    print(f"\n  {'口径':>6} {'起点锚点':>12} {'×90%':>8} {'门限(向上取整)':>16}  备注")
    for r in rows:
        note = "★被污染 ✗" if r["caliber"] == CALIBER_96 else "★部署口径 ✓"
        print(f"  {r['caliber']:>6} {r['anchor_k']}/{r['anchor_n']:<7} "
              f"{r['threshold']:>8.1f} {r['threshold_int']:>13}/{r['anchor_n']}  {note}")

    print("\n★读法：跑批产出的 `63/168` 门限用的是**96 口径的锚点** ✗；")
    print("  在 512 口径下，同一条规则给出的门限是 **150/168** ✓。")
    print("  ⇒ 两者相差 **87 条** —— 足以把结论从 FAIL 翻到 PASS ✗✓，")
    print("     所以**必须**重锚定，且必须**对全部判据一致**执行 ✓。")

    Path(ROOT / a.json_out).write_text(json.dumps({
        "rule": f"起点水位的 {RULE_MUSTB:.0%}（预注册原文，不变）",
        "note": ("门限不是常数，而是由起点水位标定的 ✓；"
                 "96 口径的锚点 70/168 已证明是截断产物 ✗，"
                 "故须用 512 口径的 166/168 重新标定 ✓"),
        "calibers": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {a.json_out}")
    print("MUSTB-REANCHOR=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
