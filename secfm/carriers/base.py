"""CarrierBlock 模型 + 区域标记转义（docs/01 §2.4）。

设计原则：
1. 不静默丢弃安全信号——隐藏元素、注释、事件处理器、表单目标、
   URL 不匹配等机械事实全部保留并标注；
2. 序列化器只标注机械事实，判断归模型；
3. 截断必须显式（[truncated: ...]），永不静默；
4. 版本化 + train/infer 同路径。

构造侧防注入（安全性质，测试覆盖）：
    上下文协议的区域标记不允许作为内容出现。由 build_context 构造的
    合法上下文中，载体内容不可能提前闭合区域——内容里的协议标记被
    替换为全角括号形式（⟨...⟩），解析时还原。注意：对原始攻击文本，
    parse_context 的严格顺序校验只是调试辅助；真正的边界是模型自身的
    指令/数据分离训练（docs/00 §7.2）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- 区域标记转义 ---------------------------------------------------------
# 替换规则：<tag> -> ⟨tag⟩（仅针对协议保留标记；解析时精确还原）。
_ESCAPE_PAIRS = [
    ("<dsh-protocol", "⟨dsh-protocol"),
    ("</dsh-protocol>", "⟨/dsh-protocol⟩"),
    ("<system>", "⟨system⟩"),
    ("</system>", "⟨/system⟩"),
    ("<operator>", "⟨operator⟩"),
    ("</operator>", "⟨/operator⟩"),
    ("<carrier", "⟨carrier"),
    ("</carrier>", "⟨/carrier⟩"),
    ("<user>", "⟨user⟩"),
    ("</user>", "⟨/user⟩"),
]
_ESCAPE_MAP = dict(_ESCAPE_PAIRS)
_UNESCAPE_MAP = {v: k for k, v in _ESCAPE_MAP.items()}


def escape_region_markers(text: str) -> str:
    """把协议区域标记转义为全角形式（内容绝不可能提前闭合区域）。"""
    for a, b in _ESCAPE_MAP.items():
        text = text.replace(a, b)
    return text


def unescape_region_markers(text: str) -> str:
    """escape_region_markers 的逆操作（解析侧还原内容）。"""
    for a, b in _UNESCAPE_MAP.items():
        text = text.replace(a, b)
    return text


# --- CarrierBlock ---------------------------------------------------------
_SAFE_ATTR = re.compile(r"^[A-Za-z0-9_.:@/-]+$")
# tool_output：工具返回值载体（M2 协议扩展；结构=meta 区工具名/调用号 +
# body 区返回内容，注入嵌在返回内容里——InjecAgent 型结构映射，
# docs/research/m2-sft-sources.md §2.13）
# document：文档载体（S1/2026-09-30；PDF/Office 的结构层与行为层机械事实，
# 见 secfm/carriers/document_ser.py）。**注意**：image_metadata / av_metadata
# 是 v0.3-gen 的**未见载体留出集**，刻意不注册——一旦注册，任何生成器都能产出
# 这两类载体，泛化断言的留出性立即失效（reports/review-2026-09-30.md §4.4）。
_CARRIER_TYPES = {"email", "webpage", "code", "text", "log", "tool_output",
                  "document"}
_TRUST_LEVELS = {"untrusted", "internal", "trusted"}
_SECTION_NAMES = {"dom", "urls", "attachments", "headers"}


@dataclass
class CarrierBlock:
    """序列化载体。render() 产出上下文协议中的 <carrier> 块。

    sections      : body 前置具名区，如 ("dom", ...)（网页/HTML 邮件正文）
    body          : 主内容（纯文本正文 / 代码体）
    post_sections : body 后置区，如 ("urls", ...)（邮件 URL 汇总）
    """

    ctype: str
    trust: str = "untrusted"
    cid: str = "c1"
    meta_lines: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    body: object = None
    post_sections: list = field(default_factory=list)
    version: str = "ser/0.1"

    def __post_init__(self):
        for v in (self.ctype, self.trust, self.cid):
            if not isinstance(v, str) or not _SAFE_ATTR.match(v):
                raise ValueError(f"unsafe carrier attribute value: {v!r}")
        if self.ctype not in _CARRIER_TYPES:
            raise ValueError(f"unknown carrier type: {self.ctype}")
        if self.trust not in _TRUST_LEVELS:
            raise ValueError(f"unknown trust level: {self.trust}")
        for name, _ in list(self.sections) + list(self.post_sections):
            if name not in _SECTION_NAMES:
                raise ValueError(f"reserved section names only, got: {name!r}")

    def render(self) -> str:
        out = [f'<carrier type="{self.ctype}" trust="{self.trust}" id="{self.cid}">']
        if self.meta_lines:
            out.append("<meta>")
            out.extend(escape_region_markers(str(line)) for line in self.meta_lines)
            out.append("</meta>")
        for name, content in self.sections:
            out.append(f"<{name}>")
            out.append(escape_region_markers(content))
            out.append(f"</{name}>")
        if self.body is not None:
            out.append("<body>")
            out.append(escape_region_markers(self.body))
            out.append("</body>")
        for name, content in self.post_sections:
            out.append(f"<{name}>")
            out.append(escape_region_markers(content))
            out.append(f"</{name}>")
        out.append("</carrier>")
        return "\n".join(out)
