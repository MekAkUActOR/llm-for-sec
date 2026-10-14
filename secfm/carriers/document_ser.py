# -*- coding: utf-8 -*-
"""文档载体序列化（PDF/Office/宏/嵌入对象；docs/00 §3 结构层+行为层）。

五栖居处中的**结构层与行为层**是本载体的主战场（docs/00 §3 推论 1：
"载荷常居语义之外"）：

- 结构层（机械事实）：页面/部件树、层与工作表的可见性、被隐藏的文本
  （同色/极小字号/离屏/零宽与双向控制字符）、宏流存在性、OLE/嵌入对象、
  包（package）声明类型、自定义 XML 部件、注释/修订痕迹；
- 行为层（机械事实）：打开时自动执行标志、外链/远程模板拉取、
  外部 OLE 刷新、字段（DDE）指令来源、注解动作、脚本/XFA 存在性；
- 元数据/来源：生产者/创建者/时间戳、增量更新轮数、签名覆盖、
  加密与权限位、`%%EOF` 之后残留字节；
- 语义：抽取出的文本层（显式截断；抽取不到文本层时明确标注）。

设计原则（与 html_ser/email_ser 一致）：
1. **只标注机械事实，不做安全判断**——不出 "malicious/suspicious/risk"
   一类结论词；"这是不是恶意文档"的判断归模型；
2. 不静默丢弃证据：隐藏文本、零宽字符、宏流、嵌入对象全部保留并标注；
3. 截断必须显式（`…[truncated N chars]`），永不静默。

输入是**结构化 dict**（解析器给出的机械事实），不是原始二进制：本模块
不做 PDF/OLE 解析，只做"事实 -> 可读文本"的确定性序列化，因此
train/infer 同路径且可单测。

区域名容纳（secfm/carriers/base.py `_SECTION_NAMES`）：`dom`=页面/部件
对象树（与网页 DOM 同位的结构面）；`attachments`=宏流/OLE/嵌入文件/包；
`urls`=外部引用汇总。若将来需要更细的区名，需另行扩 `_SECTION_NAMES`。

注：`CarrierBlock` 的 ctype 白名单 `_CARRIER_TYPES` 需加入 `"document"`
（`secfm/carriers/base.py` 第 60 行）。本模块在未打该补丁时**显式降级
构造**（复刻 trust/cid/区名校验，仅跳过 ctype 白名单），渲染结果与打补丁
后逐字一致；打补丁后自动走完整校验路径。
"""

from __future__ import annotations

from .base import (CarrierBlock, _CARRIER_TYPES, _SAFE_ATTR, _SECTION_NAMES,
                   _TRUST_LEVELS)
from .lookalike import url_host_notes

DOCUMENT_CTYPE = "document"

# 不可见字符（结构层隐藏信息的机械载体）
_ZERO_WIDTH = {
    0x200B: "ZWSP", 0x200C: "ZWNJ", 0x200D: "ZWJ", 0x2060: "WJ",
    0xFEFF: "ZWNBSP", 0x180E: "MVS",
}
_BIDI_CONTROL = {
    0x202A: "LRE", 0x202B: "RLE", 0x202C: "PDF", 0x202D: "LRO",
    0x202E: "RLO", 0x2066: "LRI", 0x2067: "RLI", 0x2068: "FSI",
    0x2069: "PDI",
}
_COLOR_NAMES = {"white": "#ffffff", "black": "#000000", "red": "#ff0000",
                "blue": "#0000ff", "yellow": "#ffff00", "transparent": None}


# --------------------------------------------------------------- 容忍取值 ---

def _clip(s, n=200, label="chars"):
    s = str(s)
    if len(s) <= n:
        return s
    return s[:n] + f"…[truncated {len(s) - n} {label}]"


def _oneline(v, n=200):
    """单行机械事实：折行/多空白折叠后再显式截断（None 保持 None=缺席）。"""
    if v is None:
        return None
    return _clip(" ".join(str(v).split()), n)


def _as_bool(v, default=None):
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on", "present"):
        return True
    if s in ("0", "false", "no", "n", "off", "absent", "none"):
        return False
    return default


def _flag(v):
    b = _as_bool(v)
    return None if b is None else ("yes" if b else "no")


