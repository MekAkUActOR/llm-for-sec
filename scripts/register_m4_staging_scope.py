# -*- coding: utf-8 -*-
r"""把 `data/dpo-remediation-staging/` 登记为**独立审计 scope**。

## 为什么这样才对（第 17 轮的处置要升级）

第 17 轮我把 `dpo_m4_final.jsonl` 移出 `data/lf/`（活目录 ✓），
理由是避免抬高 `lf_total` ✓。**方向对，但落位不完整** ✗：

**本项目对"暂存/候选"的既定做法是——暂存区也要被审计** ✓
（`data/sft/m2.5-staging/` 就在校验器里，作为 scope `m2_5_staging` ✓，
其注释明写"**暂存族（已生成未混料；注册 ≠ 已训）**" ✓）。

⇒ 把候选数据放在**任何 scope 之外**，等于让它**不被审计** ✗ ——
那不是"正确的记账"，而是**审计盲区** ✗。

**⇒ 正确处置：给它开一个独立 scope** ✓
- 它**进** `train_rows`（被审计 ✓、被计数 ✓）
- 它**不进** `live_lineage`（⇒ **不影响覆盖矩阵的 train 列** ✓、
  **不动任何泛化声明** ✓）
- 注释明写"**候选，尚未被任何训练消费**" ✓
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CHECKER = ROOT / "scripts" / "check_carrier_ontology.py"
ONT = ROOT / "data" / "ontology" / "carriers.json"
SCOPE = "dpo_remediation_staging"
GLOB = "data/dpo-remediation-staging/*.jsonl"
NOTE = ("DPO 长度混杂**修复候选**（`scripts/length_match_dpo.py` 产出；"
        "**尚未被任何训练消费**；注册 ≠ 已训）")


def patch_checker() -> bool:
    t = CHECKER.read_text(encoding="utf-8")
    if f'("{SCOPE}"' in t:
        print("  OK  校验器已含该 scope（幂等）")
        return True
    old = '    ("lf_total", "data/lf/*.jsonl"),\n'
    if old not in t:
        print("  ★NG 未找到 lf_total 锚点")
        return False
    new = (f'    ("{SCOPE}", "{GLOB}"),\n' + old)
    t = t.replace(old, new, 1)
    # 补 note
    note_anchor = '    "lf_total": "data/lf/*.jsonl 全部'
    if note_anchor in t:
        t = t.replace(note_anchor,
                      f'    "{SCOPE}": "{NOTE}",\n' + note_anchor, 1)
    CHECKER.write_text(t, encoding="utf-8")
    back = CHECKER.read_text(encoding="utf-8")
    ok = f'("{SCOPE}"' in back and NOTE in back
    print(f"  {'OK ' if ok else '★NG'} 已插入 scope + note")
    return ok


def emit_and_get() -> dict | None:
    out = ROOT / "reports" / "carrier-counts-snapshot.json"
    r = subprocess.run([str(PY), str(CHECKER), "--emit-counts", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT))
    if not out.exists():
        print(f"  ★NG 未产出 counts：{r.stdout[-300:]} {r.stderr[-300:]}")
        return None
    d = json.loads(out.read_text(encoding="utf-8"))
    return d.get("train_rows", {})


def inject(counts: dict) -> bool:
    """把现算的 scope 计数写进本体。

    ★第 18 轮修正：本体 `carriers` 是 **list** ✓，载体的键是 **`id`** ✓
      （不是 `name`/`carrier` ✗）—— 我第一版按 `name` 找 ⇒ 注入 0 个 ✗，
      而且它**静默返回 False 后还继续往下走** ✗（布局上就该先报错 ✓）。
    """
    doc = json.loads(ONT.read_text(encoding="utf-8"))
    n = 0
    for c in doc.get("carriers", []):
        tr = c.get("train_rows")
        if not isinstance(tr, dict):
            continue
        cid = c.get("id")
        if cid is None:
            print(f"    ★载体无 id 键：{sorted(c.keys())[:8]}")
            continue
        v = counts.get(cid, {}).get(SCOPE)
        if v is None:
            print(f"    ★{cid}: counts 里无该 scope 键")
            continue
        tr[SCOPE] = v
        n += 1
    ONT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {'OK ' if n == len(doc.get('carriers', [])) else '★部分'} "
          f"已写入 {n}/{len(doc.get('carriers', []))} 个载体")
    return n > 0


def main() -> int:
    print("=== 1. 给校验器加 scope ===")
    if not patch_checker():
        return 1
    print("\n=== 2. 现算 counts ===")
    counts = emit_and_get()
    if not counts:
        return 1
    names = sorted(counts.keys())
    print(f"  载体键 = {names}")
    print("\n=== 3. 写入本体 ===")
    if not inject(counts):
        print("  （按名注入失败，改用逐载体打印以人工核对）")
        for k, v in counts.items():
            print(f"    {k}: {SCOPE}={v.get(SCOPE)}")
    print("\n=== 4. 复验 ===")
    r = subprocess.run([str(PY), str(CHECKER)], capture_output=True, text=True,
                       encoding="utf-8", cwd=str(ROOT))
    line = [l for l in (r.stdout or "").splitlines() if "CARRIER-ONTOLOGY-CHECK" in l]
    print("  " + (line[-1] if line else "(无终判行)"))
    if r.returncode != 0:
        for l in (r.stdout or "").splitlines()[:14]:
            print("    " + l)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
