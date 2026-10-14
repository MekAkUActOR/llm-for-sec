# -*- coding: utf-8 -*-
"""M2.5 fD 族：T6 代码族双生成器（devign 行级漏洞定位 + CVEfixes 修复分析）。

对应 docs/research/m25-backfill-plan.md §3.2：
  - T6 devign_locate ~3,500：t6_devign_lines.jsonl（10,039 条，行级标注）
    target=1（每样本一个函数）、100<len<8K；输入=裸函数码（剥离 '>>' 标记），
    输出=漏洞行号 + 模式解释（防御侧，零武器化）；zh:en=40:60 × 三包梯度。
  - T6 cvefix ~1,500：(a) CVE→修复要点摘要 800（含 diff 节选）
    (b) CVE→处置建议 700（T4 接地联动）；en 为主 + zh 措辞 40%；三包轮转。

纪律（全继承 v0 红线）：devign/cvefixes 内容只作检测/分析侧输入与目标；
响应模板零武器化；与 m1 既有 T6 行（GTFOBins/LOLBAS 检测审查）零重叠
（不同语料源，仍做 md5(user) 全量排重断言）；assistant 一律 VERDICT 结尾；
seed 确定性（20260929）；不读 probes/heldout（源码无引用）。

用法：python scripts/gen_sft_m25_t6.py
输出：data/sft/m2.5-staging/fD_t6_code.jsonl
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import PACKS, build_sample, verdict_line  # noqa: E402

SRC_DEVIGN = ROOT / "data" / "corpora" / "clean" / "t6_devign_lines.jsonl"
SRC_CVEFIX = ROOT / "data" / "corpora" / "clean" / "t6_cvefixes.jsonl"
M1 = ROOT / "data" / "lf" / "sft_m1.jsonl"
OUT = ROOT / "data" / "sft" / "m2.5-staging" / "fD_t6.jsonl"
RNG_SEED = 20260929
DIFF_CAP = 2500

# ---- 漏洞模式表（防御侧：模式名 / 解释 / 修复方向 / 验证建议）----
PATTERNS = [
    (r"malloc|calloc|realloc|av_malloc|new \w+\[|alloca",
     ("内存分配缺陷", "标记行的分配操作缺乏充分校验（尺寸来源或失败路径），可导致溢出或空指针解引用。",
      "对分配尺寸做来源校验与上限约束，检查返回值并处理失败路径。",
      "用极限尺寸与畸形输入做回归测试，覆盖分配失败分支。"),
     ("allocation defect", "The allocation at the flagged lines lacks adequate validation (size provenance or failure path), enabling overflow or null dereference.",
      "Validate size provenance and enforce upper bounds; check return values and handle failure paths.",
      "Regression-test with extreme sizes and malformed inputs, covering allocation-failure branches.")),
    (r"\bfree\s*\(|delete\b|unref|av_freep",
     ("释放/所有权缺陷", "标记行的释放操作未确认所有权或生命周期，存在重复释放或释放后使用的风险。",
      "明确指针所有权；释放后置空；引入引用计数或 RAII 管理。",
      "用 sanitizer（ASan/UBSan）验证释放路径与后续访问。"),
     ("free/ownership defect", "The free at the flagged lines does not establish ownership or lifetime, risking double-free or use-after-free.",
      "Establish pointer ownership; null after free; use refcounting or RAII.",
      "Validate free paths and subsequent access with sanitizers (ASan/UBSan).")),
    (r"memcpy|strcpy|sprintf|strcat|avio_read|read\s*\(|snprintf|\blen\b|\bsize\b|\bbuf",
     ("长度/边界校验缺失", "标记行在拷贝或读取时未充分校验长度与目标边界，是越界写入的典型来源。",
      "改用带边界的安全变体；校验来源长度并限制拷贝上限。",
      "构造超长输入做边界回归测试。"),
     ("missing length/bounds validation", "The copy/read at the flagged lines lacks length and destination-boundary validation — a classic out-of-bounds write source.",
      "Switch to bounded-safe variants; validate source length and cap copy size.",
      "Boundary regression tests with oversized inputs.")),
    (r"\[\s*\w+\s*\]|\bindex\b|\boffset\b|\bsub\b",
     ("索引未校验", "标记行使用的索引或偏移未经范围校验，可造成越界读写。",
      "对索引/偏移做范围断言与钳制后再访问。",
      "用边界索引（0、max、max+1）做回归测试。"),
     ("unvalidated index", "The index or offset used at the flagged lines is not range-checked, allowing out-of-bounds access.",
      "Assert/clamp index and offset ranges before access.",
      "Regression-test with boundary indices (0, max, max+1).")),
    (r"/\s*\w+|divis|divide",
     ("除零风险", "标记行的除法运算未排除零值除数，可能导致崩溃或未定义行为。",
      "除法前显式校验除数非零，或给出安全回退值。",
      "对除数为 0 的输入做回归测试。"),
     ("division-by-zero risk", "The division at the flagged lines does not exclude a zero divisor, which can crash or invoke UB.",
      "Explicitly check divisor before dividing, or provide a safe fallback.",
      "Regression-test with zero-divisor inputs.")),
    (r"printf|%s|%d|%n",
     ("格式串缺陷", "标记行存在非恒定格式串的使用风险，可被用于信息泄露或内存破坏。",
      "格式串固定为字面量；用户数据只经 %s 传入。",
      "以含 %n/%x 的输入验证格式串不可注入。"),
     ("format-string flaw", "The flagged lines risk a non-constant format string, exploitable for info leak or memory corruption.",
      "Keep format strings literal; pass user data only via %s.",
      "Verify format-string non-injectability with %n/%x inputs.")),
    (r"NULL|null|! *\w+->|\bptr\b",
     ("空指针解引用风险", "标记行在解引用前未确认指针有效性，存在空指针崩溃路径。",
      "解引用前做空检查并在失败时提前返回或降级处理。",
      "构造指针为空的路径做回归测试。"),
     ("null-deref risk", "The flagged lines dereference without confirming pointer validity, leaving a null-crash path.",
      "Null-check before dereference; early-return or degrade on failure.",
      "Regression-test with null-pointer paths.")),
]
PAT_DEFAULT = (
    ("输入校验/边界处理缺陷", "标记行在处理外部输入时缺乏充分的校验或边界约束，构成该函数的主要风险点。",
     "对外部输入做显式校验（类型、范围、长度）后再进入后续逻辑。",
     "以畸形与越界输入做回归测试。"),
    ("input-validation/boundary defect", "The flagged lines process external input without adequate validation or boundary constraints — the function's main risk point.",
     "Explicitly validate external input (type, range, length) before downstream logic.",
     "Regression-test with malformed and out-of-range inputs."))


def classify(lines: list[str]):
    """按标记行内容选模式（防御侧解释）。"""
    blob = "\n".join(lines)
    for rx, zh, en in PATTERNS:
        if re.search(rx, blob):
            return zh, en
    return PAT_DEFAULT


def verdict(action, v, conf, findings, pack):
    return verdict_line(action, v, conf, findings, pack)


# 源文本 CJK 检测（含日文假名）：cvefixes 语料含中文/日文提交信息与注释，
# 若指令侧标为 en 会令 en 行混入 CJK（结构闸硬失败）→ 强制转 zh 指令帧。
_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")


# ---- devign 解析 ----
DEV_HDR = re.compile(
    r"Devign line-annotated vulnerable function \(project: ([^;]+); "
    r"commit: ([0-9a-f]{8,40}); split: (\w+)\): (\d+) vulnerable lines "
    r"flagged with '>>' prefix\.\s*\n")


def parse_devign(text: str):
    m = DEV_HDR.match(text)
    if not m:
        return None
    project, commit, _split, n_decl = m.group(1), m.group(2), m.group(3), int(m.group(4))
    body = text[m.end():]
    # 展示空间 = 归一化后代码；标记行号在同一空间计算（自洽）。
    # 语料伪空行 = 纯空白行（"\n  \n"），真空行 = 连续 ≥2 个空白行段。
    raw_lines = [l.rstrip() for l in body.split("\n")]
    norm, ws_run = [], 0
    for ln in raw_lines:
        if ln == "":
            ws_run += 1
            continue
        if ws_run >= 2:
            norm.append("")  # 真空行（空行 + 伪分隔）
        ws_run = 0
        norm.append(ln)
    marked, clean = [], []
    for ln in norm:
        if ln.startswith(">>"):
            marked.append(len(clean))  # 0-based 行号（剥离后空间）
            clean.append(ln[2:])
        else:
            clean.append(ln)
    if not marked or len(marked) != n_decl:
        return None  # 头部声明数与标记数不一致 → 跳过（宁缺毋滥）
    return project, commit, "\n".join(clean), [i + 1 for i in marked]


# ---- cvefixes 解析 ----
CVE_HDR = re.compile(
    r"CVEfixes record (CVE-\d{4}-\d+) \(CWE-(\d+)"
    r"(?:, severity (CRITICAL|HIGH|MEDIUM|LOW))?, published ([\d-]+)\): "
    r"fix commit ([0-9a-f]{8,40}) in (\S+) \(language: ([\w+#.]+)\)\.")


def parse_cvefix(text: str):
    m = CVE_HDR.match(text)
    if not m:
        return None
    cve, cwe, sev, pub, commit, repo, lang = m.groups()
    rest = text[m.end():]
    desc = commit_msg = ""
    files, diff = [], ""
    i = rest.find("Description:")
    if i >= 0:
        j = rest.find("Commit message:", i)
        desc = rest[i + len("Description:"):j if j >= 0 else len(rest)].strip()
        if j >= 0:
            k = rest.find("Files changed:", j)
            commit_msg = rest[j + len("Commit message:"):k if k >= 0 else len(rest)].strip()
            if k >= 0:
                d = rest.find("Fix diff:", k)
                fseg = rest[k + len("Files changed:"):d if d >= 0 else len(rest)]
                files = [x[2:].strip() for x in fseg.split("\n") if x.startswith("- ")]
                if d >= 0:
                    diff = rest[d + len("Fix diff:"):].strip()
    if not desc:
        return None
    return dict(cve=cve, cwe=cwe, sev=sev or "MEDIUM", pub=pub, commit=commit,
                repo=repo, lang=lang, desc=desc[:600],
                commit_msg=commit_msg[:400], files=files[:4], diff=diff)


CWE_CONTAIN = {
    "835": ("限流与连接超时，配合看门狗自动恢复", "rate-limiting plus connection timeouts with a watchdog for auto-recovery"),
    "400": ("限流与队列上限，配合看门狗自动恢复", "rate-limiting and queue caps with a watchdog for auto-recovery"),
    "79": ("输出编码与 CSP 收紧", "output encoding and tightened CSP"),
    "78": ("输入白名单与转义，避免拼接进 exec/shell", "input allowlists and escaping; never concatenate into exec/shell"),
    "89": ("参数化查询与最小权限账号", "parameterized queries with a least-privilege account"),
    "94": ("隔离执行环境与输入校验，禁用动态求值", "sandboxed execution and input validation; disable dynamic evaluation"),
    "22": ("路径白名单与规范化校验", "path allowlists and canonicalization checks"),
    "125": ("内存边界检查与加固编译（ASan/_FORTIFY）", "memory bounds checks plus hardened builds (ASan/_FORTIFY)"),
    "787": ("内存边界检查与加固编译（ASan/_FORTIFY）", "memory bounds checks plus hardened builds (ASan/_FORTIFY)"),
    "416": ("引用所有权审计与生命周期加固", "ownership audits and lifetime hardening"),
    "476": ("空检查与防御性解引用", "null checks and defensive dereferences"),
    "352": ("CSRF token 与 SameSite 校验", "CSRF tokens and SameSite enforcement"),
    "611": ("禁用外部实体与安全解析器配置", "disable external entities and use hardened parser configs"),
    "798": ("轮换硬编码凭证并改用密钥管理", "rotate hardcoded credentials and move to a secrets manager"),
    "862": ("最小权限与服务账号收敛", "least privilege and service-account scoping"),
    "863": ("最小权限与认证收敛", "least privilege and authentication tightening"),
}
CWE_CONTAIN_DEF = ("最小化暴露面并临时下线受影响组件", "minimize exposure and temporarily take the affected component offline")
PRIO = {"CRITICAL": ("P0 紧急", "P0 urgent"), "HIGH": ("P0 紧急", "P0 urgent"),
        "MEDIUM": ("P1 计划内", "P1 scheduled"), "LOW": ("P2 例行", "P2 routine")}


def main() -> int:
    rng = random.Random(RNG_SEED)
    rows = []

    # ---------- devign：3,500 = 1,167 记录 × 3 包（zh:en = 2:3 轮转） ----------
    recs = []
    with SRC_DEVIGN.open(encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)["text"]
            if not (100 < len(t) < 8000):
                continue
            p = parse_devign(t)
            if p and 1 <= len(p[3]) <= 4:  # 行级目标可数（target 聚焦）
                recs.append(p)
    rng.shuffle(recs)
    lang_cycle = ["zh", "en", "en", "zh", "en"]  # 40% zh
    n_dev = 0
    dev_pack = {p: 0 for p in PACKS}
    for project, commit, code, vuln_lines in recs[:1167]:
        lang = lang_cycle[n_dev % 5]
        zh_pat, en_pat = classify([code.split("\n")[i - 1] for i in vuln_lines])
        lines_str = "、".join(str(x) for x in vuln_lines) if lang == "zh" else ", ".join(str(x) for x in vuln_lines)
        n_str = "共 %d 行" % len(vuln_lines) if lang == "zh" else f"{len(vuln_lines)} line(s)"
        if lang == "zh":
            user = (f"以下函数来自开源项目 {project}。请定位其中的漏洞行：给出"
                    f"行号并解释缺陷模式（分析用途）。\n\n{code}")
            body = {
                "conservative": f"漏洞行：{lines_str}（{n_str}）。模式：{zh_pat[0]}。",
                "default": (f"漏洞行：{lines_str}（{n_str}）。\n模式：{zh_pat[0]}。\n"
                            f"成因与影响：{zh_pat[1]}\n修复方向：{zh_pat[2]}"),
                "professional": (f"漏洞行：{lines_str}（{n_str}）。\n模式：{zh_pat[0]}。\n"
                                 f"成因与影响：{zh_pat[1]}\n修复方向：{zh_pat[2]}\n"
                                 f"验证建议：{zh_pat[3]}"),
            }
        else:
            user = (f"The following function is from the open-source project "
                    f"{project}. Locate the vulnerable lines: give line numbers "
                    f"and explain the defect pattern (analysis use).\n\n{code}")
            body = {
                "conservative": f"Vulnerable lines: {lines_str} ({n_str}). Pattern: {en_pat[0]}.",
                "default": (f"Vulnerable lines: {lines_str} ({n_str}).\nPattern: {en_pat[0]}.\n"
                            f"Cause & impact: {en_pat[1]}\nFix direction: {en_pat[2]}"),
                "professional": (f"Vulnerable lines: {lines_str} ({n_str}).\nPattern: {en_pat[0]}.\n"
                                 f"Cause & impact: {en_pat[1]}\nFix direction: {en_pat[2]}\n"
                                 f"Verification: {en_pat[3]}"),
            }
        for pack in PACKS:
            n_dev += 1
            dev_pack[pack] += 1
            assistant = body[pack] + "\n" + verdict(
                "answer", "contains-vulnerability", 0.9,
                [f"devign:{project}:{commit[:8]}"], pack)
            rows.append(build_sample(f"sft-T6D-{n_dev:04d}",
                                     f"T6-code:devign:{project}:{commit[:8]}",
                                     pack, lang, user, assistant))

    # ---------- cvefix：1,500 = (a) 800 摘要 + (b) 700 处置 ----------
    cvecs = []
    with SRC_CVEFIX.open(encoding="utf-8") as f:
        for line in f:
            p = parse_cvefix(json.loads(line)["text"])
            if p and p["commit_msg"] and p["files"]:
                cvecs.append(p)
    rng.shuffle(cvecs)
    cve_pack_cycle = list(PACKS)
    lang_cycle2 = ["en", "zh", "en", "en", "zh"]  # 40% zh

    def add_cve(rec, mode, idx):
        lang = lang_cycle2[idx % 5]
        pack = cve_pack_cycle[idx % len(PACKS)]
        # 源文本含 CJK → 指令侧强制 zh（避免 en 行混入中文/日文；摘录保持逐字）。
        # 检查范围覆盖实际渲染的 diff 切片（DIFF_CAP），非只前 600 字符。
        if _CJK.search(rec["desc"] + rec["commit_msg"]
                       + " ".join(rec["files"]) + rec["diff"][:DIFF_CAP]):
            lang = "zh"
        prio_zh, prio_en = PRIO.get(rec["sev"], PRIO["MEDIUM"])
        mg = re.search(r"upgrade to version ([\d.]+)", rec["desc"])
        fixed = mg.group(1) if mg else None
        cont_zh, cont_en = CWE_CONTAIN.get(rec["cwe"], CWE_CONTAIN_DEF)
        if mode == "summary":
            diff = rec["diff"][:DIFF_CAP] + ("…(diff truncated)" if len(rec["diff"]) > DIFF_CAP else "")
            adds = [l.lstrip("+").strip() for l in rec["diff"].split("\n")
                    if l.startswith("+") and not l.startswith("+++")][:3]
            if lang == "zh":
                user = (f"CVE 记录：{rec['cve']}（CWE-{rec['cwe']}，发布 "
                        f"{rec['pub']}，语言 {rec['lang']}）。\n描述：{rec['desc']}\n"
                        f"修复提交信息：{rec['commit_msg']}\n变更文件：\n"
                        + "\n".join("- " + x for x in rec["files"])
                        + f"\n修复 diff 节选：\n{diff}\n请给出修复要点摘要。")
                core = (f"根因：CWE-{rec['cwe']} —— {rec['desc'].split('.')[0]}。"
                        f"修复实质：{rec['commit_msg'].split('.')[0]}。")
                prof = ("关键变更：" + ("；".join(adds) if adds else "见 diff 节选")
                        + f"\n回归建议：针对 CWE-{rec['cwe']} 构造触发用例验证修复。")
                body = {"conservative": core + "。",
                        "default": core + "。受影响文件：" + "、".join(rec["files"]) + "。",
                        "professional": core + "。受影响文件：" + "、".join(rec["files"]) + "。\n" + prof}
            else:
                user = (f"CVE record: {rec['cve']} (CWE-{rec['cwe']}, published "
                        f"{rec['pub']}, language {rec['lang']}).\nDescription: "
                        f"{rec['desc']}\nCommit message: {rec['commit_msg']}\n"
                        "Files changed:\n" + "\n".join("- " + x for x in rec["files"])
                        + f"\nFix diff excerpt:\n{diff}\nSummarize the fix essentials.")
                core = (f"Root cause: CWE-{rec['cwe']} — {rec['desc'].split('.')[0]}. "
                        f"Fix essence: {rec['commit_msg'].split('.')[0]}.")
                prof = ("Key changes: " + ("; ".join(adds) if adds else "see diff excerpt")
                        + f"\nRegression: build a CWE-{rec['cwe']} trigger case to verify the fix.")
                body = {"conservative": core,
                        "default": core + " Affected files: " + ", ".join(rec["files"]) + ".",
                        "professional": core + " Affected files: " + ", ".join(rec["files"]) + ".\n" + prof}
            act, verd = "answer", "fix-summary"
        else:  # disposition
            if lang == "zh":
                user = (f"CVE 记录：{rec['cve']}（CWE-{rec['cwe']}，严重级 "
                        f"{rec['sev']}，发布 {rec['pub']}）。\n描述：{rec['desc']}\n"
                        f"请给出处置建议（补丁优先级 / 缓解 / 检测方向）。")
                fix_line = (f"升级至 {fixed}（上游已修复）。" if fixed
                            else "应用上游修复提交。")
                core = (f"补丁优先级：{prio_zh}。{fix_line}\n缓解：{cont_zh}。")
                det = f"检测方向：关注 CWE-{rec['cwe']} 相关的异常信号（崩溃循环/畸形输入日志）。"
                prof = "验证步骤：灰度升级 → 触发用例回归 → 全量 rollout；保留回滚点。"
                body = {"conservative": core,
                        "default": core + "\n" + det,
                        "professional": core + "\n" + det + "\n" + prof}
            else:
                user = (f"CVE record: {rec['cve']} (CWE-{rec['cwe']}, severity "
                        f"{rec['sev']}, published {rec['pub']}).\nDescription: "
                        f"{rec['desc']}\nGive a disposition recommendation "
                        "(patch priority / containment / detection direction).")
                fix_line = (f"Upgrade to {fixed} (fixed upstream)." if fixed
                            else "Apply the upstream fix commit.")
                core = (f"Patch priority: {prio_en}. {fix_line}\nContainment: {cont_en}.")
                det = f"Detection: watch for CWE-{rec['cwe']}-related signals (crash loops, malformed-input logs)."
                prof = "Verification: staged rollout → trigger-case regression → full rollout; keep a rollback point."
                body = {"conservative": core,
                        "default": core + "\n" + det,
                        "professional": core + "\n" + det + "\n" + prof}
            act, verd = "answer", "patch-priority"
        return build_sample(f"sft-T6C-{idx:04d}", f"T6-code:cvefix:{rec['cve']}",
                            pack, lang, user,
                            body[pack] + "\n" + verdict(
                                act, verd, 0.88, [rec["cve"]], pack)), lang, pack

    n_cve = 0
    cve_lang = {"zh": 0, "en": 0}
    cve_pack_cnt = {p: 0 for p in PACKS}
    seen_ku = set()
    for rec in cvecs:
        if n_cve >= 1500:
            break
        row, lang, pack = add_cve(
            rec, "summary" if n_cve < 800 else "disposition", n_cve)
        key = (pack, row["messages"][1]["content"])
        if key in seen_ku:
            continue  # 撞行（同包同 user）弃该记录，继续下一条（池充足）
        seen_ku.add(key)
        n_cve += 1
        cve_lang[lang] += 1
        cve_pack_cnt[pack] += 1
        rows.append(row)

    # ---------- 断言与落盘 ----------
    assert len(rows) in range(4950, 5060), f"total {len(rows)} out of band"
    zh = sum(1 for r in rows if json.dumps(r, ensure_ascii=False).count("zh") and r.get("lang") == "zh") \
        if all("lang" in r for r in rows) else -1
    # lang 字段防御：build_sample 若不带 lang 则按 user 前缀统计
    if zh < 0:
        zh = sum(1 for r in rows if "以下函数" in r["messages"][1]["content"]
                 or "CVE 记录" in r["messages"][1]["content"])
    zh_ratio = zh / len(rows)
    assert 0.35 <= zh_ratio <= 0.48, f"zh ratio {zh_ratio:.3f} out of band"
    for r in rows:
        assert r["messages"][-1]["content"].lstrip().endswith("}") or \
            "VERDICT:" in r["messages"][-1]["content"], "VERDICT missing"
    # md5(user) 与 m1 零重叠
    m1_users = set()
    with M1.open(encoding="utf-8") as f:
        for line in f:
            m = json.loads(line)["messages"]
            for k in range(len(m)):
                if m[k]["role"] == "user":
                    m1_users.add(hashlib.md5(m[k]["content"].encode("utf-8")).hexdigest())
    hit = 0
    for r in rows:
        for m in r["messages"]:
            if m["role"] == "user":
                if hashlib.md5(m["content"].encode("utf-8")).hexdigest() in m1_users:
                    hit += 1
    assert hit == 0, f"{hit} rows collide with m1"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = dict(total=len(rows), devign=n_dev, cvefix=n_cve,
                  zh_ratio=round(zh_ratio, 4), dev_pack=dev_pack,
                  cve_lang=cve_lang, cve_pack=cve_pack_cnt, m1_collision=hit,
                  out=str(OUT))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
