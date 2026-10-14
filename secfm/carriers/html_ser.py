"""HTML/DOM 载体序列化（docs/01 §2.4）。

五栖居处保真（docs/00 §3）：
- 结构：隐藏元素 [hidden]、事件处理器 handler:、1x1 图片、meta refresh
- 行为：外链脚本/样式/嵌入对象标注
- 语用：表单收集字段（密码字段加 *）、显示文本与链接目标不匹配
- 注释保留 [comment]、游离标签保留 [stray-tag]（不静默丢弃证据）

只标注机械事实，判断归模型。
"""

from __future__ import annotations

import re
from collections import namedtuple
from html.parser import HTMLParser

from .base import CarrierBlock
from .lookalike import url_mismatch_note

_VOID = {"br", "img", "input", "meta", "link", "hr", "source", "track",
         "wbr", "area", "base", "col", "embed", "param"}
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|opacity\s*:\s*0(?:\.0+)?(?![\d.])"
    r"|font-size\s*:\s*0(?:\.0+)?(?![\d.])"
    r"|font-size\s*:\s*1px",
    re.IGNORECASE,
)
_OFFSCREEN = re.compile(r"(?:left|top)\s*:\s*-\d{3,}", re.IGNORECASE)

DomResult = namedtuple("DomResult", ["lines", "title", "anchors"])


def _clip(s, n, label="chars"):
    s = str(s)
    if len(s) <= n:
        return s
    return s[:n] + f"…[truncated {len(s) - n} {label}]"


class _Frame:
    __slots__ = ("tag", "hidden", "href", "display", "inputs")

    def __init__(self, tag, hidden=False, href=None, display=None, inputs=None):
        self.tag = tag
        self.hidden = hidden
        self.href = href
        self.display = display
        self.inputs = inputs


