# -*- coding: utf-8 -*-
"""人工核验：C 路补齐（e1）相对起点 m2-calib 在未见载体上的行为翻转。

对每一条"起点判 report/refuse、e1 判 comply"的条目，并排打出两边的真实回复尾部，
用来排除判分器/对齐错误（17 倍跃变必须先眼见为实）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_resp(tag):
    p = ROOT / "reports" / f"resp-chat-gen-{tag}.jsonl"
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r.get("id")] = r
    return out

def load_scored(tag):
    p = ROOT / "reports" / f"scored-chat-gen-{tag}-v2.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items") or d.get("details") or []
    return {r.get("id"): r for r in items}


def succ(r: dict):
    """attack_success 位于 derived 子字典，且为 **float 0.0/1.0**（不是 bool！）。
    见 secfm/eval/scored.py::_counts。用 float 比较，不能用 `is True/False`。
    """
    if not r:
        return None
    v = (r.get("derived") or {}).get("attack_success")
    return None if v is None else float(v)

base, e1 = "m2calib", "m3base-topup-e1"
rb, re1 = load_resp(base), load_resp(e1)
sb, se1 = load_scored(base), load_scored(e1)
print(f"responses: {base}={len(rb)} {e1}={len(re1)} | scored items: {base}={len(sb)} {e1}={len(se1)}")

flip = []
for i, r in sb.items():
    if r.get("kind") != "robustness":
        continue
    r2 = se1.get(i)
    if not r2:
        continue
    if (succ(r) == 0.0) and (succ(r2) == 1.0):
        flip.append(i)
print(f"\n鲁棒性条 {sum(1 for r in sb.values() if r.get('kind') == 'robustness')} | "
      f"起点成功 {sum(1 for r in sb.values() if r.get('kind')=='robustness' and succ(r))} | "
      f"e1 成功 {sum(1 for r in se1.values() if r.get('kind')=='robustness' and succ(r))}")
print(f"翻转条数（起点未成功、e1 成功）= {len(flip)}")
print("样本 5 条并排对比（每条截断 420 字符）：")
for i in flip[:5]:
    print("=" * 100)
    print("id:", i, "| label:", sb[i].get("label"), "->", se1[i].get("label"),
          "| carrier_evidence:", str(sb[i].get("evidence"))[:80])
    q = (rb.get(i, {}).get("query") or rb.get(i, {}).get("prompt") or "")[:300]
    print("--- prompt(截断) ---"); print(q)
    for tag, rr in ((base, rb), (e1, re1)):
        out = (rr.get(i, {}).get("text") or rr.get(i, {}).get("response") or "")
        print(f"--- {tag} 回复尾 420 字符 ---")
        print(out[-420:].replace("\n", " ⏎ "))
