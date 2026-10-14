# -*- coding: utf-8 -*-
r"""★把响应文件的结构**原样打出来**（规则 42.3：用代理前先验证代理 ✓）。

★ 我在同一个字段名上猜了两次 ✗ ⇒ 直接看结构 ✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "resp-chat-gen-m3-dpo-mnt512.jsonl"


def main() -> int:
    lines = [l for l in P.read_text(encoding="utf-8", errors="replace").splitlines()
             if l.strip()]
    print(f"=== {P.name}  {len(lines)} 行 ===")
    r = json.loads(lines[0])
    print(f"  顶层键 = {sorted(r.keys())}")
    for k, v in r.items():
        if isinstance(v, str):
            print(f"\n  --- {k} : str, len={len(v)} ---")
            print(f"  头部 300: {v[:300]!r}")
            print(f"  尾部 400: {v[-400:]!r}")
        else:
            print(f"\n  --- {k} : {type(v).__name__} --- {str(v)[:200]}")

    print("\n=== 全文里出现的特殊标记 ===")
    v = next((x for x in r.values() if isinstance(x, str)), "")
    for mark in ("<|im_start|>", "<|im_end|>", "assistant", "VERDICT",
                 "```", "system"):
        print(f"  {mark!r:<18} 出现 {v.count(mark)} 次")
    print("\n=== 最后 900 字符（响应尾部 ✓）===")
    print(v[-900:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