def _as_int(v, default=None):
    try:
        if isinstance(v, bool):
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def _as_dicts(v):
    """容忍 None / 单个 dict / 畸形元素：只保留 dict 项，永不抛异常。"""
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    if isinstance(v, (list, tuple, set)):
        return [d for d in v if isinstance(d, dict)]
    return []


def _as_strs(v):
    if v is None:
        return []
    if isinstance(v, (str, bytes)):
        return [str(v)]
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if x is not None and str(x) != ""]
    return [str(v)]


def _as_text(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, str):
        return v
    return ""


def _norm_color(c):
    """颜色归一（仅字符串事实）：'#FFF'/'white' -> '#ffffff'；无法归一 -> None。"""
    if not isinstance(c, str):
        return None
    s = c.strip().lower()
    if s in _COLOR_NAMES:
        return _COLOR_NAMES[s]
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3 and all(ch in "0123456789abcdef" for ch in h):
            return "#" + "".join(ch * 2 for ch in h)
        if len(h) == 6 and all(ch in "0123456789abcdef" for ch in h):
            return "#" + h
    return None


# ----------------------------------------------------------- 构造（兼容） ---

def _assert_safe_attributes(kw):
    """复刻 base.CarrierBlock.__post_init__ 的校验（除 ctype 白名单）。"""
    for key in ("ctype", "trust", "cid"):
        v = kw.get(key)
        if not isinstance(v, str) or not _SAFE_ATTR.match(v):
            raise ValueError(f"unsafe carrier attribute value: {v!r}")
    if kw.get("trust") not in _TRUST_LEVELS:
        raise ValueError(f"unknown trust level: {kw.get('trust')}")
    for name, _ in list(kw.get("sections") or []) + \
            list(kw.get("post_sections") or []):
        if name not in _SECTION_NAMES:
            raise ValueError(f"reserved section names only, got: {name!r}")


def _build_block(**kw):
    """构造 CarrierBlock。

    base.py 已把 "document" 加入 `_CARRIER_TYPES` 时走完整校验构造；
    未打补丁时显式降级（仅跳过 ctype 白名单，其余校验逐条复刻），
    渲染输出与打补丁后逐字一致——见模块 docstring 的补丁说明。
    """
    kw.setdefault("ctype", DOCUMENT_CTYPE)
    if kw["ctype"] in _CARRIER_TYPES:
        return CarrierBlock(**kw)
    if kw["ctype"] != DOCUMENT_CTYPE:
        # 别的未知 ctype 不做降级：保持 base 的严格语义
        raise ValueError(f"unknown carrier type: {kw['ctype']}")
    _assert_safe_attributes(kw)
    blk = CarrierBlock.__new__(CarrierBlock)
    blk.ctype = kw["ctype"]
    blk.trust = kw.get("trust", "untrusted")
    blk.cid = kw.get("cid", "c1")
    blk.meta_lines = list(kw.get("meta_lines") or [])
    blk.sections = list(kw.get("sections") or [])
    blk.body = kw.get("body")
    blk.post_sections = list(kw.get("post_sections") or [])
    blk.version = kw.get("version", "ser/0.1")
    return blk


# ------------------------------------------------------------- meta 机械 ---

