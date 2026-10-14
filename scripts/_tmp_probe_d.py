# -*- coding: utf-8 -*-
"""TEMP probe D: pack-conditioned responses, en style, insufficient-context, extra zh users. Read-only."""
import json, sys, io, re, collections, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"J:\Projects\llm_for_sec\data\lf\sft_m1.jsonl"

def msg(o, role):
    for m in o["messages"]:
        if m["role"] == role:
            return m["content"]
    return None

T3 = ["T5-policy:priv-p6-breachmatch", "T5-policy:priv-p7-extjoin", "T5-policy:sec-h0-purge",
      "T5-policy:sec-h4-readquery", "T5-policy:dual-cve-mech", "T5-policy:dual-socialeng"]
ENT = ["T5-policy:ais-promptleak", "T5-policy:dual-crypto", "T5-policy:sec-h4-logread",
       "T5-policy:priv-p4-tokensnipe", "T5-policy:priv-p8-monitor", "T5-policy:sec-h2-piiupload"]
ALLT = set(T3 + ENT + ["T5-policy:priv-p4-maskbypass", "T5-policy:priv-p6-breachmatch",
                       "T5-policy:sec-h0-backupwipe", "T5-policy:sec-h4-health", "T5-policy:dual-traffic",
                       "T5-policy:dual-weapon-probe"])

pk_row = {}          # (task, pack) -> first zh row
cond_row = {}        # task -> first zh row with verdict conditional
en_row = {}          # task -> first en row
zh_users = collections.defaultdict(list)  # task -> distinct zh users (<=4)
insuff = collections.Counter(); insuff_sample = []
sys_h = collections.defaultdict(collections.Counter)  # (task, pack) -> system hashes
idmap = collections.defaultdict(list)  # id -> [(pack, user)] for ais-promptleak

with open(P, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s:
            continue
        o = json.loads(s)
        t = o.get("task", "")
        a = msg(o, "assistant") or ""
        if "insufficient" in a.lower():
            insuff[t.split(":")[0] + ":" + t.split(":")[1] if ":" in t else t] += 1
            if len(insuff_sample) < 2:
                insuff_sample.append(o)
        if t not in ALLT:
            continue
        pk, lg = o["pack"], o["lang"]
        sy = msg(o, "system") or ""
        sys_h[(t, pk)][hashlib.md5(sy.encode()).hexdigest()[:6]] += 1
        u = msg(o, "user") or ""
        if t == "T5-policy:ais-promptleak" and len(idmap) < 6:
            if len(idmap.get(o["id"], [])) < 3:
                idmap[o["id"]].append((pk, u))
        if lg == "zh":
            if (t, pk) not in pk_row and t in T3:
                pk_row[(t, pk)] = o
            if '"verdict": "conditional"' in a and t not in cond_row:
                cond_row[t] = o
            if len(zh_users[t]) < 4 and u not in zh_users[t]:
                zh_users[t].append(u)
        elif lg == "en":
            if t not in en_row:
                en_row[t] = o

print("== insufficient-context rows by task ==")
print(dict(insuff))
for o in insuff_sample:
    print(f"  id={o['id']} task={o['task']} pack={o['pack']} lang={o['lang']}")
    print("  U>", (msg(o, 'user') or '')[:300])
    print("  A>", (msg(o, 'assistant') or '')[:400])
print("== system variants per (target task, pack): ")
bad = {k: dict(v) for k, v in sys_h.items() if len(v) > 1}
print("MULTI:", bad if bad else "none - all uniform")
canon = {}
for (t, pk), v in sys_h.items():
    canon[pk] = canon.get(pk, set()) | set(v)
print("per-pack distinct across target tasks:", {pk: len(v) for pk, v in canon.items()})
print("== same id across packs (promptleak) ==")
for i, lst in list(idmap.items())[:4]:
    print(" ", i, [(pk, u[:40]) for pk, u in lst])
print("== 3-pack zh rows ==")
for t in T3:
    for pk in ["default", "professional", "conservative"]:
        o = pk_row.get((t, pk))
        if o:
            print(f"-- {t}/{pk}")
            print("  U>", msg(o, "user"))
            print("  A>", msg(o, "assistant"))
print("== conditional zh rows ==")
for t, o in cond_row.items():
    print(f"-- {t} pack={o['pack']}")
    print("  U>", msg(o, "user"))
    print("  A>", msg(o, "assistant"))
print("== en rows ==")
for t in ENT:
    o = en_row.get(t)
    if o:
        print(f"-- {t} pack={o['pack']}")
        print("  U>", msg(o, "user"))
        print("  A>", msg(o, "assistant"))
print("== extra zh users (style pool) ==")
for t in sorted(zh_users):
    for u in zh_users[t]:
        print(f"  {t} | {u}")
