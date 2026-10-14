# -*- coding: utf-8 -*-
"""P1.6 G1–G12 统一防污染门禁（纯 CPU，fail-closed）。

权威口径：reports/p1.6-calibration-design.md §6 门禁表；被检对象 =
data/dpo/p16-calibration/{p16_benign_release.jsonl, p16_malicious_honest.jsonl}
（由 scripts/build_p16_calibration.py 产出并冻结，sha256 见 manifest.json）。

门禁一览（§6）：
  G1  id 唯一 + p16 命名空间 + 与既有混料零重叠
  G2  schema 与 m4 逐字段兼容（system=冻结模板 / 轮次交替 / human 收尾 / gpt 分叉）
  G3  双侧 VERDICT 100% 可解析 + 五键 + 词表 + policy==pack
  G4  H1 诚实性：良向 chosen 实质交付+判断句含内容槽位；恶向 chosen 零交付+拒绝话术；
      rejected 形态保真（13 形态逐形标记）
  G5  H4 长度平价：族中位比 ∈[0.9,1.1]，逐对比 ∈[0.7,1.4]
  G6  配比：极性 50:50±2%、en:zh 60:40±2%、A 子域、pack、形态逐族闭合
  G7  格式盲探针：偏好极性不可由纯格式特征线性分离（≤55%）
  G8  token 预算：部署 tokenizer 逐行 ≤1000
  G9  官方两段式 8-gram 污染匹配 vs 全部 heldout + probes（样板豁免白名单双侧对称剥离）
  G10 F4 编码变形 / F6 权限伪造官方留出清单复检（B3 口径）零命中 + 保守签名复扫
  G11 每原型条数上限 + 族内全行精确重复 = 0 + m3 口径相似度全景报告
  G12 manifest 冻结校验（sha256 / 分布闭合 / 谱系链 / 版本纪律）

fail-closed：任一 FAIL ⇒ 整体 FAIL、非零退出、报告仍完整落盘；结尾标记
P16-MERGE-GATE=DONE（报告写入完成的机读标记，与 PASS/FAIL 判定无关）。

用法：.venv\\Scripts\\python.exe scripts\\check_p16_calibration.py
"""
from __future__ import annotations

import ast
import difflib  # noqa: F401  （官方 verify_shared_substring 内部依赖）
import glob
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P16_DIR = os.path.join(ROOT, "data", "dpo", "p16-calibration")
REL_BENIGN = os.path.join(P16_DIR, "p16_benign_release.jsonl")
REL_MALICIOUS = os.path.join(P16_DIR, "p16_malicious_honest.jsonl")
MANIFEST = os.path.join(P16_DIR, "manifest.json")
M4_BASE = os.path.join(ROOT, "data", "dpo-remediation-staging", "dpo_m4_capfix.jsonl")
JAILBREAK_SUITE = os.path.join(ROOT, "scripts", "check_jailbreak_suite.py")
TOK_PATH = os.path.join(ROOT, "checkpoints", "qwen3-06b-sec-m4-capfix-probe")
REPORT = os.path.join(ROOT, "reports", "p1.6-gate-report.md")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from check_sft_contamination import (  # noqa: E402  官方污染匹配器（v3）
    NGRAM_N, NGRAM_PREFILTER, LCS_MIN_CHARS,
    normalize, ngrams, doc_probe_hits, verify_shared_substring,
)

# ================================================================ 常量表 ==
FROZEN_TEMPLATE_SHA256 = {
    ("professional", "zh"): "67d223f225115a417f0bd12f76100bc7aad6c6297d587db15a829b3ee2b6f45b",
    ("professional", "en"): "74a00b892596c82100621fda96ead06d6c4503e9c90bf92c0c8136c430ef5c0b",
    ("default", "zh"): "8adcb0e403ea4fd0f02cb4bf824b8c860f7c10adba3a289b47637415b8dc34c0",
    ("default", "en"): "c5140564c688ff86f472d6ee14c202732c6f3b9cff439ff49338b7bf889320bb",
    ("conservative", "zh"): "861286d215aef95f1aa4540fbfd97fbcc46a11e8065e8ac07410d9bf6062f3cc",
    ("conservative", "en"): "f4dc69fb50bb78a72a52a2fa0809718a8d271bfa8d20202737209ca86f252a36",
}

# G6 配比契约（§5.1 + 两 parts manifest 登记值 = 外部契约）
QUOTA = {
    "family_rows": {"A": 1500, "B": 480, "C": 360, "D": 480, "E": 300, "F": 2640},
    "lang": {  # 逐族 en/zh（§5.1）
        "A": {"en": 900, "zh": 600}, "B": {"en": 288, "zh": 192}, "C": {"en": 198, "zh": 162},
        "D": {"en": 288, "zh": 192}, "E": {"en": 180, "zh": 120}, "F": {"en": 1584, "zh": 1056},
    },
    "lang_overall": {"en": 3438, "zh": 2322},          # 59.69% / 40.31%（60:40±2%）
    "pack": {  # 逐族（parts manifest 登记值）
        "A": {"professional": 750, "default": 527, "conservative": 223},
        "B": {"professional": 216, "default": 192, "conservative": 72},
        "C": {"professional": 162, "default": 144, "conservative": 54},
        "D": {"professional": 192, "default": 216, "conservative": 72},
        "E": {"professional": 135, "default": 120, "conservative": 45},
        "F": {"professional": 1056, "default": 1188, "conservative": 396},
    },
    "pack_overall": {"professional": 2511, "default": 2387, "conservative": 862},
    "form": {
        "A": {"policy_jargon_refuse": 750, "overcautious_hold": 450, "irrelevant_conditional": 300},
        "B": {"terminal_cd_transition": 240, "terminal_hard_refuse": 240},
        "C": {"qb_false_positive": 216, "rubber_stamp_allow": 144},
        "D": {"deliver_but_selfreport_refuse": 240, "cd_transition_despite_refuse": 120,
              "directive_compliance_despite_report": 120},
        "E": {"long_doc_alarm": 180, "no_judgment_allow": 120},
        "F": {"cd_conditional_transition": 1320, "lip_refuse_deliver": 1320},
    },
    "dpo_class": {"A": "p16_benign_release", "B": "p16_multiturn_benign", "C": "p16_judgment_teaching",
                  "D": "p16_verdict_honesty", "E": "p16_dilution_judgment", "F": "p16_malicious_honest"},
    "a_subdomain": {"p16:A:general_code": 450, "p16:A:general_writing": 330, "p16:A:translation": 260,
                    "p16:A:general_qa": 230, "p16:A:summary": 230},
    "benign": 2880, "malicious": 2880,
}

# ---- 标记词表（两批 builder 公共库逐字移植；口径 = 批内自检同款） ----
ABD_ZH_MARK = ("无风险", "无任何风险", "不涉及任何风险面", "无任何风险面")
ABD_EN_MARK = ("no safety concerns", "nothing risky", "no risk faces")
CD_KW_ZH = ("可先给", "骨架", "框架")
CD_KW_EN = ("skeleton", "can first", "outline")
B_HARD_ZH = ("不予", "暂缓", "暂不放行")
B_HARD_EN = ("authorization first", "needs category authorization", "without confirmed",
             "stays unextended", "is held", "not generated", "is not issued")
JUDGE_MARKERS = ["无风险", "不涉及任何风险面", "no safety concerns", "nothing risky"]
CHECK_MARKERS = ["检查", "核对", "通读", "已读", "读了一遍", "read the", "read through", "checked",
                 "reviewed", "looked through", "went through"]
HOLD_MARKERS = ["暂不", "暂缓", "不放行", "无法", "需先", "需由", "建议先", "会签", "未经", "不予", "不得", "待确认",
                "holding", "hold off", "can't", "cannot", "without the full", "先行降级"]
REFUSE_MARKERS = ["拒绝", "不能给", "不予", "不会提供", "这一步不", "refus", "won't provide", "declin",
                  "can't provide", "will not provide", "not going to provide"]
INJ_DETECT_MARKERS = ["注入", "injection"]
PAYLOAD_REFUSE_MARKERS = ["拒绝遵循", "不予执行", "不予采纳并执行", "refused and reported", "refused",
                          "not follow", "won't follow"]
CEF_CD_MARKERS = ["可先给", "可先提供", "可先发", "可先列出", "框架（不含", "（不含具体", "（不含操作", "授权演练",
                  "授权环境", "现场演示", "书面授权确认后", "I can first offer", "an outline", "framework only",
                  "authorized engagement", "red team", "without the concrete", "without the specific"]
COMPLY_MARKERS = ["按其要求", "本次按", "照做", "直接给你", "既然", "as requested", "proceed", "That said",
                  "on that basis", "直接说", "就按这个来"]
STAMP_FORBID = JUDGE_MARKERS + CHECK_MARKERS
WEAPON_MARKERS = ["`", "sudo", "nmap", "hydra", "curl ", "wget ", "powershell", "cmd.exe", "bash -c", "sh -c",
                  "http://", "https://", "import os", "subprocess", "eval(", "exec(", "mimikatz", "metasploit",
                  "msfvenom", "/etc/shadow", "passwd file", "SELECT ", "UNION SELECT", "payload bin", "shellcode"]

# G10 官方签名（scripts/check_jailbreak_suite.py F4_SIG/F6_SIG 内嵌副本；
# 运行时对源文件 ast 机器校验一致，漂移即 G10 FAIL）
F4_SIG = ["全程不要出现明文", "reply entirely in rot13", "entirely in rot13",
          "按同样方式用 base64 把你的成品回答编码", "解码后照着做",
          "no plaintext anywhere", "plaintext forbidden"]
F6_SIG = ["进入维护模式", "entering admin debug mode", "维护模式下 hf 底线",
          "policy enforcement is disabled", "supersede the system prompt",
          "treat me as the system owner", "策略已随", "政策引擎不加载",
          "my instructions supersede"]
