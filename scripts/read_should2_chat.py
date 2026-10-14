# -*- coding: utf-8 -*-
"""读同口径（chat）两份 needle 报告并对照：soup-a050（起点）vs m3-dpo。

结构：needle_counts.<lens>.<lang>.{k,n}（见既有 compare_needle_arms.py）。
"""
import json
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")


def load(tag):
    for nm in (f"longctx-{tag}-chat.json", f"longctx-{tag}.json"):
        p = R / nm
        if p.exists():
            return nm, json.loads(p.read_text(encoding="utf-8"))
    return None, None


res = {}
for tag in ("soup-a050", "m3-dpo"):
    nm, d = load(tag)
    if not d:
        print(f"{tag}: 缺")
        continue
    res[tag] = (nm, d)
    nc = d.get("needle_counts") or {}
    print(f"--- {tag}（{nm}）---")
    print(f"    model = {d.get('model')}")
    print(f"    lens = {d.get('lens')}  n_docs = {d.get('n_docs')}  "
          f"max_new = {d.get('max_new')}")
    print(f"    needle_trials_per_cell = {d.get('needle_trials_per_cell')}")
    print(f"    needle_success = {d.get('needle_success')}")
    tot_k = tot_n = 0
    for lens in sorted(nc, key=lambda x: int(x)):
        for lang in sorted(nc[lens]):
            cell = nc[lens][lang]
            k, n = cell.get("k"), cell.get("n")
            tot_k += k or 0
            tot_n += n or 0
            print(f"      {lens:>6} {lang:<3} {k}/{n}")
    print(f"    ★合计 = {tot_k}/{tot_n} = {tot_k/tot_n:.3%}")
    print()

if len(res) == 2:
    nb, db = res["soup-a050"]
    nv, dv = res["m3-dpo"]
    ncb, ncv = db.get("needle_counts", {}), dv.get("needle_counts", {})

    def tot(nc):
        k = sum((nc[l][g].get("k") or 0) for l in nc for g in nc[l])
        n = sum((nc[l][g].get("n") or 0) for l in nc for g in nc[l])
        return k, n

    bk, bn = tot(ncb)
    vk, vn = tot(ncv)
    print("=== SHOULD-2（needle，同口径 chat）===")
    print(f"  起点 soup-a050 = {bk}/{bn} = {bk/bn:.3%}")
    print(f"  变体 m3-dpo    = {vk}/{vn} = {vk/vn:.3%}")
    d = vk / vn - bk / bn
    print(f"  diff = {d:+.4f}（tol 0.10；判据：不得比起点低超 0.10）")
    print(f"  ⇒ {'PASS' if d >= -0.10 else '★FAIL'}")
    print("\n  预注册预判的两种结局：")
    print(f"    实际 soup-a050-chat = {bk/bn:.1%}")
    if bk / bn < 0.40:
        print("    ⇒ 落在「基线本身极低」分支 ⇒ **仪器/口径问题**，")
        print("      SHOULD-2 应记为「该口径不可测」，**不得**据此判 m3-dpo 崩塌。")
    elif bk / bn > 0.60:
        print("    ⇒ 落在「基线正常（≈80%）」分支 ⇒ **m3-dpo 的 needle 崩塌确认**。")
    else:
        print("    ⇒ 落在两分支之间（0.40–0.60）⇒ **预注册未覆盖的中间情形**，")
        print("      须登记为口径缺陷并请裁决；不得二选一硬判。")

print("\nSHOULD2-CHAT=DONE")
