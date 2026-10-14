"""通用文本/日志载体序列化（docs/01 §2.4）。"""

from __future__ import annotations

from .base import CarrierBlock


def serialize_text(text, *, ctype="text", meta_lines=None, cid="c1",
                   body_limit=20000) -> CarrierBlock:
    if ctype not in ("text", "log"):
        raise ValueError("serialize_text supports ctype in {'text', 'log'}")
    body = text
    if len(body) > body_limit:
        body = body[:body_limit] + f"\n[truncated: {len(text) - body_limit} chars omitted]"
    return CarrierBlock(ctype=ctype, cid=cid,
                        meta_lines=list(meta_lines or []), body=body)
