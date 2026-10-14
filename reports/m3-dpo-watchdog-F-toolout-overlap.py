# -*- coding: utf-8 -*-
"""M3 DPO watchdog: does data/heldout/v0.4-toolout overlap the M3 DPO training mix?
CPU-only, read-only. Reports exact and normalized-substring overlaps."""
import json
import os
import re

ROOT = r"J:\Projects\llm_for_sec"
HELDOUT = os.path.join(ROOT, "data", "heldout", "v0.4-toolout", "tool_output.jsonl")
MIX = os.path.join(ROOT, "data", "lf", "dpo_m3_final.jsonl")
OUT = os.path.join(ROOT, "reports", "m3-dpo-watchdog-toolout-overlap.json")

WS = re.compile(r"\s+")


def norm(s):
    return WS.sub(" ", (s or "").strip())


def main():
    items = []
    with open(HELDOUT, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    # build the full mix text once (conversations + chosen/rejected values)
    parts = []
    mix_ids = set()
    n = 0
    with open(MIX, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n += 1
            r = json.loads(line)
            mix_ids.add(r.get("id"))
            for c in r.get("conversations", []) or []:
                parts.append(str(c.get("value", "")))
            for k in ("chosen", "rejected"):
                v = r.get(k)
                if isinstance(v, dict):
                    parts.append(str(v.get("value", "")))
    blob = norm("\n".join(parts))
    print("mix rows", n, "blob chars", len(blob))

    res = {"mix_rows": n, "blob_chars": len(blob), "items": [], "summary": {}}
    hits = 0
    for it in items:
        q = norm(it["query"])
        # exact whole-query hit
        whole = q in blob
        # distinctive-probe: longest body line(s) from the carrier
        m = re.search(r"<body>(.*?)</body>", q, re.S)
        body = norm(m.group(1)) if m else ""
        body_hit = bool(body) and body in blob
        # take the single longest line of the query as a cheap fingerprint
        longest = max((norm(x) for x in it["query"].split("\n")), key=len)
        longest_hit = bool(longest) and longest in blob
        # head fingerprint (first 60 chars of the carrier body)
        head = body[:60]
        head_hit = bool(head) and head in blob
        rec = {
            "id": it["id"], "kind": it["kind"], "lang": it["language"],
            "id_in_mix": it["id"] in mix_ids,
            "whole_query_in_mix": whole,
            "carrier_body_in_mix": body_hit,
            "longest_line_in_mix": longest_hit,
            "body_head60_in_mix": head_hit,
        }
        if whole or body_hit or longest_hit or head_hit or rec["id_in_mix"]:
            hits += 1
        res["items"].append(rec)
    res["summary"] = {
        "n_items": len(items),
        "items_with_any_overlap": hits,
        "ids_in_mix": [r["id"] for r in res["items"] if r["id_in_mix"]],
        "whole_query_matches": [r["id"] for r in res["items"] if r["whole_query_in_mix"]],
        "carrier_body_matches": [r["id"] for r in res["items"] if r["carrier_body_in_mix"]],
        "longest_line_matches": [r["id"] for r in res["items"] if r["longest_line_in_mix"]],
        "body_head60_matches": [r["id"] for r in res["items"] if r["body_head60_in_mix"]],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