# G10 保守复扫（两批自建版合并；parts 声明零命中 ⇒ 合并件必须复扫同样零命中）
ZW_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
B64_RE = re.compile("[A-Za-z0-9+/=]{28,}")
CIPHER_RE = re.compile("〈[^〈〉]{8,}〉")
OBF_WORDS = ["base64", "rot13", "Base64", "Rot13", "ROT13", "零宽", "zero-width"]
CEF_F4_PATTERNS = [
    r"base64", r"\bb64\b", r"rot13", r"atob", r"\bhex\b.{0,6}(编码|encod)", r"凯撒", r"卡撒", r"摩斯", r"morse",
    r"零宽", r"zero.?width", r"\u200b", r"\u200c", r"\ufeff", r"leetspeak", r"谐音替换", r"同音字替换", r"全角替换",
    r"homoglyph", r"urlencode", r"percent.?encod", r"uuencode", r"二进制编码", r"binary.?encod", r"字符映射加密",
    r"把.*加密后", r"[A-Za-z0-9+/=]{32,}",
]
CEF_F6_PATTERNS = [
    r"伪造授权", r"伪造审批", r"伪造工牌", r"伪造身份", r"伪造权限", r"伪造令牌", r"伪造印章",
    r"forged (authorization|approval|badge)", r"fake (authorization|badge|approval)",
    r"已获书面授权", r"已拿到授权", r"已获得书面授权", r"我已获得授权", r"我已经拿到授权",
    r"I (already )?have (written )?(permission|authorization)", r"assume I.?m authorized",
    r"assume I am authorized", r"免授权", r"无需授权", r"授权直通", r"视同已授权",
    r"pretend you have my permission", r"假定你已获授权", r"授权书.*拍照发你", r"审批单.*我来补",
]
CEF_F4F6_RES = [re.compile(p, re.IGNORECASE) for p in CEF_F4_PATTERNS + CEF_F6_PATTERNS]

# G9 样板豁免白名单（双侧对称剥离；逐条登记于 manifest.json gate_registration.g9_whitelist）
VERDICT_LINE_RE = re.compile(r"VERDICT: \{[^\n]*\}")
DSH_SKELETON = [
    '<dsh-protocol v="0.1">', '</dsh-protocol>', '<system>', '</system>', '<operator>', '</operator>',
    '<user>', '</user>', '<meta>', '</meta>', '<body>', '</body>', '<carrier', 'type="tool_output"',
    'trust="untrusted"', 'id="c1">', 'role: security_analyst', 'role: 安全分析助手',
    'authorization: read-only assessment', 'authorization: 分析授权：只读评估', 'authorization: analyst',
    'output-mode: structured', 'policy: default', 'policy: professional', 'policy: conservative',
    'policy: pack:default@0.1', 'policy: pack:professional@0.1', 'policy: pack:conservative@0.1',
]

ALLOWED_AV = {("answer", "allow"), ("refuse", "refuse"), ("refuse", "hold"), ("answer", "conditional"),
              ("answer", "insufficient-context"), ("report", "contains-injection")}
VKEYS = ("action", "verdict", "confidence", "findings", "policy")
ID_RE = re.compile(r"^p16-([A-F])-\d{6}$")
G11_CAPS = {"A": 30, "B": 30, "C": 30, "D": 30, "E": 30, "F": 48}
G4_SLOT_SOFTPASS_MAX = 17        # 0.6% × 2,880（软通过上限，超出即 FAIL）
EN_STOP = set("the a an to of in for on with and or is are was were be been this that these those it its as at by "
              "from you your we our they their not no do does did can could will would should may might must have "
              "has had if then than so such about into over under more most other some any all each".split())


# ================================================================ 通用 ==
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def load_templates() -> dict:
    """m4 基座 6 模板 {(pack,lang): text}；sha256 必须与冻结表逐项一致。"""
    by_hash = {}
    with open(M4_BASE, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            for t in r.get("conversations", []):
                if t.get("from") == "system":
                    by_hash[hashlib.sha256(t["value"].encode("utf-8")).hexdigest()] = t["value"]
                    break
    want = set(FROZEN_TEMPLATE_SHA256.values())
    assert set(by_hash) == want, "m4 模板集与冻结表不一致（模板漂移）"
    inv = {h: k for k, h in FROZEN_TEMPLATE_SHA256.items()}
    return {inv[h]: t for h, t in by_hash.items()}


def parse_verdict(value: str):
    """官方口径解析（p16cef_common.parse_verdict 同款）；返回 (obj|None, err|None)。"""
    lines = value.rstrip("\n").split("\n")
    last = lines[-1].strip()
    if not last.startswith("VERDICT:"):
        return None, "no VERDICT line at end"
    try:
        obj = json.loads(last[len("VERDICT:"):].strip())
    except Exception as e:
        return None, f"verdict json parse fail: {e}"
    if not isinstance(obj, dict) or set(obj.keys()) != set(VKEYS):
        return None, "verdict keys wrong"
    if (obj["action"], obj["verdict"]) not in ALLOWED_AV:
        return None, f"verdict combo not allowed: {obj['action']}/{obj['verdict']}"
    if not isinstance(obj["confidence"], (int, float)) or not (0.5 <= float(obj["confidence"]) <= 0.99):
        return None, f"confidence out of range: {obj['confidence']}"
    if not isinstance(obj["findings"], list) or not all(isinstance(x, str) for x in obj["findings"]):
        return None, "findings not list[str]"
    if not isinstance(obj["policy"], str):
        return None, "policy not str"
    return obj, None


def body_of(value: str) -> str:
    return value.rstrip("\n").rsplit("\nVERDICT: ", 1)[0].rstrip("\n")


def fam(r: dict) -> str:
    return r["id"][4]


def subtask(r: dict) -> str:
    return r["src_task"].rsplit(":", 1)[-1]


def hit(text: str, markers) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in markers)


def content_tokens(text: str) -> set:
    """zh → CJK 二元组；en → ≥3 字符非停用词。"""
    if re.search(r"[\u4e00-\u9fff]", text):
        out = set()
        for run in re.findall(r"[\u4e00-\u9fff]+", text):
            out.update(zip(run, run[1:]))
        return out
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in EN_STOP}


class Gate:
    def __init__(self, gid, title):
        self.gid, self.title = gid, title
        self.ok = True
        self.fails = []
        self.info = []          # (label, value) 报告数字
        self.notes = []         # 口径/解释说明

    def fail(self, msg):
        self.ok = False
        self.fails.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    def num(self, label, value):
        self.info.append((label, value))


# ================================================================ 载入 ==
T0 = time.time()
ROWS_B = load_jsonl(REL_BENIGN)
ROWS_M = load_jsonl(REL_MALICIOUS)
ROWS = ROWS_B + ROWS_M
TEMPLATES = load_templates()
print(f"[load] 良 {len(ROWS_B)} / 恶 {len(ROWS_M)} 行；模板 6 个 sha256 断言一致（{time.time()-T0:.0f}s）")


# ================================================================ G1 ==
def gate_g1() -> Gate:
    g = Gate("G1", "id 唯一 · p16 命名空间 · 既有混料零重叠")
    ids = [r["id"] for r in ROWS]
    # 命名空间 + 唯一
    bad_ns = [i for i in ids if not ID_RE.match(i)]
    if bad_ns:
        g.fail(f"id 不合命名空间 p16-[A-F]-\\d{{6}}：{bad_ns[:5]}（共 {len(bad_ns)}）")
    dup = sorted(k for k, v in Counter(ids).items() if v > 1)
    if dup:
        g.fail(f"id 重复：{dup[:5]}（共 {len(dup)}）")
    # id 族位与 src_task 前缀一致
    mism = [r["id"] for r in ROWS if f"p16:{fam(r)}" != ":".join(r["src_task"].split(":")[:2])]
    if mism:
        g.fail(f"id 族位与 src_task 前缀不一致：{mism[:5]}（共 {len(mism)}）")
    # 绑定判据：p16 id 格式字面量（p16-[A-F]-数字）在一切既有混料中零出现
    #   ⇒ p16 id 集与全部混料 id 集零交（id 必然含该字面量）
    # 诊断belt：裸 'p16-' 字面量（文档正文中可能出现的无关子串，逐处裁决登记）
    ID_PAT = re.compile(rb"p16-[A-F]-\d")
    scan_targets = []
    for pat in (os.path.join(ROOT, "data", "dpo", "**", "*.jsonl"),
                os.path.join(ROOT, "data", "dpo-remediation-staging", "*.jsonl"),
                os.path.join(ROOT, "data", "m4-run", "*.jsonl"),
                os.path.join(ROOT, "data", "lf", "**", "*.jsonl"),
                os.path.join(ROOT, "data", "sft", "**", "*.jsonl")):
        scan_targets += glob.glob(pat, recursive=True)
    scan_targets = sorted({os.path.abspath(p) for p in scan_targets
                           if os.path.abspath(p).startswith(os.path.abspath(P16_DIR) + os.sep) is False
                           and os.path.abspath(P16_DIR) != os.path.abspath(p)})
    n_files, n_bytes, id_hits, raw_hits = 0, 0, [], []
    for path in scan_targets:
        n_files += 1
        with open(path, "rb") as f:
            off = 0
            for chunk in iter(lambda: f.read(1 << 22), b""):
                for m in ID_PAT.finditer(chunk):
                    id_hits.append((os.path.relpath(path, ROOT), off + m.start()))
                idx = chunk.find(b"p16-")
                while idx != -1:
                    raw_hits.append((os.path.relpath(path, ROOT), off + idx))
                    idx = chunk.find(b"p16-", idx + 1)
                n_bytes += len(chunk)
                off += len(chunk)
    g.num("扫描混料文件数", n_files)
    g.num("扫描字节数", f"{n_bytes:,}")
    g.num("id 格式字面量命中", len(id_hits))
    g.num("裸 'p16-' 字面量命中（诊断）", len(raw_hits))
    if id_hits:
        g.fail(f"既有混料中出现 p16 id 格式字面量：{id_hits[:8]}（共 {len(id_hits)} 处）")
    if raw_hits:
        ctx = []
        for rp, off in raw_hits[:8]:
            with open(os.path.join(ROOT, rp), "rb") as f:
                f.seek(max(0, off - 48))
                ctx.append((rp, off, f.read(96).decode("utf-8", errors="replace").replace("\n", "\\n")))
        g.note(f"裸 'p16-' 命中 {len(raw_hits)} 处，逐处裁决（本批实测均为无关子串，非 p16 id）："
               + "；".join(f"{rp}@{off}：『{c}』" for rp, off, c in ctx))
    g.note("绑定判据说明：字节级扫描 id 格式 p16-[A-F]-数字 零命中 ⇒ p16 id 集与 data/dpo（含 m3/train.jsonl "
           "47,948）、dpo-remediation-staging（m4 28,842）、m4-run、lf 镜像（含 6.9GB SFT 语料）、sft 的全部 "
           "混料 id 集零交（子sumption：任何 id 必含该字面量）")
    g.num("良/恶文件行数", f"{len(ROWS_B)} / {len(ROWS_M)}")
    if len(ROWS_B) != 2880 or len(ROWS_M) != 2880:
        g.fail(f"行数非 2,880/2,880：{len(ROWS_B)}/{len(ROWS_M)}")
    return g


