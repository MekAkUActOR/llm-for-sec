# -*- coding: utf-8 -*-
"""★检验：M3 的 MUST-C PASS（ORR 9/54 → 4/54）是真改善，还是契约崩塌的伪影？

假设：ORR 由 `derived.over_refusal` 推出，而该推导**依赖解析出裁决内容**。
      若 m3-dpo 在 alignment 条目上大量**输出不可解析**的响应，
      则"过度拒绝"检测不到 ⇒ ORR 机械性下降 ⇒ PASS 是伪影。

判据（先写后算）：
  - 若 m3-dpo 的 alignment 条目里 `responded=True` 但**无可解析裁决**的比例显著高于起点
    ⇒ PASS 不可采信为改善。
  - 若两者相当 ⇒ PASS 可采信。
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import topup_verdict as tv  # noqa: E402

R = ROOT / "reports"


def doc(tag):
    return tv.load(tag, "chat-")


for tag in ("soup-a050", "m3-dpo"):
    d = doc(tag)
    if not d:
        print(f"{tag}: 无产物")
        continue
    items = [it for it in d.get("items", []) if it.get("kind") == "alignment"]
    n = len(items)
    resp = [it for it in items if it.get("responded")]
    der = [it for it in items if (it.get("derived") or {})]
    over = [it for it in items if (it.get("derived") or {}).get("over_refusal")]
    # 响应里是否含可解析的 action / verdict
    txts = []
    rp = R / f"resp-chat-{tag}-v2.jsonl"
    if not rp.exists():
        rp = R / f"resp-chat-{tag}.jsonl"
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                dd = json.loads(line)
                txts.append(dd)
    by_id = {str(x.get("id")): x.get("text", "") for x in txts}

    def parseable(i):
        t = by_id.get(str(i.get("id")), "")
        return ('"action"' in t) or ("VERDICT" in t)

    pz = sum(1 for it in resp if parseable(it))
    print(f"\n--- {tag} ---")
    print(f"  alignment 条目      = {n}")
    print(f"  responded=True      = {len(resp)}")
    print(f"  有 derived 字段     = {len(der)}")
    print(f"  over_refusal=True   = {len(over)}  ({len(over)/n*100:.1f}%)")
    print(f"  ★响应含可解析裁决  = {pz}/{len(resp)} "
          f"({pz/len(resp)*100:.1f}%)" if resp else "  ★无可解析统计")
    # 关键：over_refusal=False 的条目里，有多少其实不可解析
    unresolv = [it for it in resp if not parseable(it)]
    uo = [it for it in unresolv if (it.get("derived") or {}).get("over_refusal")]
    print(f"  不可解析的响应      = {len(unresolv)}，其中被判 over_refusal = {len(uo)}")

print("\nM3-MUSTC-ARTIFACT-CHECK=DONE")
