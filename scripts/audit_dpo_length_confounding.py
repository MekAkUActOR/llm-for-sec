# -*- coding: utf-8 -*-
"""规则 37 的机械门：偏好数据逐类 token 长度混杂审计。

★判据（docs/01 §11.36）：
  任一类同时满足「chosen/rejected 中位比 > 1.2」且「chosen 更长比例 > 80%」
  ⇒ 该类的偏好梯度主要来自**长度**而非内容 ⇒ **必须长度匹配后才可入训** ✗。

★为什么必须机械：M3 的 DPO 数据在**发射时**有 5 类 / 6,540 对缺陷，
  当时没有任何门去查它 ⇒ 契约崩塌（70/168 → 20/168）直到部署格式重测才暴露 ✗。
  "知道了要查"不够，必须有一道会 **rc≠0** 的门。

用法：
  python scripts/audit_dpo_length_confounding.py --data data/lf/dpo_m3_final.jsonl \
      --json-out reports/dpo-length-audit.json
退出码：0 = 无混杂类；1 = 有混杂类（禁止发射）
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")

RATIO_MAX = 1.2          # 中位比上限（chosen 更长 ⇒ "越长越好"偏置）
RATIO_MIN = 0.82         # ★中位比下限（rejected 更长 ⇒ "越短越好"偏置）✗
LONGER_MAX = 0.80        # chosen 更长比例上限
LONGER_MIN = 0.20        # ★chosen 更长比例下限 ✗


def assistant_text(v) -> str:
    """str / dict{'from','value'} / messages 列表 三种形状都兜住。"""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        c = v.get("value") or v.get("content") or ""
        return c if isinstance(c, str) else ""
    if isinstance(v, list):
        for m in reversed(v):
            if isinstance(m, dict):
                role = m.get("role") or m.get("from")
                if role in ("assistant", "gpt"):
                    c = m.get("content") or m.get("value") or ""
                    return c if isinstance(c, str) else ""
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="规则 37：偏好数据逐类 token 长度混杂审计")
    ap.add_argument("--data", required=True)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--ratio-max", type=float, default=RATIO_MAX)
    ap.add_argument("--ratio-min", type=float, default=RATIO_MIN,
                    help="★双边判据的下限（rejected 更长 ⇒ 教『越短越好』也是偏置）")
    ap.add_argument("--longer-max", type=float, default=LONGER_MAX)
    ap.add_argument("--longer-min", type=float, default=LONGER_MIN,
                    help="★双边判据的下限（chosen 更长比例过低同样是偏置）")
    a = ap.parse_args()

    p = Path(a.data)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        print(f"★数据不存在：{p}", file=sys.stderr)
        print("AUDIT-DPO-LENGTH=FAIL 原因=数据缺失")
        return 2

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))

    def nt(s: str) -> int:
        return len(tok(s, add_special_tokens=False)["input_ids"])

    per_class: dict[str, list[tuple[int, int]]] = {}
    n_rows = n_bad = 0
    with p.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            n_rows += 1
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                n_bad += 1
                continue
            c = assistant_text(r.get("chosen"))
            j = assistant_text(r.get("rejected"))
            if c and j:
                per_class.setdefault(str(r.get("dpo_class") or "<none>"), []).append(
                    (nt(c), nt(j)))

    if not per_class:
        print("★一条可用偏好对都没读到 —— schema 可能又变了，拒绝给出 PASS",
              file=sys.stderr)
        print("AUDIT-DPO-LENGTH=FAIL 原因=零可用对（fail-closed，规则 32）")
        return 2

    print(f"数据 = {p}")
    print(f"行数 = {n_rows:,}  解析失败 = {n_bad}  有 chosen+rejected 的对 = "
          f"{sum(len(v) for v in per_class.values()):,}")
    print(f"\n★判据是**双边**的（2026-10-06 第 17 轮修正）：")
    print(f"  正向偏置 ✗：中位比 > {a.ratio_max}  且 chosen 更长 > {a.longer_max:.0%}"
          f"  ⇒ 教『越长越好』")
    print(f"  反向偏置 ✗：中位比 < {a.ratio_min}  且 chosen 更长 < {a.longer_min:.0%}"
          f"  ⇒ 教『越短越好』")
    print(f"  ★原版只查正向 ⇒ 我第一版长度匹配把比值修到 **0.84**（rejected 反而更长）"
          f"却仍报 PASS ✗ ⇒ 必须双边\n")
    print(f"  {'dpo_class':<28} {'n':>7} {'chosen':>8} {'rej':>7} {'比':>6} "
          f"{'chosen更长':>10}  判定")

    offenders, reports = [], {}
    for cls, pairs in sorted(per_class.items(), key=lambda kv: -len(kv[1])):
        cs = [x for x, _ in pairs]
        rs = [y for _, y in pairs]
        mc, mr = statistics.median(cs), statistics.median(rs)
        ratio = (mc / mr) if mr else float("inf")
        longer = sum(1 for x, y in pairs if x > y) / len(pairs)
        fwd = ratio > a.ratio_max and longer > a.longer_max
        rev = ratio < a.ratio_min and longer < a.longer_min
        bad = fwd or rev
        if bad:
            offenders.append((cls, len(pairs), "正向" if fwd else "反向"))
        reports[cls] = {"n": len(pairs), "chosen_median_tokens": mc,
                        "rejected_median_tokens": mr, "ratio": round(ratio, 3),
                        "chosen_longer_share": round(longer, 4),
                        "offending": bad,
                        "direction": ("forward" if fwd else ("reverse" if rev else None))}
        tag = ("★正向混杂" if fwd else ("★反向混杂" if rev else "干净"))
        print(f"  {cls:<28} {len(pairs):>7} {mc:>8.0f} {mr:>7.0f} {ratio:>6.2f} "
              f"{longer:>9.1%}  {tag}")

    n_off = sum(n for _, n, _ in offenders)
    print(f"\n★触发类 {len(offenders)} 个，共 {n_off:,} 对 "
          f"（占 {n_off/max(1,sum(len(v) for v in per_class.values())):.1%}）")
    for cls, n, d in offenders:
        print(f"    - {cls}（{n:,} 对，{d}偏置）")

    if a.json_out:
        out = Path(a.json_out)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "data": str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p),
            "criteria": {"ratio_max": a.ratio_max, "longer_max": a.longer_max,
                         "source": "docs/01 §11.36 规则 37"},
            "n_rows": n_rows, "n_parse_failed": n_bad,
            "classes": reports,
            "offending_classes": [c for c, _ in offenders],
            "offending_pairs": n_off,
            "verdict": "FAIL" if offenders else "PASS",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report -> {out}")

    verdict = "FAIL" if offenders else "PASS"
    print(f"\nAUDIT-DPO-LENGTH={verdict}")
    if offenders:
        print("  ★禁止发射★：上述类必须**长度匹配**后才可入训（规则 37）；")
        print("     并注意 `carrier_inject_hollow` 另有**语义**缺陷（推论 37.2），")
        print("     『长度匹配』与『改语义』是两件事，必须都做。")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
