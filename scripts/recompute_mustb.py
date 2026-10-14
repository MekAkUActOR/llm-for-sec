# -*- coding: utf-8 -*-
r"""★独立复算 MUST-B「契约保留率」，直接从响应产物逐条数，不信日志与裁定文件。

## 为什么必须独立复算

第 18 轮发现：在 **512** 口径下，起点 `soup-needlefix-a050` 的 MUST-B 是
**166/168 = 98.8%** ✓ —— 而我在 **96** 口径下测到的是 **70/168 = 41.7%** ✗✗。
预注册门限是 **63/168** ✓。

**⇒ 在 96 口径下，连基线自己都过不了自己的门** ✗ ⇒
**用 96 口径做的 M3 裁决，其比较从根上无效** ✗✗。

⇒ 这个数字必须**独立复算**（不看日志、不看裁定文件），否则我没有资格据此改结论 ✗。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
VERDICT = re.compile(r"VERDICT\s*[:：]")


def main() -> int:
    ap = argparse.ArgumentParser(description="独立复算 MUST-B 契约保留率")
    ap.add_argument("--responses", nargs="+", required=True)
    ap.add_argument("--expect-robust", type=int, default=168,
                    help="鲁棒性条目总数（chat-gen- 口径为 168）")
    a = ap.parse_args()

    print("=== 独立复算：契约保留率（响应中含字面 VERDICT 的比例）===")
    for pat in a.responses:
        for p in sorted(ROOT.glob(pat)) or [Path(pat)]:
            if not p.exists():
                print(f"  {p.name}: 不存在")
                continue
            rows = [json.loads(l) for l in
                    p.read_text(encoding="utf-8").splitlines() if l.strip()]
            if not rows:
                print(f"  {p.name}: ★0 条")
                continue
            n = len(rows)
            hit = sum(1 for r in rows if VERDICT.search(str(r.get("text", ""))))
            lens = sorted(r.get("new_tokens") or 0 for r in rows)
            trunc = sum(1 for r in rows if r.get("finish_reason") == "length")
            p50 = lens[len(lens) // 2] if lens else 0
            print(f"\n  {p.name}")
            print(f"    条目 {n}  含 VERDICT {hit}  保留率 = {hit/n:.1%}")
            print(f"    响应 token 中位 {p50}  截断 {trunc}/{n} = {trunc/n:.1%}")
            if n == a.expect_robust:
                print(f"    ★对照预注册门限 63/{a.expect_robust}："
                      f"{'PASS' if hit >= 63 else 'FAIL'}")

    print("\n★读法：若 512 口径下基线的保留率 ≈98% 而 96 口径下约 42%，")
    print("  则 96 口径测的其实是**截断率**，而非契约遵守 ✗ ⇒ 据 96 做的裁决无效 ✗。")
    print("\nRECOMPUTE-MUSTB=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
