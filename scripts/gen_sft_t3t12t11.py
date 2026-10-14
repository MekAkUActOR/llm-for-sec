r"""fE staging generator: T3-risk / T12-policyqa / T11-calibration 扩容（m2.5-staging）.

种子 20260928，确定性（无 wall-clock / 无 dict 序依赖 / 全部 sorted）。
输出：data/sft/m2.5-staging/fE_t3t12t11.jsonl（行契约 = m1：{id,task,pack,lang,messages}）

配额（±10% 硬断言，目标精确值）：
  T3-risk      2,000  = KEV 池余量 900（m1 已用 700/1,721 剔除）+ debian-dsa 550 + redhat-csaf 550
                      （CSAF 分层 Critical100/Important200/Moderate150/Low100）
                      风险分级 medium/low 首填（m1 只有 high/critical）
  T12-policyqa 2,000  = grounded 1,500（GDPR 序言 173 + 800-53 控制项 76 + 保密法条文 ~65 +
                      OWASP LLM 段落 ~128 + RTG/NIST-PF/SP800-188/FIPS199/SP800-171/
                      AI600-1/AI-RMF/SP800-226/OWASP 附录 摘录，配额见 T12_DOC_EXCERPTS，
                      源不足自适应溢出再分配）
                      + ungrounded 负例 500（≥400 硬断言；不存在条款/框架错配/语料外文档/
                      超范围细节四类，全部经"关键词缺席断言"防幻觉）
  T11-calibration 500 = 授权不明 170 / 范围不明 165 / 时效不明 165（降级澄清，不臆测授权）

行式：照抄 m1 同族结构与 VERDICT 惯例
  T3  user=公开漏洞/通告情报（Summary 逐字取自源语料条目）问风险分级与处置优先级；
      assistant=暴露/利用状态/勒索关联/紧迫度/建议 + VERDICT report
  T12 user=政策问题（grounded 附原文片段；ungrounded 无片段）；
      assistant=要点+引用（grounded）或 不足以 grounding 声明+缺什么（insufficient-context）
  T11 user=缺语境安全请求；assistant=降级澄清关键缺失维度 + VERDICT insufficient-context

生产硬断言（生成后对落盘文件复检，任一失败 → 退出码 1）：
  1. 行数=族配额精确值（±10% 内）；三族字段集/消息结构/pack=default
  2. T12 grounded：引用片段是源语料文件文本的逐字子串；ungrounded：负例关键词
     确不存在于目标语料（生成时逐条 + 复检时按题面重建断言）；user 无 "(Policy text:" 片段
  3. T3：Summary 摘要是源语料条目文本的逐字子串（条目按 id 从语料文件单遍索引定位）
  4. ungrounded ≥ 400；T3 medium≥300 且 low≥250（首填目标）
  5. assistant 100% 以 VERDICT 行结尾（JSON 可解析、policy==pack、action/verdict 合法）
  6. zh:en = 1800:2700（40:60）；zh 行 user ≥10 CJK；en 行 user+assistant 零 CJK
  7. id 唯一；user 全文唯一；与 m1 全量 user 零同文
  8. T11 三轴各 ≥100 且全为 insufficient-context

红线遵守：data/lf/ 只读；probes/heldout 不读；全程 CPU、无网络。

用法：
  .venv\Scripts\python.exe scripts/gen_sft_t3t12t11.py                 # 全部三族
  .venv\Scripts\python.exe scripts/gen_sft_t3t12t11.py --family t12    # 单族（保留他族已有行）
  .venv\Scripts\python.exe scripts/gen_sft_t3t12t11.py --check-only    # 只复检已落盘文件
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "corpora" / "clean"
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
M1 = ROOT / "data" / "lf" / "sft_m1.jsonl"
CACHE = ROOT / ".cache" / "m1_refs_t3t12t11.json"
REPORTS = ROOT / "reports"
SEED = 20260928

# ---- m1 逐字系统提示（照抄，勿改动） ----------------------------------------
SYS_EN = ("You are a security-perception assistant. Active policy pack: pack:default@0.1.\n"
          "Adjustable band: P-DUALUSE-GRANULARITY=mixed; P-REQUESTER-TIER-MINIMUM=verified; "
          "P-CONTEXT-THRESHOLD=medium; P-ACTION-PERMISSIONS=propose; P-REFUSAL-STYLE=explanatory.\n"
          "Hard floor: HF-001~HF-006 (same as conservative).\n"
          "Direction invariant: de-protection is always refused.\n"
          "High-risk operations may only be proposed for human confirmation.\n"
          "End your reply with a VERDICT line.")
SYS_ZH = ("你是安全感知助手。激活政策包：pack:default@0.1。\n"
          "可调带：P-DUALUSE-GRANULARITY=mixed；P-REQUESTER-TIER-MINIMUM=verified；"
          "P-CONTEXT-THRESHOLD=medium；P-ACTION-PERMISSIONS=propose；P-REFUSAL-STYLE=explanatory。\n"
          "硬底线（不可被任何政策覆盖）：HF-001~HF-006（CSAM/CBRN/自伤指引/注入执行/无授权定向攻击/硬法）。\n"
          "方向性不变量：去保护方向一律拒绝。\n"
          "高危操作只可提议、由人确认执行。\n"
          "输出必须以 VERDICT 行结尾。")

# ---- 配额 --------------------------------------------------------------------
FAM_TOTAL = {"t3": 2000, "t12": 2000, "t11": 500}
FAM_ZH = {"t3": 800, "t12": 800, "t11": 200}          # 40:60
T3_SRC = {"kev": 900, "dsa": 550, "csaf": 550}
T3_SRC_ZH = {"kev": 360, "dsa": 220, "csaf": 220}
CSAF_STRATA = {"Critical": 100, "Important": 200, "Moderate": 150, "Low": 100}
T12_GROUNDED = 1500
T12_GROUNDED_ZH = 600
T12_UNGROUNDED = 500
T12_UNG_ZH = 200
T11_AXIS = {"auth-unclear": 170, "scope-unclear": 165, "validity-unclear": 165}
T11_AXIS_ZH = {"auth-unclear": 68, "scope-unclear": 66, "validity-unclear": 66}

CJK = re.compile(r"[\u4e00-\u9fff]")
RCE_RE = re.compile(r"(remote code execution|arbitrary code execution|execute arbitrary code)", re.I)

# =====================================================================
# 语料加载
# =====================================================================

def load_texts(fn: str) -> list[str]:
    out = []
    with open(CLEAN / fn, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line)["text"])
    return out


def m1_refs() -> tuple[set[str], set[str]]:
    """(m1 全量 user 哈希, m1 T3 已用 KEV CVE 集)。带 mtime/size 校验的磁盘缓存。"""
    stat = M1.stat()
    key = {"mtime": stat.st_mtime, "size": stat.st_size}
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("src") == key:
                return set(cached["user_hashes"]), set(cached["kev_used"])
        except Exception:
            pass
    user_hashes, kev_used = set(), set()
    with open(M1, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            msgs = d.get("messages", [])
            u = next((m["content"] for m in msgs if m.get("role") == "user"), None)
            if u is not None:
                user_hashes.add(hashlib.sha256(u.encode("utf-8")).hexdigest())
            t = d.get("task", "")
            if t.startswith("T3-risk:kev:"):
                kev_used.add(t.split(":", 2)[2])
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"src": key, "user_hashes": sorted(user_hashes),
                                 "kev_used": sorted(kev_used)}), encoding="utf-8")
    return user_hashes, kev_used


# =====================================================================
# 通用工具
# =====================================================================

def verdict_line(action: str, verdict, confidence: float, findings: list[str]) -> str:
    return "VERDICT: " + json.dumps(
        {"action": action, "verdict": verdict, "confidence": confidence,
         "findings": findings, "policy": "default"}, ensure_ascii=False)


def sentence_head(snippet: str, limit: int = 300) -> str:
    """片段开头句（逐字），最多 limit 字符。英文按 ". " 句界，中文按 "。：；" 句界。"""
    if len(snippet) <= limit:
        return snippet
    cjk = len(CJK.findall(snippet)) >= 10
    cut = snippet.rfind(". ", 80, limit)
    if cut == -1 and cjk:
        for sep in ("。", "：", "；"):
            cut = snippet.rfind(sep, 40, limit)
            if cut != -1:
                break
    if cut == -1:
        return snippet[:limit]
    return snippet[:cut + 1]


def cut_verbatim(text: str, start: int, lo: int, hi: int, min_periods: int = 1) -> str | None:
    """从 text[start:] 取逐字摘要：推进到词界，句子边界截断，长度 [lo, hi+150]。"""
    n = len(text)
    if start >= n - lo:
        return None
    while start < n and start > 0 and text[start - 1] not in " \n\t":
        start += 1
    seg = text[start:min(n, start + hi + 150)]
    cut = seg.rfind(". ", lo - 1, hi + 150)
    if cut == -1:
        cut = seg.find(". ", lo - 1)
    if cut == -1:
        return None
    piece = text[start:start + cut + 1]
    if not (lo <= len(piece) <= hi + 150):
        return None
    if not piece[0].isupper():
        return None
    if "|" in piece or "http" in piece or piece.count(". ") < min_periods:   # 拒绝表格/链接清单/碎片
        return None
    ok = sum(c.isalpha() or c in " ,.;:'()\"-" for c in piece) / len(piece)
    if ok < 0.85 or CJK.search(piece):
        return None
    return piece


def assign_langs(items: list, zh_count: int, rng: random.Random) -> list[str]:
    idx = list(range(len(items)))
    rng.shuffle(idx)
    zh_set = set(idx[:zh_count])
    return ["zh" if i in zh_set else "en" for i in range(len(items))]


# =====================================================================
# T3 风险评估
# =====================================================================

KEV_RE = re.compile(
    r"^(CVE-\d{4}-\d+) \(CISA KEV, known exploited, added (\d{4}-\d{2}-\d{2})\): "
    r"(.+?)\. Product: (.+?)\. (.+)$", re.S)
DSA_HEAD_RE = re.compile(r"\[(DSA[- ]\d{3,4}-\d+)\]")
DSA_DATE_RE = re.compile(r"\([A-Za-z]{3}, (\d{1,2} [A-Za-z]{3} \d{4})")
CSAF_HEAD_RE = re.compile(r"^Red Hat Security Advisory (RHSA-\d{4}:\d+):\s*(.*?)\s*\((\d{4}-\d{2}-\d{2})\)", re.M)

LOW_KWS = ["symlink", "temporary file", "race condition", "information leak",
           "information disclosure", "memory leak", "brute force", "insecure default",
           "default password", "insecure permissions", "file permissions"]


def parse_kev(text: str):
    m = KEV_RE.match(text)
    if not m:
        return None
    desc = m.group(5).strip()
    if len(desc) < 100 or CJK.search(desc):
        return None
    if len(desc) > 700:                       # 逐字截断到句界
        cut = desc.rfind(". ", 300, 700)
        desc = desc[:cut + 1] if cut != -1 else desc[:700]
    return {"cve": m.group(1), "added": m.group(2), "title": m.group(3),
            "product": m.group(4), "desc": desc}


def parse_dsa(text: str):
    if CJK.search(text[:2000]):
        return None
    head = DSA_HEAD_RE.search(text)
    if not head:
        return None
    dsa = head.group(1).replace("DSA ", "DSA-")
    pkg = re.search(r"^Package\s*:\s*(.+)$", text, re.M)
    cve = re.search(r"(CVE-\d{4}-\d+)", text)
    if not pkg or not cve:
        return None
    date = DSA_DATE_RE.search(text)
    marks = []
    for pat in (r"^Debian-specific\s*:.*$", r"^Debian Bug\s*:.*$", r"^CVE ID\s*:.*$"):
        mm = re.search(pat, text, re.M)
        if mm:
            marks.append(mm.end())
    if not marks:
        return None
    pos = max(marks)
    nl = text.find("\n", pos)
    pos = nl + 1 if nl != -1 else pos
    while pos < len(text) and text[pos] == "\n":
        pos += 1
    pt = re.search(r"^Problem type\s*:\s*(.+)$", text, re.M)
    desc = cut_verbatim(text, pos, 130, 560)
    if desc is None:
        return None
    return {"dsa": dsa, "package": pkg.group(1).strip(), "cve": cve.group(1),
            "date": date.group(1) if date else "", "desc": desc,
            "pt": pt.group(1).strip().lower() if pt else ""}


def parse_csaf(text: str):
    head = CSAF_HEAD_RE.search(text)
    sev = re.search(r"^Severity:\s*(\w+)", text, re.M)
    cve = re.search(r"(CVE-\d{4}-\d+)", text)
    if not head or not sev or not cve or sev.group(1) not in CSAF_STRATA:
        return None
    stop = len(text)
    for pat in (r"^Vulnerability CVE", r"^References", r"^Updated "):
        mm = re.search(pat, text[sev.end():], re.M)
        if mm:
            stop = min(stop, sev.end() + mm.start())
    desc = cut_verbatim(text, sev.end(), 130, 560)
    if desc is None:
        return None
    title = re.sub(r"^Red Hat Security Advisory:\s*:?\s*", "", head.group(2)).strip() or "security update"
    if len(title) > 110:
        title = title[:107] + "..."
    return {"rhsa": head.group(1), "title": title, "severity": sev.group(1),
            "cve": cve.group(1), "date": head.group(3), "desc": desc}


def tier_kev(desc: str) -> str:
    low = desc.lower()
    if RCE_RE.search(low) and "unauthenticated" in low:
        return "critical"
    return "high"


def tier_dsa(pt: str, desc: str) -> str:
    t = (pt + " " + desc).lower()
    if RCE_RE.search(t) and ("unauthenticated" in t or "remote" in t):
        return "high"
    dos = "denial of service" in t or "dos" in pt
    remote = "remote" in t
    if any(k in t for k in LOW_KWS):
        return "medium" if (dos and remote) else "low"
    return "medium"


def tier_csaf(sev: str) -> str:
    return {"Critical": "high", "Important": "medium", "Moderate": "low", "Low": "low"}[sev]


T3_KEV_U_EN = ("Given this public vulnerability intel (CISA KEV listed), produce a risk assessment: "
               "exposure, exploitation status, ransomware link, urgency, and a risk tier.\n\n"
               "CVE: {cve}\nProduct: {product}\nVuln: {title}\nAdded: {added}\n"
               "Ransomware use: {rw}\nSummary: {desc}")
T3_KEV_U_ZH = ("以下是一份公开漏洞情报（CISA KEV 收录）。给出风险评估：资产暴露、利用状态、勒索关联、紧迫度，"
               "并给出风险等级。\n\nCVE：{cve}\n产品：{product}\n漏洞：{title}\n收录日期：{added}\n"
               "勒索软件利用：{rw}\n描述：{desc}")

T3_A_EN = {
    "kev": {
        "critical": ("Exposure: {exposure}\nExploitation: KEV-listed = observed in the wild.\n"
                     "Ransomware link: {rwline}\nUrgency: emergency — in-the-wild exploitation with "
                     "unauthenticated remote code execution.\nRecommendation: apply vendor fixes now; "
                     "isolate exposed assets; add detection rules and hunt for compromise."),
        "high": ("Exposure: {exposure}\nExploitation: KEV-listed = observed in the wild.\n"
                 "Ransomware link: {rwline}\nUrgency: prioritize — confirmed in-the-wild.\n"
                 "Recommendation: patch per vendor advisory; if not immediately patchable, isolate "
                 "exposure and add detection rules."),
    },
    "adv": {
        "high": ("Exposure: {exposure}\nExploitation: no in-the-wild evidence in this advisory.\n"
                 "Urgency: prioritize — remote unauthenticated code-execution risk.\n"
                 "Recommendation: apply the vendor update as soon as practicable; restrict exposure "
                 "until patched."),
        "medium": ("Exposure: {exposure}\nExploitation: no in-the-wild evidence in this advisory.\n"
                   "Urgency: schedule within the normal patch window.\n"
                   "Recommendation: update per the advisory and track exploitation intel."),
        "low": ("Exposure: {exposure}\nExploitation: no in-the-wild evidence in this advisory.\n"
                "Urgency: address during routine maintenance.\n"
                "Recommendation: fix in the regular update cycle; no emergency action required."),
    },
}
T3_A_ZH = {
    "kev": {
        "critical": ("资产暴露：{exposure}\n利用状态：KEV 收录=已观测在野利用。\n勒索关联：{rwline}\n"
                     "紧迫度：紧急——在野利用且为未认证远程代码执行。\n"
                     "建议：立即应用厂商修复；隔离暴露资产；加检测规则并排查入侵痕迹。"),
        "high": ("资产暴露：{exposure}\n利用状态：KEV 收录=已观测在野利用。\n勒索关联：{rwline}\n"
                 "紧迫度：优先处置（在野利用确认）。\n建议：按厂商通告升级；无法立即修补时隔离暴露面并加检测规则。"),
    },
    "adv": {
        "high": ("资产暴露：{exposure}\n利用状态：该通告未提供在野利用证据。\n"
                 "紧迫度：优先处置（远程未认证代码执行风险）。\n建议：尽快应用厂商更新；修补前先限制暴露面。"),
        "medium": ("资产暴露：{exposure}\n利用状态：该通告未提供在野利用证据。\n"
                   "紧迫度：常规修补窗口内安排。\n建议：按通告更新，并跟踪利用情报。"),
        "low": ("资产暴露：{exposure}\n利用状态：该通告未提供在野利用证据。\n"
                "紧迫度：例行维护中处理。\n建议：随常规更新周期修复即可，无需紧急动作。"),
    },
}
T3_CONF = {"critical": 0.9, "high": 0.9, "medium": 0.85, "low": 0.8}


def t3_exposure(unit: dict, src: str, lang: str) -> str:
    hay = " ".join([unit.get("desc", ""), unit.get("pt", ""), unit.get("product", ""),
                    unit.get("title", ""), unit.get("severity", "")])
    remote = "remote" in hay.lower() or "unauthenticated" in hay.lower()
    if src == "kev":
        subj = unit["product"]
    elif src == "dsa":
        subj = f"{unit['package']} (Debian)"
    else:
        subj = unit["title"]
    if lang == "en":
        return f"{subj}; " + ("remote attack surface." if remote else "local/limited attack surface.")
    return f"{subj}，" + ("远程攻击面。" if remote else "本地/受限攻击面。")


def build_t3_unit_rows(units: list[dict], src: str, zh_count: int,
                       rng: random.Random) -> list[dict]:
    langs = assign_langs(units, zh_count, rng)
    rows = []
    for unit, lang in zip(units, langs):
        rw_hit = "ransom" in unit["desc"].lower()
        if src == "kev":
            tier = tier_kev(unit["desc"])
            finding, task = f"KEV:{unit['cve']}", f"T3-risk:kev:{unit['cve']}"
            if lang == "en":
                rw = "Referenced in the advisory text" if rw_hit else "Unknown"
                user = T3_KEV_U_EN.format(cve=unit["cve"], product=unit["product"],
                                          title=unit["title"], added=unit["added"], rw=rw,
                                          desc=unit["desc"])
                body = T3_A_EN["kev"][tier].format(
                    exposure=t3_exposure(unit, src, "en"),
                    rwline=rw if rw_hit else "Unknown")
            else:
                rw = "描述中提及勒索软件" if rw_hit else "Unknown"
                user = T3_KEV_U_ZH.format(cve=unit["cve"], product=unit["product"],
                                          title=unit["title"], added=unit["added"], rw=rw,
                                          desc=unit["desc"])
                body = T3_A_ZH["kev"][tier].format(
                    exposure=t3_exposure(unit, src, "zh"),
                    rwline="描述中提及勒索软件。" if rw_hit else "Unknown。")
        else:
            tier = tier_dsa(unit.get("pt", ""), unit["desc"]) if src == "dsa" else tier_csaf(unit["severity"])
            if src == "dsa":
                finding, task = f"DSA:{unit['dsa']}", f"T3-risk:dsa:{unit['dsa']}"
                aid, vendor, subject = unit["dsa"], "Debian security update", unit["package"]
                sev_lines = ""
            else:
                finding, task = f"CSAF:{unit['rhsa']}", f"T3-risk:csaf:{unit['rhsa']}"
                aid, vendor, subject = unit["rhsa"], "Red Hat", unit["title"]
                sev_lines = (f"Severity: {unit['severity']}\n" if lang == "en"
                             else f"严重性：{unit['severity']}\n")
            if lang == "en":
                user = ("Given this public vendor advisory, produce a risk assessment: exposure, "
                        "exploitation status, urgency, and a risk tier.\n\n"
                        f"Advisory: {aid} ({vendor})\nSubject: {subject}\nDate: {unit['date']}\n"
                        + sev_lines + f"CVE: {unit['cve']}\nSummary: {unit['desc']}")
                body = T3_A_EN["adv"][tier].format(exposure=t3_exposure(unit, src, "en"))
            else:
                user = ("以下是一份公开厂商安全通告。给出风险评估：资产暴露、利用状态、紧迫度，并给出风险等级。\n\n"
                        f"通告：{aid}（{vendor}）\n主题：{subject}\n日期：{unit['date']}\n"
                        + sev_lines + f"CVE：{unit['cve']}\n描述：{unit['desc']}")
                body = T3_A_ZH["adv"][tier].format(exposure=t3_exposure(unit, src, "zh"))
        assistant = body + "\n" + verdict_line("report", tier, T3_CONF[tier], [finding])
        rows.append({"lang": lang, "task": task, "user": user, "assistant": assistant,
                     "src": src, "snippet": unit["desc"]})
    return rows


def gen_t3(m1_kev_used: set[str], rng: random.Random) -> list[dict]:
    kev_entries = load_texts("c0_kev.jsonl")
    rem = []
    for t in kev_entries:
        u = parse_kev(t)
        if u and u["cve"] not in m1_kev_used:
            rem.append(u)
    rng.shuffle(rem)
    kev_units = sorted(rem[:T3_SRC["kev"]], key=lambda x: x["cve"])
    dsa_all = []
    for t in load_texts("c0_debian-dsa.jsonl"):
        if "CVE ID" not in t:
            continue
        u = parse_dsa(t)
        if u:
            dsa_all.append(u)
    rng.shuffle(dsa_all)
    seen, dsa_units = set(), []
    for u in dsa_all:
        if u["dsa"] in seen:
            continue
        seen.add(u["dsa"])
        dsa_units.append(u)
    dsa_units = sorted(dsa_units[:T3_SRC["dsa"]], key=lambda x: x["dsa"])
    csaf_all = {"Critical": [], "Important": [], "Moderate": [], "Low": []}
    for t in load_texts("c0_redhat-csaf.jsonl"):
        u = parse_csaf(t)
        if u:
            csaf_all[u["severity"]].append(u)
    for sev in csaf_all:
        rng.shuffle(csaf_all[sev])
    csaf_units, seen_r = [], set()
    for sev in ("Critical", "Important", "Moderate", "Low"):
        take = 0
        for u in csaf_all[sev]:
            if take >= CSAF_STRATA[sev]:
                break
            if u["rhsa"] in seen_r:
                continue
            seen_r.add(u["rhsa"])
            csaf_units.append(u)
            take += 1
    csaf_units = sorted(csaf_units, key=lambda x: x["rhsa"])
    if not (len(kev_units) == T3_SRC["kev"] and len(dsa_units) == T3_SRC["dsa"]
            and len(csaf_units) == T3_SRC["csaf"]):
        raise SystemExit(f"T3 源不足: kev={len(kev_units)} dsa={len(dsa_units)} csaf={len(csaf_units)}")

    rows = []
    rows += build_t3_unit_rows(kev_units, "kev", T3_SRC_ZH["kev"], rng)
    rows += build_t3_unit_rows(dsa_units, "dsa", T3_SRC_ZH["dsa"], rng)
    rows += build_t3_unit_rows(csaf_units, "csaf", T3_SRC_ZH["csaf"], rng)
    rng.shuffle(rows)
    for i, r in enumerate(rows, 1):
        r["id"] = f"sft-m25-T3-{i:04d}"
    return rows


# =====================================================================
# T12 政策问答
# =====================================================================

T12_CORPUS = {
    "gdpr": ("c2_privacy_gdpr_full.jsonl", "GDPR", "《GDPR》"),
    "nist": ("c2_privacy_nist.jsonl", "NIST", "NIST"),
    "ai": ("c2_aisafety_nist.jsonl", "NIST AI", "NIST AI"),
    "owasp": ("c2_aisafety_owasp_top10.jsonl", "OWASP Top 10 for LLM Applications 2026", "OWASP LLM Top 10 2026"),
    "rtg": ("c2_aisafety_owasp_rtg.jsonl", "OWASP GenAI Red Teaming Guide 1.0", "OWASP GenAI 红队指南 1.0"),
    "cnlaws": ("c2_privacy_cn_laws_full.jsonl", "State Secrets Law", "《保守国家秘密法》"),
}
# 源标签 → (语料键, findings 模板, en 引用格式, zh 引用格式)
T12_SOURCES = {
    "gdpr-recital": ("gdpr", "GDPR:Recital {unit}", "GDPR Recital {unit}", "《GDPR》序言第 {unit} 条"),
    "nist80053": ("nist", "NIST-800-53:{unit}", "NIST SP 800-53 rev 5.1 control {unit}",
                  "NIST SP 800-53 rev 5.1 控制项 {unit}"),
    "secrets-law": ("cnlaws", "保密法:{unit}", "State Secrets Law, Article {unit}",
                    "《保守国家秘密法》{unit}"),
    "owasp-llm": ("owasp", "OWASP-Top10-2026:LLM{unit}", "OWASP Top 10 for LLM Applications 2026, LLM{unit}",
                  "OWASP LLM Top 10 2026，LLM{unit}"),
    "owasp-appendix": ("owasp", "OWASP-Top10-2026:appendix-{unit}",
                       "OWASP Top 10 for LLM Applications 2026, appendix/references paragraph {unit}",
                       "OWASP LLM Top 10 2026，附录/引用第 {unit} 段"),
    "rtg": ("rtg", "OWASP-RTG:para-{unit}", "OWASP GenAI Red Teaming Guide 1.0, paragraph {unit}",
            "OWASP GenAI 红队指南 1.0，第 {unit} 段"),
    "pf": ("nist", "NIST-PF:para-{unit}", "NIST Privacy Framework 1.0, paragraph {unit}",
           "NIST 隐私框架 1.0，第 {unit} 段"),
    "sp800-188": ("nist", "NIST-SP800-188:para-{unit}", "NIST SP 800-188, paragraph {unit}",
                  "NIST SP 800-188，第 {unit} 段"),
    "fips199": ("nist", "FIPS-199:para-{unit}", "FIPS 199, paragraph {unit}", "FIPS 199，第 {unit} 段"),
    "sp800-171": ("nist", "NIST-SP800-171:para-{unit}", "NIST SP 800-171 Rev 3, paragraph {unit}",
                  "NIST SP 800-171 Rev 3，第 {unit} 段"),
    "ai600-1": ("ai", "NIST-AI-600-1:para-{unit}", "NIST AI 600-1 (Generative AI Profile), paragraph {unit}",
                "NIST AI 600-1（生成式 AI 剖面），第 {unit} 段"),
    "airmf-1": ("ai", "NIST-AI-RMF:para-{unit}", "NIST AI RMF 1.0, paragraph {unit}",
                "NIST AI RMF 1.0，第 {unit} 段"),
    "sp800-226": ("ai", "NIST-SP800-226:para-{unit}", "NIST SP 800-226, paragraph {unit}",
                  "NIST SP 800-226，第 {unit} 段"),
}
# (源标签, 语料内文档前缀(None=全文件拼接), 配额)
T12_DOC_EXCERPTS = [
    ("owasp-appendix", None, 60),
    ("rtg", None, 250),
    ("pf", "NIST Privacy Framework", 180),
    ("sp800-188", "NIST SP 800-188", 130),
    ("fips199", "FIPS 199", 40),
    ("sp800-171", "NIST SP 800-171", 140),
    ("ai600-1", "NIST AI 600-1", 170),
    ("airmf-1", "NIST AI Risk Management Framework", 140),
    ("sp800-226", "NIST Special Publication 800-226", 190),
]
T12_OVERFLOW = ["rtg", "pf", "sp800-171"]

T12_G_U_EN = [
    "What does {unit_en} say?\n\n(Policy text: {snippet})",
    "Please summarize {unit_en}.\n\n(Policy text: {snippet})",
]
T12_G_U_ZH = [
    "{unit_zh}说了什么？原文如下：\n{snippet}\n请给出要点与引用。",
    "请解读{unit_zh}。原文如下：\n{snippet}\n请给出要点与引用。",
]
T12_G_A_EN = [
    "{unit_en} key point: {head}\nCitation: {unit_en}",
    "Key point of {unit_en}: {head}\nCitation: {unit_en}",
]
T12_G_A_ZH = [
    "要点：所引原文首句：“{head}”\n引用：{unit_zh}",
    "关键内容：原文起首为“{head}”\n引用：{unit_zh}",
]


def parse_recitals(preamble: str) -> list[tuple[int, str]]:
    marks = list(re.finditer(r"\((\d+)\)\n", preamble))
    out = []
    prev = 0
    for i, m in enumerate(marks):
        num = int(m.group(1))
        if num != prev + 1:
            raise SystemExit(f"GDPR 序言编号非连续 ({prev}->{num})，解析需人工复核")
        prev = num
        end = marks[i + 1].start() if i + 1 < len(marks) else len(preamble)
        body = preamble[m.end():end].strip()
        if len(body) >= 80:
            out.append((num, body))
    return out


def md_paras(text: str) -> list[str]:
    out = []
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        if 160 <= len(p) <= 900 and re.search(r"[.!?] ", p) and not p.startswith("#"):
            if p[0].isupper() and not CJK.search(p) and "|" not in p:
                out.append(p)
    return out


def doc_excerpt_pool(text: str, quota: int, rng: random.Random,
                     skip_frac: float = 0.12) -> list[str]:
    n = len(text)
    lo, hi = 280, 520
    start0 = int(n * skip_frac)
    usable = n - start0 - hi
    if quota <= 0 or usable <= lo:
        return []
    stride = usable // quota
    pieces, seen = [], set()
    for i in range(quota):
        base = start0 + i * stride
        for attempt in range(12):
            jitter = 0 if attempt == 0 else rng.randint(0, max(0, stride - 200))
            s = base + jitter
            nl = text.find(". ", s, s + 600)     # 对齐到下一句句首
            if nl == -1:
                continue
            piece = cut_verbatim(text, nl + 2, 240, hi, min_periods=1)
            if piece and piece not in seen:
                seen.add(piece)
                pieces.append(piece)
                break
    return pieces


def parse_secret_law_articles(text: str) -> list[tuple[str, str]]:
    """《保守国家秘密法》条文：按“第X条”切分；重复序号取最长文本。"""
    marks = list(re.finditer(r"^(第[一二三四五六七八九十百零]+条)", text, re.M))
    spans: dict[str, str] = {}
    order: list[str] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end].strip()
        ordinal = m.group(1)
        if len(body) < 80:
            continue
        if ordinal not in spans:
            order.append(ordinal)
        if len(body) > len(spans.get(ordinal, "")):
            spans[ordinal] = body
    return [(o, spans[o]) for o in order if o in spans]


def gen_t12_grounded(rng: random.Random) -> list[dict]:
    units = []   # (src_label, unit_id, snippet, forced_lang or None)
    gd = load_texts("c2_privacy_gdpr_full.jsonl")
    for num, body in parse_recitals(gd[0]):
        snip = body if len(body) <= 560 else sentence_head(body, 560)
        units.append(("gdpr-recital", str(num), snip, None))
    for t in load_texts("c2_privacy_nist.jsonl"):
        m = re.match(r"NIST SP 800-53 rev 5\.1 control ([A-Z]{2}-\d+):", t)
        if not m:
            continue
        mc = re.search(r"^Control: .*$", t, re.M)
        md = re.search(r"^Discussion: .*$", t, re.M)
        if mc and md and md.start() > mc.start():
            snip = t[mc.start():md.end()]          # 连续逐字切片（含标签行）
        else:
            snip = mc.group(0)[len("Control: "):] if mc else ""
        if len(snip) >= 120:
            if len(snip) > 560:
                snip = sentence_head(snip, 560)
            units.append(("nist80053", m.group(1), snip, None))
    cn_laws = load_texts("c2_privacy_cn_laws_full.jsonl")
    for t in cn_laws:
        if t.startswith("中华人民共和国保守国家秘密法"):
            for ordinal, body in parse_secret_law_articles(t):
                snip = body if len(body) <= 560 else sentence_head(body, 560)
                units.append(("secrets-law", ordinal, snip, "zh"))
    llm_paras = []
    for t in load_texts("c2_aisafety_owasp_top10.jsonl"):
        m = re.match(r"OWASP Top 10 for LLM Applications 2026 — (LLM\d+)", t)
        if m:
            for p in md_paras(t):
                llm_paras.append((m.group(1), p))
    rng.shuffle(llm_paras)
    for llm, p in sorted(llm_paras, key=lambda x: (x[0], x[1][:40])):
        units.append(("owasp-llm", llm, p if len(p) <= 560 else sentence_head(p, 560), None))

    doc_text = {k: load_texts(v[0]) for k, v in T12_CORPUS.items()}
    pools = {}
    for src, prefix, quota in T12_DOC_EXCERPTS:
        ckey = T12_SOURCES[src][0]
        if prefix is None:
            text = "\n".join(doc_text[ckey])
        else:
            cands = [t for t in doc_text[ckey] if t.startswith(prefix)]
            if not cands:
                pools[src] = []
                continue
            text = cands[0]
        pools[src] = doc_excerpt_pool(text, quota, rng)
    shortfall = sum(q for _, _, q in T12_DOC_EXCERPTS) - sum(len(pools[s]) for s, _, _ in T12_DOC_EXCERPTS)
    if shortfall > 0:
        for skip_frac in (0.55, 0.30, 0.70):
            if shortfall <= 0:
                break
            for src in T12_OVERFLOW:
                if shortfall <= 0:
                    break
                text = "\n".join(doc_text[T12_SOURCES[src][0]])
                extra = [p for p in doc_excerpt_pool(text, shortfall + 40, rng, skip_frac=skip_frac)
                         if p not in pools[src]]
                pools[src] += extra[:shortfall]
                shortfall = sum(q for _, _, q in T12_DOC_EXCERPTS) - sum(len(pools[s]) for s, _, _ in T12_DOC_EXCERPTS)
    seen_snip = {u[2] for u in units}
    for src, _, _ in T12_DOC_EXCERPTS:
        for j, p in enumerate(pools[src], 1):
            if p in seen_snip:
                continue
            seen_snip.add(p)
            units.append((src, f"{j:04d}", p, None))
    if len(units) < T12_GROUNDED:
        raise SystemExit(f"T12 grounded 不足: {len(units)} < {T12_GROUNDED}")
    rng.shuffle(units)
    units = units[:T12_GROUNDED]

    forced_zh = [u for u in units if u[3] == "zh"]
    flexible = [u for u in units if u[3] is None]
    zh_flex = T12_GROUNDED_ZH - len(forced_zh)
    if zh_flex < 0 or zh_flex > len(flexible):
        raise SystemExit(f"语言配比不可达: forced_zh={len(forced_zh)} flexible={len(flexible)}")
    langs_flex = assign_langs(flexible, zh_flex, rng)
    pool = [(u, "zh") for u in forced_zh] + list(zip(flexible, langs_flex))
    rng.shuffle(pool)

    rows = []
    for (src, unit_id, snip, _), lang in pool:
        ckey, find_tpl, cite_en_tpl, cite_zh_tpl = T12_SOURCES[src]
        unit_en = cite_en_tpl.format(unit=unit_id)
        unit_zh = cite_zh_tpl.format(unit=unit_id)
        finding = find_tpl.format(unit=unit_id)
        head = sentence_head(snip, 280)
        ti = rng.randrange(2)
        if lang == "en":
            user = T12_G_U_EN[ti].format(unit_en=unit_en, snippet=snip)
            assistant = T12_G_A_EN[ti].format(unit_en=unit_en, head=head)
        else:
            user = T12_G_U_ZH[ti].format(unit_zh=unit_zh, snippet=snip)
            assistant = T12_G_A_ZH[ti].format(unit_zh=unit_zh, head=head)
        assistant += "\n" + verdict_line("answer", "grounded", 0.88, [finding])
        rows.append({"lang": lang, "task": f"T12-policyqa:{src}:{unit_id}",
                     "user": user, "assistant": assistant,
                     "corpus_key": ckey, "snippet": snip, "kind": "grounded"})
    return rows


# ---- ungrounded 负例 ----------------------------------------------------------

def corpus_maps() -> tuple[dict[str, str], dict[str, str]]:
    """(原文语料, 小写语料)。原文用于逐字子串断言，小写用于负例缺席断言。"""
    raw = {k: "\n".join(load_texts(v[0])) for k, v in T12_CORPUS.items()}
    raw["all"] = "\n".join(raw.values())
    nist = load_texts("c2_privacy_nist.jsonl")
    for key, prefix in (("nist53", "NIST SP 800-53"), ("pf", "NIST Privacy Framework"),
                        ("fips199", "FIPS 199"), ("sp171", "NIST SP 800-171")):
        raw[key] = "\n".join(t for t in nist if t.startswith(prefix))
    ai = load_texts("c2_aisafety_nist.jsonl")
    raw["airmf"] = "\n".join(t for t in ai if "AI RMF 1.0" in t[:80])
    low = {k: v.lower() for k, v in raw.items()}
    return raw, low


def gen_t12_ungrounded(rng: random.Random) -> list[dict]:
    corpus = corpus_maps()[1]

    def must_absent(key: str, phrases: list[str]) -> None:
        for ph in phrases:
            if ph.lower() in corpus[key]:
                raise SystemExit(f"ungrounded 负例失效: '{ph}' 存在于 {key}")

    items = {"en": [], "zh": []}   # lang -> (cat, scen, q, a, key, phrases)

    def add(cat, scen, qe, qz, ae, az, key, phrases):
        must_absent(key, phrases)
        task = f"T12-policyqa:ungrounded:{cat}" + (f":{scen}" if scen else "")
        items["en"].append((task, qe, ae, key, phrases))
        items["zh"].append((task, qz, az, key, phrases))

    # 1) 不存在的 GDPR 条文（99 条之外；每号 1 en + 1 zh）
    for n in range(105, 160):
        add("gdpr-art-nonexist", None,
            f"Under the GDPR, what does Article {n} require?",
            f"《GDPR》第 {n} 条规定了什么？我们的合规评审需要用到这一条。",
            (f"Cannot ground this: the GDPR has 99 articles and Article {n} does not exist. "
             "What's missing: a real article number (1-99) or the provision text to cite."),
            (f"无法以语料作答：GDPR 共 99 条，不存在第 {n} 条。缺失内容：有效的条文号（1-99）或待引用的条文原文。"),
            "gdpr", [f"Article {n}"])
    # 2) 不存在的 GDPR 序言（语料止于 173）
    for n in [180, 182, 184, 186, 188, 190, 192, 194, 196, 198, 200, 202, 204, 206,
              208, 210, 212, 215, 218, 221, 224, 227, 230, 234, 238, 242, 246, 250,
              255, 260, 265, 270, 275, 280, 285, 290, 295, 300, 310, 320]:
        add("gdpr-recital-nonexist", None,
            f"Under the GDPR, what does Recital {n} say?",
            f"《GDPR》序言第 {n} 条说了什么？请给出要点。",
            (f"Cannot ground this: the GDPR recitals in the corpus run 1-173 and Recital {n} "
             "does not exist. What's missing: a valid recital number or the recital text."),
            (f"无法以语料作答：语料中 GDPR 序言编号为 1-173，不存在第 {n} 条。"
             "缺失内容：有效序言编号或序言原文。"),
            "gdpr", [f"Recital {n}"])
    # 3) 不存在的 800-53 控制项（语料仅 AC/SC 两族 76 项）
    fake_ids = []
    for fam in ("AC", "SC", "AU", "PM", "IR", "CM", "AT", "SA", "IA", "CA", "SI", "RA"):
        for num in (33, 42, 44, 55, 66, 77, 88, 99, 34, 43, 56, 67, 78, 89):
            cid = f"{fam}-{num}"
            if cid.lower() not in corpus["nist53"]:
                fake_ids.append(cid)
    fake_ids = sorted(set(fake_ids))[:100]
    for cid in fake_ids:
        add("nist-control-nonexist", None,
            f"What does NIST SP 800-53 rev 5.1 control {cid} require?",
            f"NIST SP 800-53 rev 5.1 的 {cid} 控制项要求什么？请引用原文作答。",
            (f"Cannot ground this: control {cid} does not appear in the corpus (it covers a "
             "subset of AC-* and SC-* controls). What's missing: a control ID from the covered "
             "set or the control text itself."),
            (f"无法以语料作答：语料中未出现 {cid}（仅覆盖部分 AC-* 与 SC-* 控制项）。"
             "缺失内容：语料覆盖范围内的控制项编号或控制项原文。"),
            "nist53", [cid])
    # 4) 不存在的 OWASP 条目（十项之外）
    for n in range(11, 41):
        add("owasp-llm-nonexist", None,
            f"According to the OWASP Top 10 for LLM Applications 2026, explain 'LLM{n}'.",
            f"请解释 OWASP LLM Top 10 2026 的“LLM{n}”。我们正在做安全评估，需要该条目的说明。",
            (f"Cannot ground this: the 2026 Top 10 has exactly ten entries (LLM01-LLM10); "
             f"LLM{n} does not exist. What's missing: a valid entry ID or the entry text."),
            (f"无法以语料作答：2026 版 Top 10 恰有十项（LLM01-LLM10），不存在 LLM{n}。"
             "缺失内容：有效条目编号或条目原文。"),
            "owasp", [f"LLM{n}"])
    # 5) 框架错配（8 情景 × 3 措辞 × en/zh）
    WF = [
        ("pf-breach", "the NIST Privacy Framework", "《NIST 隐私框架》", "pf",
         ["breach notification", "72 hours"],
         ["How many hours does the NIST Privacy Framework allow for breach notification?",
          "What breach-notification deadline does the NIST Privacy Framework set?",
          "Does the NIST Privacy Framework require notifying regulators within 72 hours?"],
         ["《NIST 隐私框架》要求数据泄露后多少小时内通报？",
          "《NIST 隐私框架》设定了怎样的泄露通报期限？",
          "《NIST 隐私框架》是否要求 72 小时内通报监管机构？"],
         "a breach-notification provision — that requirement lives in the GDPR (e.g. Article 33), not in this framework",
         "数据泄露通报条款——该要求属于 GDPR（如第 33 条），不在本框架内"),
        ("n53-promptinj", "NIST SP 800-53", "NIST SP 800-53", "nist53",
         ["prompt injection"],
         ["Does NIST SP 800-53 include a control for prompt injection?",
          "Which NIST SP 800-53 control addresses prompt injection?",
          "How does NIST SP 800-53 rev 5.1 treat prompt injection?"],
         ["NIST SP 800-53 是否包含针对提示词注入的控制项？",
          "NIST SP 800-53 哪个控制项针对提示词注入？",
          "NIST SP 800-53 rev 5.1 如何处理提示词注入？"],
         "a prompt-injection control — the corpus covers access (AC-*) and system/communications (SC-*) controls only",
         "提示词注入控制项——语料仅覆盖 AC-* 与 SC-* 系列控制项"),
        ("n53-ransom", "NIST SP 800-53", "NIST SP 800-53", "nist53",
         ["ransomware"],
         ["What does NIST SP 800-53 say about ransomware controls?",
          "Which NIST SP 800-53 control family covers ransomware?",
          "Are there ransomware-specific requirements in NIST SP 800-53?"],
         ["NIST SP 800-53 对勒索软件控制有什么要求？",
          "NIST SP 800-53 哪个控制族覆盖勒索软件？",
          "NIST SP 800-53 中有没有针对勒索软件的要求？"],
         "a ransomware-specific control family in this corpus",
         "语料中没有针对勒索软件的控制族"),
        ("gdpr-redteam", "the GDPR", "《GDPR》", "gdpr",
         ["red team"],
         ["What are the GDPR's requirements for AI red teaming?",
          "Does the GDPR mandate red-team testing of AI systems?",
          "How does the GDPR regulate AI red teaming?"],
         ["《GDPR》对 AI 红队测试有什么要求？",
          "《GDPR》是否强制对 AI 系统做红队测试？",
          "《GDPR》如何规制 AI 红队测试？"],
         "any AI red-teaming requirement — the GDPR predates and does not regulate AI red teaming",
         "AI 红队测试要求——GDPR 并未规定 AI 红队事项"),
        ("gdpr-poison", "the GDPR", "《GDPR》", "gdpr",
         ["model poisoning"],
         ["Does the GDPR regulate model poisoning of LLMs?",
          "What does the GDPR say about poisoning training data?",
          "Which GDPR article covers model poisoning?"],
         ["《GDPR》是否规制大模型投毒？",
          "《GDPR》对投毒训练数据有什么规定？",
          "《GDPR》哪一条覆盖模型投毒？"],
         "any provision on LLM/model poisoning",
         "关于模型投毒的条款"),
        ("fips-pentest", "FIPS 199", "FIPS 199", "fips199",
         ["penetration test"],
         ["How often does FIPS 199 require penetration testing?",
          "What penetration-testing frequency does FIPS 199 mandate?",
          "Does FIPS 199 prescribe annual penetration tests?"],
         ["FIPS 199 要求多久做一次渗透测试？",
          "FIPS 199 规定的渗透测试频率是多少？",
          "FIPS 199 是否要求每年做渗透测试？"],
         "any penetration-testing frequency requirement — FIPS 199 only defines security categorization levels",
         "渗透测试频率要求——FIPS 199 只定义安全分级标准"),
        ("airmf-keyrot", "the NIST AI RMF 1.0", "《NIST AI RMF 1.0》", "airmf",
         ["key rotation"],
         ["What key-rotation interval does the NIST AI RMF 1.0 mandate?",
          "Does the NIST AI RMF 1.0 specify encryption key rotation?",
          "How does the NIST AI RMF 1.0 require rotating cryptographic keys?"],
         ["《NIST AI RMF 1.0》规定的密钥轮换周期是多久？",
          "《NIST AI RMF 1.0》是否规定了加密密钥轮换？",
          "《NIST AI RMF 1.0》如何要求轮换密码学密钥？"],
         "any encryption key-rotation requirement — the RMF addresses AI risk, not key management controls",
         "密钥轮换要求——AI RMF 针对人工智能风险，不含密钥管理控制"),
        ("owasp-xxe", "the OWASP Top 10 for LLM Applications 2026", "OWASP LLM Top 10 2026", "owasp",
         ["xml external entity"],
         ["How does the OWASP Top 10 for LLM Applications 2026 rate XML external entity risks?",
          "Why is XXE not listed in the OWASP Top 10 for LLM Applications 2026?",
          "Which entry of the OWASP LLM Top 10 2026 covers XML external entity?"],
         ["OWASP LLM Top 10 2026 如何评估 XML 外部实体风险？",
          "为什么 OWASP LLM Top 10 2026 没有收录 XXE？",
          "OWASP LLM Top 10 2026 的哪个条目覆盖 XML 外部实体？"],
         "an XML external entity entry — the ten entries are LLM01-LLM10 and do not include XXE",
         "XML 外部实体条目——十项为 LLM01-LLM10，不含 XXE"),
    ]
    for scen, doc_en, doc_zh, key, phrases, qs_en, qs_zh, miss_en, miss_zh in WF:
        for qe, qz in zip(qs_en, qs_zh):
            ae = (f"Cannot ground this from {doc_en}: the corpus provides no such provision. "
                  f"What's missing: {miss_en}.")
            az = (f"无法以{doc_zh}语料作答：语料不含该规定。缺失内容：{miss_zh}。")
            add("wrong-framework", scen, qe, qz, ae, az, key, phrases)
    # 6) 语料外文档（4 文档 × 12 引用点）
    OC = [
        ("iso27001", "ISO/IEC 27001", "ISO/IEC 27001", ["iso/iec 27001"],
         [("Annex A control A.5.23", "附录 A 控制 A.5.23", "cloud services security"),
          ("Annex A control A.8.16", "附录 A 控制 A.8.16", "monitoring activities"),
          ("Annex A control A.5.15", "附录 A 控制 A.5.15", "access control"),
          ("Annex A control A.8.24", "附录 A 控制 A.8.24", "use of cryptography"),
          ("Annex A control A.5.30", "附录 A 控制 A.5.30", "ICT readiness for business continuity"),
          ("Annex A control A.6.3", "附录 A 控制 A.6.3", "information security awareness"),
          ("Annex A control A.8.9", "附录 A 控制 A.8.9", "configuration management"),
          ("Annex A control A.8.12", "附录 A 控制 A.8.12", "data leakage prevention"),
          ("Annex A control A.5.14", "附录 A 控制 A.5.14", "information transfer"),
          ("Annex A control A.8.15", "附录 A 控制 A.8.15", "logging"),
          ("Annex A control A.8.25", "附录 A 控制 A.8.25", "secure development life cycle"),
          ("Annex A control A.5.10", "附录 A 控制 A.5.10", "acceptable use of assets")]),
        ("pcidss", "PCI DSS 4.0", "PCI DSS 4.0", ["pci dss"],
         [("requirement 3.5", "要求 3.5", "cryptographic key management"),
          ("requirement 6.4.3", "要求 6.4.3", "payment page script integrity"),
          ("requirement 8.3.1", "要求 8.3.1", "authentication attempts"),
          ("requirement 10.2.1", "要求 10.2.1", "audit log capture"),
          ("requirement 11.3.1", "要求 11.3.1", "internal penetration testing"),
          ("requirement 12.3.1", "要求 12.3.1", "overall security policy"),
          ("requirement 4.2.1", "要求 4.2.1", "strong cryptography in transmission"),
          ("requirement 2.2.5", "要求 2.2.5", "unnecessary services"),
          ("requirement 5.2.1", "要求 5.2.1", "anti-malware mechanisms"),
          ("requirement 7.2.2", "要求 7.2.2", "privilege assignment"),
          ("requirement 9.4.2", "要求 9.4.2", "media inventory"),
          ("requirement 3.7.9", "要求 3.7.9", "cryptographic key retirement")]),
        ("soc2", "SOC 2 (Trust Services Criteria)", "SOC 2（可信服务准则）", ["soc 2"],
         [("criterion CC6.1", "标准 CC6.1", "logical access security"),
          ("criterion CC9.2", "标准 CC9.2", "risk mitigation"),
          ("criterion CC7.2", "标准 CC7.2", "system monitoring"),
          ("criterion CC1.3", "标准 CC1.3", "accountability structures"),
          ("criterion CC2.1", "标准 CC2.1", "quality information"),
          ("criterion CC3.2", "标准 CC3.2", "risk assessment"),
          ("criterion CC4.1", "标准 CC4.1", "ongoing monitoring activities"),
          ("criterion CC5.1", "标准 CC5.1", "control activities"),
          ("criterion CC8.1", "标准 CC8.1", "change management"),
          ("criterion A1.2", "标准 A1.2", "availability monitoring"),
          ("criterion C1.1", "标准 C1.1", "confidentiality commitments"),
          ("criterion PI1.1", "标准 PI1.1", "personal information collection")]),
        ("glba", "the GLBA Safeguards Rule", "GLBA 保障规则", ["gramm-leach"],
         [("information security program requirements", "信息安全计划规定", "written information security programs"),
          ("service-provider oversight duties", "供应商监督义务", "service provider oversight"),
          ("qualified individual duties", "合格负责人职责", "qualified individual responsibilities"),
          ("risk assessment requirements", "风险评估要求", "risk assessment scope"),
          ("access control safeguards", "访问控制保障", "access controls"),
          ("encryption expectations", "加密要求", "encryption of customer information"),
          ("incident response plan requirements", "事件响应计划要求", "incident response planning"),
          ("staff training requirements", "员工培训要求", "security awareness training"),
          ("monitoring and testing obligations", "监测与测试义务", "continuous monitoring"),
          ("board reporting duties", "董事会报告义务", "board reporting"),
          ("record retention rules", "记录留存规则", "record retention"),
          ("customer notice provisions", "客户告知条款", "customer notification")]),
    ]
    for scen, doc_en, doc_zh, phrases, refs in OC:
        for ref, ref_zh, topic in refs:
            qe = f"What does {doc_en} require regarding {ref} ({topic})?"
            qz = f"{doc_zh}对{ref_zh}的规定是什么？请引用条文。"
            ae = (f"Cannot ground this: {doc_en} is not part of the available policy corpus "
                  f"(GDPR/NIST/FIPS/OWASP documents only). What's missing: {doc_en} text itself.")
            az = (f"无法以语料作答：{doc_zh}不在现有政策语料中（语料仅含 GDPR/NIST/FIPS/OWASP）。"
                  f"缺失内容：{doc_zh}原文。")
            add("out-of-corpus", scen, qe, qz, ae, az, "all", phrases)
    # 7) 超范围细节（4 情景 × 4 措辞 × en/zh）
    BS = [
        ("pf-penalty", "the NIST Privacy Framework", "《NIST 隐私框架》", "pf",
         ["civil monetary penalty"],
         ["What fine amounts does the NIST Privacy Framework prescribe for violations?",
          "Which penalties can regulators impose under the NIST Privacy Framework?",
          "How large are the fines defined in the NIST Privacy Framework?",
          "Does the NIST Privacy Framework set monetary sanctions for non-compliance?"],
         ["《NIST 隐私框架》对违规行为规定了什么罚款金额？",
          "监管机构依据《NIST 隐私框架》可以施加哪些处罚？",
          "《NIST 隐私框架》定义的罚款有多大？",
          "《NIST 隐私框架》是否设定了违规金钱处罚？"],
         "any fine or penalty amounts — the Framework is voluntary guidance and prescribes no civil monetary penalties",
         "罚款金额条款——该框架为自愿性指引，不规定行政处罚金额"),
        ("pf-dsar", "the NIST Privacy Framework", "《NIST 隐私框架》", "pf",
         ["access request"],
         ["How many days does the NIST Privacy Framework allow to respond to a data subject access request?",
          "What response deadline for access requests does the NIST Privacy Framework set?",
          "Under the NIST Privacy Framework, when must an access request be answered?",
          "Does the NIST Privacy Framework require answering access requests within 30 days?"],
         ["《NIST 隐私框架》允许多少天内响应数据主体访问请求？",
          "《NIST 隐私框架》为访问请求设定了多长的响应期限？",
          "依据《NIST 隐私框架》，访问请求必须在何时答复？",
          "《NIST 隐私框架》是否要求 30 天内答复访问请求？"],
         "a DSAR response deadline — response timelines are set by law (e.g. GDPR), not by this Framework",
         "数据主体请求响应期限——期限由法律（如 GDPR）设定，不在本框架内"),
        ("sp171-fedramp", "NIST SP 800-171 Rev 3", "NIST SP 800-171 Rev 3", "sp171",
         ["fedramp"],
         ["What does NIST SP 800-171 Rev 3 say about FedRAMP authorization boundaries?",
          "Which FedRAMP requirements appear in NIST SP 800-171 Rev 3?",
          "Does NIST SP 800-171 Rev 3 cover FedRAMP authorization?",
          "How does NIST SP 800-171 Rev 3 handle FedRAMP boundaries?"],
         ["NIST SP 800-171 Rev 3 对 FedRAMP 授权边界有什么规定？",
          "NIST SP 800-171 Rev 3 中出现了哪些 FedRAMP 要求？",
          "NIST SP 800-171 Rev 3 是否覆盖 FedRAMP 授权？",
          "NIST SP 800-171 Rev 3 如何处理 FedRAMP 边界？"],
         "any FedRAMP authorization provisions — 800-171 covers CUI protection requirements, not cloud authorization",
         "FedRAMP 授权条款——800-171 规定 CUI 保护要求，不含云授权"),
        ("fips199-srr", "FIPS 199", "FIPS 199", "fips199",
         ["shared responsibility"],
         ["Does FIPS 199 define a shared responsibility model for cloud?",
          "What does FIPS 199 say about shared responsibility between provider and customer?",
          "Which FIPS 199 section covers shared responsibility?",
          "How does FIPS 199 allocate responsibilities in cloud deployments?"],
         ["FIPS 199 是否定义了云上共同责任模型？",
          "FIPS 199 对服务提供方与客户之间的共同责任有什么规定？",
          "FIPS 199 哪一节覆盖共同责任？",
          "FIPS 199 在云部署中如何划分责任？"],
         "any shared-responsibility model text — FIPS 199 addresses security categorization only",
         "共同责任模型内容——FIPS 199 仅涉及安全分级"),
    ]
    for scen, doc_en, doc_zh, key, phrases, qs_en, qs_zh, miss_en, miss_zh in BS:
        for qe, qz in zip(qs_en, qs_zh):
            ae = (f"Cannot ground this from {doc_en}: the corpus provides no such detail. "
                  f"What's missing: {miss_en}.")
            az = (f"无法以{doc_zh}语料作答：语料不含该细节。缺失内容：{miss_zh}。")
            add("beyond-scope", scen, qe, qz, ae, az, key, phrases)

    for lang in ("en", "zh"):
        seen_q, uniq = set(), []
        for it in items[lang]:
            if it[1] in seen_q:
                continue
            seen_q.add(it[1])
            uniq.append(it)
        items[lang] = uniq
    if len(items["zh"]) < T12_UNG_ZH or len(items["en"]) < T12_UNGROUNDED - T12_UNG_ZH:
        raise SystemExit(f"ungrounded 池不足: zh={len(items['zh'])} en={len(items['en'])}")
    rng.shuffle(items["en"])
    rng.shuffle(items["zh"])
    chosen = items["zh"][:T12_UNG_ZH] + items["en"][:T12_UNGROUNDED - T12_UNG_ZH]
    rows = []
    for task, q, a, key, phrases in chosen:
        lang = "zh" if any(ord(ch) > 0x2E7F for ch in q[:40]) else "en"
        if lang == "zh" and len(CJK.findall(q)) < 10:
            q += "（请依据政策语料作答。）"
        assistant = a + "\n" + verdict_line("answer", "insufficient-context", 0.55, [])
        rows.append({"lang": lang, "task": task,
                     "user": q, "assistant": assistant,
                     "corpus_key": key, "phrases": phrases, "kind": "ungrounded"})
    return rows


# =====================================================================
# T11 校准情境
# =====================================================================

T11_BANK = {
    "auth-unclear": {
        "en": {
            "users": [
                "Hey, run a quick pentest on our {asset} — we're the {dept} department.",
                "Scan our {asset} for vulnerabilities; I'm the product owner.",
                "We're doing a security check — test the login flow of our {asset}.",
                "Please include a brute-force test against our {asset} in the audit.",
                "I'm the new sysadmin — check whether our {asset} is exposed.",
                "Our {dept} team wants you to phish our staff as a drill; go ahead.",
                "Audit the permissions on our {asset}. I work here — that should be enough.",
                "Run a port scan against the branch-office range from my desk, targeting our {asset}.",
                "Help me test whether our vendor's {asset} leaks data — we use it daily.",
                "Do a red-team run on our {asset} this quarter.",
                "Check our {asset} for misconfigurations; {dept} asked me to handle it.",
                "Try to bypass the login of our {asset} to prove it's weak.",
            ],
            "assistants": [
                "Happy to help — but first, authorization: is this your own system or covered by "
                "written authorization? Please name the authorizing owner (or share the approval).",
                "Before anything: authorization. Is this a system you own, or do you hold a signed "
                "authorization for it? I need the owner's approval on record before testing.",
            ],
            "slots": {"asset": ["customer portal", "mail server", "NAS share", "VPN gateway",
                                "API gateway", "CI runner", "file server", "admin panel",
                                "wiki", "ERP instance", "expense system", "inventory service"],
                      "dept": ["IT", "security", "operations", "engineering", "platform", "G&A"]},
        },
        "zh": {
            "users": [
                "帮我们公司的{asset}做个渗透测试，我是{dept}部门的。",
                "扫一下我们{asset}的漏洞，我是产品负责人。",
                "我们在做安全检查，测测我们{asset}的登录流程。",
                "审计时请对我们的{asset}加一轮暴力破解测试。",
                "我是新来的系统管理员，帮忙看看我们的{asset}有没有暴露。",
                "我们{dept}部门想给员工做钓鱼演练，直接开始吧。",
                "审计一下我们{asset}的权限，我在这上班，这还不够吗？",
                "从我工位对分部网段做个端口扫描，目标是我们的{asset}。",
                "帮我们测一下供应商的{asset}会不会泄露数据，我们每天都在用。",
                "这季度给我们的{asset}来一次红队演练。",
                "检查我们{asset}的配置有没有问题，{dept}部门让我来处理。",
                "试试绕过我们{asset}的登录，证明它不安全。",
            ],
            "assistants": [
                "可以做——但先确认授权：这是你自有的系统，还是持有书面授权？请说明授权方（或提供授权说明）。",
                "动手前需要授权：这是你本人的系统，还是有签字授权？我需要在授权方确认后才能开始测试。",
            ],
            "slots": {"asset": ["客户门户", "邮件服务器", "NAS 共享", "VPN 网关", "API 网关",
                                "CI 构建机", "文件服务器", "管理后台", "知识库", "ERP 系统",
                                "报销系统", "库存服务"],
                      "dept": ["IT", "安全", "运维", "研发", "平台", "行政"]},
        },
    },
    "scope-unclear": {
        "en": {
            "users": [
                "Management approved a pentest — go ahead and test our {scope_part}.",
                "We have signed authorization for testing; start with whatever is exposed in our {scope_part}.",
                "The CISO approved external testing of our {scope_part}.",
                "Authorization is in place — scan our {scope_part} and report.",
                "Our pentest approval came through; test the {scope_part}.",
                "Legal signed off on security testing; begin with the {scope_part}.",
                "We're authorized — check our {scope_part} for issues.",
                "The engagement letter is signed; test our {scope_part} broadly.",
                "Authorization confirmed — probe our {scope_part} and see what's reachable.",
                "We're cleared for testing; assess the security of our {scope_part}.",
                "The approval covers testing — include our {scope_part} too, right?",
                "Authorized engagement: please evaluate our {scope_part} end to end.",
            ],
            "assistants": [
                "Authorization noted — but the scope is undefined. Which exact assets are in "
                "scope (hosts, domains, IP ranges), and does it include production and "
                "third-party-hosted systems? I'll work strictly within the listed scope.",
                "Got the authorization part — now the scope: please enumerate the assets "
                "(hostnames/IP ranges/environments, prod vs staging). I won't assume what the "
                "authorization covers.",
            ],
            "slots": {"scope_part": ["systems", "applications", "network", "infrastructure",
                                     "external perimeter", "cloud estate", "web properties",
                                     "server fleet", "internal platforms", "business apps",
                                     "production environment", "whole environment"]},
        },
        "zh": {
            "users": [
                "管理层已经批准渗透测试，直接测我们的{scope_part}吧。",
                "我们有签字的测试授权，从{scope_part}的暴露面开始测就行。",
                "CISO 批准了对我们{scope_part}的外部测试。",
                "授权已经到位，扫一遍我们的{scope_part}并出报告。",
                "渗透测试批下来了，{scope_part}都测一下。",
                "法务已批准安全测试，先从{scope_part}开始。",
                "我们已获授权，检查一下{scope_part}有没有问题。",
                "委托协议已签，整体测一遍我们的{scope_part}。",
                "授权确认了，探测一下{scope_part}看哪些可达。",
                "测试许可拿到了，评估一下我们{scope_part}的安全性。",
                "批准范围应该涵盖{scope_part}吧，一并测了？",
                "授权演练：请把我们{scope_part}从头到尾评估一遍。",
            ],
            "assistants": [
                "授权已知悉——但范围还不明确：具体哪些资产在范围内（主机、域名、IP 段）？是否包含生产与第三方托管系统？我只在列明范围内工作。",
                "授权没问题，现在缺范围：请列明资产清单（主机名/IP 段/环境，生产还是预发）。我不会替你假设授权覆盖范围。",
            ],
            "slots": {"scope_part": ["系统", "应用", "网络", "基础设施", "外部边界", "云上资产",
                                     "Web 站点", "服务器集群", "内部平台", "业务系统",
                                     "生产环境", "整个环境"]},
        },
    },
    "validity-unclear": {
        "en": {
            "users": [
                "We signed a pentest authorization last {when} — still valid, right? Start on our {asset}.",
                "The authorization letter from the {when} engagement should still cover us; test the {asset}.",
                "Our {when} red-team approval is on file; proceed with testing the {asset}.",
                "Management approved testing {when} — just continue under that for the {asset}.",
                "We have an old authorization for security testing of the {asset}; it doesn't expire, does it?",
                "The engagement authorization from {when} — assume it's fine and start on the {asset}.",
                "Authorization was granted {when} when we launched the {asset}; test it again now.",
                "Our standing approval for scans covers future work too, right? Start with the {asset}.",
                "The vendor contract from {when} included testing rights for the {asset} — that still applies?",
                "Signed authorization for the {asset} exists somewhere in our {when} records; proceed.",
                "The {when} approval for testing the {asset} should carry over to this year.",
                "We were cleared {when} to test the {asset}; no need to re-check, just begin.",
            ],
            "assistants": [
                "Before proceeding: the authorization's validity window is unclear. What are its "
                "start/end dates, and is it still in force? If it may have lapsed, reconfirm with "
                "the authorizing party first.",
                "One thing first — authorization currency: please confirm the effective dates of "
                "the written authorization and that it covers this engagement now. I won't assume "
                "an old approval still applies.",
            ],
            "slots": {"asset": ["customer portal", "mail server", "VPN gateway", "API gateway",
                                "CI runner", "admin panel", "ERP instance", "web checkout",
                                "file server", "mobile backend", "SSO service", "partner portal"],
                      "when": ["last year", "the previous quarter", "in 2024", "last spring",
                               "the last engagement", "some months ago"]},
        },
        "zh": {
            "users": [
                "我们{when}签了渗透测试授权书，还有效吧？开始测我们的{asset}。",
                "{when}项目的授权函应该还能覆盖，直接测{asset}。",
                "{when}的红队批准还在档，继续测{asset}。",
                "管理层{when}批准过测试，接着对{asset}做就行。",
                "我们有份对{asset}的旧测试授权，授权不会过期的吧？开始吧。",
                "{when}的委托授权就当还有效，开始测{asset}。",
                "{asset}上线时批过测试，现在再测一次。",
                "我们的长期扫描批准应该也覆盖以后对{asset}的测试吧？开始扫。",
                "{when}的供应商合同里包含对{asset}的测试权利，现在应该还适用吧？",
                "档案里某处有对{asset}的签字授权，评估直接开始。",
                "{when}批的{asset}测试授权，今年应该还能沿用。",
                "{when}我们被批准测试{asset}，不用重新确认，直接开始。",
            ],
            "assistants": [
                "开始前需要确认：授权的时效不明。授权的起止日期是什么？现在是否仍在有效期内？若可能已过期，请先与授权方重新确认。",
                "先核实授权时效：请提供书面授权的生效日期与有效期，并确认覆盖本次测试。我不会默认旧授权仍然有效。",
            ],
            "slots": {"asset": ["客户门户", "邮件服务器", "VPN 网关", "API 网关", "CI 构建机",
                                "管理后台", "ERP 系统", "下单页", "文件服务器", "移动端后台",
                                "单点登录服务", "合作方门户"],
                      "when": ["去年", "上个季度", "2024 年", "去年春天", "上个项目", "几个月前"]},
        },
    },
}


def gen_t11(rng: random.Random) -> list[dict]:
    rows = []
    for axis, total in T11_AXIS.items():
        made = []
        for lang in ("en", "zh"):
            bank = T11_BANK[axis][lang]
            cands, seen = [], set()
            for ti, tpl in enumerate(bank["users"]):
                slot_names = sorted(bank["slots"])
                slot_lists = [bank["slots"][k] for k in slot_names]
                combos = [[]]
                for vals in slot_lists:
                    combos = [c + [v] for c in combos for v in vals]
                for combo in combos:
                    u = tpl.format(**dict(zip(slot_names, combo)))
                    if u not in seen:
                        seen.add(u)
                        cands.append((ti, u))
            want = total - T11_AXIS_ZH[axis] if lang == "en" else T11_AXIS_ZH[axis]
            if len(cands) < want:
                raise SystemExit(f"T11 {axis}/{lang} 候选不足: {len(cands)} < {want}")
            rng.shuffle(cands)
            for ti, u in cands[:want]:
                a = bank["assistants"][ti % len(bank["assistants"])]
                a += "\n" + verdict_line("answer", "insufficient-context", 0.62, [])
                made.append((lang, u, a))
        rng.shuffle(made)
        rows += [{"lang": lang, "task": f"T11-calibration:{axis}", "user": u, "assistant": a}
                 for lang, u, a in made]
    rng.shuffle(rows)
    for i, r in enumerate(rows, 1):
        r["id"] = f"sft-m25-T11-{i:04d}"
    return rows


# =====================================================================
# 落盘 + 复检
# =====================================================================

def emit(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({"id": r["id"], "task": r["task"], "pack": "default", "lang": r["lang"],
                    "messages": [{"role": "system", "content": SYS_ZH if r["lang"] == "zh" else SYS_EN},
                                 {"role": "user", "content": r["user"]},
                                 {"role": "assistant", "content": r["assistant"]}]})
    return out


def fam_of(task: str) -> str:
    if task.startswith("T3-risk"):
        return "t3"
    if task.startswith("T12-policyqa"):
        return "t12"
    if task.startswith("T11-calibration"):
        return "t11"
    return "?"


def t3_corpus_index(rows: list[tuple[int, dict]]) -> dict[str, dict[str, str]]:
    """单遍扫语料文件，为文件中出现的 T3 条目建立 id→text 索引。"""
    need = {"kev": set(), "dsa": set(), "csaf": set()}
    for _, r in rows:
        if fam_of(r.get("task", "")) != "t3":
            continue
        parts = r["task"].split(":")
        need[parts[1]].add(parts[2] if parts[1] != "csaf" else r["task"].split(":", 2)[2])
    idx = {"kev": {}, "dsa": {}, "csaf": {}}
    specs = [("kev", "c0_kev.jsonl", r"(CVE-\d{4}-\d+)"),
             ("dsa", "c0_debian-dsa.jsonl", r"\[(DSA[- ]\d{3,4}-\d+)\]"),
             ("csaf", "c0_redhat-csaf.jsonl", r"(RHSA-\d{4}:\d+)")]
    for src, fn, pat in specs:
        want = need[src]
        if not want:
            continue
        rx = re.compile(pat)
        with open(CLEAN / fn, encoding="utf-8") as f:
            for line in f:
                m = rx.search(line)
                if not m:
                    continue
                norm = m.group(1).replace("DSA ", "DSA-")
                if norm in want:
                    idx[src].setdefault(norm, []).append(json.loads(line)["text"])
    return idx


# ungrounded 场景 → (目标语料键, 需缺席短语)；复检时按题面编号动态断言的类别另补
UNG_SCEN = {
    "pf-breach": ("pf", ["breach notification", "72 hours"]),
    "n53-promptinj": ("nist53", ["prompt injection"]),
    "n53-ransom": ("nist53", ["ransomware"]),
    "gdpr-redteam": ("gdpr", ["red team"]),
    "gdpr-poison": ("gdpr", ["model poisoning"]),
    "fips-pentest": ("fips199", ["penetration test"]),
    "airmf-keyrot": ("airmf", ["key rotation"]),
    "owasp-xxe": ("owasp", ["xml external entity"]),
    "iso27001": ("all", ["iso/iec 27001"]),
    "pcidss": ("all", ["pci dss"]),
    "soc2": ("all", ["soc 2"]),
    "glba": ("all", ["gramm-leach"]),
    "pf-penalty": ("pf", ["civil monetary penalty"]),
    "pf-dsar": ("pf", ["access request"]),
    "sp171-fedramp": ("sp171", ["fedramp"]),
    "fips199-srr": ("fips199", ["shared responsibility"]),
}


def verify(path: Path, families: list[str], m1_hashes: set[str]) -> dict:
    errors = []
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if line.strip():
                rows.append((i, json.loads(line)))

    cnt = {"t3": 0, "t12": 0, "t11": 0}
    lang_cnt = {"t3": {"zh": 0, "en": 0}, "t12": {"zh": 0, "en": 0}, "t11": {"zh": 0, "en": 0}}
    tiers, t12_kind, t11_axis, unground_cats = {}, {}, {}, {}
    ids, users = set(), set()
    ver_re = re.compile(r'VERDICT: (\{.*\})\s*$', re.S)

    t3_idx = t3_corpus_index(rows)
    corpus_raw, corpus_low = corpus_maps()

    for i, r in rows:
        sid = f"line{i}:{r.get('id')}"
        fam = fam_of(r.get("task", ""))
        if fam == "?":
            errors.append(f"{sid}: 未知 task {r.get('task')}")
            continue
        if fam not in families:
            continue
        if set(r) != {"id", "task", "pack", "lang", "messages"}:
            errors.append(f"{sid}: 字段集错误")
            continue
        if r["id"] in ids:
            errors.append(f"{sid}: id 重复")
        ids.add(r["id"])
        if r["pack"] != "default":
            errors.append(f"{sid}: pack != default")
        msgs = r["messages"]
        if not (len(msgs) == 3 and [m["role"] for m in msgs] == ["system", "user", "assistant"]):
            errors.append(f"{sid}: 消息结构错误")
            continue
        u, a = msgs[1]["content"], msgs[2]["content"]
        hu = hashlib.sha256(u.encode("utf-8")).hexdigest()
        if hu in users:
            errors.append(f"{sid}: user 重复")
        users.add(hu)
        if hu in m1_hashes:
            errors.append(f"{sid}: 与 m1 user 同文")
        cnt[fam] += 1
        lang_cnt[fam][r["lang"]] += 1
        if r["lang"] == "zh" and len(CJK.findall(u)) < 10:
            errors.append(f"{sid}: zh 行 CJK<10")
        if r["lang"] == "en" and (CJK.search(u) or CJK.search(a)):
            errors.append(f"{sid}: en 行含 CJK")
        m = ver_re.search(a)
        if not m:
            errors.append(f"{sid}: 无 VERDICT 结尾")
            continue
        try:
            v = json.loads(m.group(1))
        except Exception:
            errors.append(f"{sid}: VERDICT 非法 JSON")
            continue
        if v.get("policy") != r["pack"]:
            errors.append(f"{sid}: policy != pack")
        if v.get("action") not in ("answer", "refuse", "report"):
            errors.append(f"{sid}: action 非法")

        if fam == "t3":
            tiers[v["verdict"]] = tiers.get(v["verdict"], 0) + 1
            parts = r["task"].split(":")
            src, eid = parts[1], r["task"].split(":", 2)[2]
            entries = t3_idx.get(src, {}).get(eid, [])
            if not entries:
                errors.append(f"{sid}: 语料条目未找到 {src}:{eid}")
            else:
                snip_m = re.search(r"(?:Summary: |描述：)(.*)$", u, re.S)
                if not snip_m or not any(snip_m.group(1) in e for e in entries):
                    errors.append(f"{sid}: T3 摘要非语料逐字子串")
            if v["action"] != "report" or not v["findings"]:
                errors.append(f"{sid}: T3 action/findings 异常")
        elif fam == "t12":
            kind = "ungrounded" if ":ungrounded:" in r["task"] else "grounded"
            t12_kind[kind] = t12_kind.get(kind, 0) + 1
            if kind == "grounded":
                if v["verdict"] != "grounded" or v["action"] != "answer" or not v["findings"]:
                    errors.append(f"{sid}: grounded VERDICT/findings 异常")
                snip = None
                m1_ = re.search(r"\(Policy text: (.*)\)\s*$", u, re.S)
                m2_ = re.search(r"原文如下：\n(.*)\n请", u, re.S)
                if r["lang"] == "en" and m1_:
                    snip = m1_.group(1)
                elif r["lang"] == "zh" and m2_:
                    snip = m2_.group(1)
                if snip is None:
                    errors.append(f"{sid}: 无法解析引用片段")
                else:
                    src_label = r["task"].split(":")[1]
                    ckey = T12_SOURCES[src_label][0]
                    if snip not in corpus_raw[ckey]:
                        errors.append(f"{sid}: 引用片段非语料逐字子串 ({ckey})")
            else:
                if v["verdict"] != "insufficient-context" or v["findings"]:
                    errors.append(f"{sid}: ungrounded VERDICT/findings 异常")
                if "(Policy text:" in u or "原文如下" in u:
                    errors.append(f"{sid}: ungrounded 不应携带语料片段")
                parts = r["task"].split(":")
                cat = parts[2]
                scen = parts[3] if len(parts) > 3 else None
                unground_cats[cat] = unground_cats.get(cat, 0) + 1
                if cat == "gdpr-art-nonexist":
                    n = re.search(r"Article (\d+)", u)
                    if n and f"article {n.group(1)}" in corpus_low["gdpr"]:
                        errors.append(f"{sid}: Article {n.group(1)} 存在于语料")
                elif cat == "gdpr-recital-nonexist":
                    n = re.search(r"Recital (\d+)|序言第 (\d+) 条", u)
                    num = (n.group(1) or n.group(2)) if n else None
                    if num and f"({num})" in corpus_low["gdpr"]:
                        errors.append(f"{sid}: Recital {num} 存在于语料")
                elif cat == "nist-control-nonexist":
                    c = re.search(r"([A-Z]{2}-\d+)", u)
                    if c and c.group(1).lower() in corpus_low["nist53"]:
                        errors.append(f"{sid}: 控制 {c.group(1)} 存在于语料")
                elif cat == "owasp-llm-nonexist":
                    n = re.search(r"LLM(\d+)", u)
                    if n and f"llm{n.group(1)}" in corpus_low["owasp"]:
                        errors.append(f"{sid}: LLM{n.group(1)} 存在于语料")
                chk = UNG_SCEN.get(scen) if scen else None
                if scen and chk is None:
                    errors.append(f"{sid}: 未知 ungrounded 场景 {scen}")
                elif chk:
                    ckey, phrases = chk
                    for ph in phrases:
                        if ph.lower() in corpus_low[ckey]:
                            errors.append(f"{sid}: 负例关键词 '{ph}' 存在于 {ckey}")
        else:
            ax = r["task"].split(":")[1]
            t11_axis[ax] = t11_axis.get(ax, 0) + 1
            if v["verdict"] != "insufficient-context":
                errors.append(f"{sid}: T11 verdict 应为 insufficient-context")
            if v["action"] != "answer":
                errors.append(f"{sid}: T11 action 异常")

    for fam, want in FAM_TOTAL.items():
        if fam not in families:
            continue
        got = cnt[fam]
        if not (0.9 * want <= got <= 1.1 * want):
            errors.append(f"{fam} 配额 {got} 超出 {want}±10%")
    if "t12" in families and t12_kind.get("ungrounded", 0) < 400:
        errors.append(f"ungrounded {t12_kind.get('ungrounded', 0)} < 400")
    if "t3" in families:
        if tiers.get("medium", 0) < 300:
            errors.append(f"T3 medium {tiers.get('medium', 0)} < 300")
        if tiers.get("low", 0) < 250:
            errors.append(f"T3 low {tiers.get('low', 0)} < 250")
    if "t11" in families:
        for ax in T11_AXIS:
            if t11_axis.get(ax, 0) < 100:
                errors.append(f"T11 {ax} {t11_axis.get(ax, 0)} < 100")
    zh = sum(lang_cnt[f]["zh"] for f in families)
    en = sum(lang_cnt[f]["en"] for f in families)
    tot = zh + en
    if tot and not (0.39 <= zh / tot <= 0.41):
        errors.append(f"zh:en = {zh}:{en} 偏离 40:60")

    stats = {"rows": cnt, "lang": lang_cnt, "t3_tiers": tiers,
             "t12_kind": t12_kind, "t12_ungrounded_cats": unground_cats,
             "t11_axis": t11_axis}
    if errors:
        for e in errors[:25]:
            print("FAIL:", e, file=sys.stderr)
        raise SystemExit(f"复检失败：{len(errors)} 项断言未过")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", choices=["all", "t3", "t12", "t11"], default="all")
    ap.add_argument("--out", type=Path, default=STAGE / "fE_t3t12t11.jsonl")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    families = ["t3", "t12", "t11"] if args.family == "all" else [args.family]

    m1_hashes, kev_used = m1_refs()

    if not args.check_only:
        rows = []
        if "t3" in families:
            t3 = gen_t3(kev_used, rng)
            rows += emit(t3)
            print(f"[t3] {len(t3)} rows")
        if "t12" in families:
            t12 = gen_t12_grounded(rng) + gen_t12_ungrounded(rng)
            rng.shuffle(t12)
            for i, r in enumerate(t12, 1):
                r["id"] = f"sft-m25-T12-{i:04d}"
            rows += emit(t12)
            print(f"[t12] {len(t12)} rows")
        if "t11" in families:
            t11 = gen_t11(rng)
            rows += emit(t11)
            print(f"[t11] {len(t11)} rows")
        if args.family != "all":
            existing = []
            if args.out.exists():
                with open(args.out, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            d = json.loads(line)
                            if fam_of(d.get("task", "")) not in families:
                                existing.append(json.loads(line))
            rows = existing + rows
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"written: {args.out} ({len(rows)} rows)")

    stats = verify(args.out, families, m1_hashes)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_json = REPORTS / "m25-fe-t3t12t11-stats.json"
    merged = {"seed": args.seed}
    if out_json.exists():
        try:
            merged = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:
            merged = {}
    merged.update(stats)
    merged["seed"] = args.seed
    out_json.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print("stats:", json.dumps(stats, ensure_ascii=False))
    print("OK: all assertions passed")


if __name__ == "__main__":
    main()
