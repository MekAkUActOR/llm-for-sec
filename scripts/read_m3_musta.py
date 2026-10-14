# -*- coding: utf-8 -*-
"""★更正重算 M3 的 MUST-A：必须用 "chat-gen-" 后缀（v0.3-gen / robustness 168 条）。

上一版脚本误传 "chat-"（= v0.2.1，robustness 64 条）⇒ 报出错误的 9/64 → 27/64。
本版与门禁同源（topup_verdict.py L274 `load(..., "chat-gen-")`），
并以预注册登记的起点水位 7/168 作为交叉验证。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import topup_verdict as tv  # noqa: E402

print("=== MUST-A（未见载体 ASR）—— 正确口径 chat-gen-（v0.3-gen）===\n")
print(f"{'臂':<14} {'ASR(all)':>14} {'fwd':>10} {'nfwd':>10}")
for tag in ("m2calib", "soup-a050", "m25full", "m2full", "m3-dpo"):
    d = tv.load(tag, "chat-gen-")
    if not d:
        print(f"{tag:<14} （无 scored-chat-gen-{tag}-v2.json）")
        continue
    ax = tv.robustness_axes(d)
    a, f, nf = ax["all"], ax["fwd"], ax["nfwd"]

    def s(x):
        return f"{x['success']}/{x['n']}"
    print(f"{tag:<14} {s(a):>14} {s(f):>10} {s(nf):>10}")

print("\n交叉验证：预注册登记起点 soup-a050 MUST-A = 7/168 = 0.0417")
d = tv.load("soup-a050", "chat-gen-")
if d:
    a = tv.robustness_axes(d)["all"]
    ok = (a["success"], a["n"]) == (7, 168)
    print(f"  实测 soup-a050 = {a['success']}/{a['n']}"
          f"  {'✓ 与预注册一致' if ok else '✗ 与预注册不一致'}")

# 同时给出与上一版错误口径的对照，说明差异来源
print("\n=== 口径对照（同一次运行、同一模型）===")
for suff in ("chat-gen-", "chat-"):
    d = tv.load("soup-a050", suff)
    if d:
        a = tv.robustness_axes(d)["all"]
        print(f"  suffix={suff:<10} → {a['success']}/{a['n']}")

print("\nM3-MUSTA-CORRECTED=DONE")
