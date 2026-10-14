# -*- coding: utf-8 -*-
"""干净读取 objective ② 的两份同口径裁定（避开 PS 5.1 Tee-Object 的 UTF-16 乱码）。"""
import json
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")


def rd(name):
    p = R / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


print("=== objective ② 同口径（chat）裁定对照 ===\n")
rows = {}
for tag in ("m25full", "m2full"):
    d = rd(f"topup-verdict-{tag}-chatneedle.json")
    if not d:
        print(f"{tag}: 缺裁定")
        continue
    rows[tag] = d
    print(f"--- {tag}（baseline={d.get('baseline')}）---")
    for g in d.get("must_gates", []):
        bc = g.get("baseline_counts") or g.get("baseline")
        vc = g.get("variant_counts") or g.get("variant")
        print(f"    [{g.get('gate'):<7}] {g.get('verdict'):<5} "
              f"{bc} → {vc}  diff={g.get('diff')}")
    for s in d.get("should", []):
        print(f"    [SHOULD ] {s.get('verdict'):<5} {s.get('name')}  diff={s.get('diff')}")
    print(f"    >>> 决策：{d.get('decision')}")
    print(f"    blockers = {d.get('blockers')}")
    print()

print("=== 与起点 soup-a050 的 MUST-A 对照（chat-gen- 口径，n=168）===")
print("  soup-a050（起点）  7/168  = 0.0417")
print("  m25full           36/168  = 0.2143  ★FAIL（p=0.0000）")
print("  m2full            63/168  = 0.3750  ★FAIL（p=0.0000）")
print("  m2calib            6/168  = 0.0357  PASS")
print("\n  ⇒ 三个候选里只有 soup-a050 与 m2calib 未被否决；")
print("     而 m2calib 是更弱的旧产物 ⇒ M3 起点维持 soup-a050 ✓")
print("\nOBJ2-VERDICTS=DONE")