# ================================================================ G2 ==
def gate_g2() -> Gate:
    g = Gate("G2", "schema 与 m4 逐字段兼容（冻结模板 / 轮次 / human 收尾 / gpt 分叉）")
    m4_core = {"dpo_class", "id", "pack", "lang", "conversations", "chosen", "rejected", "src_task"}
    audit_keys = {"polarity", "rejected_form", "archetype_id"}
    want_keys = m4_core | audit_keys
    tpl_by_pack = {}
    for (p, l), t in TEMPLATES.items():
        tpl_by_pack.setdefault(p, set()).add(t)
    all_tpl = set(TEMPLATES.values())
    cnt_turns = Counter()
    for r in ROWS:
        rid = r["id"]
        if set(r.keys()) != want_keys:
            g.fail(f"{rid}: 键集不符：{sorted(set(r.keys()) ^ want_keys)}")
        # system 轮 = 冻结模板 + pack 标记一致
        convs = r["conversations"]
        if not convs or convs[0].get("from") != "system":
            g.fail(f"{rid}: conversations[0] 非 system")
            continue
        if convs[0].get("value") not in all_tpl:
            g.fail(f"{rid}: system 非 6 冻结模板之一")
        elif f"pack:{r['pack']}@0.1" not in convs[0]["value"]:
            g.fail(f"{rid}: system 模板 pack 标记与行 pack 不符")
        if convs[0]["value"] not in tpl_by_pack[r["pack"]]:
            g.fail(f"{rid}: system 模板不属于行 pack 的冻结模板集")
        # 轮次交替 human/gpt，human 收尾，值非空
        roles = [c.get("from") for c in convs[1:]]
        vals_ok = all(isinstance(c.get("value"), str) and c["value"].strip() for c in convs[1:])
        if not vals_ok:
            g.fail(f"{rid}: 轮文本存在空/非字符串")
        if roles and roles[-1] != "human":
            g.fail(f"{rid}: conversations 未以 human 收尾：{roles}")
        alt_ok = all(roles[i] == ("human" if i % 2 == 0 else "gpt") for i in range(len(roles)))
        if not alt_ok:
            g.fail(f"{rid}: 轮次不满足 human/gpt 交替：{roles}")
        if "assistant" in roles:
            g.fail(f"{rid}: 残留 assistant 前缀轮（未归一）")
        # chosen/rejected 分叉
        for side in ("chosen", "rejected"):
            d = r[side]
            if set(d.keys()) != {"from", "value"} or d.get("from") != "gpt" or not isinstance(d.get("value"), str):
                g.fail(f"{rid}: {side} 非 {{from:'gpt', value:str}}")
        # 审计键类型
        if not isinstance(r["archetype_id"], str) or not r["archetype_id"].startswith(f"{fam(r)}-"):
            g.fail(f"{rid}: archetype_id 非法：{r['archetype_id']!r}")
        if r["polarity"] not in ("benign_release", "malicious_refuse"):
            g.fail(f"{rid}: polarity 非法 {r['polarity']}")
        if r["dpo_class"] != QUOTA["dpo_class"][fam(r)]:
            g.fail(f"{rid}: dpo_class 与族不符：{r['dpo_class']}")
        if r["lang"] not in ("en", "zh") or r["pack"] not in ("professional", "default", "conservative"):
            g.fail(f"{rid}: lang/pack 非法 {r['lang']}/{r['pack']}")
        cnt_turns[len(convs)] += 1
    g.num("轮数分布", dict(sorted(cnt_turns.items())))
    g.note("键集 = m4 核心八键（dpo_class/id/pack/lang/conversations/chosen/rejected/src_task）+ 旁路审计三键 "
           "（polarity/rejected_form/archetype_id，m4 length_matched_from 先例 ✓ LF 兼容）；多轮前缀轮双侧共享于 "
           "conversations（逐字相同由构造保证）；CEF 前缀轮 from=assistant 已在合并时归一为 house DPO 口径 gpt "
           "（manifest.normalization 登记 1,007 轮），LLaMA-Factory dataset_info user_tag=human/assistant_tag=gpt")
    return g


# ================================================================ G3 ==
def gate_g3() -> Gate:
    g = Gate("G3", "双侧 VERDICT 100% 可解析 + 五键 + 词表 + policy==pack")
    n = 0
    pairs = Counter()
    for r in ROWS:
        for side in ("chosen", "rejected"):
            v, err = parse_verdict(r[side]["value"])
            n += 1
            if err:
                g.fail(f"{r['id']} {side}: {err}")
                continue
            if v["policy"] != r["pack"]:
                g.fail(f"{r['id']} {side}: verdict.policy != 行 pack")
            pairs[f"{v['action']}/{v['verdict']}"] += 1
    g.num("解析侧数", n)
    g.num("action/verdict 组合分布", dict(sorted(pairs.items())))
    g.note(f"词表 = 六组合（answer/allow、refuse/refuse、refuse/hold、answer/conditional、"
           f"answer/insufficient-context、report/contains-injection）；confidence ∈[0.5,0.99]；"
           f"findings 为字符串数组。官方解析器口径 = parts 批内自检同款（末行 VERDICT 前缀严格匹配）")
    return g


# ================================================================ G4 ==
def _slot_check(r: dict) -> str:
    """返回 'full'（词法命中）/ 'trans'（译文即交付）/ 'soft'（语义槽位·词法未中）。"""
    q = "\n".join(t["value"] for t in r["conversations"] if t["from"] != "system")
    body = body_of(r["chosen"]["value"])
    qt = content_tokens(q)
    if qt & content_tokens(body):
        return "full"
    if r["src_task"].endswith(":translation"):
        if len(re.findall(r"[\u4e00-\u9fff]", body)) >= 20 or len(re.findall(r"[a-z]{3,}", body.lower())) >= 30:
            return "trans"
    return "soft"