def _meta_lines(facts, inv):
    f = facts
    meta = []

    def add(label, value):
        if value is not None and value != "" and value != []:
            meta.append(f"{label}: {value}")

    add("filename", _oneline(f.get("filename") or f.get("name"), 120))
    add("declared-type", _oneline(f.get("declared_type"), 80))
    add("detected-container", _oneline(
        f.get("detected_type") or f.get("container") or f.get("format"), 80))
    if f.get("declared_type") and (f.get("detected_type") or f.get("container")):
        dec = _oneline(f.get("declared_type"), 80).lower()
        det = _oneline(f.get("detected_type") or f.get("container"), 80).lower()
        if dec and det and dec != det:
            meta.append(f"   [note: declared {dec} but container is {det}]")
    add("size-bytes", _as_int(f.get("size_bytes") or f.get("size")))
    add("pdf-version", _oneline(f.get("pdf_version"), 20))
    add("pages", _as_int(f.get("page_count") or f.get("pages_count")))
    add("parts", _as_int(f.get("part_count")))
    add("producer", _oneline(f.get("producer"), 120))
    add("creator", _oneline(f.get("creator") or f.get("application"), 120))
    add("author", _oneline(f.get("author"), 120))
    add("title", _oneline(f.get("title"), 120))
    add("created", _oneline(f.get("created") or f.get("creation_date"), 60))
    add("modified", _oneline(f.get("modified") or f.get("mod_date"), 60))
    cust = _as_strs(f.get("custom_metadata_keys") or f.get("custom_keys"))
    if cust:
        add("custom-metadata-keys",
            "%s (%d total)" % (", ".join(_oneline(c, 40) for c in cust[:8]),
                               len(cust)))
    add("incremental-updates", _as_int(f.get("incremental_updates")))
    add("revision-marks", _as_int(f.get("revision_count")))
    add("trailing-bytes-after-eof",
        _as_int(f.get("trailing_bytes_after_eof")))
    add("xref", _oneline(f.get("xref") or f.get("xref_style"), 40))

    enc = _as_bool(f.get("encrypted"))
    if enc is not None:
        line = f"encrypted: {'yes' if enc else 'no'}"
        if enc:
            bits = []
            if f.get("encryption_algorithm"):
                bits.append(_oneline(f["encryption_algorithm"], 60))
            if _as_int(f.get("key_bits")):
                bits.append("%d-bit key" % _as_int(f["key_bits"]))
            perms = _as_strs(f.get("permissions"))
            if perms:
                bits.append("permissions: " + ", ".join(
                    _oneline(p, 24) for p in perms[:8]))
            if bits:
                line += " (" + "; ".join(bits) + ")"
        meta.append(line)

    sigs = _as_dicts(f.get("signatures"))
    if sigs or _as_bool(f.get("digital_signature")) is not None:
        by = ", ".join(
            "%s[coverage: %s]" % (_oneline(s.get("signer") or "signer?", 60),
                                  _oneline(s.get("coverage") or "unspecified", 40))
            for s in sigs[:4]) or "none"
        meta.append(f"signatures: {len(sigs)} ({by}); validity: not-checked"
                    "   [mechanical: signature bytes not verified by serializer]")

    fonts = _as_strs(f.get("fonts"))
    if isinstance(f.get("fonts"), (list, tuple)) and \
            _as_dicts(f.get("fonts")):
        fonts = []  # dict 形态的字体描述走 font_details（见下）
    if fonts:
        meta.append("fonts: " + ", ".join(_oneline(x, 60) for x in fonts[:10])
                    + (" (%d total)" % len(fonts) if len(fonts) > 10 else ""))
    for fd in (_as_dicts(f.get("font_details")) or _as_dicts(f.get("fonts")))[:10]:
        flags = []
        if _as_bool(fd.get("embedded")) is not None:
            flags.append("embedded" if _as_bool(fd["embedded"])
                         else "not-embedded")
        if _as_bool(fd.get("subset")) is not None:
            flags.append("subset" if _as_bool(fd["subset"]) else "full-set")
        meta.append("font: %s (%s)" % (_oneline(fd.get("name") or "?", 60),
                                       ", ".join(flags) or "flags: unspecified"))

    macros = _as_dicts(f.get("macros"))
    if macros:
        auto = []
        for m in macros:
            flag = m.get("autoexec_flag")
            if flag is None:
                flag = m.get("autoexec")
            if _as_bool(flag):
                auto.append(_oneline(m.get("name") or "stream?", 40))
        meta.append("macros: %d stream(s); autoexec-flags: %s"
                    % (len(macros), ", ".join(auto) if auto
                       else "none-declared"))
    elif _as_bool(f.get("macro_present")) is not None:
        meta.append("macros: %s" % _flag(f.get("macro_present")))
    else:
        meta.append("macros: none-declared")

    js = _as_dicts(f.get("javascript"))
    if js:
        names = ", ".join(_oneline(j.get("name") or j.get("trigger") or "?",
                                   40) for j in js[:6])
        meta.append("javascript: %d entr(ies) (%s); triggers: %s"
                    % (len(js), names,
                       ", ".join(sorted({_oneline(j.get("trigger"), 40)
                                         for j in js
                                         if j.get("trigger")})) or "unspecified"))
    else:
        b = _as_bool(f.get("javascript_present") or f.get("js_present"))
        meta.append("javascript: %s" % ("present" if b else "absent")
                    if b is not None else "javascript: none-declared")

    b = _as_bool(f.get("xfa_present") or f.get("xfa"))
    if b is not None:
        meta.append("xfa: %s" % ("present" if b else "absent"))

    ole = _as_dicts(f.get("ole_objects"))
    emb = _as_dicts(f.get("embedded_objects")) + _as_dicts(
        f.get("embedded_files"))
    if ole or emb:
        assigns = [d for d in ole + emb if _as_bool(d.get("external"))]
        meta.append("embedded-objects: %d (external-link: %d)"
                    % (len(ole) + len(emb), len(assigns)))

    refs = _external_refs(f)
    if refs:
        meta.append("external-references: %d" % len(refs))
    rt = _as_strs(f.get("remote_template") or f.get("attached_template"))
    if rt:
        meta.append("remote-template: " + _oneline(rt[0], 200))

    fields = _as_dicts(f.get("fields"))
    if fields:
        dde = [x for x in fields if "dde" in str(x.get("instruction_source",
                                                        "")).lower()
               or _as_bool(x.get("dde"))]
        line = "form-fields: %d" % len(fields)
        if dde:
            line += ("; instruction-source: DDE on %d field(s)" % len(dde))
        meta.append(line)

    hidden = _as_dicts(f.get("hidden_text"))
    if hidden:
        kinds = sorted({_oneline(h.get("kind") or h.get("type") or "unspecified",
                                 40) for h in hidden})
        meta.append("hidden-text-runs: %d (kinds: %s)"
                    % (len(hidden), ", ".join(kinds)))
    notes = _as_dicts(f.get("annotations"))
    if notes:
        meta.append("annotations: %d" % len(notes))
    if inv["total"]:
        meta.append("invisible-chars: zero-width=%d, bidi-controls=%d"
                    % (inv["zero_width_total"], inv["bidi_total"]))
    if _as_bool(f.get("text_layer")) is False:
        meta.append("text-layer: absent   [mechanical: no extractable text]")
    return meta


