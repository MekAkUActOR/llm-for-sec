# -*- coding: utf-8 -*-
"""m5b-r2 门禁：toolout 拆分口径提取（topup_verdict.toolout_rates 同源逻辑）。"""
import json
import sys

R = r"J:\Projects\llm_for_sec\reports"


def toolout_rates(tag: str) -> dict:
    p = R + rf"\scored-chat-to-{tag}-v2-mnt512.json"
    doc = json.loads(open(p, encoding="utf-8").read())
    rk = rn = ok = on = 0
    bad = 0
    for it in doc.get("items") or []:
        dv = it.get("derived") or {}
        if "malformed" in str(it.get("note") or "").lower():
            bad += 1
        try:
            s = float(dv.get("attack_success"))
            if s in (0.0, 1.0):
                rn += 1
                rk += int(s == 1.0)
        except (TypeError, ValueError):
            pass
        try:
            o = float(dv.get("over_refusal"))
            if o in (0.0, 1.0):
                on += 1
                ok += int(o == 1.0)
        except (TypeError, ValueError):
            pass
    return {"rob": (rk, rn), "orr": (ok, on), "malformed": bad}


for tag in sys.argv[1:]:
    r = toolout_rates(tag)
    print(f"{tag}: rob={r['rob'][0]}/{r['rob'][1]}  orr={r['orr'][0]}/{r['orr'][1]}  malformed={r['malformed']}")
