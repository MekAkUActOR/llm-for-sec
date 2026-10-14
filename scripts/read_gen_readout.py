# -*- coding: utf-8 -*-
"""快速读取指定 tag 的未见载体门禁读数（同仪器对照用）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from secfm.eval.scored import robustness_axes, label_distribution  # noqa: E402

tags = sys.argv[1:] or ["m2calib", "m2full", "m25full", "m3base-topup-e1", "m3base-topup-e2"]
print(f"{'tag':18} {'all':>12} {'fwd':>10} {'nfwd':>12}   labels")
for t in tags:
    p = ROOT / "reports" / f"scored-chat-gen-{t}-v2.json"
    if not p.exists():
        print(f"{t:18} {'（缺）':>12}")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    a = robustness_axes(d)
    def fmt(x):
        n, k = x.get("n", 0), x.get("success", 0)
        return f"{k}/{n}={k/n:.3f}" if n else "n/a"
    lab = label_distribution(d)
    print(f"{t:18} {fmt(a['all']):>12} {fmt(a['fwd']):>10} {fmt(a['nfwd']):>12}   {lab}")
