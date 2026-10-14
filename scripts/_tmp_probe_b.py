# -*- coding: utf-8 -*-
"""TEMP probe B: identify policy family marker, VERDICT grammar, pack systems, class samples. Read-only."""
import json, os, sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"J:\Projects\llm_for_sec\data\lf\sft_m1.jsonl"

def msg(o, role):
    for m in o["messages"]:
        if m["role"] == role:
            return m["content"]
    return None

prefix = collections.Counter()
idpfx = collections.Counter()
pol_tasks = collections.Counter()
vpat = collections.Counter()
vraw = []
CLS = ["POL-PRIV-004", "POL-PRIV-006", "POL-PRIV-007", "POL-PRIV-008", "H0", "H2", "H4", "双用途", "提示词"]
in_user = collections.Counter(); in_task = collections.Counter(); in_id = collections.Counter()
cpk = collections.Counter(); cvd = collections.Counter()
systems = {}
samples = {}
polish = 0
lang_p = collections.Counter()

with open(P, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s:
            continue
        o = json.loads(s)
        t = o.get("task", ""); i = o.get("id", ""); pk = o.get("pack", ""); lg = o.get("lang", "")
        prefix[t.split(":")[0]] += 1
        idpfx[i.split("-")[0]] += 1
        if re.search(r"(?i)pol|pair|priv", t):
            pol_tasks[t] += 1
        u = msg(o, "user") or ""
        a = msg(o, "assistant") or ""
        # verdict line
        vl = ""
        for ln in reversed(a.splitlines()):
            if ln.strip().upper().startswith("VERDICT"):
                vl = ln.strip(); break
        if vl:
            vpat[re.sub(r"\d+", "#", vl)[:120]] += 1
            if len(vraw) < 10:
                vraw.append(vl)
        is_pol = ("POL-PRIV" in u) or ("POLICY" in u) or ("提示词" in u)
        if is_pol:
            polish += 1; lang_p[lg] += 1
            sy = msg(o, "system")
            if pk not in systems and sy:
                systems[pk] = sy
        for c in CLS:
            if c in u: in_user[c] += 1
            if c in t: in_task[c] += 1
            if c in i: in_id[c] += 1
        for c in CLS:
            if c in u:
                cpk[(c, pk, lg)] += 1
                if vl:
                    m = re.search(r"(?i)verdict[^\w]*(\w[\w\-]*)", vl)
                    if m: cvd[(c, m.group(1).lower())] += 1
                if c not in samples:
                    samples[c] = (o, is_pol)
print("TASK_PREFIX", prefix.most_common(30))
print("ID_PREFIX", idpfx.most_common(30))
print("POL_TASKS", pol_tasks.most_common(40))
print("VERDICT_PAT")
for k, v in vpat.most_common(15): print("  ", v, repr(k))
print("VERDICT_RAW")
for r in vraw: print("  ", repr(r))
print("TOKEN_in_user", dict(in_user)); print("TOKEN_in_task", dict(in_task)); print("TOKEN_in_id", dict(in_id))
print("polish_rows(user has POL-PRIV/POLICY/提示词)", polish, "lang", dict(lang_p))
print("CLS x PACK x LANG")
for k, v in sorted(cpk.items()): print("  ", k, v)
print("CLS x VERB")
for k, v in sorted(cvd.items()): print("  ", k, v)
ref = {"systems": systems, "samples": {}}
for c, (o, isp) in samples.items():
    ref["samples"][c] = {"id": o["id"], "task": o["task"], "pack": o["pack"], "lang": o["lang"],
                         "is_polish": isp, "system": msg(o, "system"), "user": msg(o, "user"),
                         "assistant": msg(o, "assistant")}
with open(r"J:\Projects\llm_for_sec\scripts\_tmp_policy_ref.json", "w", encoding="utf-8") as f:
    json.dump(ref, f, ensure_ascii=False, indent=1)
print("REF_WRITTEN", os.path.getsize(r"J:\Projects\llm_for_sec\scripts\_tmp_policy_ref.json"))
