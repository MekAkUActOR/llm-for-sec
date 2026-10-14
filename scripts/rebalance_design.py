# -*- coding: utf-8 -*-
r"""★★★★★ 重配比**设计**（轴 1 ✓，纯 dry-run ✓，**不改任何数据** ✗）。

## 为什么不能一刀切删同动作对 ✗

第 30 轮实测（`scripts/capfix_similarity.py` ✓）：
**同动作对 = 15,663 / 28,842 = **54.3%**** ✗，其中 `(answer,answer)` 8,413 ✓ / `(refuse,refuse)` 7,250 ✓。

**★ 但同动作 ≠ 无用** ✗：
- **同动作 + verdict/findings/confidence **不同**** ✓ ⇒ **仍在教**契约质量与校准**** ✓（**该留** ✓）
- **同动作 + verdict **也**相同** ⇒ **纯文风** ✗ ⇒ **该降权或改写** ✓

**⇒ 本脚本把每一对分成三类 ✓**：
| 类 | 判据 | 处置建议 |
|---|---|---|
| **S（方向对 ✓）** | `action` 不同 ✓ | **保留 ✓**（核心信号 ✓） |
| **C（契约对 ✓）** | `action` 同 ✓，但 `verdict`/`findings`/`confidence` 至少一项不同 ✓ | **保留 ✓**（教契约 ✓） |
| **F（风格对 ✗）** | `action` 同 ✓ 且 `verdict` 同 ✓ 且 `findings`/`confidence` 同 ✓ | **降权/改写** ✓ |

**★★ 处置建议**：**降权**（重复采样 ✓）而**不是删除** ✗ ——
**删除会改变总量与类间比例** ✗；**降权只改该类的梯度占比** ✓（Cor 42.4 ✓）。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
SRC = R / "data" / "m4-run" / "dpo_m4_capfix.jsonl"
OUT = R / "reports" / "rebalance-design.json"

FIELD = re.compile(r'"([a-z_]+)"\s*:\s*("([^"]*)"|(-?[\d.]+)|(\[[^\]]*\]))')


def parse_verdict(t: str) -> dict:
    m = re.search(r"VERDICT\s*:\s*(\{.*\})", t or "", re.S)
    if not m:
        return {}
    s = m.group(1)
    # 截到最后一个右花括号，容忍尾随文本 ✓
    k = s.rfind("}")
    s = s[:k + 1] if k >= 0 else s
    try:
        return json.loads(s)
    except Exception:
        out = {}
        for mm in FIELD.finditer(s):
            out[mm.group(1)] = (mm.group(3) if mm.group(3) is not None
                                else (mm.group(4) if mm.group(4) is not None
                                      else mm.group(5)))
        return out


def main() -> int:
    if not SRC.exists():
        print(f"  ★缺 {SRC}")
        return 2
    n = 0
    cat = Counter()
    per_class: dict[str, Counter] = {}
    mass = Counter()
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            ct = (row.get("chosen") or {}).get("value") or ""
            rt = (row.get("rejected") or {}).get("value") or ""
            cv, rv = parse_verdict(ct), parse_verdict(rt)
            ca, ra = cv.get("action"), rv.get("action")
            same_act = bool(ca) and ca == ra
            if not same_act:
                k = "S_directional"
            else:
                diffs = any(str(cv.get(x)) != str(rv.get(x))
                            for x in ("verdict", "findings", "confidence"))
                k = "C_contract" if diffs else "F_style"
            cat[k] += 1
            mass[k] += len(rt)
            cls = str(row.get("dpo_class") or "?")
            per_class.setdefault(cls, Counter())[k] += 1

    tot_mass = sum(mass.values()) or 1

    def pct(x, t):
        return f"{x/max(t,1):.1%}"

    print(f"=== ★三分结果（{n:,} 对 ✓，dry-run ✓，未改任何数据 ✓）===")
    print(f"  {'类':<16} {'对数':>8} {'占比':>7} {'梯度质量占比':>13}")
    labels = {"S_directional": "S 方向对 ✓", "C_contract": "C 契约对 ✓",
              "F_style": "F 风格对 ✗"}
    for k in ("S_directional", "C_contract", "F_style"):
        print(f"  {labels[k]:<16} {cat[k]:>8,} {pct(cat[k], n):>7} "
              f"{pct(mass[k], tot_mass):>13}")

    print(f"\n  === ★按 dpo_class 分解（S/C/F ✓）===")
    print(f"  {'class':<30} {'n':>7} {'S':>7} {'C':>7} {'F':>7} {'F 占比':>8}")
    for c in sorted(per_class, key=lambda x: -sum(per_class[x].values())):
        d = per_class[c]
        t = sum(d.values())
        print(f"  {c:<30} {t:>7,} {d['S_directional']:>7,} "
              f"{d['C_contract']:>7,} {d['F_style']:>7,} {pct(d['F_style'], t):>8}")

    print(f"\n★判读：")
    f_share = cat["F_style"] / max(n, 1)
    print(f"  · F（纯文风 ✗）= {cat['F_style']:,} 对 = **{f_share:.1%}**")
    print(f"  · S+C（有信号 ✓）= {cat['S_directional']+cat['C_contract']:,} 对 "
          f"= **{pct(cat['S_directional']+cat['C_contract'], n)}**")
    if f_share > 0.30:
        print(f"  ⇒ **F 类过大（{f_share:.1%} ✗）**——与第 30 轮的「54.3% 同动作」一致 ✓")
        print("  ⇒ **处置 = 降权（重复采样 ✓），不是删除** ✗")
        print("     ★理由：删除会改变总量与类间比例 ✗；降权只改该类的**梯度占比** ✓（Cor 42.4 ✓）")
        print("  ⇒ **★ 改前必须先 `--dry-run` + 预注册改后预期 ASR** ✓（本轮即为 dry-run ✓）")
    else:
        print("  ⇒ F 类不大 ✓ ⇒ 重配比**不是**主要轴 ✗ ⇒ 集中走**预算轴** ✓")
    OUT.write_text(json.dumps(
        {"n": n, "categories": dict(cat), "mass": dict(mass),
         "per_class": {k: dict(v) for k, v in per_class.items()}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  report -> {OUT}")
    print("\nREBALANCE-DESIGN=DONE（★未改动任何数据 ✓）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
