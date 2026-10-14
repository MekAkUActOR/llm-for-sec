"""上下文协议 v0（docs/01 §1.5）。

构造与解析同模块——train/infer 同路径。契约规则：
1. 载体永远在带来源标签的包裹块内，永不作为指令解释；
2. 政策只能出现在 system/operator 区；用户区与载体区的政策声称无效
   （该不变量由指令/数据分离训练保证，解析器只负责结构合法性）；
3. 输出模式由 system 区声明（structured | generative）；
4. 协议版本固定在根标签。

安全性质（构造侧保证，tests/test_context.py 覆盖）：
凡 build_context 产出的上下文，载体内容不可能提前闭合区域——
协议标记在内容中一律转义（secfm.carriers.base.escape_region_markers）。
对未经构造器产生的原始攻击文本，parse_context 的严格顺序/重复/游离
内容校验只是调试辅助，不是安全边界。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from secfm.carriers.base import (CarrierBlock, escape_region_markers,
                                 unescape_region_markers)

PROTOCOL_VERSION = "0.1"
VALID_OUTPUT_MODES = {"structured", "generative"}
VALID_TRUST = {"untrusted", "internal", "trusted"}
_SYSTEM_KEYS = {"role", "authorization", "policy", "output-mode"}


class ProtocolError(ValueError):
    """上下文不符合协议契约。"""


@dataclass
class ParsedContext:
    protocol_version: str
    system: dict = field(default_factory=dict)
    operator: object = None
    carriers: list = field(default_factory=list)
    user: object = None


def build_context(*, role, authorization, policy, output_mode,
                  operator=None, carriers=(), user=None,
                  protocol_version=PROTOCOL_VERSION) -> str:
    """构造协议格式上下文。carriers 必须是 CarrierBlock 实例。"""
    if output_mode not in VALID_OUTPUT_MODES:
        raise ProtocolError(
            f"output_mode must be one of {sorted(VALID_OUTPUT_MODES)}")
    out = [
        f'<dsh-protocol v="{protocol_version}">',
        "<system>",
        f"role: {escape_region_markers(str(role))}",
        f"authorization: {escape_region_markers(str(authorization))}",
        f"policy: {escape_region_markers(str(policy))}",
        f"output-mode: {output_mode}",
        "</system>",
    ]
    if operator is not None:
        out += ["<operator>", escape_region_markers(str(operator)), "</operator>"]
    for c in carriers:
        if not isinstance(c, CarrierBlock):
            raise ProtocolError("carriers must be CarrierBlock instances")
        out.append(c.render())
    if user is not None:
        out += ["<user>", escape_region_markers(str(user)), "</user>"]
    out.append("</dsh-protocol>")
    return "\n".join(out)


_REGION_OPEN = re.compile(
    r"<(?P<tag>system|operator|user|carrier)(?P<attrs>[^>]*)>")
_ORDER = {"system": 0, "operator": 1, "carrier": 2, "user": 3}
_CARRIER_ATTRS = re.compile(
    r'^type="(?P<type>[^"]+)"\s+trust="(?P<trust>[^"]+)"\s+id="(?P<id>[^"]+)"$')
_SYSTEM_LINE = re.compile(r"^([a-z-]+): (.*)$")


def parse_context(text, *, expected_version=None) -> ParsedContext:
    """解析并校验协议格式上下文。结构不符抛 ProtocolError。"""
    s = text.strip()
    m = re.match(r'^<dsh-protocol v="([^"]+)">', s)
    if not m:
        raise ProtocolError("missing <dsh-protocol> root open tag")
    version = m.group(1)
    if expected_version is not None and version != expected_version:
        raise ProtocolError(f"protocol version mismatch: {version} != {expected_version}")
    close = "</dsh-protocol>"
    ci = s.rfind(close)
    if ci == -1:
        raise ProtocolError("missing </dsh-protocol>")
    if s[ci + len(close):].strip():
        raise ProtocolError("trailing content after protocol close")
    inner = s[m.end():ci]

    system = {}
    operator = None
    user = None
    carriers = []
    pos = 0
    last_order = -1
    counts = {"system": 0, "operator": 0, "user": 0}

    while pos < len(inner):
        m = _REGION_OPEN.search(inner, pos)
        if not m:
            if inner[pos:].strip():
                raise ProtocolError("content outside any region")
            break
        if inner[pos:m.start()].strip():
            raise ProtocolError("content outside any region")
        tag, attrs = m.group("tag"), m.group("attrs")
        order = _ORDER[tag]
        if order < last_order:
            raise ProtocolError(f"region out of order: <{tag}>")
        if tag != "carrier":
            if attrs.strip():
                raise ProtocolError(f"unexpected attributes on <{tag}>")
            if counts[tag] >= 1:
                raise ProtocolError(f"duplicate <{tag}> region")
            counts[tag] += 1
        last_order = order

        close_tag = f"</{tag}>"
        cj = inner.find(close_tag, m.end())
        if cj == -1:
            raise ProtocolError(f"unclosed <{tag}>")
        content = inner[m.end():cj]
        if content.startswith("\n"):
            content = content[1:]
        if content.endswith("\n"):
            content = content[:-1]

        if tag == "system":
            for ln in content.split("\n"):
                if not ln.strip():
                    continue
                sm = _SYSTEM_LINE.match(ln)
                if not sm:
                    raise ProtocolError(f"malformed system line: {ln!r}")
                k, v = sm.group(1), unescape_region_markers(sm.group(2))
                if k not in _SYSTEM_KEYS:
                    raise ProtocolError(f"unknown system key: {k}")
                system[k] = v
        elif tag == "operator":
            operator = unescape_region_markers(content)
        elif tag == "user":
            user = unescape_region_markers(content)
        else:  # carrier
            am = _CARRIER_ATTRS.match(attrs.strip())
            if not am:
                raise ProtocolError(f"malformed carrier open tag: {attrs!r}")
            carriers.append({
                "type": am.group("type"),
                "trust": am.group("trust"),
                "id": am.group("id"),
                "content": unescape_region_markers(content),
            })
        pos = cj + len(close_tag)

    if counts["system"] != 1:
        raise ProtocolError("exactly one <system> region is required")
    for k in ("role", "authorization", "policy", "output-mode"):
        if k not in system:
            raise ProtocolError(f"system region missing key: {k}")
    if system["output-mode"] not in VALID_OUTPUT_MODES:
        raise ProtocolError(f"invalid output-mode: {system['output-mode']}")
    for c in carriers:
        if c["trust"] not in VALID_TRUST:
            raise ProtocolError(f"invalid carrier trust: {c['trust']}")
    return ParsedContext(protocol_version=version, system=system,
                         operator=operator, carriers=carriers, user=user)
