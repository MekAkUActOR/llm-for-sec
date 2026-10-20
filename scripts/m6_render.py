# -*- coding: utf-8 -*-
"""M6 input normalization + rendering (ADR-1 D9, SYS-1 contract).

Single rendering path shared by train / infer / eval -- byte-identical
serialization via the r5 chat_template.jinja:

  normalize_input(rec)  : BatchLine ({id,text}|{id,turns}|{id,input}) or
                          m6-sample row -> unified five-form input dict
  render(tok, inp)      : -> (rendered_str, msg_spans)
                          msg_spans = [(msg_index, start, end)] char ranges of
                          each user/assistant content inside the rendered
                          string (sequential locate, asserted)
  tokenize_windowed(tok, rendered)
                        : -> token ids + offsets + truncation flag
                          (4096 window; head 512 + tail 3584 per ADR-1 D9)
  spans_to_bio(...)     : gold PII spans (original-text coords) -> token BIO
  bio_to_spans(...)     : predicted token BIO -> PII spans (original coords)

Carrier form: v1 placeholder rendering (structured, body verbatim) until
SYS-1 freezes the dsh-protocol/0.1 envelope spec; swap point is
render_carrier() only.
"""
from __future__ import annotations

import json
from pathlib import Path

# PII entity types -- FINAL vocabulary per dataeng/arch ruling (SYS-1 freeze):
# 11 classes, gov_id unified (sub: resident_id|passport carried on spans).
PII_TYPES = [
    "person", "phone", "email", "gov_id", "address", "bank_card",
    "credential", "dob", "license_plate", "medical_id", "other_id",
]
# legacy aliases (older m6-common drafts) -> canonical, defensive only
PII_TYPE_ALIASES = {
    "name": "person", "id_card": "gov_id", "passport": "gov_id",
    "medical_record": "medical_id", "other": "other_id",
}
PII_TYPE_INDEX = {t: i for i, t in enumerate(PII_TYPES)}
N_BIO_CHANNELS = 2 * len(PII_TYPES) + 1  # 23

WINDOW_TOKENS = 4096
HEAD_TOKENS = 512
TAIL_TOKENS = 3584


# --------------------------------------------------------------------------- #
# input normalization
# --------------------------------------------------------------------------- #
def normalize_input(rec: dict) -> dict:
    """Normalize a batch line or m6-sample row into a unified input dict:
    {"kind": text|turns|messages|carrier|protocol, "system": str|None, ...}

    Accepts:
      {id, text}                       -> text form
      {id, turns: [str]}               -> turns form (all-user)
      {id, input: {text|turns|messages|carrier|protocol_text, system?}}
      m6-sample row (schema m6-sample) -> its input field
    Also tolerates legacy {id, turns: [{role, content}]} (messages semantics).
    """
    if "input" in rec and isinstance(rec["input"], dict):
        inp = dict(rec["input"])
    elif "text" in rec:
        inp = {"text": rec["text"]}
    elif "turns" in rec:
        inp = {"turns": rec["turns"]}
    else:
        raise ValueError(f"cannot normalize input for id={rec.get('id')!r}: "
                         f"need text/turns/input, got keys {sorted(rec)}")
    system = inp.pop("system", None) or rec.get("system")

    if "text" in inp:
        return {"kind": "text", "text": str(inp["text"]), "system": system}
    if "protocol_text" in inp:
        return {"kind": "protocol", "protocol_text": str(inp["protocol_text"]),
                "system": system}
    if "messages" in inp:
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in inp["messages"]]
        return {"kind": "messages", "messages": msgs, "system": system}
    if "turns" in inp:
        turns = inp["turns"]
        if turns and isinstance(turns[0], dict):
            # legacy [{role, content}] -> messages semantics
            msgs = [{"role": t.get("role", "user"), "content": t["content"]}
                    for t in turns]
            return {"kind": "messages", "messages": msgs, "system": system}
        return {"kind": "turns", "turns": [str(t) for t in turns],
                "system": system}
    if "carrier" in inp:
        out = {"kind": "carrier", "operator_task": inp.get("operator_task", ""),
               "carrier": inp["carrier"], "user_turn": inp.get("user_turn"),
               "system": system}
    else:
        raise ValueError(f"unsupported input form, keys={sorted(inp)}")
    # render-side knobs (lang / policy_pack) best-effort from the row
    out["lang"] = rec.get("lang") or (rec.get("input") or {}).get("lang") or "zh"
    opts = rec.get("options") or {}
    out["policy_pack"] = (opts.get("policy_pack") or rec.get("policy_pack")
                          or (rec.get("meta") or {}).get("policy_pack") or "default")
    return out


