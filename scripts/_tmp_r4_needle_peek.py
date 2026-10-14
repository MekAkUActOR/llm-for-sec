# -*- coding: utf-8 -*-
import json

d = json.load(open(r"reports\longctx-m5a-dpo-r4-chat.json", encoding="utf-8"))
nc = d["needle_counts"]
tot_s = tot_n = 0
for k, v in nc.items():
    if isinstance(v, dict) and "success" in v and "total" in v:
        tot_s += v["success"]
        tot_n += v["total"]
        print(f"  {k}: {v['success']}/{v['total']}")
    else:
        print(f"  {k}: {v}")
if tot_n:
    print(f"needle total: {tot_s}/{tot_n} = {tot_s / tot_n * 100:.2f}%")
print("ppl:", json.dumps(d.get("ppl"), ensure_ascii=False))
