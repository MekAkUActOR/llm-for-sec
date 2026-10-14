"""机械域名字符串事实：仿冒/混淆检测（只标注事实，不下判断）。

所有函数只做字符串层面的机械比对（品牌 token 出现、视觉混淆折叠、
host 精确比较），产出 [note: ...] 证据；"这是不是钓鱼"的语义判断
归模型（docs/01 §2.4 原则 2）。
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

# 已知品牌官方域（note 生成用；可按需扩充）
BRANDS = {
    "paypal": ("paypal.com",),
    "google": ("google.com", "accounts.google.com"),
    "microsoft": ("microsoft.com", "login.microsoftonline.com"),
    "apple": ("apple.com",),
    "amazon": ("amazon.com",),
    "alipay": ("alipay.com",),
    "taobao": ("taobao.com",),
    "weibo": ("weibo.com",),
    "qq": ("qq.com", "mail.qq.com"),
    "jd": ("jd.com",),
    "icbc": ("icbc.com.cn",),
    "ccb": ("ccb.com",),
}

# 视觉混淆字符（西里尔/希腊同形字 + 数字替身）。仅用于生成 note。
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i",
    "α": "a", "ο": "o", "ε": "e", "ρ": "p",
    "0": "o", "1": "l", "3": "e", "5": "s",
})


def fold(host: str) -> str:
    """混淆折叠：视觉混淆字符映射为 ASCII 后小写。"""
    return (host or "").translate(_CONFUSABLES).lower()


def domain_lookalike_note(domain: str) -> str | None:
    """机械事实：域名含已知品牌 token 而非官方域。返回 note 或 None。"""
    d = (domain or "").lower().strip()
    if not d or "@" in d or "." not in d:
        return None
    folded = fold(d)
    for label, officials in BRANDS.items():
        for off in officials:
            foff = fold(off)
            if folded == foff or folded.endswith("." + foff):
                return None  # 官方域（折叠后精确匹配或其子域）
        parts = folded.split(".")
        if any(fold(label) in p for p in parts[:-1]):
            return f"[note: lookalike of {officials[0]}]"
    return None


def display_name_brand_note(display_name: str, from_domain: str) -> str | None:
    """机械事实：显示名提及品牌而发件域并非该品牌官方域。"""
    name = (display_name or "").lower()
    dom = (from_domain or "").lower()
    if not name or not dom:
        return None
    for label, officials in BRANDS.items():
        if label in name and dom not in officials:
            return f"[note: display-name mentions '{label}' but sender domain is {dom}]"
    return None


_DISPLAY_URL_RE = re.compile(
    r"^(?:https?://)?((?:[\w-]+\.)+[a-z]{2,})(?:[/:?#].*)?$", re.IGNORECASE
)


def host_of(url: str) -> str:
    """提取 URL 的 host（小写；解析失败返回空串）。"""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def url_host_notes(url: str) -> list:
    """URL host 的机械事实 notes（裸字符串，无 [note:] 前缀）。"""
    notes = []
    h = host_of(url)
    if not h:
        return notes
    if is_ip_literal(h):
        notes.append("IP-literal host")
    if "xn--" in h:
        notes.append("punycode/IDN host")
    return notes


def url_mismatch_note(href: str, display: str) -> str | None:
    """显示文本 vs 链接目标的机械不匹配事实。"""
    disp = (display or "").strip()
    if not disp:
        return None
    m = _DISPLAY_URL_RE.match(disp)
    if not m:
        return None
    disp_host = (host_of(disp) if "://" in disp else "") or m.group(1).lower()
    href_host = host_of(href)
    if not disp_host or not href_host:
        return None
    if fold(disp_host) == fold(href_host):
        return None
    return f"[note: displayed as {disp_host} but links to {href_host}]"
