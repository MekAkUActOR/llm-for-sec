# -*- coding: utf-8 -*-
"""TEMP probe C: full samples per target class, pack systems, verdict dist. Read-only."""
import json, sys, io, re, collections, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"J:\Projects\llm_for_sec\data\lf\sft_m1.jsonl"

def msg(o, role):
    for m in o["messages"]:
        if m["role"] == role:
            return m["content"]
    return None

CLS_TASKS = {
    "POL-PRIV-004": ["T5-policy:priv-p4-tokensnipe", "T5-policy:priv-p4-maskbypass"],
    "POL-PRIV-006": ["T5-policy:priv-p6-breachmatch"],
    "POL-PRIV-007": ["T5-policy:priv-p7-extjoin"],
    "POL-PRIV-008": ["T5-policy:priv-p8-monitor"],
    "H0": ["T5-policy:sec-h0-purge", "T5-policy:sec-h0-backupwipe"],
    "H2": ["T5-policy:sec-h2-piiupload"],
    "H4": ["T5-policy:sec-h4-readquery", "T5-policy:sec-h4-logread", "T5-policy:sec-h4-health"],
    "DUAL": ["T5-policy:dual-crypto", "T5-policy:dual-cve-mech", "T5-policy:dual-traffic",
             "T5-policy:dual-socialeng", "T5-policy:dual-weapon-probe"],
    "PROMPTLEAK": ["T5-policy:ais-promptleak"],
}
TASKS = {t for ts in CLS_TASKS.values() for t in ts}

pk_lang = collections.Counter()
vd = collections.defaultdict(collections.Counter)
conf = collections.defaultdict(collections.Counter)
find = collections.defaultdict(collections.Counter)
syscnt = collections.defaultdict(collections.Counter)   # pack -> Counter(system_hash)
systext = {}                                            # (pack, hash) -> text
sample = {}                                             # task -> (row, pack, lang) first zh + first en
sample_en = {}
pl_pk = {}                                              # promptleak: pack -> row
ids = []
polpriv_task = collections.Counter()

def verdict_line(a):
    for ln in reversed(a.splitlines()):
        if ln.strip().upper().startswith("VERDICT"):
            return ln.strip()
    return ""

with open(P, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s:
            continue
        o = json.loads(s)
        t = o.get("task", "")
        if t.startswith("T5-policy"):
            pk = o["pack"]; lg = o["lang"]
            sy = msg(o, "system") or ""
            h = hashlib.md5(sy.encode()).hexdigest()[:8]
            syscnt[pk][h] += 1
            systext[(pk, h)] = sy
        if t not in TASKS:
            continue
        pk = o["pack"]; lg = o["lang"]
        pk_lang[(t, pk, lg)] += 1
        a = msg(o, "assistant") or ""
        u = msg(o, "user") or ""
        vl = verdict_line(a)
        try:
            vj = json.loads(vl[len("VERDICT:"):]) if vl.startswith("VERDICT:") else {}
        except Exception:
            vj = {}
        vd[t][(vj.get("action"), vj.get("verdict"))] += 1
        conf[t][str(vj.get("confidence"))] += 1
        find[t][",".join(map(str, vj.get("findings") or []))] += 1
        if len(ids) < 6:
            ids.append(o["id"])
        if t == "T5-policy:ais-promptleak" and pk not in pl_pk:
            pl_pk[pk] = o
        if t not in sample and lg == "zh":
            sample[t] = o
        if t not in sample_en and lg == "en":
            sample_en[t] = o
        for c in ["POL-PRIV-004", "POL-PRIV-006", "POL-PRIV-007", "POL-PRIV-008"]:
            if c in u or c in a:
                polpriv_task[(c, t)] += 1

print("== T5-policy distinct systems per pack ==")
for pk, c in syscnt.items():
    print(" pack", pk, dict(c))
    for h, _ in c.most_common(1):
        print("  FULL_SYSTEM_BEGIN")
        print(systext[(pk, h)])
        print("  FULL_SYSTEM_END")
print("== ids examples ==", ids)
print("== POLPRIV token x task ==")
for k, v in sorted(polpriv_task.items()):
    print("  ", k, v)
print("== task x pack x lang ==")
for k, v in sorted(pk_lang.items()):
    print("  ", k, v)
print("== verdict dist ==")
for t in sorted(TASKS):
    print("  ", t, dict(vd[t]), "conf", dict(conf[t]), "findings", dict(find[t]))

def show(o, tag):
    print(f"---- {tag} | id={o['id']} task={o['task']} pack={o['pack']} lang={o['lang']}")
    u = msg(o, "user") or ""; a = msg(o, "assistant") or ""
    print("USER>>>"); print(u[:1800] + ("…TRUNC" if len(u) > 1800 else ""))
    print("ASST>>>"); print(a[:3500] + ("…TRUNC" if len(a) > 3500 else ""))

print("== CLASS SAMPLES (zh preferred) ==")
for cls, ts in CLS_TASKS.items():
    for t in ts:
        if t in sample:
            show(sample[t], f"{cls}/{t}")
            break
print("== PROMPTLEAK 3-pack comparison ==")
for pk in ["default", "professional", "conservative"]:
    if pk in pl_pk:
        show(pl_pk[pk], f"promptleak/{pk}")