# --------------------------------------------------------------- 各区域 ---

def _layer_line(ly):
    items = ["name: %s" % _oneline(ly.get("name") or "?", 60)]
    vis = ly.get("visibility")
    if vis is None:
        vis = ly.get("visible")
    b = _as_bool(vis)
    if b is not None:
        items.append("visibility: %s" % ("hidden" if b is False else "visible"))
    elif vis is not None:
        items.append("visibility: %s" % _oneline(vis, 40))
    return "layer [%s]" % "] [".join(items)


def _structure_lines(facts):
    """dom 区：页面/部件对象树（只列非文本节点，文本走 body）。"""
    lines = []
    head = []
    if facts.get("detected_type") or facts.get("container"):
        head.append("container: %s" % _oneline(
            facts.get("detected_type") or facts.get("container"), 60))
    pc = _as_int(facts.get("page_count") or facts.get("pages_count"))
    if pc is not None:
        head.append("pages: %d" % pc)
    pt = _as_int(facts.get("part_count"))
    if pt is not None:
        head.append("parts: %d" % pt)
    lines.append("document" + ("" if not head else " [" + "] [".join(head) + "]"))

    for i, pg in enumerate(_as_dicts(facts.get("pages")), start=1):
        num = _as_int(pg.get("page"), i) or i
        tags = []
        if pg.get("size"):
            tags.append("size: %s" % _oneline(pg["size"], 40))
        if _as_int(pg.get("rotation")) is not None:
            tags.append("rotation: %d" % _as_int(pg["rotation"]))
        if _as_int(pg.get("text_runs")) is not None:
            tags.append("text-runs: %d" % _as_int(pg["text_runs"]))
        lines.append("  page %d%s" % (num, "" if not tags
                                      else " [" + "] [".join(tags) + "]"))
        for a in _as_dicts(pg.get("annotations")):
            items = []
            if a.get("subtype") or a.get("type"):
                items.append("subtype: %s" % _oneline(
                    a.get("subtype") or a.get("type"), 40))
            if a.get("action"):
                items.append("action: %s" % _oneline(a["action"], 40))
            if a.get("target"):
                items.append("target: %s" % _oneline(a["target"], 200))
            if a.get("field"):
                items.append("field: %s" % _oneline(a["field"], 60))
            lines.append("    annotation [%s]" % "] [".join(items))
        for ly in _as_dicts(pg.get("layers")):
            lines.append("    " + _layer_line(ly))

    for ly in _as_dicts(facts.get("layers")):
        lines.append("  " + _layer_line(ly))

    for p in _as_dicts(facts.get("parts")):
        items = []
        if p.get("name"):
            items.append("name: %s" % _oneline(p["name"], 120))
        if _as_int(p.get("size") or p.get("size_bytes")) is not None:
            items.append("size: %d" % _as_int(p.get("size") or p.get("size_bytes")))
        if p.get("content_type") or p.get("declared_type"):
            items.append("declared-type: %s" % _oneline(
                p.get("content_type") or p.get("declared_type"), 80))
        lines.append("  part [%s]" % "] [".join(items))

    for w in _as_dicts(facts.get("worksheets")):
        items = ["name: %s" % _oneline(w.get("name") or "?", 60)]
        vis = w.get("visibility")
        if vis is not None:
            items.append("visibility: %s" % _oneline(vis, 40))
        if _as_int(w.get("cells") or w.get("used_cells")) is not None:
            items.append("cells: %d" % _as_int(w.get("cells")
                                               or w.get("used_cells")))
        if _as_bool(w.get("protected")) is not None:
            items.append("protection: %s" % _flag(w.get("protected")))
        lines.append("  worksheet [%s]" % "] [".join(items))

    for d in _as_dicts(facts.get("defined_names")):
        items = ["name: %s" % _oneline(d.get("name") or "?", 60)]
        if d.get("refers_to"):
            items.append("refers-to: %s" % _oneline(d["refers_to"], 120))
        if _as_bool(d.get("hidden")) is not None:
            items.append("hidden: %s" % _flag(d["hidden"]))
        lines.append("  defined-name [%s]" % "] [".join(items))

    for x in _as_dicts(facts.get("custom_xml_parts")):
        lines.append("  custom-xml-part [name: %s]"
                     % _oneline(x.get("name") or "?", 120))
    for rel in _as_dicts(facts.get("relationships")):
        items = []
        for key in ("id", "type", "target", "target_mode"):
            if rel.get(key):
                items.append("%s: %s" % (key, _oneline(rel[key], 160)))
        lines.append("  relationship [%s]" % "] [".join(items))

    ff = _as_dicts(facts.get("fields"))
    if ff:
        lines.append("  form [fields: %d]" % len(ff))
        for fd in ff:
            items = ["name: %s" % _oneline(fd.get("name") or "?", 60)]
            if fd.get("type"):
                items.append("type: %s" % _oneline(fd["type"], 40))
            if fd.get("instruction_source"):
                items.append("instruction-source: %s"
                             % _oneline(fd["instruction_source"], 40))
            if _as_bool(fd.get("required")) is not None:
                items.append("required: %s" % _flag(fd["required"]))
            lines.append("    field [%s]" % "] [".join(items))

    for key, label in (("bookmarks", "outline-entries"),
                       ("comments", "comments"),
                       ("tracked_changes", "tracked-changes"),
                       ("signatures", "signature-fields")):
        items = _as_dicts(facts.get(key))
        if items:
            lines.append("  %s [count: %d]" % (label, len(items)))
        elif _as_int(facts.get(key)) is not None:
            lines.append("  %s [count: %d]" % (label, _as_int(facts.get(key))))
    return lines


