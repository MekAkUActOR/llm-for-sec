# -*- coding: utf-8 -*-
"""Probe m4 chosen VERDICT structure for the chosen-first converter."""
import json, re, sys, io, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

VD = re.compile(r"VERDICT:\s*(\{.*\})\s*$", re.S)

def parse_vd(text):
    m = VD.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None

cls_stats = collections.defaultdict(collections.Counter)
findings_keys = collections.Counter()
src_task_by_cls = collections.defaultdict(collections.Counter)
field_keys = collections.Counter()
examples = {}

for line in open("data/m4-run/dpo_m4_capfix.jsonl", encoding="utf-8"):
    d = json.loads(line)
    cls = d.get("dpo_class")
    vd = parse_vd(d.get("chosen", {}).get("value", ""))
    if vd is None:
        cls_stats[cls]["no_verdict"] += 1
        continue
    action = vd.get("action")
    verdict = vd.get("verdict")
    cls_stats[cls]["%s/%s" % (action, verdict)] += 1
    for k in vd:
        field_keys[k] += 1
    f = vd.get("findings") or []
    for item in f:
        if isinstance(item, dict):
            for k in item:
                findings_keys[k] += 1
    st = d.get("src_task") or ""
    src_task_by_cls[cls][st.split(":")[0]] += 1
    if cls not in examples and f:
        examples[cls] = (d.get("id"), vd)

for cls in sorted(cls_stats):
    print("==", cls, "==")
    print("  action/verdict:", dict(cls_stats[cls].most_common(8)))
    print("  src_task:", dict(src_task_by_cls[cls].most_common(5)))
print("VERDICT field keys:", dict(field_keys.most_common()))
print("findings item keys:", dict(findings_keys.most_common(12)))
print()
for cls, (iid, vd) in examples.items():
    print("example", cls, iid, json.dumps(vd, ensure_ascii=False)[:300])
