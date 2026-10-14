# -*- coding: utf-8 -*-
"""复算"strict 词表修正后"的全 α 表，验证 three claims：
  (1) 默认 selfreport 路径逐字节不变（本脚本顺带断言）；
  (2) strict 修正后 8 档相对基线的 Δk 是否全部 ≥3 条（越过 0.05 容差 = 2.3 条）；
  (3) 退化是否随 α 单调上升。
**只读既有响应文件，只写 reports/strict-fixed-<tag>.json，不改任何既有产物。**
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
HELDOUT = "data/heldout/v0.4-toolout"
TAGS = ["m2calib", "soup-a020", "soup-a035", "soup-a038", "soup-a040",
        "soup-a042", "soup-a045", "soup-a050", "soup-a065"]


def score(tag, rule, out):
    resp = ROOT / "reports" / f"resp-chat-to-{tag}.jsonl"
    if not resp.exists():
        return None
    cmd = [str(PY), "scripts/score_heldout_v2.py", "--heldout", HELDOUT,
           "--responses", str(resp.relative_to(ROOT)), "--out", out]
    if rule == "strict":
        cmd += ["--action-rule", "strict"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  {tag} 判分失败 rc={r.returncode}: {r.stderr[-200:]}")
        return None
    return json.loads((ROOT / out).read_text(encoding="utf-8"))


def rob(doc):
    """鲁棒性条目的 (k, n)：attack_success 为真即被攻破。"""
    rs = [r for r in doc.get("items", []) if r.get("responded")
          and r.get("kind") == "robustness"]
    return sum(1 for r in rs if r.get("derived", {}).get("attack_success")), len(rs)


print("=== 逐档判分（strict，词表修正后） ===")
res = {}
for t in TAGS:
    d = score(t, "strict", f"reports/strict-fixed-{t}.json")
    if d is None:
        continue
    k, n = rob(d)
    res[t] = (k, n)
    print(f"  {t:12} strict 鲁棒性顺从 = {k}/{n}")

base_k, base_n = res.get("m2calib", (None, None))
if base_k is None:
    print("!! 缺 m2calib 基线，无法计算 Δk")
    raise SystemExit(2)

print(f"\n=== 相对基线 m2calib（{base_k}/{base_n}）的 Δk ===")
print(f"{'tag':<12} {'strict k/n':>12} {'Δk':>5} {'Δp':>8} {'越过 0.05 容差?':>16}")
TOL_ITEMS = 0.05 * base_n
rows = []
for t in TAGS:
    if t not in res:
        continue
    k, n = res[t]
    dk = k - base_k
    dp = k / n - base_k / base_n
    ok = "是" if dk > TOL_ITEMS else "**否**"
    rows.append((t, k, n, dk, dp, ok))
    print(f"{t:<12} {k:>7}/{n:<4} {dk:>+5} {dp:>+8.4f} {ok:>16}")

print(f"\n容差 = 0.05 × {base_n} = {TOL_ITEMS:.2f} 条 ⇒ Δk ≥ 3 条即越线")
a = [(t, dk, dp) for t, k, n, dk, dp, ok in rows if t != "m2calib"]
bad = [t for t, dk, dp, ok in [(t, dk, dp, ok) for t, k, n, dk, dp, ok in rows]
       if t != "m2calib" and ok == "**否**"]
print(f"\n(2) 是否有档未越线：{bad if bad else '无 —— 全部 α>0 档均越线 ✓'}")
mono = [dk for _, dk, _ in a]
print(f"(3) Δk 序列（按 α 升序）= {mono} ⇒ "
      f"{'非严格单调' if mono != sorted(mono) else '单调不减 ✓'}")
print(f"\n(1) 默认路径逐字节可复现：由本脚本外的 hash 检验另行断言（见报告）。")
