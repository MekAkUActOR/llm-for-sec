# -*- coding: utf-8 -*-
"""定位 MUST-B 崩塌的根因：是**训练数据**教模型丢掉 `VERDICT:` 前缀，还是推理侧退化？

两条检验：
  (A) 推理侧：m3-dpo 的响应里有多少**含 JSON 载荷**（"action"/"verdict" 键）但**不含字面 VERDICT**？
      以及有多少呈现**复读**（同一句重复 ≥3 次）？
  (B) 训练侧：`data/lf/dpo_m3_final.jsonl` 的 **chosen** 侧是否都含字面 `VERDICT`？
      若 chosen 侧本身就有缺失 ⇒ DPO 是被**教**着丢标记的（根因在数据，不在超参）。
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"


def load_dump(name):
    rows = {}
    for line in (R / name).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            rows[d["id"]] = d
    return rows


print("=" * 72)
print("(A) 推理侧：m3-dpo vs soup-a050 的输出形态")
print("=" * 72)
a = load_dump("resp-chat-gen-soup-a050.jsonl")
b = load_dump("resp-chat-gen-m3-dpo.jsonl")
common = sorted(set(a) & set(b))
print(f"共同条目 = {len(common)}")


def has_json_payload(t: str) -> bool:
    return bool(re.search(r'"(action|verdict|findings)"\s*:', t))


def is_repetitive(t: str, min_rep: int = 3) -> bool:
    """检测复读：把文本按句子/行切开，看是否有片段重复 ≥min_rep 次。"""
    parts = [p.strip() for p in re.split(r"[。！？\n]+", t) if len(p.strip()) >= 6]
    if not parts:
        return False
    c = Counter(parts)
    return any(v >= min_rep for v in c.values())


def profile(name, d):
    n = len(d)
    v = sum(1 for x in d.values() if "VERDICT" in x["text"])
    j = sum(1 for x in d.values() if has_json_payload(x["text"]))
    jv = sum(1 for x in d.values() if has_json_payload(x["text"]) and "VERDICT" not in x["text"])
    rp = sum(1 for x in d.values() if is_repetitive(x["text"]))
    print(f"\n  [{name}] n={n}")
    print(f"    含字面 VERDICT            = {v:>4} ({v/n*100:5.1f}%)")
    print(f"    含 JSON 载荷键            = {j:>4} ({j/n*100:5.1f}%)")
    print(f"    ★含 JSON 载荷但无 VERDICT = {jv:>4} ({jv/n*100:5.1f}%)")
    print(f"    呈复读（同片段 ≥3 次）     = {rp:>4} ({rp/n*100:5.1f}%)")


profile("soup-a050（起点）", a)
profile("m3-dpo（M3 产物）", b)

print("\n" + "=" * 72)
print("(B) 训练侧：dpo_m3_final.jsonl 的 chosen/rejected 是否都含字面 VERDICT")
print("=" * 72)
p = ROOT / "data/lf/dpo_m3_final.jsonl"
if not p.exists():
    print(f"✗ 缺 {p}")
else:
    n = 0
    ch_v = ch_j = ch_none = 0
    rj_v = rj_j = rj_none = 0
    ch_rep = 0
    shown = 0
    for line in p.open(encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        n += 1
        msgs = d.get("messages") or d.get("conversations") or []
        # DPO 常见结构：{"chosen": [...], "rejected": [...]}
        def side_text(side):
            if isinstance(side, str):
                return side
            if isinstance(side, list):
                out = []
                for m in side:
                    if isinstance(m, dict):
                        out.append(str(m.get("content", "")))
                    else:
                        out.append(str(m))
                return "\n".join(out)
            return ""
        cht = side_text(d.get("chosen", ""))
        rjt = side_text(d.get("rejected", ""))
        for t, is_ch in ((cht, True), (rjt, False)):
            hv = "VERDICT" in t
            hj = has_json_payload(t)
            if is_ch:
                ch_v += hv
                ch_j += hj
                ch_none += (not hv and not hj)
                ch_rep += is_repetitive(t)
            else:
                rj_v += hv
                rj_j += hj
                rj_none += (not hv and not hj)
        if shown < 3 and not ("VERDICT" in cht):
            shown += 1
            print(f"\n  ★chosen 侧缺 VERDICT 的样例（第 {shown} 条）:")
            print("    " + cht[:300].replace("\n", "\n    "))
    print(f"\n  总对数 = {n}")
    print(f"  chosen   含 VERDICT = {ch_v} ({ch_v/n*100:.1f}%)；"
          f"含 JSON = {ch_j} ({ch_j/n*100:.1f}%)；两者皆无 = {ch_none}；复读 = {ch_rep}")
    print(f"  rejected 含 VERDICT = {rj_v} ({rj_v/n*100:.1f}%)；"
          f"含 JSON = {rj_j} ({rj_j/n*100:.1f}%)；两者皆无 = {rj_none}")

print("\nM3-ROOTCAUSE-PROBE=DONE")