def render_kind(inp: dict) -> str:
    return inp["kind"]


# --------------------------------------------------------------------------- #
# carrier placeholder rendering (SYS-1 dsh-protocol/0.1 pending)
# --------------------------------------------------------------------------- #
def render_carrier(inp: dict, policy_pack: str = "default", lang: str = "zh") -> str:
    """dsh-protocol/0.1 envelope (sysdesign final spec, frozen-suite verified).
    The whole envelope is the chat-template USER message. carrier.body is
    verbatim (span coordinates stay valid). Optional <dom>/<urls> blocks
    render only when the fields exist (v0.6-document carriers)."""
    c = inp["carrier"]
    role = "security-analysis-assistant" if lang == "en" else "安全分析助手"
    lines = [
        '<dsh-protocol v="0.1">',
        "<system>",
        f"role: {role}",
        "authorization: analyst",
        f"policy: {policy_pack}",
        "output-mode: structured",
        "</system>",
        "<operator>",
        str(inp.get("operator_task", "")),
        "</operator>",
        f'<carrier type="{c.get("type", "other")}" trust="untrusted" '
        f'id="{c.get("id", "c1")}">',
    ]
    meta = c.get("meta") or {}
    if meta:
        lines.append("<meta>")
        lines.extend(f"{k}: {v}" for k, v in meta.items())
        lines.append("</meta>")
    lines += ["<body>", c["body"], "</body>"]
    dom = c.get("dom") or meta.get("dom")
    if dom:
        lines += ["<dom>", str(dom), "</dom>"]
    urls = c.get("urls") or meta.get("urls")
    if urls:
        seq = urls if isinstance(urls, list) else [urls]
        lines.append("<urls>")
        lines.extend(str(u) for u in seq)
        lines.append("</urls>")
    lines += ["</carrier>", "<user>",
              str(inp.get("user_turn") or "请给出整理结果。"), "</user>",
              "</dsh-protocol>"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _chat_messages(inp: dict) -> tuple[list[dict], list[dict]]:
    """Build (messages_for_template, content_messages_for_span_location).
    The second list only contains messages whose content is span-addressable
    (user/assistant turns; system excluded per m6-common Span semantics)."""
    k = inp["kind"]
    if k == "text":
        msgs = [{"role": "user", "content": inp["text"]}]
    elif k == "turns":
        msgs = [{"role": "user", "content": t} for t in inp["turns"]]
    elif k == "messages":
        msgs = [dict(m) for m in inp["messages"]]
    elif k == "protocol":
        msgs = [{"role": "user", "content": inp["protocol_text"]}]
    elif k == "carrier":
        msgs = [{"role": "user",
                 "content": render_carrier(inp, inp.get("policy_pack", "default"),
                                           inp.get("lang", "zh"))}]
    else:
        raise ValueError(k)
    template_msgs = ([{"role": "system", "content": inp["system"]}]
                     if inp.get("system") else []) + msgs
    return template_msgs, msgs


def render(tok, inp: dict) -> tuple[str, list[tuple[int, int, int]]]:
    """Full serialization via r5 chat template (byte-identical everywhere).

    Returns (rendered, msg_spans) where msg_spans[i] = (msg_index, start, end)
    gives the char range of message i's content within `rendered`
    (msg_index counts only user/assistant messages, 0-based, aligned with
    m6-common Span.message_index).
    """
    template_msgs, msgs = _chat_messages(inp)
    rendered = tok.apply_chat_template(template_msgs, tokenize=False,
                                       add_generation_prompt=True)
    msg_spans = []
    pos = 0
    for mi, m in enumerate(msgs):
        c = m["content"]
        idx = rendered.find(c, pos)
        assert idx >= 0, (
            f"render span location failed for message {mi} "
            f"(id-context); template output did not contain content verbatim")
        msg_spans.append((mi, idx, idx + len(c)))
        pos = idx + len(c)
    return rendered, msg_spans


# --------------------------------------------------------------------------- #
# windowed tokenization (D9: 4096 window, head 512 + tail 3584)
# --------------------------------------------------------------------------- #
def tokenize_windowed(tok, rendered: str, window: int = WINDOW_TOKENS,
                      head: int = HEAD_TOKENS, tail: int = TAIL_TOKENS):
    """Tokenize with char offsets; apply head+tail truncation if over window.

    Returns dict(input_ids=[T], offsets=[(s,e)], truncation=bool).
    Offsets are (start, end) char ranges into `rendered`, end exclusive;
    special/template tokens carry their true ranges (no overlap with content
    spans because template scaffolding sits between message contents).
    """
    enc = tok(rendered, add_special_tokens=False, return_offsets_mapping=True)
    ids = enc["input_ids"]
    offs = [tuple(o) for o in enc["offset_mapping"]]
    trunc = len(ids) > window
    if trunc:
        ids = ids[:head] + ids[-tail:]
        offs = offs[:head] + offs[-tail:]
    return {"input_ids": ids, "offsets": offs, "truncation": trunc}


# --------------------------------------------------------------------------- #
# PII span <-> BIO conversion
# --------------------------------------------------------------------------- #
def _locate_span_abs(span: dict, msg_spans) -> tuple[int, int, int]:
    """Map a gold span (original-field coords) to absolute rendered coords.
    Returns (start_abs, end_abs, type_index)."""
    t = span.get("type", "other_id")
    t = PII_TYPE_ALIASES.get(t, t)
    t_idx = PII_TYPE_INDEX.get(t, PII_TYPE_INDEX["other_id"])
    mi = span.get("message_index", 0)
    base = None
    for (mi_, s, e) in msg_spans:
        if mi_ == mi:
            base = (s, e)
            break
    if base is None:
        # carrier / single-text forms: span coords are relative to the single
        # addressable message (index 0 semantics)
        base = msg_spans[0][1], msg_spans[0][2]
    return base[0] + int(span["start"]), base[0] + int(span["end"]), t_idx


def spans_to_bio(spans: list[dict], offsets, msg_spans,
                 n_types: int = len(PII_TYPES)) -> list[int]:
    """Gold spans -> per-token BIO labels (channel index).
    O = 0; B-type = 1 + t_idx; I-type = 1 + n_types + t_idx.
    A token is inside a span if its char range overlaps the span range."""
    labels = [0] * len(offsets)
    for span in spans or []:
        s_abs, e_abs, t_idx = _locate_span_abs(span, msg_spans)
        first = True
        for ti, (ts, te) in enumerate(offsets):
            if te <= s_abs or ts >= e_abs:
                continue
            if labels[ti] == 0:
                labels[ti] = (1 + t_idx) if first else (1 + n_types + t_idx)
            first = False
    return labels


def bio_to_spans(bio: list[int], offsets, msg_spans, text_of_message,
                 n_types: int = len(PII_TYPES)) -> list[dict]:
    """Predicted per-token BIO -> spans in original-field coordinates.
    text_of_message: callable(msg_index) -> original text of that message.
    Consecutive same-type B/I runs merge into one span (bio-consecutive)."""
    spans = []
    cur = None  # [type_idx, start_tok, end_tok]
    for ti, lab in enumerate(bio):
        if lab == 0:
            if cur:
                spans.append(cur)
                cur = None
            continue
        if 1 <= lab <= n_types:
            if cur:
                spans.append(cur)
            cur = [lab - 1, ti, ti + 1]
        else:
            t = lab - 1 - n_types
            if cur and cur[0] == t:
                cur[2] = ti + 1
            else:
                if cur:
                    spans.append(cur)
                cur = [t, ti, ti + 1]
    if cur:
        spans.append(cur)

    out = []
    for t_idx, t0, t1 in spans:
        s_abs = offsets[t0][0]
        e_abs = offsets[t1 - 1][1]
        # find owning message by max overlap
        best_mi, best_ov = 0, -1
        for (mi, cs, ce) in msg_spans:
            ov = min(e_abs, ce) - max(s_abs, cs)
            if ov > best_ov:
                best_ov, best_mi = ov, mi
        mi, cs, ce = next((m for m in msg_spans if m[0] == best_mi), msg_spans[0])
        text = text_of_message(best_mi)
        start = max(0, s_abs - cs)
        end = min(len(text), e_abs - cs)
        if end <= start:
            continue
        out.append({
            "start": start, "end": end, "type": PII_TYPES[t_idx],
            "text": text[start:end], "message_index": best_mi,
            # gov_id sub-resolution (resident_id|passport) is gold-side only;
            # BIO channels are unified, predicted spans carry no sub.
        })
    return out


def load_jsonl(path) -> list[dict]:
    recs = []
    # utf-8-sig: accept both BOM (PS5.1) and plain UTF-8
    with open(path, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                r = json.loads(line)
                assert "id" in r, f"{path}:{i + 1} missing 'id'"
                recs.append(r)
    return recs


def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