def _embedded_lines(facts):
    """attachments 区：宏流/嵌入对象/嵌入文件/包（结构层+行为层事实）。"""
    lines = []
    for i, m in enumerate(_as_dicts(facts.get("macros")), start=1):
        items = ["name: %s" % _oneline(m.get("name") or "stream?", 60)]
        if _as_int(m.get("size") or m.get("size_bytes")) is not None:
            items.append("size: %d bytes" % _as_int(m.get("size")
                                                    or m.get("size_bytes")))
        trig = _as_strs(m.get("triggers") or m.get("trigger"))
        if trig:
            items.append("trigger: " + ", ".join(_oneline(t, 40)
                                                 for t in trig[:6]))
        auto = m.get("autoexec_flag")
        if auto is None:
            auto = m.get("autoexec")
        if auto is not None:
            items.append("autoexec: %s" % _flag(auto))
        if m.get("signature") or _as_bool(m.get("signed")) is not None:
            sig = m.get("signature") or ("signed" if _as_bool(m["signed"])
                                         else "none")
            items.append("signature: %s" % _oneline(sig, 40))
        if _as_bool(m.get("obfuscated_stream")) is not None:
            items.append("stream-encoding: %s"
                         % ("non-plain" if _as_bool(m["obfuscated_stream"])
                            else "plain"))
        lines.append("macro-stream [%d] [%s]" % (i, "] [".join(items)))
        lines.append("  body: withheld by serializer "
                     "   [mechanical: macro source text not serialized]")

    objs = _as_dicts(facts.get("ole_objects")) + _as_dicts(
        facts.get("embedded_objects"))
    for i, o in enumerate(objs, start=1):
        items = ["kind: %s" % _oneline(o.get("kind") or "ole-object", 40)]
        if o.get("name"):
            items.append("name: %s" % _oneline(o["name"], 120))
        if o.get("declared_type") or o.get("content_type"):
            items.append("declared-type: %s" % _oneline(
                o.get("declared_type") or o.get("content_type"), 80))
        if o.get("detected_type") or o.get("container"):
            items.append("detected-type: %s" % _oneline(
                o.get("detected_type") or o.get("container"), 80))
        if o.get("class_id") or o.get("prog_id"):
            items.append("class: %s" % _oneline(o.get("class_id")
                                                or o.get("prog_id"), 80))
        if _as_int(o.get("size") or o.get("size_bytes")) is not None:
            items.append("size: %d bytes" % _as_int(o.get("size")
                                                    or o.get("size_bytes")))
        if _as_bool(o.get("package")) is not None:
            items.append("package: %s" % _flag(o["package"]))
        if _as_bool(o.get("external")) is not None:
            items.append("external: %s" % _flag(o["external"]))
        if o.get("target"):
            items.append("target: %s" % _oneline(o["target"], 200))
        if o.get("flags"):
            items.append("flags: %s" % _oneline(o["flags"], 60))
        lines.append("embedded-object [%d] [%s]" % (i, "] [".join(items)))

    for i, e in enumerate(_as_dicts(facts.get("embedded_files")), start=1):
        items = ["name: %s" % _oneline(e.get("name") or "?", 120)]
        if e.get("declared_type") or e.get("content_type"):
            items.append("declared-type: %s" % _oneline(
                e.get("declared_type") or e.get("content_type"), 80))
        if _as_int(e.get("size") or e.get("size_bytes")) is not None:
            items.append("size: %d bytes" % _as_int(e.get("size")
                                                    or e.get("size_bytes")))
        if e.get("flags"):
            items.append("flags: %s" % _oneline(e["flags"], 60))
        lines.append("embedded-file [%d] [%s]" % (i, "] [".join(items)))

    for i, x in enumerate(_as_dicts(facts.get("javascript")), start=1):
        items = ["name: %s" % _oneline(x.get("name") or x.get("id") or "?", 60)]
        if x.get("trigger"):
            items.append("trigger: %s" % _oneline(x["trigger"], 40))
        if _as_int(x.get("size") or x.get("size_bytes")) is not None:
            items.append("size: %d bytes" % _as_int(x.get("size")
                                                    or x.get("size_bytes")))
        lines.append("script-entry [%d] [%s]" % (i, "] [".join(items)))
    return lines


