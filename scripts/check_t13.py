r"""t13 检索种子独立复检（生产硬断言复跑——不信生成器自报）。

对象：data/sft/m2.5-staging/{t13_retrieval,t13_retrieval_longctx}.jsonl
断言（任一失败 → 退出码 1，reports/t13-staging-check.json 记录全量）：
  1. 行数精确：主集 1,500 / 深位 200；字段集与 key 顺序 = m1 契约
     {id,task,pack,lang,messages}；id 前缀与唯一性；task ∈ T13 族表
  2. 结构：system 逐字等于政策包模板（pack:@0.1）/ system-user-assistant
     交替 / 末轮 VERDICT 闭环（action=answer；verdict ∈ retrieved /
     not-in-doc；policy==pack；hardneg findings 携 absent 术语）
  3. lang↔内容一致：zh 行 user ≥10 CJK；en 行 user+assistant 零 CJK
  4. 文档区：开始/结束标记各恰一次；hit 行答案值（assistant 首行）在
     文档区**恰好出现一次**；引文（“…”）确在文档区
  5. **深位断言**：hit 行答案值 token 相对深度 ∈ [0.30, 0.90]（Qwen3
     tokenizer 口径，与 needle 探针对齐）
  6. **出处可验证**：回复引用的段号/行号处确实包含答案值（按族解析引用
     格式，段=\n\n 切分、行=\n 切分）
  7. hard-negative：absent 术语不在文档区且出现在回复中；回复含
     “未出现”/“does not appear”
  8. 包络：主集文档 ∈ [1000,3500] tok 且全行（sys+user+asst+32 开销）
     ≤4096；深位文档 ∈ [8000,32768] tok
  9. 配比精确：zh:en=600:900 / 80:120；sec:gen=900:600 / 120:80；
     hardneg=225 / 29；每族三包非零
 10. 去重：与 v0/v0x/m1/m25-staging(t1,t9) 及自身/跨文件零同文
 11. 污染：8-gram 匹配器 v3（探针四版本 + 留出三版本全量基线）零命中

用法：.venv\\Scripts\\python.exe scripts\\check_t13.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import POLICY_SYSTEM  # noqa: E402  契约源（system 模板）
from check_sft_contamination import (  # noqa: E402  匹配器 v3 复用
    PREFIX_LEN, build_ngram_index, compile_alt_regex, doc_probe_hits,
    extract_ais_title, normalize, verify_shared_substring)

STAGE = ROOT / "data" / "sft" / "m2.5-staging"
OUT = ROOT / "reports" / "t13-staging-check.json"
CJK = re.compile(r"[\u4e00-\u9fff]")
DOC_MARK = {"zh": ("===== 文档开始 =====", "===== 文档结束 ====="),
            "en": ("===== DOCUMENT START =====", "===== DOCUMENT END =====")}
FAMILIES = {"log-ip", "credential", "cve-digest", "cwe-lookup",
            "clause-lookup", "code-needle", "wiki-fact", "spec-block"}
SEC_FAMILIES = {"log-ip", "credential", "cve-digest", "cwe-lookup",
                "clause-lookup", "code-needle"}

# 期望配额（独立重述，不 import 生成器）
EXPECT = {
    "t13_retrieval": {
        "n": 1500, "zh": 600, "en": 900, "sec": 900, "hardneg": 225,
        "doc_lo": 1000, "doc_hi": 3500, "row_cap": True,
        "quota": {
            "log-ip":        {"en": (122, 22), "zh": (82, 14)},
            "credential":    {"en": (92, 16), "zh": (61, 11)},
            "cve-digest":    {"en": (202, 38)},
            "cwe-lookup":    {"en": (51, 9)},
            "clause-lookup": {"zh": (77, 13)},
            "code-needle":   {"en": (77, 13)},
            "wiki-fact":     {"en": (143, 25), "zh": (189, 33)},
            "spec-block":    {"en": (77, 13), "zh": (102, 18)},
        }},
    "t13_retrieval_longctx": {
        "n": 200, "zh": 80, "en": 120, "sec": 120, "hardneg": 29,
        "doc_lo": 8000, "doc_hi": 32768, "row_cap": False,
        "quota": {
            "log-ip":        {"en": (17, 3), "zh": (11, 2)},
            "credential":    {"en": (12, 2), "zh": (8, 2)},
            "cve-digest":    {"en": (23, 4)},
            "cwe-lookup":    {"en": (7, 1)},
            "clause-lookup": {"zh": (10, 2)},
            "code-needle":   {"en": (14, 2)},
            "wiki-fact":     {"en": (19, 3), "zh": (26, 4)},
            "spec-block":    {"en": (11, 2), "zh": (13, 2)},
        }},
}

CITE_ZH_PL = re.compile(r"第 (\d+) 段.*?第 (\d+) 行")
CITE_ZH_P = re.compile(r"第 (\d+) 段")
CITE_EN_PL = re.compile(r"paragraph (\d+).*?line (\d+)")
CITE_EN_P = re.compile(r"paragraph (\d+)")
CITE_EN_L = re.compile(r"document line (\d+)")


def load_rows() -> dict[str, list[tuple[int, dict]]]:
    out = {}
    for name in EXPECT:
        rows = []
        with open(STAGE / f"{name}.jsonl", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip():
                    rows.append((i, json.loads(line)))
        out[name] = rows
    return out


def get_tok():
    os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from transformers import AutoTokenizer
    t = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B-Base")

    def n(text: str) -> int:
        return len(t(text, add_special_tokens=False)["input_ids"])
    return n


def doc_region(user: str, lang: str) -> str:
    m0, m1 = DOC_MARK[lang]
    i = user.index(m0) + len(m0)
    j = user.index(m1)
    return user[i: j].strip("\n")


def check_rows(name, rows, tok_n, errors, report):
    quota = EXPECT[name]["quota"]
    stats = {"family": {}, "lang": {}, "pack": {}, "kind": {}, "depth": [],
             "doc_tokens": []}
    for i, r in rows:
        sid = f"{name}:{i}:{r.get('id')}"
        if list(r.keys()) != ["id", "task", "pack", "lang", "messages"]:
            errors.append(f"{sid}: 字段集/顺序 != m1 契约")
            continue
        fam, kind = r["task"].rsplit(":", 2)[1], r["task"].rsplit(":", 1)[1]
        if fam not in FAMILIES or kind not in ("hit", "hardneg"):
            errors.append(f"{sid}: task 非法 {r['task']}")
            continue
        if not r["id"].startswith("sft-m25-T13L-" if "longctx" in name
                                  else "sft-m25-T13-"):
            errors.append(f"{sid}: id 前缀非法")
        if r["pack"] not in POLICY_SYSTEM or r["lang"] not in ("zh", "en"):
            errors.append(f"{sid}: pack/lang 非法")
            continue
        msgs = r["messages"]
        if [m["role"] for m in msgs] != ["system", "user", "assistant"]:
            errors.append(f"{sid}: 角色交替断裂")
            continue
        lang, pack = r["lang"], r["pack"]
        if msgs[0]["content"] != POLICY_SYSTEM[pack][lang]:
            errors.append(f"{sid}: system 模板不匹配")
        user, asst = msgs[1]["content"], msgs[2]["content"]
        if not user.strip() or not asst.strip():
            errors.append(f"{sid}: 空 content")
            continue
        # lang ↔ 内容
        if lang == "zh" and len(CJK.findall(user)) < 10:
            errors.append(f"{sid}: zh user CJK 不足")
        if lang == "en" and (CJK.search(user) or CJK.search(asst)):
            errors.append(f"{sid}: en 含 CJK")
        # VERDICT 闭环
        if "VERDICT: " not in asst:
            errors.append(f"{sid}: 缺 VERDICT")
            continue
        try:
            v = json.loads(asst.rsplit("VERDICT: ", 1)[1])
        except json.JSONDecodeError:
            errors.append(f"{sid}: VERDICT JSON 解析失败")
            continue
        if v.get("policy") != pack or v.get("action") != "answer":
            errors.append(f"{sid}: VERDICT policy/action 非法")
        # 文档区
        m0, m1 = DOC_MARK[lang]
        if user.count(m0) != 1 or user.count(m1) != 1:
            errors.append(f"{sid}: 文档标记异常")
            continue
        doc = doc_region(user, lang)
        dt = tok_n(doc)
        stats["doc_tokens"].append(dt)
        if not (EXPECT[name]["doc_lo"] <= dt <= EXPECT[name]["doc_hi"]):
            errors.append(f"{sid}: 文档 token {dt} 越界")
        if EXPECT[name]["row_cap"]:
            total = tok_n(msgs[0]["content"]) + tok_n(user) + tok_n(asst) + 32
            if total > 4096:
                errors.append(f"{sid}: 全行 token {total} > 4096")
        first_line = asst.split("\n", 1)[0]
        if v.get("verdict") == "retrieved":
            if kind != "hit":
                errors.append(f"{sid}: verdict/kind 不一致")
                continue
            value = first_line.rstrip("。.")
            if not value or value not in doc:
                errors.append(f"{sid}: 答案值不在文档区")
                continue
            if doc.count(value) != 1:
                errors.append(f"{sid}: 答案值非唯一（{doc.count(value)}）")
                continue
            off = doc.index(value)
            depth = tok_n(doc[:off]) / max(1, dt)
            stats["depth"].append(depth)
            if not (0.30 <= depth <= 0.90):
                errors.append(f"{sid}: 深位 {depth:.3f} 越界")
            if v.get("findings") != []:
                errors.append(f"{sid}: hit findings 非空")
            # 引文可验证
            qm = re.search(r"“([^”]+)”", asst)
            if not qm or qm.group(1) not in doc:
                errors.append(f"{sid}: 引文不在文档区")
            # 出处定位：段/行处确实含答案值
            paras = doc.split("\n\n")
            lines = doc.split("\n")
            ok = False
            if fam in ("log-ip", "credential", "spec-block"):
                mm = (CITE_ZH_PL.search(asst) if lang == "zh"
                      else CITE_EN_PL.search(asst))
                if mm:
                    p, ln = int(mm.group(1)), int(mm.group(2))
                    ok = (1 <= p <= len(paras) and 1 <= ln <= len(
                        paras[p - 1].split("\n")) and value in
                        paras[p - 1].split("\n")[ln - 1])
            elif fam == "code-needle":
                mm = CITE_EN_L.search(asst)
                if mm:
                    nline = int(mm.group(1))
                    ok = 1 <= nline <= len(lines) and value in \
                        lines[nline - 1]
            else:
                mm = (CITE_ZH_P.search(asst) if lang == "zh"
                      else CITE_EN_P.search(asst))
                if mm:
                    p = int(mm.group(1))
                    ok = 1 <= p <= len(paras) and value in paras[p - 1]
            if not ok:
                errors.append(f"{sid}: 出处定位不可验证")
        elif v.get("verdict") == "not-in-doc":
            if kind != "hardneg":
                errors.append(f"{sid}: verdict/kind 不一致")
                continue
            f = v.get("findings") or []
            if len(f) != 1 or not str(f[0]).startswith("absent: "):
                errors.append(f"{sid}: hardneg findings 缺 absent 术语")
                continue
            term = str(f[0])[len("absent: "):]
            if term in doc:
                errors.append(f"{sid}: absent 术语出现在文档区")
            if term not in asst:
                errors.append(f"{sid}: absent 术语未在回复中说明")
            if "未出现" not in asst and "does not appear" not in asst:
                errors.append(f"{sid}: hardneg 回复缺未出现表述")
        else:
            errors.append(f"{sid}: verdict 非法 {v.get('verdict')}")
        stats["family"][fam] = stats["family"].get(fam, 0) + 1
        stats["lang"][lang] = stats["lang"].get(lang, 0) + 1
        stats["pack"][pack] = stats["pack"].get(pack, 0) + 1
        stats["kind"][kind] = stats["kind"].get(kind, 0) + 1
    # 配额断言
    exp = EXPECT[name]
    if len(rows) != exp["n"]:
        errors.append(f"{name}: 行数 {len(rows)} != {exp['n']}")
    if stats["lang"] != {"zh": exp["zh"], "en": exp["en"]}:
        errors.append(f"{name}: 语言配比 {stats['lang']}")
    sec = sum(c for f, c in stats["family"].items() if f in SEC_FAMILIES)
    if sec != exp["sec"]:
        errors.append(f"{name}: sec:gen {sec} != {exp['sec']}")
    if stats["kind"].get("hardneg", 0) != exp["hardneg"]:
        errors.append(f"{name}: hardneg {stats['kind'].get('hardneg')}"
                      f" != {exp['hardneg']}")
    for fam, langs in exp["quota"].items():
        for ln, (nh, nn) in langs.items():
            got = [r for _, r in rows if
                   r["task"] == f"T13-retrieval:{fam}:hit" and r["lang"] == ln]
            gotn = [r for _, r in rows if r["task"] ==
                    f"T13-retrieval:{fam}:hardneg" and r["lang"] == ln]
            if len(got) != nh or len(gotn) != nn:
                errors.append(f"{name}: 配额漂移 {fam}/{ln}: "
                              f"{len(got)},{len(gotn)} != {nh},{nn}")
    for fam in stats["family"]:
        packs = {r["pack"] for _, r in rows
                 if r["task"].rsplit(":", 2)[1] == fam}
        if packs != {"conservative", "default", "professional"}:
            errors.append(f"{name}: {fam} 包梯度缺失 {packs}")
    ids = [r["id"] for _, r in rows]
    if len(set(ids)) != len(ids):
        errors.append(f"{name}: id 重复")
    pu = [(r["pack"], r["messages"][1]["content"]) for _, r in rows]
    if len(set(pu)) != len(pu):
        errors.append(f"{name}: (pack,user) 重复")
    report[name] = {"rows": len(rows), "by_family": stats["family"],
                    "by_lang": stats["lang"], "by_pack": stats["pack"],
                    "by_kind": stats["kind"],
                    "depth_min_max": ([round(min(stats["depth"]), 4),
                                       round(max(stats["depth"]), 4)]
                                      if stats["depth"] else None),
                    "doc_tokens_min_max": ([min(stats["doc_tokens"]),
                                            max(stats["doc_tokens"])]
                                           if stats["doc_tokens"] else None)}


def check_dedup(all_rows, errors):
    old = set()
    for d in (ROOT / "data" / "sft" / "v0", ROOT / "data" / "sft" / "v0x"):
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    old.add(normalize(j["messages"][1]["content"] + "\x00"
                                      + j["messages"][2]["content"]))
    for nm in ("t1_injection", "t9_phishing"):
        p = STAGE / f"{nm}.jsonl"
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                old.add(normalize(j["messages"][1]["content"] + "\x00"
                                  + j["messages"][2]["content"]))
    with open(ROOT / "data" / "sft" / "m1" / "train.jsonl", encoding="utf-8") \
            as f:
        for line in f:
            if line.strip():
                j = json.loads(line)
                old.add(normalize(j["messages"][1]["content"] + "\x00"
                                  + j["messages"][2]["content"]))
    seen = set()
    for name, rows in all_rows.items():
        for i, r in rows:
            k = normalize(r["messages"][1]["content"] + "\x00"
                          + r["messages"][2]["content"])
            if k in old:
                errors.append(f"{name}:{i}:{r['id']}: 与既有语料同文")
            if k in seen:
                errors.append(f"{name}:{i}:{r['id']}: 跨行同文")
            seen.add(k)


def load_baseline():
    probe_dirs = [ROOT / "data" / "probes" / v
                  for v in ("v0.1", "v0.1.1", "v0.3", "ais-500-draft")]
    heldout_dirs = [ROOT / "data" / "heldout" / v
                    for v in ("v0.1", "v0.2", "v0.2.1")]
    probes, ais_titles, seen = {}, {}, set()
    for d in probe_dirs:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                j = json.loads(line)
                text = j.get("text") or ""
                if text:
                    key = normalize(text)
                    if key not in seen:
                        seen.add(key)
                        probes[f"{d.name}/{f.stem}:{j.get('id', len(probes))}"] \
                            = text
                        if f.stem == "ais":
                            t = extract_ais_title(text)
                            if t:
                                ais_titles.setdefault(normalize(t), 1)
    queries = set()
    for d in heldout_dirs:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                j = json.loads(line)
                q = j.get("query") or j.get("text") or ""
                if q:
                    queries.add(normalize(q))
    return probes, ais_titles, queries


def check_contamination(all_rows, report):
    probes, ais_titles, queries = load_baseline()
    ngram_index = build_ngram_index(probes)
    prefix_re = compile_alt_regex(
        [normalize(t)[:PREFIX_LEN] for t in probes.values()
         if len(normalize(t)) >= PREFIX_LEN])
    title_re = compile_alt_regex([t for t in ais_titles if len(t) >= 16])
    query_re = compile_alt_regex([q for q in queries if len(q) >= 12])
    report["baseline"] = {"probes_unique": len(probes),
                          "ais_titles": len(ais_titles),
                          "queries": len(queries)}
    flagged = []
    for name, rows in all_rows.items():
        for i, r in rows:
            doc = r["messages"][1]["content"] + "\n" \
                + r["messages"][2]["content"]
            t = normalize(doc)
            methods = []
            if prefix_re.search(t):
                methods.append("prefix")
            if title_re.search(t):
                methods.append("title")
            if query_re.search(t):
                methods.append("query")
            for pid, win in doc_probe_hits(doc, ngram_index).items():
                if verify_shared_substring(doc, probes[pid], window=win) >= 60:
                    methods.append(f"ngram:{pid[:60]}")
            if methods:
                flagged.append({"row": f"{name}:{i}", "id": r["id"],
                                "methods": methods})
    report["contamination_flagged"] = flagged
    return len(flagged)


def main() -> int:
    errors: list[str] = []
    report: dict = {"targets": {}}
    all_rows = load_rows()
    print("loading tokenizer...")
    tok_n = get_tok()
    for name, rows in all_rows.items():
        print(f"checking {name} ({len(rows)} rows)...")
        check_rows(name, rows, tok_n, errors, report["targets"])
    print("dedup vs v0/v0x/m1/t1/t9 + self/cross...")
    check_dedup(all_rows, errors)
    print("contamination sweep (matcher v3, full baseline)...")
    n_flag = check_contamination(all_rows, report)
    if n_flag:
        errors.append(f"污染检查 {n_flag} 行命中")
    report["errors"] = errors[:200]
    report["n_errors"] = len(errors)
    report["verdict"] = "PASS" if not errors else f"FAIL ({len(errors)})"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"],
                      "baseline": report.get("baseline"),
                      "errors": errors[:20]}, ensure_ascii=False, indent=2))
    print(f"-> {OUT}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