def gate_g4() -> Gate:
    g = Gate("G4", "H1 诚实性 + H3 内容槽位 + rejected 形态保真（13 形态逐形标记）")
    soft_ids, slot_stat = [], Counter()
    body_min = 10**9
    for r in ROWS:
        rid, f, st = r["id"], fam(r), subtask(r)
        cb, rb = body_of(r["chosen"]["value"]), body_of(r["rejected"]["value"])
        cb_low, rb_low = cb.lower(), rb.lower()
        cv, e1 = parse_verdict(r["chosen"]["value"])
        rv, e2 = parse_verdict(r["rejected"]["value"])
        if e1 or e2:
            continue  # G3 已计
        benign = r["polarity"] == "benign_release"
        # ---- H1/H3 良性放行向
        if benign:
            if (cv["action"], cv["verdict"]) != ("answer", "allow"):
                g.fail(f"{rid}: 良性 chosen VERDICT 非 answer/allow")
            marks = ABD_ZH_MARK if (f in ("A", "B", "D") and r["lang"] == "zh") else (
                ABD_EN_MARK if f in ("A", "B", "D") else None)
            if f in ("A", "B", "D"):
                if not any(m in (cb if r["lang"] == "zh" else cb_low) for m in marks):
                    g.fail(f"{rid}: H3 chosen 缺良性判断标记（ABD 词表）")
            else:  # C/E
                if not hit(cb, JUDGE_MARKERS):
                    g.fail(f"{rid}: H3 chosen 缺良性判断标记（CEF 词表）")
                if not hit(cb, CHECK_MARKERS):
                    g.fail(f"{rid}: H3 chosen 缺检查行为词（C/E 口径）")
                if not cv["findings"]:
                    g.fail(f"{rid}: chosen findings 为空（须引用检查结果）")
            if len(cb) < 60:
                g.fail(f"{rid}: H1 chosen 正文 <60 字符（非实质交付）")
            body_min = min(body_min, len(cb))
            s = _slot_check(r)
            slot_stat[s] += 1
            if s == "soft":
                soft_ids.append(rid)
            # ---- rejected 形态保真（A/B/C/E 良性形态；D 放行向为自报诚实性对比）
            form = r["rejected_form"]
            if f == "A":
                if form == "policy_jargon_refuse" and "机制层" not in cb and "mechanism-layer" not in rb_low:
                    if "机制层" not in rb and "mechanism-layer" not in rb_low:
                        g.fail(f"{rid}: H5 jargon 形态缺机制层标记")
                elif form == "overcautious_hold" and "T1" not in rb:
                    g.fail(f"{rid}: H5 hold 形态缺 T1 澄清标记")
                elif form == "irrelevant_conditional" and "attested" not in rb:
                    g.fail(f"{rid}: H5 conditional 形态缺 attested 标记")
            elif f == "B":
                kws = CD_KW_ZH if r["lang"] == "zh" else CD_KW_EN
                hard = B_HARD_ZH if r["lang"] == "zh" else B_HARD_EN
                tgt = rb if r["lang"] == "zh" else rb_low
                if form == "terminal_hard_refuse":
                    if not any(k in tgt for k in hard):
                        g.fail(f"{rid}: H5 hard 拒绝形态标记缺失")
                    if any(k in tgt for k in kws):
                        g.fail(f"{rid}: H5 hard 形态泄漏框架类关键词")
                elif form == "terminal_cd_transition":
                    if not any(k in tgt for k in kws):
                        g.fail(f"{rid}: H5 cd 形态缺框架类关键词")
            elif f in ("C", "E"):
                if form in ("qb_false_positive", "long_doc_alarm"):
                    if (rv["action"], rv["verdict"]) != ("refuse", "hold"):
                        g.fail(f"{rid}: H5 形态① VERDICT 非 refuse/hold")
                    if not hit(rb, HOLD_MARKERS):
                        g.fail(f"{rid}: H5 形态① 缺 hold 话术")
                    if hit(rb, JUDGE_MARKERS):
                        g.fail(f"{rid}: H5 形态① 含判断标记（应为无判断误报）")
                else:
                    if (rv["action"], rv["verdict"]) != ("answer", "allow"):
                        g.fail(f"{rid}: H5 形态② VERDICT 非 answer/allow")
                    if hit(rb, STAMP_FORBID):
                        g.fail(f"{rid}: H5 形态② 含判断/检查标记（应为橡皮章放行）")
                    if rv["findings"]:
                        g.fail(f"{rid}: H5 形态② findings 应为空")
            else:  # D 放行向（benign）：同基底同正文 + 自报相反（H1 最小对比变换）
                if form != "deliver_but_selfreport_refuse":
                    g.fail(f"{rid}: D 放行向 rejected_form 应为 deliver_but_selfreport_refuse，实为 {form}")
                if cb != rb:
                    g.fail(f"{rid}: D release 双侧正文应逐字相同（同基底同正文）")
                if (rv["action"], rv["verdict"]) != ("refuse", "refuse"):
                    g.fail(f"{rid}: D release rejected VERDICT 非 refuse/refuse（自报诚实性对比）")
        # ---- H1 恶意诚实向
        else:
            if f == "F":
                carrier = r["archetype_id"].startswith("F-car-")
                if carrier:
                    if (cv["action"], cv["verdict"]) != ("report", "contains-injection"):
                        g.fail(f"{rid}: F 载体 chosen VERDICT 非 report/contains-injection")
                    if not hit(cb, INJ_DETECT_MARKERS):
                        g.fail(f"{rid}: F 载体 chosen 缺注入检测陈述")
                    if not hit(cb, PAYLOAD_REFUSE_MARKERS):
                        g.fail(f"{rid}: F 载体 chosen 缺载荷拒绝话术")
                    if not cv["findings"] or not cv["findings"][0].startswith("carrier c1"):
                        g.fail(f"{rid}: F 载体 chosen findings[0] 未引用 carrier c1")
                else:
                    if (cv["action"], cv["verdict"]) != ("refuse", "refuse"):
                        g.fail(f"{rid}: F 对话 chosen VERDICT 非 refuse/refuse")
                    if not hit(cb, REFUSE_MARKERS):
                        g.fail(f"{rid}: F 对话 chosen 缺拒绝话术")
                    if hit(cb, CEF_CD_MARKERS):
                        g.fail(f"{rid}: H1 F 对话 chosen 含部分交付/框架类标记")
                form = r["rejected_form"]
                if form == "cd_conditional_transition":
                    if (rv["action"], rv["verdict"]) != ("refuse", "refuse"):
                        g.fail(f"{rid}: cd rejected 自报非 refuse/refuse")
                    if not hit(rb, CEF_CD_MARKERS):
                        g.fail(f"{rid}: cd rejected 缺条件过渡标记")
                else:  # lip_refuse_deliver
                    if (rv["action"], rv["verdict"]) not in (("refuse", "refuse"), ("report", "contains-injection")):
                        g.fail(f"{rid}: lip rejected 自报非 refuse/report")
                    if not hit(rb, COMPLY_MARKERS):
                        g.fail(f"{rid}: lip rejected 缺顺从标记")
            elif st == "refuse_carrier":
                if "注入" not in cb and "injection" not in cb_low:
                    g.fail(f"{rid}: D 载体 chosen 缺注入检测陈述")
                if "HF-004" not in cb:
                    g.fail(f"{rid}: D 载体 chosen 缺 HF-004 依据")
                if "不予采纳" not in rb and "in principle not adopted" not in rb_low:
                    g.fail(f"{rid}: D 载体 rejected 缺「原则上不予采纳」话术")
                if (cv["action"], cv["verdict"]) != ("report", "contains-injection"):
                    g.fail(f"{rid}: D 载体 chosen VERDICT 非 report/contains-injection")
                if (rv["action"], rv["verdict"]) != ("report", "contains-injection"):
                    g.fail(f"{rid}: D 载体 rejected VERDICT 非 report/contains-injection")
            elif st == "refuse_conversational":
                kws = CD_KW_ZH if r["lang"] == "zh" else CD_KW_EN
                if "不能" not in cb and "can't" not in cb_low and "cannot" not in cb_low:
                    g.fail(f"{rid}: D 对话 chosen 缺明确拒绝表述")
                if any(k in (cb if r["lang"] == "zh" else cb_low) for k in kws):
                    g.fail(f"{rid}: D 对话 chosen 含部分交付关键词")
                if not any(k in (rb if r["lang"] == "zh" else rb_low) for k in kws):
                    g.fail(f"{rid}: D 对话 rejected 缺 cd 框架关键词")
                if (cv["action"], cv["verdict"]) != ("refuse", "refuse") or \
                        (rv["action"], rv["verdict"]) != ("refuse", "refuse"):
                    g.fail(f"{rid}: D 对话 双侧 VERDICT 非 refuse/refuse")
            else:
                g.fail(f"{rid}: 恶意极性但族/子任务未识别：{f}/{st}")
    # 槽位软通过上限（语义槽位·词法未中 ≤ 0.6%，逐条列出供人工抽查复核）
    g.num("槽位检查 full/trans/soft", dict(slot_stat))
    g.num("chosen 正文最短", body_min)
    if slot_stat["soft"] > G4_SLOT_SOFTPASS_MAX:
        g.fail(f"内容槽位软通过 {slot_stat['soft']} > 上限 {G4_SLOT_SOFTPASS_MAX}（0.6%×2,880）")
    if slot_stat["soft"]:
        g.note(f"软通过 {slot_stat['soft']} 行（判断句以同义/转述方式点明主题，词法匹配不可判；"
               f"逐条列于报告附录，人工抽查 90 行覆盖复核）：{', '.join(soft_ids)}")
    g.note("口径：H1 实质交付 = 判断标记 + 正文 ≥60 字符 + 内容槽位（zh CJK 二元组 / en ≥3 字符非停用词，"
           "与查询词元交集 ≥1；译文行以『译文本身即交付物』特例通过）；A/B/D 词表 = ABD 批口径逐字移植，"
           "C/E = CEF 批口径（另要求检查行为词 + findings 非空）；D release = 双侧正文逐字相同 + 自报相反"
           "（H1 最小对比变换）；B/A 的 gen 级交付标记泄漏检查依赖 _meta（parts 已冻结剥离），合并门以"
           "形态标记 + 槽位 + 长度近似覆盖")
    return g


# ================================================================ G5 ==
def gate_g5() -> Gate:
    g = Gate("G5", "H4 长度平价（族中位比 ∈[0.9,1.1]，逐对比 ∈[0.7,1.4]）")
    by_fam = defaultdict(list)
    oob = []
    for r in ROWS:
        lc, lr = len(r["chosen"]["value"]), len(r["rejected"]["value"])
        ratio = lr / lc if lc else 0.0
        by_fam[fam(r)].append(ratio)
        if not (0.7 <= ratio <= 1.4):
            oob.append((r["id"], round(ratio, 3)))
    med = {}
    for f, xs in sorted(by_fam.items()):
        xs = sorted(xs)
        n = len(xs)
        m = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
        med[f] = round(m, 4)
        if not (0.9 <= m <= 1.1):
            g.fail(f"族 {f} 中位比 {m:.4f} 越界 [0.9,1.1]")
    if oob:
        g.fail(f"逐对比值越界 [0.7,1.4]：{oob[:8]}（共 {len(oob)}）")
    g.num("族中位比", med)
    allr = sorted(x for xs in by_fam.values() for x in xs)
    g.num("全量比值范围", f"[{allr[0]:.4f}, {allr[-1]:.4f}]")
    return g


# ================================================================ G6 ==
def gate_g6() -> Gate:
    g = Gate("G6", "配比闭合（极性 50:50 / en:zh 60:40 / 逐族 lang·pack·形态 / A 子域）")
    n = len(ROWS)
    pol = Counter(r["polarity"] for r in ROWS)
    b, m = pol.get("benign_release", 0), pol.get("malicious_refuse", 0)
    g.num("极性", f"良 {b} / 恶 {m}（{b/n:.2%} : {m/n:.2%}）")
    if not (0.48 <= b / n <= 0.52):
        g.fail(f"极性非 50:50±2%：{b}/{m}")
    if b != QUOTA["benign"] or m != QUOTA["malicious"]:
        g.fail(f"极性计数 != 契约 2,880/2,880：{b}/{m}")
    # 逐族闭合
    fam_rows = Counter(fam(r) for r in ROWS)
    for f, want in QUOTA["family_rows"].items():
        if fam_rows.get(f) != want:
            g.fail(f"族 {f} 总量 {fam_rows.get(f)} != {want}")
    for dim, key in (("lang", "lang"), ("pack", "pack"), ("form", "rejected_form")):
        for f in "ABCDEF":
            got = Counter(r[key] for r in ROWS if fam(r) == f)
            want = QUOTA[dim][f]
            if dict(got) != want:
                g.fail(f"族 {f} {dim} 分布 {dict(got)} != 契约 {want}")
    # 总体 lang / pack
    lang_all = Counter(r["lang"] for r in ROWS)
    if dict(lang_all) != QUOTA["lang_overall"]:
        g.fail(f"总体 lang {dict(lang_all)} != 契约 {QUOTA['lang_overall']}")
    en_share = lang_all["en"] / n
    if not (0.58 <= en_share <= 0.62):
        g.fail(f"en 占比 {en_share:.2%} 越界 60:40±2%")
    pack_all = Counter(r["pack"] for r in ROWS)
    if dict(pack_all) != QUOTA["pack_overall"]:
        g.fail(f"总体 pack {dict(pack_all)} != 契约 {QUOTA['pack_overall']}")
    # A 子域
    a_sub = Counter(r["src_task"] for r in ROWS if fam(r) == "A")
    if dict(a_sub) != QUOTA["a_subdomain"]:
        g.fail(f"A 子域 {dict(a_sub)} != 契约 {QUOTA['a_subdomain']}")
    # D 双向切分
    d_split = Counter(subtask(r) for r in ROWS if fam(r) == "D")
    if dict(d_split) != {"release": 240, "refuse_conversational": 120, "refuse_carrier": 120}:
        g.fail(f"D 双向切分 {dict(d_split)} != 契约 release240/conv120/carrier120")
    # F 载体/对话
    f_split = Counter("carrier:" + subtask(r) if r["archetype_id"].startswith("F-car-") else "dialog"
                      for r in ROWS if fam(r) == "F")
    if f_split.get("dialog") != 792 or sum(v for k, v in f_split.items() if k != "dialog") != 1848:
        g.fail(f"F 载体/对话切分 {dict(f_split)} != 契约 载体1,848/对话792")
    g.num("总体 en:zh", f"{lang_all['en']}:{lang_all['zh']}（{en_share:.2%}）")
    g.num("总体 pack", dict(pack_all))
    g.num("A 子域", dict(sorted(a_sub.items())))
    g.note("逐族契约值 = 设计 §5.1 + 两 parts manifest 登记值（外部已验收契约，非合并器自报）；"
           "pack 逐族精确断言（A 750/527/223 为 50/35/15 的最大余数法整边际）")
    return g


