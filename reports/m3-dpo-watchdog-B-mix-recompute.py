# -*- coding: utf-8 -*-
"""M3 DPO watchdog: independent recompute of data/lf/dpo_m3_final.jsonl.

Read-only. Prints JSON summary to stdout; also writes
reports/m3-dpo-watchdog-mix-recompute.json (watchdog-owned artifact).
"""
import hashlib
import json
import os
import sys
from collections import Counter

ROOT = r"J:\Projects\llm_for_sec"
DS = os.path.join(ROOT, "data", "lf", "dpo_m3_final.jsonl")
OUT = os.path.join(ROOT, "reports", "m3-dpo-watchdog-mix-recompute.json")

def last_nonempty_line(s):
    lines = [ln for ln in s.replace("\r\n", "\n").split("\n") if ln.strip()]
    return lines[-1] if lines else ""

def main():
    n = 0
    ids = set()
    dup_ids = 0
    ids_missing = 0
    keyset = Counter()
    verdict_both = 0
    verdict_chosen = 0
    verdict_rejected = 0
    verdict_json_chosen = 0
    verdict_json_rejected = 0
    verdict_json_both = 0
    dpo_class = Counter()
    component = Counter()
    top_level_extra = Counter()
    empty_chosen = 0
    empty_rejected = 0
    bad_json_lines = []
    identical_sides = 0
    first_sample = None
    sha = hashlib.sha256()

    with open(DS, "rb") as fb:
        for chunk in iter(lambda: fb.read(1 << 22), b""):
            sha.update(chunk)

    with open(DS, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            n += 1
            try:
                rec = json.loads(line)
            except Exception as e:
                bad_json_lines.append([lineno, repr(e)[:200]])
                if len(bad_json_lines) > 20:
                    bad_json_lines = bad_json_lines[:21]
                continue
            if first_sample is None:
                first_sample = {
                    "top_keys": sorted(rec.keys()),
                    "chosen_keys": sorted(rec["chosen"].keys()) if isinstance(rec.get("chosen"), dict) else None,
                    "rejected_keys": sorted(rec["rejected"].keys()) if isinstance(rec.get("rejected"), dict) else None,
                    "conversations_len": len(rec.get("conversations", []) or []),
                }
            keyset[tuple(sorted(rec.keys()))] += 1
            for k in rec.keys():
                if k not in ("conversations", "chosen", "rejected", "system"):
                    top_level_extra[k] += 1
            rid = rec.get("id")
            if rid is None:
                ids_missing += 1
            else:
                if rid in ids:
                    dup_ids += 1
                ids.add(rid)
            ch = rec.get("chosen") or {}
            rj = rec.get("rejected") or {}
            cv = ch.get("value") if isinstance(ch, dict) else None
            rv = rj.get("value") if isinstance(rj, dict) else None
            if not cv:
                empty_chosen += 1
            if not rv:
                empty_rejected += 1
            cl = last_nonempty_line(cv or "")
            rl = last_nonempty_line(rv or "")
            c_ok = cl.startswith("VERDICT:")
            r_ok = rl.startswith("VERDICT:")
            if c_ok:
                verdict_chosen += 1
            if r_ok:
                verdict_rejected += 1
            if c_ok and r_ok:
                verdict_both += 1
            cj = False
            rj_ok = False
            if c_ok:
                try:
                    json.loads(cl[len("VERDICT:"):].strip())
                    cj = True
                except Exception:
                    pass
            if r_ok:
                try:
                    json.loads(rl[len("VERDICT:"):].strip())
                    rj_ok = True
                except Exception:
                    pass
            if cj:
                verdict_json_chosen += 1
            if rj_ok:
                verdict_json_rejected += 1
            if cj and rj_ok:
                verdict_json_both += 1
            if cv is not None and cv == rv:
                identical_sides += 1
            dc = rec.get("dpo_class")
            dpo_class[str(dc)] += 1
            comp = rec.get("mix_component") or rec.get("component") or rec.get("source") or rec.get("origin")
            component[str(comp)] += 1

    summary = {
        "file": DS,
        "file_bytes": os.path.getsize(DS),
        "file_mtime": os.path.getmtime(DS),
        "sha256": sha.hexdigest(),
        "total_lines": n,
        "unique_ids": len(ids),
        "duplicate_or_missing_ids": dup_ids,
        "records_without_id": ids_missing,
        "chosen_last_line_VERDICT": verdict_chosen,
        "rejected_last_line_VERDICT": verdict_rejected,
        "both_sides_VERDICT": verdict_both,
        "both_sides_VERDICT_ratio": round(verdict_both / n, 6) if n else None,
        "both_sides_VERDICT_parsable_json": verdict_json_both,
        "both_sides_VERDICT_parsable_json_ratio": round(verdict_json_both / n, 6) if n else None,
        "chosen_parsable_json_only": verdict_json_chosen,
        "rejected_parsable_json_only": verdict_json_rejected,
        "empty_chosen_value": empty_chosen,
        "empty_rejected_value": empty_rejected,
        "chosen_equals_rejected_text": identical_sides,
        "dpo_class_counts": dict(dpo_class.most_common()),
        "dpo_class_reserve_ratio": (
            round(dpo_class.get("reserve", 0) / n, 6) if n else None
        ),
        "dpo_class_reserve_ratio_over_decidable": None,
        "component_counts": dict(component.most_common(20)),
        "top_level_extra_fields": dict(top_level_extra.most_common(30)),
        "key_signatures": [{"keys": list(k), "count": v} for k, v in keyset.most_common(20)],
        "bad_json_lines": bad_json_lines,
        "first_sample": first_sample,
    }
    dec = n - dpo_class.get("reserve", 0)
    if dec:
        summary["dpo_class_reserve_ratio_over_decidable"] = round(dpo_class.get("reserve", 0) / dec, 6)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
