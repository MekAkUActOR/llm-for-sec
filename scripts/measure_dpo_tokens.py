# -*- coding: utf-8 -*-
"""查 DPO 数据 schema 并测 chosen/rejected 的 token 长度分布。

上一轮 `measure_token_budgets.py` 对 DPO 段**什么都没输出** ✗ ⇒ 解析没读到数据。
本脚本先打印真实 schema（不猜键名），再按实际键名测长度。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
DPO = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
BUDGETS = (96, 128, 192, 256, 384, 512, 768)


def assistant_text(v) -> str:
    """从 **str / dict / messages 列表** 里取 assistant 侧文本。

    ★2026-10-06：DPO 数据的 chosen/rejected 实际是**字典** `{'from': 'gpt', 'value': '...'}`
      （不是字符串，也不是 messages 列表）✗ —— 上一轮没处理 dict ⇒ 测出 0 条 ✗。
      本函数对三种形状都兜住，避免再因 schema 猜错而静默得到空结果。
    """
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        c = v.get("value") or v.get("content") or ""
        return c if isinstance(c, str) else str(c)
    if isinstance(v, list):
        for m in reversed(v):
            if isinstance(m, dict):
                role = m.get("role") or m.get("from")
                if role in ("assistant", "gpt"):
                    c = m.get("content") or m.get("value") or ""
                    return c if isinstance(c, str) else str(c)
    return ""


def main() -> int:
    print(f"DPO 文件 = {DPO}")
    if not DPO.exists():
        print("★文件不存在")
        return 1
    with DPO.open(encoding="utf-8") as f:
        first = json.loads(f.readline())
    print("\n=== 首行 schema ===")
    print(f"顶层键 = {sorted(first.keys())}")
    for k, v in first.items():
        if isinstance(v, str):
            print(f"  {k}: str len={len(v)}  {v[:70]!r}")
        elif isinstance(v, list):
            print(f"  {k}: list len={len(v)}")
            for i, m in enumerate(v[:4]):
                if isinstance(m, dict):
                    cc = m.get("content") or m.get("value") or ""
                    print(f"      [{i}] keys={sorted(m.keys())} "
                          f"role={m.get('role') or m.get('from')!r} len={len(str(cc))}")
        else:
            print(f"  {k}: {type(v).__name__} = {str(v)[:70]}")

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))

    def nt(s: str) -> int:
        return len(tok(s, add_special_tokens=False)["input_ids"])

    ch: list[int] = []
    rj: list[int] = []
    by_class: dict[str, list[tuple[int, int]]] = {}
    n_bad = 0
    with DPO.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                n_bad += 1
                continue
            a, b = assistant_text(r.get("chosen")), assistant_text(r.get("rejected"))
            if a:
                ch.append(nt(a))
            if b:
                rj.append(nt(b))
            if a and b:
                by_class.setdefault(str(r.get("dpo_class")), []).append((nt(a), nt(b)))
    print(f"\n解析失败 {n_bad} 行；chosen 有文本 {len(ch)}；rejected 有文本 {len(rj)}")
    if not ch or not rj:
        print("★仍然读不到文本 —— 解析逻辑可能又猜错了 schema（须实测后再改）")
        return 1

    def rep(nm: str, xs: list[int]) -> None:
        if not xs:
            print(f"--- {nm}: 无数据 ✗")
            return
        q = sorted(xs)
        n = len(q)
        at = lambda p: q[min(n - 1, int(n * p))]
        print(f"--- {nm}（n={n}）---")
        print(f"    p25={at(.25)}  p50={at(.50)}  p75={at(.75)}  p90={at(.90)}  "
              f"p99={at(.99)}  max={q[-1]}  mean={statistics.fmean(q):.1f}")
        cov = "  ".join(f"{b}:{sum(1 for x in xs if x <= b)/n:.1%}" for b in BUDGETS)
        print(f"    预算覆盖率  {cov}")

    rep("chosen", ch)
    rep("rejected", rj)
    if ch and rj:
        mc, mr = statistics.median(ch), statistics.median(rj)
        print(f"\n★chosen/rejected 中位比 = {mc/mr:.2f}×（>1.2 ⇒ 长度混杂风险）")
        longer = sum(1 for a, b in zip(ch, rj) if a > b) / min(len(ch), len(rj))
        print(f"★chosen 更长的比例 = {longer:.1%}")

    print("\n=== 按 dpo_class 分解（找长度混杂的类）===")
    print(f"  {'dpo_class':<28} {'n':>6} {'chosen中位':>10} {'rej中位':>9} "
          f"{'比':>6} {'chosen更长':>10}")
    rows = []
    for cls, pairs in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
        a = [x for x, _ in pairs]
        b = [y for _, y in pairs]
        mc, mr = statistics.median(a), statistics.median(b)
        lr = sum(1 for x, y in pairs if x > y) / len(pairs)
        rows.append((cls, len(pairs), mc, mr, mc / mr if mr else float("inf"), lr))
    for cls, n, mc, mr, ratio, lr in rows:
        flag = " ★" if ratio > 1.2 else ""
        print(f"  {cls:<28} {n:>6} {mc:>10.0f} {mr:>9.0f} {ratio:>6.2f} {lr:>9.1%}{flag}")
    print("\n★判据（规则 33）：chosen 中位 > rejected 中位 ×1.2 且 chosen 更长比例 >80% "
          "⇒ 该类的偏好梯度主要来自**长度**而非内容 ⇒ 必须长度匹配。")
    print("\nDPO-TOKEN-MEASURE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