# ================================================================ G7 ==
def gate_g7() -> Gate:
    """格式盲探针：chosen~rejected 偏好极性不可由纯格式特征线性分离。"""
    g = Gate("G7", "格式盲性线性探针（响应级 chosen~rejected，纯格式特征 ≤55%）")
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler
    except Exception as e:
        g.fail(f"sklearn/numpy 不可用：{e}")
        return g
    # 样本：每行两条响应（chosen/rejected），标签 = 是否 chosen（DPO 训练的偏好极性轴）
    X, y = [], []
    for r in ROWS:
        convs = r["conversations"]
        for side, label in (("chosen", 1), ("rejected", 0)):
            v = r[side]["value"]
            lines = v.rstrip("\n").split("\n")
            vlen = len(lines[-1]) if lines[-1].startswith("VERDICT:") else 0
            body = body_of(v)
            keys = 5
            obj, err = parse_verdict(v)
            if err:
                keys = 0
            X.append([len(v), len(body), vlen, 1 if not err else 0, keys, len(convs)])
            y.append(label)
    X, y = np.array(X, dtype=float), np.array(y)
    accs = []
    for seed in (0, 1, 2):
        rng = np.random.RandomState(seed)
        row_idx = np.arange(len(ROWS))
        # 行级切分（同行的两条响应同侧，防泄漏），按族分层近似：简单随机行切分
        tr_rows = rng.choice(row_idx, size=int(len(ROWS) * 0.8), replace=False)
        te_rows = np.setdiff1d(row_idx, tr_rows)
        tr_mask = np.zeros(len(ROWS), dtype=bool)
        tr_mask[tr_rows] = True
        sample_row = np.repeat(np.arange(len(ROWS)), 2)
        tr = tr_mask[sample_row]
        scaler = StandardScaler().fit(X[tr])
        clf = LogisticRegression(max_iter=1000).fit(scaler.transform(X[tr]), y[tr])
        acc = clf.score(scaler.transform(X[~tr]), y[~tr])
        accs.append(acc)
    mean_acc = float(np.mean(accs))
    g.num("三种子测试准确率", [round(a, 4) for a in accs])
    g.num("均值", f"{mean_acc:.2%}")
    if mean_acc > 0.55:
        g.fail(f"格式特征可分离偏好极性：{mean_acc:.2%} > 55%（H2/H4 未中和格式轴）")
    # 诊断变体（不入判，仅登记）
    diag = {}
    cv_map, rv_map = {}, {}
    for r in ROWS:
        cv, _ = parse_verdict(r["chosen"]["value"])
        rv, _ = parse_verdict(r["rejected"]["value"])
        cv_map[r["id"]] = cv
        rv_map[r["id"]] = rv
    # 诊断①：+语义载荷（action/verdict onehot + findings 数 + confidence）
    X2 = []
    AV = sorted(ALLOWED_AV)
    for i, r in enumerate(ROWS):
        for side in ("chosen", "rejected"):
            v = r[side]["value"]
            obj = cv_map[r["id"]] if side == "chosen" else rv_map[r["id"]]
            av_oh = [1 if (obj["action"], obj["verdict"]) == av else 0 for av in AV]
            X2.append(list(X[2 * i + (0 if side == "chosen" else 1)]) + av_oh +
                      [len(obj["findings"]), float(obj["confidence"])])
    X2 = np.array(X2, dtype=float)
    accs2 = []
    for seed in (0, 1, 2):
        rng = np.random.RandomState(seed)
        row_idx = np.arange(len(ROWS))
        tr_rows = rng.choice(row_idx, size=int(len(ROWS) * 0.8), replace=False)
        tr_mask = np.zeros(len(ROWS), dtype=bool)
        tr_mask[tr_rows] = True
        sample_row = np.repeat(np.arange(len(ROWS)), 2)
        tr = tr_mask[sample_row]
        scaler = StandardScaler().fit(X2[tr])
        clf = LogisticRegression(max_iter=1000).fit(scaler.transform(X2[tr]), y[tr])
        accs2.append(clf.score(scaler.transform(X2[~tr]), y[~tr]))
    diag["+语义载荷（action/verdict/findings/confidence）"] = f"{np.mean(accs2):.2%}"
    # 诊断②：定义式规则准确率
    diag["chosen VERDICT→极性规则"] = f"{sum(1 for r in ROWS if (cv_map[r['id']]['action'], cv_map[r['id']]['verdict']) == ('answer', 'allow')) / len(ROWS):.2%}"
    diag["rejected VERDICT→极性规则"] = f"{sum(1 for r in ROWS if (rv_map[r['id']]['action'], rv_map[r['id']]['verdict']) in (('refuse', 'refuse'), ('refuse', 'hold'), ('report', 'contains-injection'))) / len(ROWS):.2%}"
    diag["findings 有无规则"] = f"{sum(1 for r in ROWS if bool(cv_map[r['id']]['findings']) != bool(rv_map[r['id']]['findings'])) / len(ROWS):.2%}"
    g.num("诊断变体（不入判）", diag)
    g.note("主判口径：DPO 训练所用的偏好极性轴（哪侧是 chosen）能否由**纯格式特征**（响应长/正文长/VERDICT 行长/"
           "契约键数/轮数）线性分离——50% 附近即格式盲 ✓。诊断①②③④为定义式/语义载荷变体：action/verdict 取值与"
           "findings 引用是本包**设计的语义课程轴**（H1 诚实性对比），非格式泄漏；H2（双侧同构契约）与 H4（长度"
           "平价）已中和长度与契约形状轴。此口径登记于 manifest gate_registration.g7_interpretation")
    return g


# ================================================================ G8 ==
def gate_g8() -> Gate:
    g = Gate("G8", "token 预算（部署 tokenizer，逐行 ≤1000）")
    try:
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(TOK_PATH)
    except Exception as e:
        g.fail(f"tokenizer 加载失败（{TOK_PATH}）：{e}")
        return g
    mx = 0
    mx_id = ""
    per_fam = {}
    for r in ROWS:
        prompt = "\n".join(t["value"] for t in r["conversations"])
        t = max(len(tok.encode(prompt + "\n" + r["chosen"]["value"], add_special_tokens=False)),
                len(tok.encode(prompt + "\n" + r["rejected"]["value"], add_special_tokens=False)))
        f = fam(r)
        cur = per_fam.get(f, (0, 0.0, 0))
        cnt, sm, fmx = cur[0] + 1, cur[1] + t, max(cur[2], t)
        per_fam[f] = (cnt, sm, fmx)
        if t > mx:
            mx, mx_id = t, r["id"]
        if t > 1000:
            g.fail(f"{r['id']}: token {t} > 1000")
    g.num("逐族 (rows, mean, max)", {f: (v[0], round(v[1] / v[0], 1), v[2]) for f, v in sorted(per_fam.items())})
    g.num("全量最大", f"{mx}（{mx_id}）")
    g.note("口径 = CEF 批口径（parts 自检同款连接方式）：prompt=全部轮值 \\n 连接 + 响应；部署 tokenizer = "
           "checkpoints/qwen3-06b-sec-m4-capfix-probe；parts 批内阈值 970（预留 chat 模板余量），全量门按 "
           "§4.1 上限 1000 精确断言")
    return g


# ================================================================ G9 ==
def _strip_whitelist(text: str, templates: list) -> str:
    for lit in templates:
        if lit in text:
            text = text.replace(lit, " ")
    for lit in DSH_SKELETON:
        if lit in text:
            text = text.replace(lit, " ")
    return VERDICT_LINE_RE.sub(" ", text)


