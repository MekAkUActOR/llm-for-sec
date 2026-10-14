# -*- coding: utf-8 -*-
"""TEMP probe A: streaming schema + census of data/lf/sft_m1.jsonl (read-only). Delete after use."""
import json, os, sys, io, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

P = r"J:\Projects\llm_for_sec\data\lf\sft_m1.jsonl"
print("exists", os.path.exists(P), "size_MB",
      round(os.path.getsize(P) / 1e6, 2) if os.path.exists(P) else -1)
for d in [r"J:\Projects\llm_for_sec\scripts",
          r"J:\Projects\llm_for_sec\data\sft",
          r"J:\Projects\llm_for_sec\data\sft\m2.5-staging"]:
    print("dir", d, os.path.isdir(d))
outp = r"J:\Projects\llm_for_sec\data\sft\m2.5-staging\fA_policy_v0x2.jsonl"
print("out_exists", os.path.exists(outp))

TOK = ["POL-PRIV-004", "POL-PRIV-006", "POL-PRIV-007", "POL-PRIV-008", "POL-PRIV",
       "POLICY", "提示词", "双用途", "H0", "H2", "H4", "VERDICT",
       "policy_pairs", '"action": "refuse"']
tok = {t: 0 for t in TOK}
n = 0; bad = 0; first = None; lens = []
cat = None
with open(P, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s:
            continue
        n += 1; lens.append(len(s))
        for t in TOK:
            if t in s:
                tok[t] += 1
        try:
            o = json.loads(s)
        except Exception:
            bad += 1; continue
        if first is None:
            first = o
            print("KEYS", list(o.keys()))
            for k, v in o.items():
                print(f"[{k}] {str(v)[:300]}")
            cat = {k: collections.Counter() for k, v in o.items()
                   if isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) < 120)}
        if cat:
            for k in cat:
                if k in o:
                    cat[k][str(o.get(k))] += 1
print("lines", n, "badjson", bad)
if lens:
    ls = sorted(lens)
    print("len min/med/avg/max", ls[0], ls[len(ls)//2], sum(ls)//len(ls), ls[-1])
print("TOKENS")
for t in TOK:
    print(" ", t, tok[t])
if cat:
    print("CAT_FIELDS")
    for k, c in cat.items():
        print(" ", k, "distinct", len(c), "top", c.most_common(12))
