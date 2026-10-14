"""载体序列化 v0（docs/01 §2.4）。

可用入口：
    serialize_email(raw_email)      -> CarrierBlock
    serialize_webpage(html, ...)    -> CarrierBlock
    serialize_code(code, path=...)  -> CarrierBlock
    serialize_text(text, ...)       -> CarrierBlock
    serialize_document(facts, ...)  -> CarrierBlock   （S1：PDF/Office 结构层/行为层）
    linearize_dom(html)             -> DomResult(lines, title, anchors)

注意：meta_ser（image_metadata / av_metadata）**刻意不在此导出**——它是 v0.3-gen
未见载体留出集，注册/导出即破坏留出性。
"""

from .base import (CarrierBlock, escape_region_markers,
                   unescape_region_markers)
from .code_ser import serialize_code
from .document_ser import attach_document_carrier, serialize_document
from .email_ser import serialize_email
from .html_ser import linearize_dom, serialize_webpage
from .text_ser import serialize_text

__all__ = [
    "CarrierBlock",
    "escape_region_markers",
    "unescape_region_markers",
    "serialize_code",
    "serialize_document",
    "attach_document_carrier",
    "serialize_email",
    "serialize_text",
    "serialize_webpage",
    "linearize_dom",
]
