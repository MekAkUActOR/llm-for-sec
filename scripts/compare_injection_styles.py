# -*- coding: utf-8 -*-
r"""★★★★★ 决定性假说：**测试集的注入比训练集更像"备注"** ⇒ 落进答话区域 ✗。

## 推理链

- 训练侧：注入 ①祈使率 **42.4%** ✓、干净侧 **9.8%** ✗
- 但模型的失败模式是 **`action=answer`（照做）** ✗，不是"误判为注入" ✗
- ⇒ "祈使 ⇒ 注入"这条捷径**解释不了**"该 report 却 answer" ✗
- ⇒ **唯一自洽的解释**：**测试注入落在"备注形态"区域** ✗ ⇒ 模型按事实处理 ⇒ 答 ✓

**⇒ 必须直接把**测试集的注入载体**与**训练集的注入载体**在同一个尺子上量** ✓✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)

IMPERATIVE = ("请", "必须", "应当", "务必", "立即", "不得", "禁止", "忽略", "无视",
              "跳过", "覆盖", "改为", "照做", "执行以下", "按以下",
              "不要", "无需", "直接")
META = ("面向AI", "面向 AI", "给AI", "给 AI", "助手", "模型", "系统", "指令",
        "注记", "备注", "说明", "提示", "协议", "裁决")
#: ★"备注/事实性"形态 —— 训练里被判为"不是指令"的那一类
NOTE_SHAPED = ("备注", "说明", "注记", "参考", "重复", "已关联", "供参考", "事实",
               "仅为", "不影响", "无需处理", "已确认")


def texts_of(path: Path) -> list[str]:
    """★heldout 的 schema 是 `query` ✓（不是 `conversations` ✗）。"""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        src = r.get("query")
        if not isinstance(src, str):
            for c in (r.get("conversations") or []):
                if c.get("from") == "human":
                    src = str(c.get("value") or "")
                    break
        m = CARRIER.search(src or "")
        if m:
            out.append(m.group(1))
    return out


def rate(texts: list[str], keys) -> float:
    if not texts:
        return 0.0
    return sum(1 for t in texts if any(k.lower() in t.lower() for k in keys)) / len(texts)


def main() -> int:
    ap = argparse.ArgumentParser(description="训练/测试的注入风格对照")
    ap.add_argument("--heldout-dir", default="data/heldout/v0.3-gen")
    ap.add_argument("--train", default="data/lf/dpo_m3_final.jsonl")
    ap.add_argument("--train-classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow"])
    ap.add_argument("--show", type=int, default=2)
    a = ap.parse_args()

    print("=== ① 训练侧注入载体 vs 测试侧（v0.3-gen）载体 ===")
    d = ROOT / a.train
    rows = [json.loads(l) for l in d.read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list[str]] = {}
    for r in rows:
        cls = str(r.get("dpo_class"))
        if cls not in a.train_classes:
            continue
        for c in (r.get("conversations") or []):
            if c.get("from") == "human":
                m = CARRIER.search(str(c.get("value") or ""))
                if m:
                    by.setdefault(cls, []).append(m.group(1))
                break

    hd = ROOT / a.heldout_dir
    test_texts: list[str] = []
    per: dict[str, list[str]] = {}
    for p in sorted(hd.glob("*.jsonl")):
        t = texts_of(p)
        per[p.name] = t
        test_texts += t

    print(f"  {'集合':<40} {'n':>5} {'①祈使':>7} {'②元/角色':>9} {'③备注形态':>10} "
          f"{'中位长度':>8}")
    def row(label: str, ts: list[str]) -> None:
        if not ts:
            print(f"  {label:<40} ★0 条")
            return
        ln = sorted(len(x) for x in ts)[len(ts) // 2]
        print(f"  {label:<40} {len(ts):>5} {rate(ts,IMPERATIVE):>7.1%} "
              f"{rate(ts,META):>9.1%} {rate(ts,NOTE_SHAPED):>10.1%} {ln:>8}")

    for cls, ts in sorted(by.items()):
        row(f"训练 · {cls}", ts)
    row("**测试 · v0.3-gen 全部**", test_texts)
    print()
    for name, ts in sorted(per.items()):
        if ts:
            row(f"   测试分文件 · {name}", ts)

    print("\n★判读：")
    tr = [x for ts in by.values() for x in ts]
    if tr and test_texts:
        di = rate(test_texts, IMPERATIVE) - rate(tr, IMPERATIVE)
        dn = rate(test_texts, NOTE_SHAPED) - rate(tr, NOTE_SHAPED)
        print(f"  ★测试 − 训练：①祈使 {di:+.1%}   ③备注形态 {dn:+.1%}")
        if di < -0.10:
            print("  ⇒ 测试注入**明显更少祈使形态** ✗ ⇒ 假说成立：")
            print("     它们落进了训练里『备注形态 ⇒ 事实性 ⇒ answer』的区域 ✗✓")
        elif di > 0.10:
            print("  ⇒ 测试注入**更多祈使形态** ⇒ 假说不成立，须另找机制 ✗")
        else:
            print("  ⇒ 两侧祈使度接近 ⇒ 该假说解释力有限，须看语义内容 ✓")

    for i, t in enumerate(test_texts[:a.show], 1):
        print(f"\n--- 测试载体样本 {i} ---\n{t[:600]}")
    print("\nTRAIN-VS-TEST-INJECTION=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