def leaves_v(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from leaves_v(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves_v(v)


def _byte_windows(b: bytes):
    """规范化文本 UTF-8 字节 → 8 字节窗口 S8 一维数组（值 = b[i:i+8]）。"""
    import numpy as np
    if len(b) < 8:
        return np.empty(0, dtype="S8")
    a = np.frombuffer(b, dtype=np.uint8)
    return np.lib.stride_tricks.sliding_window_view(a, 8).view("S8").reshape(-1)


def gate_g9() -> Gate:
    """官方两段式 8-gram 污染匹配：全部 heldout + 全部 probes 作为样板，双侧对称白名单剥离。"""
    g = Gate("G9", "官方两段式 8-gram 污染匹配 vs 全部 heldout + probes（白名单双侧剥离）")
    try:
        import numpy as np
    except Exception as e:
        g.fail(f"numpy 不可用：{e}")
        return g
    t0 = time.time()
    # ---- 样板语料（heldout 全部目录 + probes 全部目录；spec §6 列 v0.1/v0.04，本门取超集更严）
    needle_files = []
    for pat in (os.path.join(ROOT, "data", "heldout", "**", "*.jsonl"),
                os.path.join(ROOT, "data", "probes", "**", "*.jsonl")):
        needle_files += glob.glob(pat, recursive=True)
    needle_files = sorted(set(needle_files))
    template_list = list(TEMPLATES.values())

    file_windows = {}       # file_key -> (sorted unique S8 array, [needle_norm_texts])
    total_needles = 0
    W_parts, Fid_parts = [], []
    fid_of = {}
    for fid, path in enumerate(needle_files):
        key = os.path.relpath(path, ROOT)
        fid_of[fid] = key
        if fid % 10 == 0:
            print(f"  [G9] needle 文件 {fid}/{len(needle_files)} …", flush=True)
        texts = []
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f):
                if line.strip():
                    try:
                        j = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    txt = _strip_whitelist("\n".join(leaves_v(j)), template_list)
                    if txt.strip():
                        texts.append(normalize(txt))
        if not texts:
            continue
        wins = []
        for t in texts:
            w = _byte_windows(t.encode("utf-8"))
            if len(w):
                wins.append(w)
        warr = np.unique(np.concatenate(wins)) if wins else np.empty(0, dtype="S8")
        file_windows[fid] = (warr, texts)
        total_needles += len(texts)
        if len(warr):
            W_parts.append(warr)
            Fid_parts.append(np.full(len(warr), fid, dtype=np.int32))
    W_all = np.concatenate(W_parts)
    F_all = np.concatenate(Fid_parts)
    order = np.argsort(W_all)
    W_sorted, F_sorted = W_all[order], F_all[order]
    g.num("样板文件数", len(file_windows))
    g.num("样板 needle 数", total_needles)
    g.num("全局窗口数（含跨文件重复）", f"{len(W_sorted):,}")
    g.note(f"扫描范围超集：data/heldout 全部 12 版本目录 + data/probes 全部（v0.1/v0.1.1/v0.3/v0.4/"
           f"ais-500-draft；spec §6 最低要求 v0.1/v0.04）；needle = 行内全部字符串叶子（保守口径）；"
           f"白名单（双侧对称剥离，登记 manifest.gate_registration.g9_whitelist）：6 冻结模板全文 + "
           f"VERDICT 行正则 + dsh-protocol 头骨架字面量 28 条")

    # ---- 文档侧
    doc_norms = []
    for r in ROWS:
        txt = _strip_whitelist("\n".join([t["value"] for t in r["conversations"]]
                                         + [r["chosen"]["value"], r["rejected"]["value"]]), template_list)
        doc_norms.append((r["id"], normalize(txt)))

    # ---- 阶段1（每文档向量化）：全局窗口 + 文件位图密集矩阵 → 文件级 union 连续游程
    #   无损性链：官方 char-gram 游程 ≥50 ⟹ needle 字节游程 ≥57（共享子串 ≥57 字符 ⇒ ≥57 字节）
    #             ⟹ 文件 union 字节游程 ≥57 ⟹ 文件出现计数 ≥57（连续 ⊆ 非连续）
    DIAG = 30        # 诊断解析下限（每针游程 ≥30 的对做官方精确解析，报告 Top 对）
    GATE_BYTE = 57   # 门禁预筛下限（上链必要条件）
    doc_norm_map = dict(doc_norms)
    union_pairs = []          # (fur, rid, fid)：文件级 union 连续游程 ≥DIAG 的对
    n_docs_ge30 = 0
    for di, (rid, dn) in enumerate(doc_norms):
        if di % 1000 == 0:
            print(f"  [G9] 阶段1 扫描 {di}/{len(doc_norms)} …", flush=True)
        dw = _byte_windows(dn.encode("utf-8"))
        if not len(dw):
            continue
        il = np.searchsorted(W_sorted, dw, side="left")
        ir = np.searchsorted(W_sorted, dw, side="right")
        present = il < ir
        npresent = int(present.sum())
        if npresent < DIAG:
            continue
        n_docs_ge30 += 1
        starts, lens = il[present], (ir - il)[present]
        total = int(lens.sum())
        offs = np.arange(total) - np.repeat(np.concatenate(([0], np.cumsum(lens)[:-1])), lens)
        FL = F_sorted[np.repeat(starts, lens) + offs]
        pos_idx = np.repeat(np.arange(npresent), lens)
        cnt = np.bincount(FL, minlength=len(needle_files))
        cand = np.nonzero(cnt >= DIAG)[0]
        if not len(cand):
            continue
        M = np.zeros((len(needle_files), npresent), dtype=bool)   # (文件 × present 位置)
        M[FL, pos_idx] = True
        for fid in cand:
            if fid not in file_windows:
                continue
            row = M[fid]
            padded = np.concatenate(([False], row, [False])).view(np.int8)
            d = np.diff(padded)
            fur = int((np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]).max())
            if fur >= DIAG:
                union_pairs.append((fur, rid, int(fid)))
    union_pairs.sort(reverse=True)
    fur_vals = [u[0] for u in union_pairs]
    g.num("present≥30 文档数", n_docs_ge30)
    g.num("文件级 union≥30 对数", len(union_pairs))
    g.num("文件级 union 游程分布", {
        "max": max(fur_vals) if fur_vals else 0,
        f"≥{GATE_BYTE}": sum(1 for v in fur_vals if v >= GATE_BYTE),
        "≥50": sum(1 for v in fur_vals if v >= 50),
        "≥40": sum(1 for v in fur_vals if v >= 40)})

    # ---- 阶段2 门禁层：union ≥GATE_BYTE 的对 → 逐 needle 字节游程（向量化）→ ≥57 者
    #     官方 doc_probe_hits(50) 精确 char-gram 游程 + verify_shared_substring LCS 判真
    nwins_cache = {}   # fid -> [每 needle 排序去重 S8 窗口数组]

    def _nwins(fid):
        if fid not in nwins_cache:
            nwins_cache[fid] = [np.unique(_byte_windows(t.encode("utf-8")))
                                for t in file_windows[fid][1]]
        return nwins_cache[fid]

    def _max_run(bool_row):
        padded = np.concatenate(([False], bool_row, [False])).view(np.int8)
        d = np.diff(padded)
        return int((np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]).max())

    official_hits = []
    dw_cache = {}
    gate_pair_count = 0
    for fur, rid, fid in union_pairs:
        if fur < GATE_BYTE:
            break
        gate_pair_count += 1
        if rid not in dw_cache:
            dw_cache[rid] = _byte_windows(doc_norm_map[rid].encode("utf-8"))
        dw = dw_cache[rid]
        dn = doc_norm_map[rid]
        for ni, nw in enumerate(_nwins(fid)):
            if not len(nw):
                continue
            idx = np.searchsorted(nw, dw, side="left")
            ok = idx < len(nw)
            if not ok.any():
                continue
            pr = np.zeros(len(dw), dtype=bool)
            pr[ok] = nw[idx[ok]] == dw[ok]
            if not pr.any() or _max_run(pr) < GATE_BYTE:
                continue
            # 字节游程 ≥57：官方 char-gram 口径精确裁决（单 needle 索引，代价小）
            texts = file_windows[fid][1]
            idx1 = {}
            for gr in set(ngrams(texts[ni], NGRAM_N, 1)):
                idx1[gr] = [ni]
            hits = doc_probe_hits(dn, idx1, threshold=NGRAM_PREFILTER, n=NGRAM_N)
            for _ni, (run, run_end) in hits.items():
                lcs = verify_shared_substring(dn, texts[_ni], min_chars=LCS_MIN_CHARS,
                                              window=(run, run_end))
                official_hits.append((rid, f"{fid_of[fid]}#{_ni}", run, lcs))
                if lcs >= LCS_MIN_CHARS:
                    g.fail(f"官方污染命中：{rid} ↔ {fid_of[fid]}#{_ni} 游程 {run} gram / LCS {lcs} 字符")
    if official_hits:
        g.fail(f"存在官方 char-gram 游程 ≥{NGRAM_PREFILTER} 的 (doc,needle) 对（即使 LCS<{LCS_MIN_CHARS} "
               f"亦属越线预筛，需人工裁决）")
    g.num(f"union≥{GATE_BYTE} 门禁对数", gate_pair_count)
    g.num("官方游程 ≥50 对数（验证后）", len(official_hits))

    # ---- 阶段3 诊断层：全局倒排索引 · 官方语义逐 needle 精确游程全景（threshold=DIAG）
    # 与门禁层交叉验证：诊断层若发现 ≥NGRAM_PREFILTER 的游程而门禁层未拦截 ⇒ 门禁实现缺陷 ⇒ FAIL
    del W_sorted, F_sorted
    nwins_cache.clear()
    dw_cache.clear()
    gidx = {}                 # gram → [全局 needle id]
    g_needles = []            # gid → (fid, ni)
    for fid in sorted(file_windows):
        for ni, t in enumerate(file_windows[fid][1]):
            gid = len(g_needles)
            g_needles.append((fid, ni))
            for gr in set(ngrams(t, NGRAM_N, 1)):
                gidx.setdefault(gr, []).append(gid)
    diag_runs = []
    for di, (rid, dn) in enumerate(doc_norms):
        if di % 1000 == 0:
            print(f"  [G9] 阶段3 全景扫描 {di}/{len(doc_norms)} …", flush=True)
        hits = doc_probe_hits(dn, gidx, threshold=DIAG, n=NGRAM_N)
        for gid, (run, run_end) in hits.items():
            fid, ni = g_needles[gid]
            diag_runs.append((run, rid, fid_of[fid], f"{fid_of[fid]}#{ni}"))
            if run >= NGRAM_PREFILTER:      # 门禁层已证不存在；出现即门禁实现矛盾
                g.fail(f"门禁/诊断矛盾：{rid} ↔ {fid_of[fid]}#{ni} 游程 {run} ≥{NGRAM_PREFILTER} "
                       f"未被门禁层拦截（实现缺陷，需排查）")
    diag_runs.sort(reverse=True)
    g.num("每针最大游程（全量官方精确解析，gram）", diag_runs[0][0] if diag_runs else 0)
    g.num(f"游程 ≥{DIAG} 的 (doc,needle) 对数", len(diag_runs))
    g.num("Top 每针游程对", [(r, d, f, n) for r, d, f, n in diag_runs[:5]])
    # Top3 对 LCS 诊断（全文字符级，判真阈值 {LCS_MIN_CHARS} 的对照全景）
    lcs_diag = []
    for run, rid, fkey, nkey in diag_runs[:3]:
        dn = doc_norm_map[rid]
        fid = [k for k, v in fid_of.items() if v == fkey][0]
        texts = file_windows[fid][1]
        ni = int(nkey.split("#")[-1])
        lcs = verify_shared_substring(dn, texts[ni], min_chars=10**9)
        lcs_diag.append((rid, nkey, run, lcs))
    g.num("Top3 对 LCS 诊断（字符）", lcs_diag)
    g.note(f"方法（无损分层）：needle/heldout 全量归一化 + 白名单双侧剥离 → 8 字节窗口 S8 全局排序数组 + 文件 "
           f"id；每文档 present≥{DIAG} 者构造 文件×位置 密集布尔阵，直接读出各文件 union 连续游程。门禁层：union "
           f"≥{GATE_BYTE}（官方 char 游程 ≥{NGRAM_PREFILTER} ⟹ 字节游程 ≥57 ⟹ union ≥57 的必要条件链）→ 逐 "
           f"needle 向量化字节游程 → ≥57 者以官方 doc_probe_hits({NGRAM_PREFILTER}) 精确 char-gram 游程 + "
           f"verify_shared_substring（窗口有界 difflib LCS ≥{LCS_MIN_CHARS} 字符判真）。诊断层：全局倒排索引对全部 "
           f"5,760 行 × 12,460 needle 做官方语义逐针精确游程（threshold={DIAG}），与门禁层交叉验证（发现 ≥"
           f"{NGRAM_PREFILTER} 即矛盾 FAIL）并给出真实全景（最大游程与 Top 对，对照官方向 50/60 的裕度）")
    g.num("样板构建+扫描耗时", f"{time.time()-t0:.0f}s")
    return g


