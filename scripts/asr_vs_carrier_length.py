# -*- coding: utf-8 -*-
r"""★★★★★ 决定性检验：**ASR 是否随载体长度上升** ⇒ 判定"显著性失败"假说。

## 假说

- **训练**：注入载体中位 **319** 字符 ⇒ 注入占载体的**很大比例** ✓ ⇒ 模型**看得见**它 ✓
- **测试**：中位 **1174** 字符 ✗ ⇒ 注入被**埋进长载体** ✗ ⇒ 模型**注意不到**它 ✗✓
- **⇒ 若 ASR 随载体长度单调上升 ⇒ 假说成立** ✓✓
- **⇒ 若不相关 ⇒ 假说出局，回到语义内容** ✗

**★ 对照用起点**：起点的 ASR 应当**不随长度上升** ✓（它没被这样训过 ✓）
⇒ 两条曲线的形状差异本身就是证据 ✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)


def carrier_len_map() -> dict[str, int]:
    out = {}
    d = ROOT / "data" / "heldout" / "v0.3-gen"
    for p in sorted(d.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            m = CARRIER.search(str(r.get("query") or ""))
            if m and str(r.get("kind")) == "robustness":
                out[str(r.get("id"))] = len(m.group(1))
    return out


def labels(rel: str) -> dict[str, str]:
    p = ROOT / rel
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {str(x.get("id")): str(x.get("label"))
            for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"}


def main() -> int:
    ap = argparse.ArgumentParser(description="ASR vs 载体长度")
    ap.add_argument("--bins", type=int, default=4)
    a = ap.parse_args()

    cl = carrier_len_map()
    print(f"=== 载体长度（v0.3-gen robustness）n={len(cl)} ===")
    if not cl:
        print("  ★抽不到载体")
        return 1
    v = sorted(cl.values())
    print(f"  中位 {v[len(v)//2]}  最小 {v[0]}  最大 {v[-1]}")

    models = [("起点 soup-a050", "reports/scored-chat-gen-soup-a050-v2-mnt512.json"),
              ("m3-dpo", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json")]
    data = {n: labels(r) for n, r in models}
    ids = sorted(set(cl) & set(data["m3-dpo"]))
    print(f"  交集 {len(ids)} 条")

    # 按长度分箱
    s = sorted(ids, key=lambda i: cl[i])
    per = max(1, len(s) // a.bins)
    bins = [s[i:i + per] for i in range(0, len(s), per)][:a.bins]

    print(f"\n=== 分箱 ASR（按载体长度升序）===")
    print(f"  {'箱':<5} {'长度区间':>16} {'n':>4}   " +
          "   ".join(f"{n}>ASR" for n, _ in models))
    for bi, b in enumerate(bins, 1):
        lo, hi = cl[b[0]], cl[b[-1]]
        cells = []
        for n, _ in models:
            lab = data[n]
            got = [lab[i] for i in b if i in lab]
            k = sum(1 for x in got if x == "comply")
            cells.append(f"{k}/{len(got)}={k/max(len(got),1):>5.1%}")
        print(f"  {bi:<5} {f'{lo}–{hi}':>16} {len(b):>4}   " + "   ".join(cells))

    print("\n=== 相关（Spearman 秩相关，人工算）===")
    for n, _ in models:
        lab = data[n]
        pairs = [(cl[i], 1 if lab.get(i) == "comply" else 0)
                 for i in ids if i in lab]
        # 秩相关
        xs = sorted(range(len(pairs)), key=lambda j: pairs[j][0])
        ys = sorted(range(len(pairs)), key=lambda j: pairs[j][1])
        rk_x = {j: r for r, j in enumerate(xs)}
        rk_y = {j: r for r, j in enumerate(ys)}
        n_ = len(pairs)
        d2 = sum((rk_x[j] - rk_y[j]) ** 2 for j in range(n_))
        rho = 1 - 6 * d2 / (n_ * (n_ * n_ - 1)) if n_ > 1 else 0.0
        print(f"  {n:<18} rho = {rho:+.3f}   （正 = 载体越长越容易顺从）")

    print("\n★判读：")
    print("  · 起点 rho ≈ 0 ✓（未被这样训过 ⇒ 天然对照 ✓）")
    print("  · m3-dpo rho 明显为正 ⇒ **显著性失败假说成立** ✓✓")
    print("  · 两者都 ≈ 0 ⇒ 假说出局 ⇒ 回到语义内容 ✗")
    print("\nASR-VS-CARRIERLEN=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