class _Linearizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.anchors = []
        self.title = None
        self._stack = []
        self._in_title = False

    # -- 辅助 ---------------------------------------------------------------
    @property
    def _hidden_ctx(self):
        return any(f.hidden for f in self._stack)

    def _emit(self, s):
        self.lines.append(s)

    def _indent(self):
        return "  " * len(self._stack)

    def _record_input(self, ad, default_type="text"):
        for f in reversed(self._stack):
            if f.tag == "form":
                name = ad.get("name") or ad.get("id") or "?"
                typ = (ad.get("type") or default_type).lower()
                f.inputs.append((name, typ in ("password", "file")))
                break

    # -- HTMLParser 钩子 ------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        ad = {}
        for k, v in attrs:
            ad.setdefault(k.lower(), v or "")
        style = ad.get("style", "")
        hidden = (
            self._hidden_ctx
            or ("hidden" in ad)
            or bool(_HIDDEN_STYLE.search(style))
            or bool(_OFFSCREEN.search(style))
        )
        notes = []
        for k, v in ad.items():
            if k.startswith("on") and len(k) > 2:
                notes.append(f"handler:{k}={_clip(v, 100)}")
        if tag == "script":
            notes.append("inline-script" if not ad.get("src") else "external-script")
        if tag == "iframe":
            notes.append("embedded-frame")
        if tag in ("object", "embed"):
            notes.append("embedded-object")
        if tag == "link" and "stylesheet" in ad.get("rel", "").lower():
            notes.append("external-stylesheet")
        if tag == "meta" and ad.get("http-equiv", "").lower() == "refresh":
            notes.append("redirect")
        if (tag == "img" and ad.get("width", "") in ("0", "1")
                and ad.get("height", "") in ("0", "1")):
            notes.append("1x1-image")

        parts = [f"{self._indent()}<{tag}"]
        if ad.get("id"):
            parts.append(f' id="{_clip(ad["id"], 40)}"')
        if ad.get("class"):
            parts.append(f' class="{_clip(ad["class"], 60)}"')
        for key in ("href", "action", "src", "type", "name", "value",
                    "content", "http-equiv", "method", "style"):
            if key in ad:
                parts.append(f' {key}="{_clip(ad[key], 200)}"')
        if notes:
            parts.append(" [" + ", ".join(notes) + "]")
        if hidden:
            parts.append(" [hidden]")
        self._emit("".join(parts) + ">")

        if tag in _VOID:
            if tag == "input":
                self._record_input(ad)
            return
        self._stack.append(_Frame(
            tag=tag,
            hidden=hidden,
            href=ad.get("href") if tag == "a" else None,
            display=[] if tag == "a" else None,
            inputs=[] if tag == "form" else None,
        ))
        if tag == "title":
            self._in_title = True
        if tag in ("textarea", "select"):
            self._record_input(ad, default_type=tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag:
                idx = i
                break
        if idx is None:
            # 游离闭合标签：不是错误，但作为证据保留（不静默丢弃）
            self._emit(f"{self._indent()}<!--[stray-tag: /{tag}]-->")
            return
        while len(self._stack) > idx + 1:
            self._close_frame(self._stack.pop(), implicit=True)
        self._close_frame(self._stack.pop(), implicit=False)

    def _close_frame(self, f, implicit):
        if f.tag == "title":
            self._in_title = False
        if f.tag == "a" and f.href:
            disp = " ".join(f.display or []).strip()
            self.anchors.append((f.href, disp))
            note = url_mismatch_note(f.href, disp)
            if note:
                self._emit(f"{self._indent()}</a> {note}")
                return
        if f.tag == "form" and f.inputs is not None:
            names = ", ".join(f"{n}{'*' if s else ''}" for n, s in f.inputs) or "(none)"
            line = f"{self._indent()}</form> [collects: {names}]"
            if any(s for _, s in f.inputs):
                line += " [sensitive-input]"
            self._emit(line)
            return
        if not implicit:
            self._emit(f"{self._indent()}</{f.tag}>")

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if not self._stack:
            text = " ".join(data.split())
            if text:
                self._emit(_clip(text, 4000))
            return
        top = self._stack[-1]
        if top.tag == "a" and top.display is not None:
            top.display.append(data)
        text = " ".join(data.split())
        if not text:
            return
        if top.tag in ("script", "style"):
            self._emit(self._indent() + _clip(text, 400))
            return
        if self._hidden_ctx:
            self._emit(self._indent() + f"[hidden] {_clip(text, 4000)} [/hidden]")
        else:
            self._emit(self._indent() + _clip(text, 4000))

    def handle_comment(self, data):
        self._emit(
            f"{self._indent()}<!--[comment] "
            f"{_clip(' '.join(data.split()), 500)} [/comment]-->"
        )

    def handle_decl(self, decl):
        self._emit(f"{self._indent()}<!--[decl] {_clip(decl, 100)} -->")

    def unknown_decl(self, data):
        self._emit(f"{self._indent()}<!--[decl] {_clip(str(data), 100)} -->")

    def handle_pi(self, data):
        self._emit(f"{self._indent()}<!--[pi] {_clip(data, 100)} -->")


def linearize_dom(html_text: str) -> DomResult:
    """HTML -> 线性化 DOM 文本（保留安全信号标注）。"""
    p = _Linearizer()
    p.feed(html_text)
    p.close()
    title = " ".join((p.title or "").split()) or None
    return DomResult(lines=list(p.lines), title=title, anchors=list(p.anchors))


def serialize_webpage(html_text, *, url=None, fetched=None, redirects=None,
                      cid="c1", max_lines=300) -> CarrierBlock:
    dom = linearize_dom(html_text)
    lines = dom.lines
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [
            f"[truncated: {len(dom.lines) - max_lines} more dom lines omitted]"
        ]
    meta = []
    if url:
        meta.append(f"url: {url}")
    if fetched:
        meta.append(f"fetched: {fetched}")
    if redirects is not None:
        meta.append(f"redirects: {redirects}")
    if dom.title:
        meta.append(f"title: {dom.title}")
    return CarrierBlock(
        ctype="webpage",
        cid=cid,
        meta_lines=meta,
        sections=[("dom", "\n".join(lines))],
    )
