# -*- coding: utf-8 -*-
"""M6 DATA-1 audit probe: distribution stats over m4-run / dpo recipe files."""
import json, collections, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def verdict_of(text):
    m = re.search(r'"verdict":\s*"([a-z\-]+)"', text or "")
    return m.group(1) if m else "none"

def probe(path):
    cls = collections.Counter(); lang = collections.Counter(); pack = collections.Counter()
    verd_r = collections.Counter(); verd_c = collections.Counter(); nturn = collections.Counter()
    src = collections.Counter(); ids = set(); dup = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        cls[d.get("dpo_class")] += 1
        lang[d.get("lang")] += 1
        pack[d.get("pack")] += 1
        st = (d.get("src_task") or "")
        src[st.split(":")[0]] += 1
        conv = d.get("conversations", [])
        nh = sum(1 for m in conv if m.get("from") == "human")
        nturn[nh] += 1
        verd_r[verdict_of(d.get("rejected", {}).get("value", ""))] += 1
        verd_c[verdict_of(d.get("chosen", {}).get("value", ""))] += 1
        i = d.get("id")
        if i in ids:
            dup += 1
        ids.add(i)
    print("=== %s ===" % path)
    print("lines: %d  unique_ids: %d  dup_ids: %d" % (sum(cls.values()), len(ids), dup))
    print("dpo_class:", dict(cls.most_common()))
    print("lang:", dict(lang.most_common()))
    print("pack:", dict(pack.most_common()))
    print("human_turns:", dict(sorted(nturn.items())))
    print("rejected_verdict:", dict(verd_r.most_common()))
    print("chosen_verdict:", dict(verd_c.most_common()))
    print("src_task_prefix:", dict(src.most_common(20)))
    print()

if __name__ == "__main__":
    for p in sys.argv[1:]:
        probe(p)
