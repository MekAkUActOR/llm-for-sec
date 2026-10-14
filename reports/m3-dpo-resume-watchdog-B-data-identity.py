# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog B: data identity + VERDICT coverage, CPU only, read-only.

Writes reports/m3-dpo-resume-watchdog-B-data-identity.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
DATA = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
EXPECT_SHA = "c272ff9d0f8583982322f691736bac82f571af8c2be73c6087e2081882445b07"
EXPECT_ROWS = 28842

VERDICT_RE = re.compile(r"VERDICT\s*:")
JSON_RE = re.compile(r"VERDICT\s*:?\s*(\{.*?\})", re.S)


def side_has_verdict(text: str) -> tuple[bool, bool]:
    """(has VERDICT token, has parseable JSON object after it)"""
    m = VERDICT_RE.search(text)
    if not m:
        return False, False
    j = JSON_RE.search(text)
    if not j:
        return True, False
    try:
        json.loads(j.group(1))
        return True, True
    except Exception:
        return True, False


def main() -> int:
    out: dict = {"path": str(DATA)}

    h = hashlib.sha256()
    with DATA.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    out["sha256"] = h.hexdigest()
    out["sha256_expected"] = EXPECT_SHA
    out["sha256_match"] = out["sha256"] == EXPECT_SHA
    out["size_bytes"] = DATA.stat().st_size
    out["mtime"] = DATA.stat().st_mtime

    rows = 0
    ids: set[str] = set()
    dup_ids = 0
    src_counter: Counter = Counter()
    bad_json = 0
    both_v = 0
    chosen_v = 0
    rejected_v = 0
    chosen_v_json = 0
    rejected_v_json = 0
    carriers = 0
    examples_missing = []
    first_keys = None

    with DATA.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                o = json.loads(line)
            except Exception:
                bad_json += 1
                continue
            if first_keys is None:
                first_keys = sorted(o.keys())
            _id = o.get("id") or o.get("uid")
            if _id is not None:
                if _id in ids:
                    dup_ids += 1
                ids.add(_id)
            src = o.get("_src") or o.get("source") or o.get("src") or o.get("origin")
            src_counter[str(src)] += 1
            ch = o.get("chosen")
            rj = o.get("rejected")
            if isinstance(ch, list):
                ctext = "\n".join(m.get("content", "") for m in ch)
            else:
                ctext = str(ch)
            if isinstance(rj, list):
                rtext = "\n".join(m.get("content", "") for m in rj)
            else:
                rtext = str(rj)
            cv, cj = side_has_verdict(ctext)
            rv, rjj = side_has_verdict(rtext)
            chosen_v += cv
            rejected_v += rv
            chosen_v_json += cj
            rejected_v_json += rjj
            both_v += (cv and rv)
            if (not cv or not rv) and len(examples_missing) < 5:
                examples_missing.append({"id": _id, "chosen_v": cv, "rejected_v": rv,
                                         "src": src})

    out["rows"] = rows
    out["rows_expected"] = EXPECT_ROWS
    out["rows_match"] = rows == EXPECT_ROWS
    out["unique_ids"] = len(ids)
    out["duplicate_ids"] = dup_ids
    out["bad_json_lines"] = bad_json
    out["top_level_keys"] = first_keys
    out["src_field_counter"] = dict(src_counter)
    out["verdict_coverage"] = {
        "both_sides_have_VERDICT": both_v,
        "both_pct": round(100.0 * both_v / max(1, rows), 4),
        "chosen_has_VERDICT": chosen_v,
        "rejected_has_VERDICT": rejected_v,
        "chosen_parseable_json": chosen_v_json,
        "rejected_parseable_json": rejected_v_json,
        "examples_missing": examples_missing,
    }
    (R / "m3-dpo-resume-watchdog-B-data-identity.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("sha256      =", out["sha256"])
    print("expected    =", EXPECT_SHA, "MATCH" if out["sha256_match"] else "*** MISMATCH ***")
    print("size_bytes  =", out["size_bytes"])
    print("rows        =", rows, "(expected", EXPECT_ROWS, ")")
    print("unique_ids  =", len(ids), "dup_ids =", dup_ids, "bad_json =", bad_json)
    print("top-level keys =", first_keys)
    print("src counter =", dict(src_counter))
    print("VERDICT coverage:", json.dumps(out["verdict_coverage"], ensure_ascii=False))
    print("WROTE", R / "m3-dpo-resume-watchdog-B-data-identity.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
