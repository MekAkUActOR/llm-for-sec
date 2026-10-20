# -*- coding: utf-8 -*-
"""M6 data build common utilities (dataeng-m6).

Shared helpers for all m6 generators/converters: deterministic RNG, jsonl IO,
text normalization, exact-hash and 8-gram near-dup isolation checks, and a
segment builder that guarantees correct character-offset span annotations.
"""
import hashlib
import io
import json
import os
import random
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_WS_RE = re.compile(r"\s+")


def norm_text(s: str) -> str:
    """Normalization key for dedup: lowercase + collapse whitespace."""
    return _WS_RE.sub(" ", (s or "").strip().lower())


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def ngrams(s: str, n: int = 8):
    """Word-level n-grams of normalized text (for near-dup isolation checks)."""
    words = norm_text(s).split(" ")
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


class Seg:
    """Segment builder: append literal text or typed entities; tracks spans.

    Usage:
        sb = Seg()
        sb.txt("工单 #4711：客户 ")
        sb.ent("张伟", "name")
        sb.txt(" 来电，手机 ")
        sb.ent("13812345678", "phone")
        text, spans = sb.build()
    """

    def __init__(self):
        self.parts = []
        self.pos = 0
        self.spans = []

    def txt(self, s: str):
        self.parts.append(s)
        self.pos += len(s)
        return self

    def ent(self, value: str, etype: str, sub=None):
        start = self.pos
        self.parts.append(value)
        self.pos += len(value)
        sp = {"start": start, "end": self.pos, "type": etype}
        if sub:
            sp["sub"] = sub
        self.spans.append(sp)
        return self

    def build(self):
        return "".join(self.parts), self.spans


def make_row(task, split_hint, lang, kind, label, label_detail, source_family,
             text=None, turns=None, difficulty="medium", lineage=None, extra_meta=None):
    row = {
        "task": task,
        "split_hint": split_hint,  # advisory; final split decided by build_all
        "lang": lang,
        "kind": kind,
        "label": label,
        "label_detail": label_detail,
        "source_family": source_family,
        "meta": {
            "difficulty": difficulty,
            "lineage": lineage or {},
            "text_sha16": None,
        },
    }
    if turns is not None:
        row["turns"] = turns
        joined = "\n".join(t["content"] for t in turns)
        row["meta"]["text_sha16"] = sha16(joined)
    else:
        row["text"] = text
        row["meta"]["text_sha16"] = sha16(text or "")
    if extra_meta:
        row["meta"].update(extra_meta)
    return row


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("[write] %s  rows=%d" % (path, len(rows)))


def read_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def assign_ids(rows, prefix):
    """Assign deterministic sequential ids like m6-t4-000123."""
    for i, r in enumerate(rows, 1):
        r["id"] = "%s-%06d" % (prefix, i)
    return rows


class Deduper:
    """Exact-dup removal by normalized hash; optionally near-dup by 8-grams."""

    def __init__(self):
        self.seen = set()
        self.ngram_index = {}

    def is_dup(self, text, near=True):
        h = sha16(norm_text(text))
        if h in self.seen:
            return True
        if near:
            grams = ngrams(text)
            hit = sum(1 for g in grams if g in self.ngram_index)
            if grams and hit / max(1, len(grams)) > 0.6:
                return True
        return False

    def add(self, text):
        h = sha16(norm_text(text))
        self.seen.add(h)
        for g in ngrams(text):
            self.ngram_index.setdefault(g, 0)
            self.ngram_index[g] += 1


def rng_of(seed: int):
    return random.Random(seed)
