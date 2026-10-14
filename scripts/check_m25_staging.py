r"""M2.5 staging 种子复检（生产硬断言独立复跑——不信生成器自报）。

对象：data/sft/m2.5-staging/{t1_injection,t9_phishing}.jsonl
断言（任一失败 → 退出码 1）：
  1. 行数精确：t1=375 / t9=50；字段集 = m1 契约 {id,task,pack,lang,messages}
  2. 结构：system 政策引用（pack:@0.1）/ user-assistant 交替 / 末轮
     VERDICT 闭环 / policy==pack / action ∈ {answer,refuse,report}
  3. lang↔内容一致：zh 行 user ≥10 CJK；en 行 user+assistant 零 CJK
     （6.4K en 字段误写垃圾行教训——硬闸）
  4. 唯一性：id 唯一；(pack,user) 唯一；与 v0/v0x 全量零同文
  5. 配比：t1 zh:en=150:225、t9=20:30；三包均非零；t1 攻击:对照=300:75、
     t9 phishing/suspicious/benign=20/15/15
  6. 污染：8-gram 匹配器 v3（check_sft_contamination 复用）对照
     data/probes/ 全版本（v0.1/v0.1.1/v0.3/ais-500-draft）+
     data/heldout/ 全版本（v0.1/v0.2/v0.2.1）零命中
输出：reports/m25-staging-check.json

用法：.venv\\Scripts\\python.exe scripts/check_m25_staging.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_sft_contamination import (  # noqa: E402  匹配器 v3 复用
    PREFIX_LEN, build_ngram_index, compile_alt_regex, doc_probe_hits,
    extract_ais_title, normalize, verify_shared_substring)

STAGE = ROOT / "data" / "sft" / "m2.5-staging"
V0_DIR = ROOT / "data" / "sft" / "v0"
V0X_DIR = ROOT / "data" / "sft" / "v0x"
PROBE_DIRS = [ROOT / "data" / "probes" / v
              for v in ("v0.1", "v0.1.1", "v0.3", "ais-500-draft")]
# 2026-10-07：新增 v0.6-dilution（P0.6 稀释仪器载荷池；load_baseline 读
# query/text 字段 ⇒ 载荷文本进入 m25 污染基线。接线要求见
# reports/p0.6-dilution-instrument-design.md §11.4）。
# 2026-10-14：新增 v0.7-jailbreak（P0.7 对话式越狱仪器；同上读
# query/text 字段进入 m25 污染基线。接线要求见
# reports/p0.7-jailbreak-instrument-design.md §11.2）。
HELDOUT_DIRS = [ROOT / "data" / "heldout" / v
                for v in ("v0.1", "v0.2", "v0.2.1", "v0.3-gen", "v0.6-dilution",
                          "v0.7-jailbreak")]
OUT = ROOT / "reports" / "m25-staging-check.json"
_CJK = re.compile(r"[\u4e00-\u9fff]")
EXPECT = {"t1_injection": 375, "t9_phishing": 50}
# EXTRA：全族复检（存在才查；min_rows 下限；prefixes=None 跳过前缀断言）
EXTRA = {
    "fA_policy_v0x2": (6000, ("T5-policy",)),
    "fB_t4ground": (5000, None),
    "fC_cvpku_release": (7000, ("T5-attack",)),
    "fD_t6": (4500, ("T6-code",)),
    "fE_t3t12t11": (3500, ("T3-risk", "T12-policyqa", "T11-calibration")),
    "fG_t6_devign_ext": (11000, ("T6-code",)),
    "t13_retrieval": (1400, ("T13-retrieval",)),
    "t14_authinject": (2400, ("T14-authinject",)),
    # S1 族线（2026-09-30 起）：T9 扩容 96→1,596 行；task 沿用 T9-phish:{carrier}:{cue}:{verdict}
    "t9_phish_expand": (1500, ("T9-phish",)),
    "doc_structure": (1100, ("T15-doc",)),
    "t2_mechanism": (1100, ("T2-mechanism",)),
}


def load_rows() -> dict[str, list[dict]]:
    out = {}
    files = dict(EXPECT)
    for name in EXTRA:
        if (STAGE / f"{name}.jsonl").exists():
            files[name] = None  # 无精确行数预期（下限断言）
    for name in files:
        rows = []
        with open(STAGE / f"{name}.jsonl", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip():
                    rows.append((i, json.loads(line)))
        out[name] = rows
    return out


def check_structure_lang_uniqueness(rows, name, errors, prefixes=None):
    ids, seen_pack_user = set(), set()
    # prefixes=None → 跳过前缀断言；默认仅 t1/t9（主调用方显式传入）
    allowed = prefixes
    stats = {"lang": {}, "pack": {}, "verdict": {}, "action": {}}
    for i, r in rows:
        sid = f"{name}:{i}:{r.get('id')}"
        if set(r) != {"id", "task", "pack", "lang", "messages"}:
            errors.append(f"{sid}: 字段集 != m1 契约")
            continue
        if r["id"] in ids:
            errors.append(f"{sid}: id 重复")
        ids.add(r["id"])
        if r["lang"] not in ("zh", "en"):
            errors.append(f"{sid}: lang 非法 {r['lang']}")
            continue
        if r["pack"] not in ("conservative", "default", "professional"):
            errors.append(f"{sid}: pack 非法 {r['pack']}")
        msgs = r["messages"]
        if not (len(msgs) == 3 and msgs[0]["role"] == "system"
                and msgs[1]["role"] == "user"
                and msgs[2]["role"] == "assistant"):
            errors.append(f"{sid}: 消息结构非 system/user/assistant")
            continue
        if "pack:" not in msgs[0]["content"] or "@0.1" not in \
                msgs[0]["content"]:
            errors.append(f"{sid}: system 缺政策引用")
        user, asst = msgs[1]["content"], msgs[2]["content"]
        if not user.strip() or not asst.strip():
            errors.append(f"{sid}: 空内容")
            continue
        if "VERDICT: " not in asst:
            errors.append(f"{sid}: assistant 缺 VERDICT")
            continue
        try:
            v = json.loads(asst.rsplit("VERDICT: ", 1)[1])
        except json.JSONDecodeError:
            errors.append(f"{sid}: VERDICT JSON 解析失败")
            continue
        if v.get("policy") != r["pack"]:
            errors.append(f"{sid}: policy≠pack")
        if v.get("action") not in ("answer", "refuse", "report"):
            errors.append(f"{sid}: action 非法 {v.get('action')}")
        # lang↔内容一致性（dsh-protocol 信封的固定中文标签=m1 T4a 既定
        # 约定，user 侧豁免；assistant 侧仍严查）
        env = user.lstrip().startswith("<dsh-protocol")
        if r["lang"] == "zh" and len(_CJK.findall(user)) < 10 and not env:
            errors.append(f"{sid}: zh 行 user 中文不足")
        if r["lang"] == "en":
            if _CJK.search(user) and not env:
                # 引文源豁免：T4 法条接地行的「引用源段」可为中文条文原文
                # （m1 t4b 同形态），但末段（用户查询）必须纯英文
                parts = user.rsplit("\n\n", 1)
                tail = parts[-1] if len(parts) > 1 else ""
                quoted = user.lstrip().startswith("Policy text (")
                if not (quoted and tail and not _CJK.search(tail)):
                    errors.append(f"{sid}: en 行 user 含中文")
            if _CJK.search(asst):
                errors.append(f"{sid}: en 行 assistant 含中文")
        key = (r["pack"], user)
        if key in seen_pack_user:
            errors.append(f"{sid}: (pack,user) 重复")
        seen_pack_user.add(key)
        if allowed is not None and not r["task"].startswith(allowed):
            errors.append(f"{sid}: task 前缀非法 {r['task']}")
        stats["lang"][r["lang"]] = stats["lang"].get(r["lang"], 0) + 1
        stats["pack"][r["pack"]] = stats["pack"].get(r["pack"], 0) + 1
        stats["verdict"][str(v.get("verdict"))] = (
            stats["verdict"].get(str(v.get("verdict")), 0) + 1)
        stats["action"][v.get("action")] = (
            stats["action"].get(v.get("action"), 0) + 1)
    return stats


def check_no_dup_vs_v0x(all_rows, errors):
    old = set()
    for d in (V0_DIR, V0X_DIR):
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    old.add(normalize(j["messages"][1]["content"]
                                      + "\x00"
                                      + j["messages"][2]["content"]))
    for name, rows in all_rows.items():
        for i, r in rows:
            k = normalize(r["messages"][1]["content"] + "\x00"
                          + r["messages"][2]["content"])
            if k in old:
                errors.append(f"{name}:{i}:{r['id']}: 与 v0/v0x 同文")


def load_baseline():
    probes, ais_titles, seen = {}, {}, set()
    for d in PROBE_DIRS:
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
                        probes[f"{d.name}/{f.stem}:{j.get('id', len(probes))}"] = text
                        if f.stem == "ais":
                            t = extract_ais_title(text)
                            if t:
                                ais_titles.setdefault(normalize(t), 1)
    queries = set()
    for d in HELDOUT_DIRS:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    q = j.get("query") or j.get("text") or ""
                    if q:
                        queries.add(normalize(q))
    return probes, ais_titles, queries


# 污染命中裁定表（m1 先例：公共法条/公共漏洞库文本的双侧复用为良性；
# 详见 docs/research/probe-contamination-audit.md 与 m25-backfill-plan §6）。
# key = (行 task 前缀, 探针 id 前缀)；命中 → adjudicated 桶（计数上报，不算错误）
ADJUDICATED = [
    ("T4-grounding:t4b2", "v0.1/privacy"),   # GDPR/法规条文逐字引用
    ("T12-policyqa", "v0.1/privacy"),        # GDPR 序言逐字引用
    ("T3-risk:kev", "v0.1/sec"),             # CISA KEV 公开描述双侧复用
]


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
                          "queries": len(queries),
                          "ngram_index_keys": len(ngram_index)}
    flagged = []
    adjudicated = []
    for name, rows in all_rows.items():
        for i, r in rows:
            doc = r["messages"][1]["content"] + "\n" + \
                r["messages"][2]["content"]
            t = normalize(doc)
            methods = []
            if prefix_re.search(t):
                methods.append("prefix")
            if title_re.search(t):
                methods.append("title")
            if query_re.search(t):
                methods.append("query")
            hits = doc_probe_hits(doc, ngram_index)
            if hits:
                for pid, win in hits.items():
                    if verify_shared_substring(doc, probes[pid],
                                               window=win) >= 60:
                        methods.append(f"ngram:{pid}")
            if methods:
                entry = {"row": f"{name}:{i}", "id": r["id"],
                         "task": r.get("task", ""), "methods": methods}
                task = r.get("task", "")
                adj_classes = [pp for tp, pp in ADJUDICATED
                               if task.startswith(tp)]
                ngrams = [m.split(":", 1)[1] for m in methods
                          if m.startswith("ngram:")]
                # 裁定：存在适用类，且所有 ngram 命中都落在该类探针内
                # （prefix/title/query 与 ngram 同文本源，随行豁免）
                ok = bool(adj_classes) and (
                    not ngrams or
                    any(all(pid.startswith(pp) for pid in ngrams)
                        for pp in adj_classes))
                (adjudicated if ok else flagged).append(entry)
    report["contamination_flagged"] = flagged
    report["contamination_adjudicated"] = adjudicated
    report["adjudicated_count"] = len(adjudicated)
    return len(flagged)


def main() -> int:
    errors = []
    all_rows = load_rows()
    report = {"targets": {}}
    for name, rows in all_rows.items():
        if name in EXPECT and len(rows) != EXPECT[name]:
            errors.append(f"{name}: 行数 {len(rows)} != {EXPECT[name]}")
        if name in EXTRA:
            floor, _ = EXTRA[name]
            if len(rows) < floor:
                errors.append(f"{name}: 行数 {len(rows)} < 下限 {floor}")
        prefixes = EXTRA[name][1] if name in EXTRA else ("T1-injection",
                                                         "T9-phish")
        stats = check_structure_lang_uniqueness(rows, name, errors,
                                                prefixes=prefixes)
        report["targets"][name] = {"rows": len(rows), **stats}
    check_no_dup_vs_v0x(all_rows, errors)

    # 配比断言（仅 t1/t9 精确配比；全族包梯度非零）
    t1s, t9s = report["targets"].get("t1_injection", {}), \
        report["targets"].get("t9_phishing", {})
    if "t1_injection" in report["targets"] and \
            t1s.get("lang") not in ({"zh": 150, "en": 225}, None):
        errors.append(f"t1 语言配比 != 150:225: {t1s.get('lang')}")
    if "t9_phishing" in report["targets"] and \
            t9s.get("lang") not in ({"zh": 20, "en": 30}, None):
        errors.append(f"t9 语言配比 != 20:30: {t9s.get('lang')}")
    for name, s in report["targets"].items():
        if name == "fE_t3t12t11":
            continue  # 沿 m1 task_single 先例：default 单包
        for p in ("conservative", "default", "professional"):
            if s.get("pack", {}).get(p, 0) == 0:
                errors.append(f"{name}: 包梯度缺失 {p}")
    if "t1_injection" in report["targets"] and (
            t1s.get("verdict", {}).get("contains-injection") != 300 or
            t1s.get("verdict", {}).get("clean") != 75):
        errors.append(f"t1 攻击:对照 != 300:75: {t1s.get('verdict')}")
    if "t9_phishing" in report["targets"]:
        for k, want in (("phishing", 20), ("suspicious", 15), ("benign", 15)):
            if t9s.get("verdict", {}).get(k) != want:
                errors.append(f"t9 {k} != {want}: {t9s.get('verdict')}")

    n_flag = check_contamination(all_rows, report)
    if n_flag:
        errors.append(f"污染检查 {n_flag} 行命中")

    report["errors"] = errors
    report["verdict"] = "PASS" if not errors else f"FAIL ({len(errors)})"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"],
                      "baseline": report.get("baseline"),
                      "errors": errors[:20]}, ensure_ascii=False, indent=2))
    print(f"-> {OUT}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