def _external_refs(facts):
    """外部引用的机械汇总（兼容多种输入键名与标量/字典混合形态）。"""
    refs = []
    for key in ("external_references", "external_links", "urls"):
        v = facts.get(key)
        if isinstance(v, dict):
            refs.append(dict(v))
        elif isinstance(v, (list, tuple, set)):
            for item in v:
                if isinstance(item, dict):
                    refs.append(dict(item))
                elif item is not None and str(item) != "":
                    refs.append({"target": str(item)})
        elif isinstance(v, (str, bytes)) and str(v) != "":
            refs.append({"target": str(v)})
    refs += _as_dicts(facts.get("external_reference_details"))
    for t in _as_strs(facts.get("remote_template")
                      or facts.get("attached_template")):
        refs.append({"target": t, "kind": "remote-template",
                     "accessed_on": "open"})
    refs += [dict(r) for r in _as_dicts(facts.get("relationships"))
             if str(r.get("target_mode", "")).lower() == "external"
             and r.get("target")]
    refs += [o for o in _as_dicts(facts.get("ole_objects"))
             if _as_bool(o.get("external")) and o.get("target")]
    return refs


def _external_lines(refs):
    lines = []
    seen = set()
    for r in refs:
        target = _oneline(r.get("target") or r.get("url"), 300)
        if not target or target in seen:
            continue
        seen.add(target)
        line = "[%d] %s" % (len(lines) + 1, target)
        if r.get("kind") or r.get("rel_type"):
            line += " [kind: %s]" % _oneline(r.get("kind")
                                             or r.get("rel_type"), 60)
        if r.get("accessed_on") or r.get("trigger"):
            line += " [accessed-on: %s]" % _oneline(
                r.get("accessed_on") or r.get("trigger"), 40)
        if r.get("refresh"):
            line += " [refresh: %s]" % _oneline(r["refresh"], 40)
        for note in url_host_notes(str(r.get("target") or r.get("url") or "")):
            line += " [note: %s]" % note
        lines.append(line)
    return lines


