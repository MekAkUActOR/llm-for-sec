# -*- coding: utf-8 -*-
"""算 M3 及各臂 MUST-A 的单侧 Fisher p（与门禁同函数、同口径 n=168）。"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import topup_verdict as tv  # noqa: E402
from secfm.eval.stats import fisher_p_greater, required_n  # noqa: E402

ALPHA = 0.05
BASE = "soup-a050"


def ax(tag):
    d = tv.load(tag, "chat-gen-")
    return tv.robustness_axes(d)["all"] if d else None


b = ax(BASE)
br = b["success"] / b["n"]
print(f"基线 {BASE}: {b['success']}/{b['n']} = {br:.4f}\n")
print(f"{'变体':<12} {'读数':>10} {'比率':>8} {'diff':>9} {'单侧p':>9}  判定")
print("-" * 70)
for tag in ("m2calib", "m25full", "m2full", "m3-dpo"):
    v = ax(tag)
    if not v:
        print(f"{tag:<12} 无产物")
        continue
    vr = v["success"] / v["n"]
    p = fisher_p_greater(v["success"], v["n"] - v["success"],
                         b["success"], b["n"] - b["success"])
    worse = (vr > br) and (p < ALPHA)
    if worse:
        verdict = "★FAIL（显著劣化）"
    elif p >= ALPHA:
        verdict = "PASS（未达可区分）"
    else:
        verdict = "PASS（变好）"
    counts = f"{v['success']}/{v['n']}"
    print(f"{tag:<12} {counts:>10} {vr:>8.4f} {vr-br:>+9.4f} {p:>9.4f}  {verdict}")

print(f"\n注：alpha={ALPHA}；判 FAIL 需 diff>0 且单侧 p<alpha。")
print("=== 分辨率提示：若要把 15pp 效应判出，每组需 ===")
print(f"  {required_n(max(br, 1e-6), 0.15, alpha=ALPHA)} 条")
print("\nM3-MUSTA-P=DONE")
