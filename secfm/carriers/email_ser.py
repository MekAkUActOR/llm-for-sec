"""邮件载体序列化（docs/01 §2.4）。

五栖居处保真：
- 元数据/来源：From/Reply-To/认证结果(SPF/DKIM/DMARC)/Received 跳数/
  发件域仿冒与显示名品牌不符（机械字符串事实）
- 结构：HTML 正文走 linearize_dom（隐藏文本、表单、事件处理器保留）
- 行为：URL 汇总区（IP 字面量、punycode、显示文本与目标不匹配）
- 语义：纯文本正文（显式截断）
- 附件：文件名/声明类型不匹配、双扩展名
"""

from __future__ import annotations

import email
import html as _html
import re
from email import policy
from email.utils import parseaddr

from .base import CarrierBlock
from .html_ser import linearize_dom
from .lookalike import (display_name_brand_note, domain_lookalike_note,
                        url_host_notes, url_mismatch_note)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

_EXT_MIME = {
    "pdf": "application/pdf",
    "zip": "application/zip",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "js": "application/javascript",
    "exe": "application/x-msdownload",
}
_DOUBLE_EXT = re.compile(
    r"\.(pdf|doc|docx|xls|xlsx|txt|jpg|png)\.(exe|scr|js|vbs|bat|cmd|ps1|zip|lnk)$",
    re.IGNORECASE,
)


def _addr_domain(addr):
    if not addr or "@" not in addr:
        return ""
    return addr.rsplit("@", 1)[-1].lower().strip()


def _part_text(part):
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode("utf-8", "replace")
        return str(payload or "")


def _strip_tags(html_text):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(_html.unescape(text).split())


def serialize_email(raw, *, cid="c1", body_limit=8000, dom_max_lines=200):
    """raw: RFC 5322 原始邮件（str 或 bytes）。返回 CarrierBlock。

    注意：内部统一走 bytes 解析（message_from_bytes）。若用
    message_from_string 解析含非 ASCII 的 str 正文，email 库会走
    raw-unicode-escape 路径把正文变成 \\uXXXX 字面量。
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    msg = email.message_from_bytes(raw, policy=policy.default)

    from_name, from_addr = parseaddr(str(msg.get("From") or ""))
    from_domain = _addr_domain(from_addr)
    _, reply_addr = parseaddr(str(msg.get("Reply-To") or ""))
    reply_domain = _addr_domain(reply_addr)

    meta = []
    note = domain_lookalike_note(from_domain)
    meta.append(f"from: {from_addr}" + (f"   {note}" if note else ""))
    if from_name:
        note = display_name_brand_note(from_name, from_domain)
        meta.append(f"from-name: {from_name}" + (f"   {note}" if note else ""))
    if reply_addr:
        mismatch = ("   [note: from/reply-to domain mismatch]"
                    if (reply_domain and from_domain and reply_domain != from_domain)
                    else "")
        meta.append(f"reply-to: {reply_addr}{mismatch}")
    to_hdr = str(msg.get("To") or "")
    if to_hdr:
        meta.append(f"to: {parseaddr(to_hdr)[1] or to_hdr}")
    meta.append(f"subject: {str(msg.get('Subject') or '')}")
    date_hdr = str(msg.get("Date") or "")
    if date_hdr:
        meta.append(f"date: {date_hdr}")

    ar = " ".join(str(h) for h in (msg.get_all("Authentication-Results") or []))
    if ar:
        def _tok(name):
            m = re.search(rf"\b{name}=(\w+)", ar, re.IGNORECASE)
            return m.group(1).lower() if m else "unknown"
        meta.append(
            f"auth: spf={_tok('spf')} dkim={_tok('dkim')} dmarc={_tok('dmarc')}"
            "   [source: Authentication-Results]"
        )
    else:
        meta.append("auth: spf=unknown dkim=unknown dmarc=unknown"
                    "   [note: no Authentication-Results header]")
    meta.append(f"received-hops: {len(msg.get_all('Received') or [])}")

    # 附件：机械事实（声明类型与扩展名不符、双扩展名）
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        fname = part.get_filename()
        if not fname:
            continue
        ctype = part.get_content_type()
        att = f"attachment: {fname} ({ctype})"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        expected = _EXT_MIME.get(ext)
        if expected and ctype != expected:
            att += f"   [note: declared {ctype} but .{ext} usually {expected}]"
        if _DOUBLE_EXT.search(fname):
            att += "   [note: double extension]"
        meta.append(att)

    # 正文部件
    plain_part = None
    html_part = None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain_part is None:
            plain_part = part
        elif ctype == "text/html" and html_part is None:
            html_part = part

    sections = []
    anchors = []
    body_text = None
    if plain_part is not None:
        body_text = _part_text(plain_part)
    if html_part is not None:
        dom = linearize_dom(_part_text(html_part))
        anchors = dom.anchors
        lines = dom.lines
        if len(lines) > dom_max_lines:
            lines = lines[:dom_max_lines] + [
                f"[truncated: {len(dom.lines) - dom_max_lines} more dom lines omitted]"
            ]
        sections.append(("dom", "\n".join(lines)))
        if body_text is None:
            body_text = _strip_tags(_part_text(html_part))
            meta.append("body-format: html (tags stripped; linearized dom below)")

    body_text = body_text or ""
    if len(body_text) > body_limit:
        body_text = body_text[:body_limit] + \
            f"\n[truncated: {len(body_text) - body_limit} chars omitted]"

    # URL 汇总区
    url_lines = []
    seen = set()

    def _add_url(href, display=None):
        href = href.strip().rstrip(".,;:!?")
        if not href or href in seen:
            return
        seen.add(href)
        line = f"[{len(url_lines) + 1}] {href}"
        if display and display.strip() and display.strip() != href:
            line += f" (displayed as: {display.strip()})"
        notes = url_host_notes(href)
        mnote = url_mismatch_note(href, display or "")
        if mnote:
            notes.insert(0, mnote)
        for n in notes:
            line += f" {n}" if n.startswith("[") else f" [note: {n}]"
        url_lines.append(line)

    for href, display in anchors:
        _add_url(href, display)
    for u in _URL_RE.findall(body_text):
        _add_url(u)

    return CarrierBlock(
        ctype="email",
        cid=cid,
        meta_lines=meta,
        sections=sections,
        body=body_text if body_text else None,
        post_sections=[("urls", "\n".join(url_lines))] if url_lines else [],
    )
