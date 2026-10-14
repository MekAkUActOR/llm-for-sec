"""上下文协议 v0（docs/01 §1.5）。"""

from .context import (PROTOCOL_VERSION, ParsedContext, ProtocolError,
                      build_context, parse_context)

__all__ = [
    "PROTOCOL_VERSION",
    "ParsedContext",
    "ProtocolError",
    "build_context",
    "parse_context",
]