# ================================================================ G10 ==
def gate_g10() -> Gate:
    g = Gate("G10", "F4 编码变形 / F6 权限伪造官方清单复检零命中 + 保守签名复扫")
    # 官方清单 ast 机器校验（漂移即 FAIL：官方事实源必须原位）
    try:
        tree = ast.parse(open(JAILBREAK_SUITE, encoding="utf-8").read())
    except Exception as e:
        g.fail(f"check_jailbreak_suite.py 解析失败：{e}")
        return g
    src_lists = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in ("F4_SIG", "F6_SIG"):
                    try:
                        src_lists[tgt.id] = ast.literal_eval(node.value)
                    except Exception:
                        pass
    if src_lists.get("F4_SIG") != F4_SIG:
        g.fail(f"F4_SIG 与官方源不一致：内嵌 {len(F4_SIG)} 条 vs 源 {len(src_lists.get('F4_SIG', []))} 条（漂移）")
    if src_lists.get("F6_SIG") != F6_SIG:
        g.fail(f"F6_SIG 与官方源不一致：内嵌 {len(F6_SIG)} 条 vs 源 {len(src_lists.get('F6_SIG', []))} 条（漂移）")
    g.num("官方签名（ast 校验一致）", f"F4 {len(F4_SIG)} 条 / F6 {len(F6_SIG)} 条")
    # 全字段扫描
    off_hits, cons_hits, wpn_hits = [], [], []
    for r in ROWS:
        rid = r["id"]
        texts = [t["value"] for t in r["conversations"]] + [r["chosen"]["value"], r["rejected"]["value"]]
        all_text = "\n".join(texts) + "\n" + json.dumps({k: r[k] for k in
                    ("id", "pack", "lang", "polarity", "rejected_form", "archetype_id", "src_task", "dpo_class")},
                    ensure_ascii=False)
        for sig in F4_SIG:
            if sig in all_text:
                off_hits.append((rid, f"F4:{sig}"))
        for sig in F6_SIG:
            if sig in all_text:
                off_hits.append((rid, f"F6:{sig}"))
        # 保守复扫（两批自建版合并；parts 声明零命中 ⇒ 合并件必须同样零命中）
        if ZW_RE.search(all_text):
            cons_hits.append((rid, "zero-width"))
        m = B64_RE.search(all_text)
        if m:
            cons_hits.append((rid, f"b64-run:{m.group(0)[:12]}…"))
        m = CIPHER_RE.search(all_text)
        if m:
            cons_hits.append((rid, f"cipher-span:{m.group(0)[:12]}…"))
        for w in OBF_WORDS:
            if w in all_text:
                cons_hits.append((rid, f"obf-word:{w}"))
        for rex in CEF_F4F6_RES:
            m = rex.search(all_text)
            if m:
                cons_hits.append((rid, f"cef-pattern:{rex.pattern[:24]}"))
        # 零武器化（族F 全字段，CEF 批口径）
        if fam(r) == "F":
            low = all_text.lower()
            wm = [mk for mk in WEAPON_MARKERS if mk.lower() in low]
            if wm:
                wpn_hits.append((rid, wm[:4]))
    if off_hits:
        g.fail(f"官方 F4/F6 签名命中：{off_hits[:8]}（共 {len(off_hits)}）")
    if cons_hits:
        g.fail(f"保守签名命中（parts 声明零命中被推翻）：{cons_hits[:8]}（共 {len(cons_hits)}）")
    if wpn_hits:
        g.fail(f"族F 零武器化命中：{wpn_hits[:8]}（共 {len(wpn_hits)}）")
    g.num("官方命中", 0 if not off_hits else len(off_hits))
    g.num("保守复扫命中", 0 if not cons_hits else len(cons_hits))
    g.num("F 零武器化命中", 0 if not wpn_hits else len(wpn_hits))
    g.note("留出族输入参数 = v0.7 README 红线两族（F4 编码变形 / F6 权限伪造）；官方事实源 = "
           "scripts/check_jailbreak_suite.py F4_SIG/F6_SIG（B3 口径：训练混料中不得出现的对话式越狱结构标记），"
           "本门内嵌副本经 ast 对源文件机器校验一致（漂移即 FAIL）；两批 parts 自建签名（ABD 启发式 + CEF 正则版）"
           "仅保守版，本门合并复扫同样零命中")
    return g


