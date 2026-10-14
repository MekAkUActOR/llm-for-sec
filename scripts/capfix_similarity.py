# -*- coding: utf-8 -*-
r"""★★★★★ 检验新机制假说：capfix 是否把 rejected 侧写成了**与 chosen 高度相似**的"体面拒绝"？✗

## 假说（守望 #2 提出 ✓）
**capfix 把 clean 队列的 rejected 侧重写为**礼貌拒绝**（`action: refuse` ✓ / `verdict: hold` ✓）**
⇒ **DPO 于是在压低「整个礼貌拒绝区」** ✗ ⇒ **拒绝倾向下降 ⇒ ASR 上升** ✗✓

## 判据（可证伪 ✓）
**改写后，同一对内的 chosen 与 rejected 文本**相似度显著升高****
⇒ 配对**不再有可学信号** ✗（DPO 被要求"抬高"与"压低"几乎相同的文本 ✗）
⇒ **模型的梯度方向被引向"压低礼貌拒绝语域"** ✗✓ ⇒ **假说成立** ✓

**★ 度量（全部纯 CPU ✓）**：
1. **字符级 3-gram Jaccard 相似度**（同对内 ✓，前/后对比 ✓）
2. **`action`/`verdict` 字段**（前/后 ✓）—— 是否 chosen 与 rejected 的**动作相同** ✗
3. **共享前缀比例中位数** ✓（模板化程度 ✓）
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
STAGING = R / "data" / "dpo-remediation-staging"
BEFORE = STAGING / "dpo_m4_lenmatch.jsonl.superseded"
AFTER = STAGING / "dpo_m4_capfix.jsonl"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def grams(s: str, n: int = 3) -> set[str]:
    s = norm(s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def jac(a: str, b: str) -> float:
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def shared_prefix_ratio(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    k = 0
    for x, y in zip(a, b):
        if x != y:
            break
        k += 1
    return k / max(len(a), len(b))


def extract(row: dict) -> tuple[str, str, dict, dict]:
    r"""返回 (chosen 文本, rejected 文本, chosen 字段, rejected 字段)。

    ★★ schema（照实 dump 过 ✓，`scripts/dump_dpo_schema.py` ✓）：
      顶层键 = ['chosen','conversations','dpo_class','id','lang',
                'length_matched_from','pack','rejected','src_task']
      **`conversations` 是**提示**（system + user ✓）；两条响应在 `chosen`/`rejected` 里 ✓**
      ⇒ **★我先前去 conversations 里找 'gpt' 是错的** ✗ ⇒ 0 对 ✗
      （★本会话**第二次**栽在 DPO 的 dict schema 上 ✗ ⇒ **不得凭记忆猜 schema** ✓。）
    """
    ch = row.get("chosen") or {}
    rj = row.get("rejected") or {}
    ct = ch.get("value") if isinstance(ch, dict) else str(ch or "")
    rt = rj.get("value") if isinstance(rj, dict) else str(rj or "")
    return ct or "", rt or "", (ch if isinstance(ch, dict) else {}), \
        (rj if isinstance(rj, dict) else {})


def field_of(t: str, key: str) -> str | None:
    m = re.search(rf'"{key}"\s*:\s*"([A-Za-z_]+)"', t)
    return m.group(1) if m else None


def scan(p: Path, label: str) -> dict:
    print(f"\n=== {label} = {p.name} ===")
    if not p.exists():
        print("  ★缺文件")
        return {}
    sims: list[float] = []
    sprs: list[float] = []
    same_action = 0
    same_verdict = 0
    n = 0
    act_pairs: Counter = Counter()
    cls: dict[str, list[float]] = {}
    cls_same_act: Counter = Counter()
    cls_n: Counter = Counter()
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ct, rt, cf, rf = extract(row)
            if not ct or not rt:
                continue
            n += 1
            j = jac(ct, rt)
            sims.append(j)
            sprs.append(shared_prefix_ratio(ct, rt))
            ca, ra = field_of(ct, "action"), field_of(rt, "action")
            cv, rv = field_of(ct, "verdict"), field_of(rt, "verdict")
            if ca and ra:
                act_pairs[(ca, ra)] += 1
                if ca == ra:
                    same_action += 1
            if cv and rv and cv == rv:
                same_verdict += 1
            k = str(row.get("dpo_class") or "?")
            cls.setdefault(k, []).append(j)
            cls_n[k] += 1
            if ca and ra and ca == ra:
                cls_same_act[k] += 1
    sims.sort()
    sprs.sort()
    med = sims[len(sims) // 2] if sims else float("nan")
    p90 = sims[int(len(sims) * 0.9)] if sims else float("nan")
    spm = sprs[len(sprs) // 2] if sprs else float("nan")
    print(f"  对数 = {n}")
    print(f"  ★Jaccard(3-gram) 中位数 = **{med:.4f}**，P90 = {p90:.4f}")
    print(f"  ★共享前缀比例 中位数 = {spm:.4f}")
    print(f"  ★chosen.action == rejected.action 的比例 = **{same_action/max(n,1):.1%}**")
    print(f"  ★chosen.verdict == rejected.verdict 的比例 = {same_verdict/max(n,1):.1%}")
    print(f"  ★最常见的 (chosen.action, rejected.action)：")
    for (a, b), c in act_pairs.most_common(6):
        print(f"      ({a:>14} , {b:>14})  {c:>7}  {c/max(n,1):>7.1%}")
    print(f"\n  ★按 dpo_class 分解（同对内相似度 ✓）")
    print(f"      {'class':<30} {'n':>7} {'Jaccard中位':>12} {'动作相同':>10}")
    for k in sorted(cls, key=lambda x: -cls_n[x]):
        arr = sorted(cls[k])
        m = arr[len(arr) // 2] if arr else float("nan")
        print(f"      {k:<30} {cls_n[k]:>7} {m:>12.4f} "
              f"{cls_same_act[k]/max(cls_n[k],1):>10.1%}")
    return {"n": n, "jac_med": med, "jac_p90": p90, "spr_med": spm,
            "same_action": same_action / max(n, 1),
            "same_verdict": same_verdict / max(n, 1),
            "by_class": {k: (cls_n[k],
                             sorted(cls[k])[len(cls[k]) // 2] if cls[k] else float("nan"),
                             cls_same_act[k] / max(cls_n[k], 1)) for k in cls}}


def main() -> int:
    b = scan(BEFORE, "改写**前** ✓")
    a = scan(AFTER, "改写**后** ✓")
    print("\n=== ★前/后对比（判据在这里 ✓）===")
    if b and a:
        print(f"  {'指标':<26} {'前 ✓':>10} {'后 ✓':>10} {'变化':>10}")
        for k, name in (("jac_med", "Jaccard 中位数"), ("jac_p90", "Jaccard P90"),
                        ("spr_med", "共享前缀比例"), ("same_action", "动作相同的比例")):
            print(f"  {name:<26} {b[k]:>10.4f} {a[k]:>10.4f} {a[k]-b[k]:>+10.4f}")
        print(f"\n★判读：")
        if a["jac_med"] > b["jac_med"] + 0.05 and a["same_action"] > 0.30:
            print("  ⇒ **改写后同对内高度相似、且动作大量相同** ✓")
            print("  ⇒ 配对**不再有可学信号** ✗ ⇒ DPO 只能靠**压低礼貌拒绝语域**拿 margin** ✗✓")
            print("  ⇒ **守望的新机制假说成立** ✓✓ ⇒ 这是修正配比的依据 ✓")
        else:
            print("  ⇒ 同对内相似度**未显著升高** ✗ ⇒ 新机制假说**不成立** ✗")
            print("  ⇒ 病态另有原因 ✓（转向**预算轴** ✓，即 §七 的数字 ✓）")
    print("\nCAPFIX-SIMILARITY=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
