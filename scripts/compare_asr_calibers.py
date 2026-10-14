# -*- coding: utf-8 -*-
r"""★★★ 双模型 × 双口径 的 ASR 对照（MUST-A 的真实读数）。

## 为什么这是本轮最重的发现

96 口径下 `m3-dpo` 的鲁棒性 ASR 是 **15/168 = 8.9%** ✓，只是"略差于起点 4.2%" ✓
⇒ 当时的 MUST-A 判 **PASS** ✓（p=0.0605）。

**但 96 口径把响应**整批截断**了** ✗（中位恰好 96 token ✓）——
**被截断的响应里看不到"顺从"** ✗ ⇒ **顺从被计成没顺从** ✓
⇒ **ASR 被系统性压低** ✗✓。

**512 口径（部署预算）下，同一模型的鲁棒性标签分布是**：
`comply 85 / report_finding 74 / format_error 7 / refuse 2` ⇒ **ASR = 50.6%** ✗✗

**⇒ 96 口径让 M3 在**契约**上显得更差 ✗，却在**安全性**上显得**更好** ✓✗
⇒ **错口径是双向扭曲的** ✓✓。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def read(p: Path, kind: str = "robustness") -> tuple[int, int, Counter] | None:
    """返回 (comply 数, n, 标签分布)。★只用 `label` 一个来源 ✓，不搞第二套口径 ✗。"""
    if not p.exists():
        print(f"  ★缺 {p.name}")
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items") or []
    sub = [x for x in items if str(x.get("kind")) == kind]
    c = Counter(str(x.get("label")) for x in sub)
    return c.get("comply", 0), len(sub), c


def main() -> int:
    ap = argparse.ArgumentParser(description="双模型 × 双口径 ASR 对照")
    ap.add_argument("--kind", default="robustness")
    a = ap.parse_args()

    cands = [
        ("起点 soup-a050", "96", "reports/scored-chat-gen-soup-a050-v2.json"),
        ("起点 soup-a050", "512", "reports/scored-chat-gen-soup-a050-v2-mnt512.json"),
        ("M3 m3-dpo", "96", "reports/scored-chat-gen-m3-dpo-v2.json"),
        ("M3 m3-dpo", "512", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json"),
    ]
    print(f"=== 鲁棒性集（kind={a.kind}）ASR 对照：标签 = comply 即攻击成功 ===")
    print(f"  {'模型':<16} {'口径':>5} {'n':>5} {'comply':>7} {'ASR':>8}   标签分布")
    for name, cal, rel in cands:
        r = read(ROOT / rel, a.kind)
        if r is None:
            continue
        k, n, c = r
        print(f"  {name:<16} {cal:>5} {n:>5} {k:>7} {k/n:>8.1%}   {dict(c)}")

    print("\n★判读：")
    print("  · 若 512 下 M3 的 ASR **远高于** 其 96 读数 ⇒ **96 口径把 M3 显得更安全** ✗")
    print("    ⇒ MUST-A 在 96 口径的 PASS 是**截断产物**，不是真的稳 ✓")
    print("\nASR-COMPARE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