# ---------------------------------------------------- 不可见字符 / 隐藏文本 ---

def _invisible_report(text, max_contexts=8):
    """零宽/双向控制字符的机械计数 + 邻接上下文（不静默丢弃）。"""
    counts = {}
    bidi = {}
    contexts = []
    invisible = set(_ZERO_WIDTH) | set(_BIDI_CONTROL)
    n = len(text)
    for i, ch in enumerate(text):
        cp = ord(ch)
        tabel, store = ((_ZERO_WIDTH, counts) if cp in _ZERO_WIDTH
                        else ((_BIDI_CONTROL, bidi)
                              if cp in _BIDI_CONTROL else (None, None)))
        if tabel is None:
            continue
        store[cp] = store.get(cp, 0) + 1
        if len(contexts) < max_contexts:
            j, k = i, i + 1
            while j > 0 and ord(text[j - 1]) in invisible:
                j -= 1
            while k < n and ord(text[k]) in invisible:
                k += 1
            before = " ".join(text[max(0, j - 24):j].split())
            after = " ".join(text[k:k + 24].split())
            contexts.append(
                "[invisible #%d] U+%04X %s between %r and %r"
                % (len(contexts) + 1, cp, tabel[cp], before[-24:], after[:24]))
    inv = {
        "zero_width": counts,
        "bidi": bidi,
        "zero_width_total": sum(counts.values()),
        "bidi_total": sum(bidi.values()),
        "total": sum(counts.values()) + sum(bidi.values()),
        "contexts": contexts,
    }
    return inv


def _hidden_lines(hidden, background):
    lines = []
    for i, h in enumerate(hidden, start=1):
        items = ["kind: %s" % _oneline(h.get("kind") or h.get("type")
                                       or "unspecified", 40)]
        if h.get("page") is not None:
            items.append("page: %s" % _oneline(h["page"], 20))
        if h.get("color"):
            items.append("color: %s" % _oneline(h["color"], 40))
        if h.get("font") or h.get("font_name"):
            items.append("font: %s" % _oneline(h.get("font")
                                               or h.get("font_name"), 60))
        if h.get("font_size") is not None:
            items.append("font-size: %s" % _oneline(h["font_size"], 20))
        if h.get("visibility"):
            items.append("visibility: %s" % _oneline(h["visibility"], 40))
        line = "[hidden-run #%d] [%s]" % (i, "] [".join(items))
        bg = _norm_color(h.get("background") or background)
        fg = _norm_color(h.get("color"))
        if fg and bg and fg == bg:
            line += " [note: color equals background]"
        elif (fg == "#ffffff" and not bg
              and _as_bool(h.get("on_white")) is True):
            line += " [note: color equals background]"
        lines.append(line)
        text = _as_text(h.get("text"))
        if text:
            lines.append("  text: %s" % _clip(" ".join(text.split()), 600))
    return lines