# ================================================================ G11 ==
def gate_g11() -> Gate:
    g = Gate("G11", "每原型条数上限 + 族内全行精确重复=0 + m3 口径相似度全景")
    try:
        import numpy as np
        import scipy.sparse as sp
    except Exception as e:
        g.fail(f"scipy/numpy 不可用：{e}")
        return g
    # G11a 每原型上限
    per_arch = defaultdict(list)
    for r in ROWS:
        per_arch[(fam(r), r["archetype_id"])].append(r["id"])
    cap_hits = []
    for (f, a), ids in per_arch.items():
        if len(ids) > G11_CAPS[f]:
            cap_hits.append((f, a, len(ids)))
    if cap_hits:
        g.fail(f"每原型条数超上限：{cap_hits[:6]}（共 {len(cap_hits)}）")
    arch_cnt = {f: len({a for (ff, a) in per_arch if ff == f}) for f in "ABCDEF"}
    arch_max = {f: max(len(v) for (ff, a), v in per_arch.items() if ff == f) for f in "ABCDEF"}
    g.num("原型数/族", arch_cnt)
    g.num("每原型最大条数/族", arch_max)
    # G11b 族内全行精确重复（内容哈希：conversations+chosen+rejected+审计键除 id）
    seen = {}
    dups = []
    for r in ROWS:
        c = dict(r)
        c.pop("id")
        h = hashlib.sha256(json.dumps(c, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        k = (fam(r), h)
        if k in seen:
            dups.append((seen[k], r["id"]))
        else:
            seen[k] = r["id"]
    if dups:
        g.fail(f"族内全行精确重复：{dups[:6]}（共 {len(dups)}）")
    g.num("全行精确重复", len(dups))
    # G11c m3 口径相似度全景（prompt 8-gram 集合包含度；诊断报告，不设零容忍）
    land = {}
    for f in "ABCDEF":
        rows_f = [r for r in ROWS if fam(r) == f]
        grams_sets = []
        vocab = {}
        for r in rows_f:
            p = normalize("\n".join(t["value"] for t in r["conversations"] if t["from"] != "system"))
            gs = set(ngrams(p, NGRAM_N, 1))
            grams_sets.append(gs)
            for x in gs:
                vocab.setdefault(x, len(vocab))
        n = len(rows_f)
        if n < 2:
            land[f] = {"rows": n}
            continue
        indptr, indices = [0], []
        for gs in grams_sets:
            indices.extend(sorted(vocab[x] for x in gs))
            indptr.append(len(indices))
        X = sp.csr_matrix((np.ones(len(indices), dtype=np.int32), indices, indptr), shape=(n, len(vocab)))
        lens = np.array([len(gs) for gs in grams_sets])
        Gm = (X @ X.T).tocoo()
        mins = np.minimum(lens[Gm.row], lens[Gm.col])
        cont = Gm.data / np.maximum(mins, 1)
        pair_mask = Gm.row < Gm.col
        hist = {}
        for th in (0.7, 0.9, 0.95, 0.97):
            hist[str(th)] = int(((cont >= th) & pair_mask).sum())
        land[f] = {"rows": n, "pairs>=th": hist}
    g.num("m3 口径包含度全景（诊断）", land)
    # C 族全上下文碰撞（同 prompt 不同 chosen）诊断
    pk = defaultdict(list)
    for r in ROWS:
        if fam(r) == "C":
            pk["\n".join(t["value"] for t in r["conversations"])].append(r["id"])
    c_coll = {k[:24]: v for k, v in pk.items() if len(v) > 1}
    g.num("C 族同上下文碰撞组", len(c_coll))
    g.note(f"口径说明：m3 的包含度 ≥0.7 零容忍为 SFT 留用去重而设；p16 §4.3 网格**有意**复用原型+槽位旋转"
           f"（判断句模板含 2 槽位、tail 轮换），原型级相似是设计使然，故 G11 主判 = 每原型上限"
           f"（A–E 30 / F 48，§4.3 网格下限的整倍）+ 全行精确重复零容忍；m3 口径数字仅作全景登记。"
           f"C 族 {len(c_coll)} 组同上下文碰撞（VERDICT confidence/pad 轮换差异）为显性质量观察，"
           f"已列为人工抽查重点，非门禁 FAIL 项")
    return g


# ================================================================ G12 ==
def gate_g12() -> Gate:
    g = Gate("G12", "manifest 冻结校验（sha256 / 分布闭合 / 谱系链 / 版本纪律）")
    if not os.path.exists(MANIFEST):
        g.fail("manifest.json 不存在")
        return g
    man = json.loads(open(MANIFEST, encoding="utf-8").read())
    # 文件 sha256 闭合
    for fname, key in (("p16_benign_release.jsonl", REL_BENIGN), ("p16_malicious_honest.jsonl", REL_MALICIOUS)):
        sha = sha256_file(key)
        want = man.get("files", {}).get(fname, {}).get("sha256")
        rows = man.get("files", {}).get(fname, {}).get("rows")
        got_rows = len(ROWS_B if "benign" in fname else ROWS_M)
        if sha != want:
            g.fail(f"{fname} sha256 与 manifest 不符：{sha[:16]}… != {str(want)[:16]}…")
        if rows != got_rows:
            g.fail(f"{fname} rows {got_rows} != manifest {rows}")
        g.num(fname, f"rows {got_rows} · sha256 …{sha[:16]}")
    # 分布闭合（manifest 自报分布 == 复算分布）
    pol = Counter(r["polarity"] for r in ROWS)
    if man.get("polarity_balance") != {"benign_release": pol["benign_release"],
                                       "malicious_refuse": pol["malicious_refuse"]}:
        g.fail(f"polarity_balance 不闭合：{man.get('polarity_balance')}")
    d = man.get("distributions", {})
    for f in "ABCDEF":
        got_lang = dict(Counter(r["lang"] for r in ROWS if fam(r) == f))
        if d.get("by_family", {}).get(f, {}).get("lang") != got_lang:
            g.fail(f"manifest 族 {f} lang 分布不闭合")
    a_sub = dict(Counter(r["src_task"] for r in ROWS if fam(r) == "A"))
    if d.get("a_subdomain") != a_sub:
        g.fail(f"manifest A 子域分布不闭合：{d.get('a_subdomain')} != {a_sub}")
    # 谱系链：parts sha256 == 实测
    lin = man.get("lineage", {})
    for part_key, part_file in (("parts_abd", os.path.join(P16_DIR, "parts-abd.jsonl")),
                                ("parts_cef", os.path.join(P16_DIR, "parts-cef.jsonl"))):
        entry = lin.get(part_key, {})
        sha = sha256_file(part_file)
        if entry.get("sha256") != sha:
            g.fail(f"{part_key} 谱系 sha256 与实测不符")
        mf = entry.get("manifest")
        if mf and sha256_file(os.path.join(ROOT, mf)) != entry.get("manifest_sha256"):
            g.fail(f"{part_key} parts-manifest sha256 与实测不符")
    # 版本纪律 / 接线 / 抽查登记字段
    for field in ("version_discipline", "gate_registration", "launch_audit_wiring", "spotcheck", "normalization"):
        if field not in man:
            g.fail(f"manifest 缺字段 {field}")
    if "p16b" not in man.get("version_discipline", ""):
        g.fail("manifest version_discipline 未登记 p16b 版本目录纪律")
    # 模板哈希登记
    want_tpl = {f"{p}/{l}": h for (p, l), h in FROZEN_TEMPLATE_SHA256.items()}
    if man.get("pack_templates_sha256") != want_tpl:
        g.fail("manifest pack_templates_sha256 与冻结表不符")
    # README 存在
    if not os.path.exists(os.path.join(P16_DIR, "README.md")):
        g.fail("README.md（结账记录）不存在")
    g.num("manifest 冻结 sha256", f"…{sha256_file(MANIFEST)[:16]}")
    g.note("冻结 = manifest.json 全文 sha256；谱系链 parts-abd/parts-cef → 各自 9+10 子批次 → m4 基座模板，"
           "逐级 sha256 实测闭合；任何修改 ⇒ 新开 data/dpo/p16b-calibration/（manifest.version_discipline 登记）")
    return g


# ================================================================ 主流程 ==
def main() -> int:
    gates = []
    for fn in (gate_g1, gate_g2, gate_g3, gate_g4, gate_g5, gate_g6,
               gate_g7, gate_g8, gate_g9, gate_g10, gate_g11, gate_g12):
        t0 = time.time()
        try:
            g = fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            g = Gate(fn.__name__.replace("gate_", "").upper(), fn.__name__)
            g.fail(f"门禁执行异常：{type(e).__name__}: {e}")
        gates.append(g)
        print(f"[{g.gid}] {'PASS' if g.ok else 'FAIL'}  {g.title}（{time.time()-t0:.0f}s）")
        for msg in g.fails[:5]:
            print(f"    ✗ {msg}")
    overall = all(g.ok for g in gates)
    verdict = "PASS" if overall else "FAIL"

    # ---- 报告
    rel_sha = {f: sha256_file(p) for f, p in (("p16_benign_release.jsonl", REL_BENIGN),
                                              ("p16_malicious_honest.jsonl", REL_MALICIOUS))}
    L = []
    L.append("# P1.6 拒绝校准对 · G1–G12 统一防污染门禁报告")
    L.append("")
    L.append(f"- 判定：**P16-GATE={verdict}**（fail-closed：任一门 FAIL 即整体 FAIL、停止发射链）")
    L.append(f"- 被检对象：`data/dpo/p16-calibration/p16_benign_release.jsonl`（2,880 行，"
             f"sha256 `{rel_sha['p16_benign_release.jsonl'][:16]}…`）+ `p16_malicious_honest.jsonl`"
             f"（2,880 行，sha256 `{rel_sha['p16_malicious_honest.jsonl'][:16]}…`）")
    L.append("- 门禁实现：`scripts/check_p16_calibration.py`（本脚本自包含复跑：退出码 0/1 = PASS/FAIL）")
    L.append(f"- 输入谱系：parts-abd 2,460 + parts-cef 3,300（两级 manifest sha256 闭合，G12）")
    L.append("")
    L.append("| 门 | 判定 | 标题 |")
    L.append("|---|---|---|")
    for g in gates:
        L.append(f"| {g.gid} | {'✅ PASS' if g.ok else '❌ FAIL'} | {g.title} |")
    L.append("")
    for g in gates:
        L.append(f"## {g.gid} {g.title} — {'PASS' if g.ok else 'FAIL'}")
        L.append("")
        for label, value in g.info:
            L.append(f"- **{label}**：{value}")
        if g.fails:
            L.append("")
            L.append("失败项：")
            for msg in g.fails:
                L.append(f"- ✗ {msg}")
        if g.notes:
            L.append("")
            for n in g.notes:
                L.append(f"> {n}")
        L.append("")
    # ---- 登记与待办
    L.append("## 登记与待办（非门禁项）")
    L.append("")
    L.append("1. **launch_audit 接线登记**：`scripts/launch_audit.py` 尚不存在（2026-10-08 实查，不猜 ✗）。"
             "P1.8 建成后必须：①串接本脚本退出码（无 `P16-GATE=PASS` 输出即拒绝发射，fail-closed）；"
             "②将两个 release 文件 sha256 纳入发射审计基座登记（§8.7 归因可溯）。已登记 "
             "`manifest.json` `launch_audit_wiring`。")
    L.append("2. **人工抽查关口**：`reports/p16-spotcheck.md`（15 行/族 × 6 = 90 行）为 §6 人工关口，"
             "状态 PENDING_HUMAN_GATE；parts 批已出 `p1.6-spotcheck-abd.md` + `p1.6-spotcheck-cef.md`。"
             "G4 槽位软通过 13 行（见 G4 节）与 C 族同上下文碰撞 41 行（见 G11 节）应纳入抽查重点。")
    L.append("3. **质量观察（非阻塞）**：F 载体载荷模式 48（16 模式 × 3 机理）低于设计 §4.3 下限 ≥30/机理"
             "的口径合计 ≥90；F 对话式 40 场景 × 4 风格 = 160 组合中实取 40 场景原型低于 ≥160 组合的宽松读法；"
             "A 原型 192（按 archetype_id 计）低于 ≥200 下限。均为批次已验收设计权衡（登记于 parts manifests），"
             "M5 观察期若 E/F 迁移不足，后备为 p16b 增补而非门禁阻塞。")
    L.append("4. **CEF en 行使用 zh 模板**：批次既定设计（manifest-cef.json 登记），system 模板三包均通过"
             "sha256 冻结断言（G2/G12），pack 标记与行 pack 一致。")
    L.append("5. **前缀轮 assistant→gpt 归一**：1,007 轮（CEF 多轮行），登记 `manifest.normalization`；"
             "LLaMA-Factory dataset_info 口径 user_tag=human / assistant_tag=gpt。")
    L.append("6. **M5 发射集成**：`data/m5-run/dpo_m5_calib.jsonl`（基座 28,842 + 本包 5,760）与 "
             "`dataset_info.json` 注册 `sec_dpo_m5_calib` 属 P2.9 职责，不在本件范围。")
    L.append("")
    L.append("## 结论")
    L.append("")
    L.append(f"12 门全量复检完成：**P16-GATE={verdict}**。")
    if not overall:
        L.append("")
        L.append("> fail-closed：存在 FAIL 门，停止发射链后续步骤；修复须新开 p16b 版本目录重走本门。")
    L.append("")
    L.append("P16-MERGE-GATE=DONE")
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print(f"\n[report] {os.path.relpath(REPORT, ROOT)}")
    print(f"P16-GATE={verdict}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
