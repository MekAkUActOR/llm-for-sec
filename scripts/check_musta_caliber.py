# -*- coding: utf-8 -*-
"""★口径核对：既有 topup-verdict-soup-a050.json 的 MUST-A 是 n=168，
而现场 axes_rate() 给 n=64。查清差异来源，避免报错数。
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import topup_verdict as tv  # noqa: E402

R = ROOT / "reports"
p = R / "topup-verdict-soup-a050.json"
if p.exists():
    d = json.loads(p.read_text(encoding="utf-8"))
    m = d.get("must") or {}
    if m:
        print("=== 既有 JSON 的 MUST-A ===")
        print(f"  baseline = {m.get('baseline')}")
        print(f"  variant  = {m.get('variant')}")
    print(f"  生成时间 = {p.stat().st_mtime}")
else:
    print("✗ 缺 topup-verdict-soup-a050.json")

print("\n=== 现场重算 axes_rate ===")
for tag in ("m2calib", "soup-a050", "m3-dpo"):
    doc = tv.load(tag, "chat-")
    if not doc:
        print(f"  {tag:<12} 无产物")
        continue
    ax = tv.robustness_axes(doc)
    print(f"  {tag:<12} axes_rate = {tv.axes_rate(doc)}")
    print(f"               robustness_axes 的分组键 = {list(ax.keys())}")
    for k, v in ax.items():
        if isinstance(v, dict):
            print(f"                 [{k}] n={v.get('n')} success={v.get('success')}")

print("\n=== robustness_axes 的来源（是导入还是本地定义）===")
import inspect  # noqa: E402
try:
    src = inspect.getsourcefile(tv.robustness_axes)
    print(f"  定义于 = {src}")
    print(f"  函数体前 22 行：")
    for i, l in enumerate(inspect.getsource(tv.robustness_axes).splitlines()[:22], 1):
        print(f"    {i:>3}| {l}")
except Exception as e:  # noqa: BLE001
    print(f"  ✗ {e}")

print("\nMUSTA-CALIBER-CHECK=DONE")