def _document_body(facts, text_limit, max_zw_contexts):
    text = _as_text(facts.get("text"))
    if not text:
        parts = []
        for p in _as_dicts(facts.get("pages")):
            t = _as_text(p.get("text"))
            if t:
                parts.append(t)
        text = "\n".join(parts)
    inv = _invisible_report(text, max_zw_contexts)
    hidden = _as_dicts(facts.get("hidden_text"))
    lines = []
    if text:
        body = text
        if len(body) > text_limit:
            body = body[:text_limit] + \
                f"\n[truncated: {len(body) - text_limit} chars omitted]"
        lines.append(body)
    if hidden:
        lines.append("")
        lines.append("[hidden text runs: %d]" % len(hidden))
        lines.extend(_hidden_lines(hidden, facts.get("page_background")))
    if inv["total"]:
        lines.append("")
        counts = ", ".join("U+%04X %s=%d" % (cp, _ZERO_WIDTH.get(cp)
                                             or _BIDI_CONTROL.get(cp, "?"), c)
                           for cp, c in sorted(inv["zero_width"].items()))
        bcounts = ", ".join("U+%04X %s=%d" % (cp, _BIDI_CONTROL.get(cp, "?"), c)
                            for cp, c in sorted(inv["bidi"].items()))
        lines.append("[invisible characters: zero-width=%d%s; bidi-controls=%d%s]"
                     % (inv["zero_width_total"],
                        " (" + counts + ")" if counts else "",
                        inv["bidi_total"],
                        " (" + bcounts + ")" if bcounts else ""))
        lines.extend(inv["contexts"])
    body = "\n".join(lines)
    if len(body) > text_limit + 4000:
        body = body[:text_limit + 4000] + \
            f"\n[truncated: {len(body) - text_limit - 4000} chars omitted]"
    return (body if body else None), inv


# ------------------------------------------------------------------ 入口 ---

def serialize_document(facts, *, cid="c1", trust="untrusted", max_lines=200,
                       text_limit=8000, max_zw_contexts=8):
    """文档机械事实 dict -> CarrierBlock（可直接进 build_context）。

    容忍空输入与畸形输入：None/[]/{}/{...字段类型错} 一律按"事实缺席"
    序列化，不抛异常（结构层缺项本身就是一条可读事实）。
    """
    if isinstance(facts, (str, bytes)):
        facts = {"text": _as_text(facts)}
    elif not isinstance(facts, dict):
        facts = {}

    body, inv = _document_body(facts, text_limit, max_zw_contexts)
    meta = _meta_lines(facts, inv)

    dom_lines = _structure_lines(facts)
    if len(dom_lines) > max_lines:
        dom_lines = dom_lines[:max_lines] + [
            f"[truncated: {len(dom_lines) - max_lines} more structure lines"
            " omitted]"]
    sections = [("dom", "\n".join(dom_lines))]

    attach_lines = _embedded_lines(facts)
    if len(attach_lines) > max_lines:
        attach_lines = attach_lines[:max_lines] + [
            f"[truncated: {len(attach_lines) - max_lines} more attachment lines"
            " omitted]"]
    post = []
    if attach_lines:
        post.append(("attachments", "\n".join(attach_lines)))
    refs = _external_refs(facts)
    url_lines = _external_lines(refs)
    if url_lines:
        post.append(("urls", "\n".join(url_lines)))

    return _build_block(ctype=DOCUMENT_CTYPE, cid=cid, trust=trust,
                        meta_lines=meta, sections=sections, body=body,
                        post_sections=post)


def attach_document_carrier(facts, *, cid="c1", trust="untrusted", **kwargs):
    """便捷入口（与其它载体同一形态）：返回待装配的 document CarrierBlock。

    用法::

        blk = attach_document_carrier(facts, cid="c1")
        ctx = build_context(role=..., authorization=..., policy=...,
                            output_mode="structured", carriers=[blk])

    与 :func:`serialize_document` 同路径（同一实现，无第二份渲染逻辑）。
    """
    return serialize_document(facts, cid=cid, trust=trust, **kwargs)
