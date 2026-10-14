# -*- coding: utf-8 -*-
"""逐类统计"非长度"的判别信号是否存在（回答：除了长度，模型还能学什么？）。

★动机：抽样发现 `carrier_inject_obedient` 的 chosen 与 rejected **都**：
    流畅、都带完整合法 VERDICT、都含全部键 ⇒ **模型唯一能学的差别是长度** ✗。
  但也发现 `calibration` 的 rejected 里有 `"verdict": null` —— 若该形态
  **只出现在 rejected**，那它就是一个**与长度无关**的判别信号 ✓（好事）。
  本脚本把这个问法机械量化，避免再靠"看两条样本"下结论 ✗。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DPO = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"

VERDICT_RE = re.compile(r"VERDICT\s*[:：]\s*(\{.*?\})", re.S)
NULLVERDICT_RE = re.compile(r'"verdict"\s*:\s*null')
EMPTYFIND_RE = re.compile(r'"findings"\s*:\s*\[\s*\]')
ACTION_RE = re.compile(r'"action"\s*:\s*"([^"]*)"')


def txt(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("value") or v.get("content") or "")
    if isinstance(v, list):
        for m in reversed(v):
            if isinstance(m, dict) and (m.get("role") or m.get("from")) in ("assistant", "gpt"):
                return str(m.get("value") or m.get("content") or "")
    return ""


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="DPO 非长度判别信号审计（规则 37.3）")
    ap.add_argument("--data", default=str(DPO),
                    help="偏好数据 jsonl（默认 dpo_m3_final.jsonl；"
                         "长度匹配后请指向新版本如 dpo_m4_final.jsonl 做**复验**）")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()
    path = Path(args.data)

    per: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            cls = str(d.get("dpo_class"))
            g = per.setdefault(cls, {"n": 0, "c_null": 0, "r_null": 0,
                                     "c_ef": 0, "r_ef": 0,
                                     "c_act": {}, "r_act": {},
                                     "c_noverdict": 0, "r_noverdict": 0})
            ch, rj = txt(d.get("chosen")), txt(d.get("rejected"))
            g["n"] += 1
            if NULLVERDICT_RE.search(ch):
                g["c_null"] += 1
            if NULLVERDICT_RE.search(rj):
                g["r_null"] += 1
            if EMPTYFIND_RE.search(ch):
                g["c_ef"] += 1
            if EMPTYFIND_RE.search(rj):
                g["r_ef"] += 1
            if not VERDICT_RE.search(ch):
                g["c_noverdict"] += 1
            if not VERDICT_RE.search(rj):
                g["r_noverdict"] += 1
            for side, key in ((ch, "c_act"), (rj, "r_act")):
                m = ACTION_RE.search(side)
                a = m.group(1) if m else "<none>"
                g[key][a] = g[key].get(a, 0) + 1

    print(f"数据 = {path}")
    print("\n★问：除了长度，chosen/rejected 之间还有**哪些**可学差别？")
    print(f"  {'dpo_class':<28} {'n':>6} {'空findings':>16} {'verdict:null':>16} "
          f"{'无VERDICT':>16}")
    print(f"  {'':<28} {'':>6} {'chosen/rej':>16} {'chosen/rej':>16} {'chosen/rej':>16}")
    for cls, g in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        n = g["n"]
        print(f"  {cls:<28} {n:>6} "
              f"{g['c_ef']/n:>7.1%}/{g['r_ef']/n:<7.1%} "
              f"{g['c_null']/n:>7.1%}/{g['r_null']/n:<7.1%} "
              f"{g['c_noverdict']/n:>7.1%}/{g['r_noverdict']/n:<7.1%}")

    print("\n★ action 取值分布（chosen vs rejected）——差异越大越有判别信号：")
    for cls, g in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        if g["n"] < 100:
            continue
        ca = sorted(g["c_act"].items(), key=lambda kv: -kv[1])[:3]
        ra = sorted(g["r_act"].items(), key=lambda kv: -kv[1])[:3]
        print(f"  {cls:<28} chosen={ca}  rejected={ra}")

    print("\n=== 判读 ===")
    print("  · 若某类的 `action` 分布**在两侧明显不同**，说明该对还有")
    print("    **与长度无关**的判别信号 ✓ ⇒ 长度混杂是『叠加』的干扰，不是唯一信号。")
    print("  · 若某类两侧在空findings/verdict:null/无VERDICT 上**几乎相同**，")
    print("    且 action 分布也相同 ⇒ **唯一可学差别就是长度** ✗✗ ⇒ 必须长度匹配。")
    print("\nDPO-NONLENGTH-SIGNAL=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
