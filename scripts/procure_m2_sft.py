"""M2 SFT 物料采购(docs/research/m2-sft-sources.md §5 短名单,2026-09-25 父会话决策)。

采购范围(许可干净第一批,11 源 + 1 参照):
  hh-rlhf-harmlessness(MIT) / safety-prompts(Apache,本地克隆转正) /
  safemtdata(MIT) / advbench(MIT) / harmbench(MIT) / strongreject(MIT) /
  maliciousinstruct(CC-BY-SA-4.0) / xstest(CC-BY-4.0) / or-bench(CC-BY-4.0) /
  trustllm(MIT) / cvalues(Apache)
  tc260(**tier=reference,eval 参照,永不入训练**——父会话决策:网安标委官方
  测试集,训练它=污染行业基准;仅类目体系指导生成器模板,物料与训练物理隔离)

产物(均为 raw 物料,不做 SFT 格式转换——转换是配对生成器侧的事):
  data/corpora/raw/m2/{sid}/...          训练物料
  data/corpora/raw/m2-reference/tc260/   参照物料(物理分离)
  manifest 登记:tier=public(或 reference)/domain=sft/files 指向 raw
  reports/m2-sft-procurement.json        采购实况+红线统计+格式清单

红线纪律(父会话指令):逐条核,越线(响应侧武器化 how-to)跳过并计数——
  * prompt/请求侧 = 攻击框架输入,合法(docs/06 红线框架);
  * response/载荷侧含武器化制作细节 → 整条跳过+计数;
  * 检查器为启发式(_WEAPONIZED_RESPONSE 标记表),命中极少(学术基准均请求型),
    命中清单落报告供人工复核。

污染检查独立于本脚本:scripts/check_sft_contamination.py(§4 方案)。

用法:python scripts/procure_m2_sft.py [--skip-fetch] [--skip-manifest]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import upsert_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "m2"
REF = ROOT / "data" / "corpora" / "raw" / "m2-reference"
RESEARCH = ROOT / "data" / "corpora" / "raw" / "m2-research"
REPORT = ROOT / "reports" / "m2-sft-procurement.json"
UA = "llm-for-sec-m2-procurement/0.1"

# ------------------------------------------------------------------ 红线检查器(纯函数) --
# 响应侧武器化 how-to 标记(保守启发:命中即跳过该条+人工复核;
# prompt 侧请求措辞不算——攻击框架输入是 SFT 标准用法,docs/06)
_CBRN = (r"(synthes(?:is|ize|izing)|production of|how to make|preparation of|"
         r"step[- ]by[- ]step|制造方法|合成方法|制备)")
_AGENT = (r"(ricin|sarin|vx nerve|mustard gas|tabun|anthrax|dimethylmercury|"
          r"fentanyl precursor|pipe bomb|ied\b|pressure cooker bomb|"
          r"蓖麻毒素|沙林|芥子气|土制炸弹|遥控引爆)")
_WEAPONIZED_RESPONSE = re.compile(
    rf"(?is)(?:{_AGENT}).{{0,220}}(?:{_CBRN})|(?:{_CBRN}).{{0,220}}(?:{_AGENT})")


def response_violates(text: str) -> bool:
    """响应/载荷文本是否含武器化制作细节(启发式,命中→跳过+计数)。"""
    return bool(text) and bool(_WEAPONIZED_RESPONSE.search(text))


# ------------------------------------------------------------------ 拉取原语 --
def curl_fetch(url: str, dest: Path, timeout: int = 600, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        p = subprocess.run(
            ["curl.exe", "-sSL", "--noproxy", "*", "--max-time", str(timeout),
             "-A", UA, "-o", str(dest) + ".part", url],
            capture_output=True, timeout=timeout + 60)
        if p.returncode == 0 and dest.with_suffix(dest.suffix + ".part").exists():
            part = Path(str(dest) + ".part")
            if part.stat().st_size > 0:
                part.replace(dest)
                return True
        time.sleep(2 ** i)
    return False


def git_clone(o: str, r: str, dest: Path) -> bool:
    if dest.exists() and any(dest.iterdir()):
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        ["git", "clone", "--depth", "1", f"https://github.com/{o}/{r}.git",
         str(dest), "-c", f"http.userAgent={UA}", "-c", "http.proxy="],
        capture_output=True, timeout=900)
    return dest.exists() and any(dest.iterdir())


# ------------------------------------------------------------------ 各源解析(格式清单 + 红线) --
def _iter_jsonl_gz(p: Path):
    with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _hh_turns(conv: str) -> int:
    return conv.count("\n\nHuman:")


def src_hh_rlhf(d: Path) -> dict:
    rows = list(_iter_jsonl_gz(d / "harmless-base" / "train.jsonl.gz"))
    rows += list(_iter_jsonl_gz(d / "harmless-base" / "test.jsonl.gz"))
    skipped = 0
    for r in rows:
        for side in ("chosen", "rejected"):
            if response_violates(r.get(side, "")):
                skipped += 1
                break
    turns = [_hh_turns(r["chosen"]) for r in rows[:2000]]
    return {"entries": len(rows), "fields": ["chosen", "rejected"],
            "has_response": True, "multi_turn": "Human/Assistant 交替(2-6 轮)",
            "turn_dist_p50": sorted(turns)[len(turns) // 2] if turns else 0,
            "redline_skipped": skipped, "prompt_only": False}


def src_safety_prompts(d: Path) -> dict:
    out, skipped = {"entries": 0, "has_response": True}, 0
    cats = {}
    for fname in ["typical_safety_scenarios.json", "instruction_attack_scenarios.json"]:
        j = json.loads((d / fname).read_text(encoding="utf-8"))
        for cat, items in j.items():
            cats[f"{fname[:4]}:{cat}"] = len(items)
            out["entries"] += len(items)
            for it in items:
                if response_violates(it.get("response", "")):
                    skipped += 1
    out.update({"fields": ["prompt", "response", "type"],
                "multi_turn": "单轮(zh)", "redline_skipped": skipped,
                "categories": cats, "prompt_only": False})
    return out


def src_safemtdata(d: Path) -> dict:
    out, skipped = {"entries": 0, "has_response": True}, 0
    aq, km = [], []
    # Attack_600:multi_turn_queries(渐进攻击查询,无响应)
    j = json.loads((d / "Attack_600.json").read_text(encoding="utf-8"))
    out["entries"] += len(j)
    for it in j:
        qs = it.get("multi_turn_queries") or []
        aq.append(len(qs))
        for q in qs:
            if response_violates(q):
                skipped += 1
                break
    # SafeMTData_1K:conversations(含助手响应)
    j = json.loads((d / "SafeMTData_1K.json").read_text(encoding="utf-8"))
    out["entries"] += len(j)
    for it in j:
        convs = it.get("conversations") or []
        km.append(len(convs))
        for c in convs:
            role = c.get("from", "")
            if role in ("gpt", "assistant"):
                if response_violates(c.get("value", "")):
                    skipped += 1
                    break
    aq.sort(), km.sort()
    out.update({
        "fields": {"Attack_600.json": ["id", "query_id", "category", "actor_name",
                                       "relationship", "plain_query",
                                       "multi_turn_queries"],
                   "SafeMTData_1K.json": ["id", "query_id", "actor_name",
                                          "relationship", "plain_query",
                                          "conversations[from,value]"]},
        "multi_turn": "多轮(角色关系铺垫→渐进诱导)",
        "attack600_multi_turn_queries_p50": aq[len(aq) // 2] if aq else 0,
        "1k_messages_p50": km[len(km) // 2] if km else 0,
        "redline_skipped": skipped, "prompt_only": False})
    return out


def _csv_rows(p: Path):
    with open(p, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def src_advbench(d: Path) -> dict:
    rows = _csv_rows(d / "harmful_behaviors.csv")
    strs = _csv_rows(d / "harmful_strings.csv")
    return {"entries": len(rows) + len(strs),
            "fields": ["goal", "target"] + (["target"] if strs else []),
            "has_response": False, "multi_turn": "单轮 prompt(en)",
            "redline_skipped": 0, "prompt_only": True}


def src_harmbench(d: Path) -> dict:
    rows = _csv_rows(d / "harmbench_behaviors_text_test.csv")
    return {"entries": len(rows),
            "fields": ["Behavior", "FunctionalCategory", "SemanticCategory",
                       "Tags", "ContextString", "BehaviorID"],
            "has_response": False, "multi_turn": "单轮 behavior(en,含上下文变体)",
            "redline_skipped": 0, "prompt_only": True}


def src_strongreject(d: Path) -> dict:
    rows = _csv_rows(d / "strongreject_dataset.csv")
    return {"entries": len(rows), "fields": ["category", "source", "forbidden_prompt"],
            "has_response": False, "multi_turn": "单轮 prompt(en)",
            "redline_skipped": 0, "prompt_only": True}


def src_maliciousinstruct(d: Path) -> dict:
    import pyarrow.parquet as pq
    t = pq.read_table(d / "train-00000-of-00001.parquet")
    return {"entries": t.num_rows, "fields": list(t.column_names),
            "has_response": False, "multi_turn": "单轮 prompt(en)",
            "redline_skipped": 0, "prompt_only": True}


def src_xstest(d: Path) -> dict:
    rows = _csv_rows(d / "xstest_prompts.csv")
    return {"entries": len(rows),
            "fields": ["id", "prompt", "type", "label", "focus", "note"],
            "has_response": False, "multi_turn": "单轮 prompt(en,误拒向)",
            "redline_skipped": 0, "prompt_only": True}


def src_or_bench(d: Path) -> dict:
    out = {"entries": 0, "has_response": False, "prompt_only": True}
    files = {}
    for f in sorted(d.glob("*.csv")):
        n = len(_csv_rows(f))
        files[f.name] = n
        out["entries"] += n
    out.update({"fields": ["prompt", "category"], "multi_turn": "单轮 prompt(en,误拒向)",
                "redline_skipped": 0, "files": files})
    return out


def src_trustllm(d: Path) -> dict:
    out, skipped = {"entries": 0}, 0
    sub = {}
    for p in sorted((d / "dataset").rglob("*.json")):
        rel = p.relative_to(d / "dataset").as_posix()
        if not any(k in rel for k in ("safety", "privacy")):
            continue
        j = json.loads(p.read_text(encoding="utf-8"))
        sub[rel] = len(j)
        out["entries"] += len(j)
        for it in j:
            for v in it.values():
                if isinstance(v, str) and response_violates(v):
                    skipped += 1
                    break
    out.update({"fields": "随子集(prompt/label/source;gt-email/gt-name/prompt 等)",
                "has_response": False, "multi_turn": "单轮(en,safety+privacy 子集)",
                "redline_skipped": skipped, "subsets": sub, "prompt_only": True})
    return out


def src_cvalues(d: Path) -> dict:
    out, skipped = {"entries": 0, "has_response": True}, 0
    files = {}
    for f in sorted(d.glob("*.json")):
        j = json.loads(f.read_text(encoding="utf-8"))
        files[f.name] = len(j)
        out["entries"] += len(j)
        for r in j[:5000]:
            for k in ("chosen", "better_response", "response_1", "response_2",
                      "answer_1", "answer_2"):
                if isinstance(r.get(k), str) and response_violates(r[k]):
                    skipped += 1
                    break
    out.update({"fields": "prompt + 双响应对比 + 人标(变体随镜像)",
                "multi_turn": "单轮(zh 对比)", "redline_skipped": skipped,
                "files": files, "prompt_only": False})
    return out


def src_tc260(d: Path) -> dict:
    import pyarrow.parquet as pq
    out = {"entries": 0, "tier": "reference"}
    files = {}
    for f in sorted((d / "public").glob("*.parquet")):
        t = pq.read_table(f)
        files[f.name] = t.num_rows
        out["entries"] += t.num_rows
    out.update({"fields": ["id", "query", "category_*", "attack_level",
                           "attack_techniques", "expression_style", "...19 列"],
                "has_response": False, "multi_turn": "单轮 query(zh,攻击元数据)",
                "files": files, "prompt_only": True})
    return out


# ------------------------------------------------------ 第二批(2026-09-25 用户拍板:第二批全纳入) --
def _iter_jsonl(p: Path):
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _iter_jsonl_xz(p: Path):
    import lzma
    with lzma.open(p, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def src_pku_saferlhf(d: Path) -> dict:
    out, skipped = {"entries": 0, "has_response": True}, 0
    files = {}
    for p in sorted((d / "data").rglob("*.jsonl")):
        n = 0
        for r in _iter_jsonl(p):
            n += 1
            for k in ("response_0", "response_1"):
                if isinstance(r.get(k), str) and response_violates(r[k]):
                    skipped += 1
                    break
        files[p.relative_to(d).as_posix()] = n
        out["entries"] += n
    out.update({
        "fields": ["prompt", "response_0", "response_1", "prompt_source",
                   "is_response_0_safe", "is_response_1_safe",
                   "response_*_harm_category", "response_*_severity_level",
                   "better_response_id", "safer_response_id"],
        "multi_turn": "单轮(en,双响应+安全/偏好标注)",
        "redline_skipped": skipped, "files": files, "prompt_only": False})
    return out


def src_beavertails(d: Path) -> dict:
    out, skipped = {"entries": 0, "has_response": True}, 0
    files = {}
    unsafe_resp = 0
    for p in sorted(d.rglob("*.jsonl.gz")) + sorted(d.rglob("*.jsonl.xz")):
        it = _iter_jsonl_xz(p) if p.suffix == ".xz" else _iter_jsonl_gz(p)
        n = 0
        for r in it:
            n += 1
            if r.get("is_safe") is False:
                unsafe_resp += 1
            if isinstance(r.get("response"), str) and response_violates(r["response"]):
                skipped += 1
        files[p.relative_to(d).as_posix()] = n
        out["entries"] += n
    out.update({
        "fields": ["prompt", "response", "is_safe", "harm_category",
                   "flagged_scan", "metadata"],
        "multi_turn": "单轮(en,每 prompt ×3 响应行)",
        "redline_skipped": skipped, "unsafe_responses": unsafe_resp,
        "files": files, "prompt_only": False,
        "note": "不安全响应侧留原始作 rejected 侧信号(父指令),不生成模板;"
                "生成器侧跳过武器化 how-to(redline_skipped 计数)"})
    return out


def src_wildjailbreak(d: Path) -> dict:
    out, skipped = {"entries": 0, "has_response": True}, 0
    types = {}
    for p in sorted(d.rglob("*.tsv")):
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            rd = csv.reader(f, delimiter="\t")
            header = next(rd, None)
            if not header:
                continue
            ti = header.index("data_type") if "data_type" in header else None
            ci = header.index("completion") if "completion" in header else None
            for row in rd:
                if len(row) != len(header):
                    continue
                out["entries"] += 1
                if ti is not None and ti < len(row):
                    types[row[ti]] = types.get(row[ti], 0) + 1
                if ci is not None and ci < len(row) and response_violates(row[ci]):
                    skipped += 1
    out.update({
        "fields": ["vanilla", "adversarial", "completion", "data_type"],
        "multi_turn": "单轮(en;vanilla→adversarial 改写对+安全完成)",
        "redline_skipped": skipped, "data_type_dist": types,
        "prompt_only": False,
        "note": "ODC-By;门控数据集经 hf-mirror+token 实拉(token 已弃用不落盘)"})
    return out


def src_wildguardmix(d: Path) -> dict:
    import pyarrow.parquet as pq
    out, skipped = {"entries": 0, "has_response": True}, 0
    labels = {}
    for p in sorted(d.rglob("*.parquet")):
        t = pq.read_table(p)
        out["entries"] += t.num_rows
        for resp, ph in zip(t.column("response").to_pylist(),
                            t.column("prompt_harm_label").to_pylist()):
            labels[ph] = labels.get(ph, 0) + 1
            if isinstance(resp, str) and response_violates(resp):
                skipped += 1
    out.update({
        "fields": ["prompt", "adversarial", "response", "prompt_harm_label",
                   "response_refusal_label", "response_harm_label",
                   "subcategory"],
        "multi_turn": "单轮(en;有害性/拒绝/响应安全三标注+子类)",
        "redline_skipped": skipped, "prompt_harm_label_dist": labels,
        "prompt_only": False,
        "note": "ODC-By(card);门控数据集经 hf-mirror+token 实拉(token 已弃用不落盘)"})
    return out


BATCH2_SOURCES = [
    ("pku-saferlhf",
     [("http", f"https://hf-mirror.com/datasets/PKU-Alignment/PKU-SafeRLHF/resolve/main/data/{m}/{s}.jsonl",
       f"pku-saferlhf/data/{m}/{s}.jsonl")
      for m in ["Alpaca-7B", "Alpaca2-7B", "Alpaca3-8B"]
      for s in ["train", "test"]],
     RAW / "pku-saferlhf",
     {"url": "https://huggingface.co/datasets/PKU-Alignment/PKU-SafeRLHF (via hf-mirror)",
      "license": "CC-BY-NC-4.0 (PKU-Alignment/PKU-SafeRLHF dataset card)",
      "domain": "sft", "lang": "en",
      "note": "D3 ledger: CC-BY-NC-4.0 - non-commercial restriction conflicts "
              "with commercial-weight release; RE-EVALUATE BEFORE OPEN "
              "WEIGHTS. Decision provenance: 2026-09-25 user-approved batch-2 "
              "inclusion. Full collection: prompt + dual responses with "
              "safety labels (is_safe, harm_category, severity_level) + "
              "preference labels (better/safer_response_id), responses "
              "collected from Alpaca-7B / Alpaca2-7B / Alpaca3-8B."},
     src_pku_saferlhf),
    ("beavertails",
     [("http", "https://hf-mirror.com/datasets/PKU-Alignment/BeaverTails/resolve/main/round0/30k/train.jsonl.gz", "beavertails/round0/30k/train.jsonl.gz"),
      ("http", "https://hf-mirror.com/datasets/PKU-Alignment/BeaverTails/resolve/main/round0/30k/test.jsonl.gz", "beavertails/round0/30k/test.jsonl.gz"),
      ("http", "https://hf-mirror.com/datasets/PKU-Alignment/BeaverTails/resolve/main/round0/330k/train.jsonl.xz", "beavertails/round0/330k/train.jsonl.xz"),
      ("http", "https://hf-mirror.com/datasets/PKU-Alignment/BeaverTails/resolve/main/round0/330k/test.jsonl.xz", "beavertails/round0/330k/test.jsonl.xz")],
     RAW / "beavertails",
     {"url": "https://huggingface.co/datasets/PKU-Alignment/BeaverTails (via hf-mirror)",
      "license": "CC-BY-NC-4.0 (PKU-Alignment/BeaverTails dataset card)",
      "domain": "sft", "lang": "en",
      "note": "D3 ledger: CC-BY-NC-4.0 - non-commercial restriction conflicts "
              "with commercial-weight release; RE-EVALUATE BEFORE OPEN "
              "WEIGHTS. Decision provenance: 2026-09-25 user-approved batch-2 "
              "inclusion. 30K human-annotated QA + 330K full collection "
              "(each prompt x 3 responses with is_safe + harm_category). "
              "Unsafe response side kept raw as rejected-side signal only; "
              "no response templates generated from it (parent directive)."},
     src_beavertails),
]


# ------------------------------------------------------------------ 采购表 --
SOURCES = [
    # (sid, 供应商: http/clone/copy, 定位, spec, 采集器)
    ("hh-rlhf-harmlessness",
     [("http", "https://hf-mirror.com/datasets/Anthropic/hh-rlhf/resolve/main/harmless-base/train.jsonl.gz", "hh-rlhf/harmless-base/train.jsonl.gz"),
      ("http", "https://hf-mirror.com/datasets/Anthropic/hh-rlhf/resolve/main/harmless-base/test.jsonl.gz", "hh-rlhf/harmless-base/test.jsonl.gz")],
     RAW / "hh-rlhf",
     {"url": "https://huggingface.co/datasets/Anthropic/hh-rlhf (via hf-mirror)",
      "license": "MIT (Anthropic hh-rlhf dataset card)",
      "domain": "sft", "lang": "en",
      "note": "harmless-base 42,537 train + 2,312 test preference pairs "
              "(chosen/rejected multi-turn dialogues). Raw material; format "
              "conversion and token counting deferred to the SFT pair "
              "generator. Response-side weaponized check passed (see "
              "m2-sft-procurement.json)."},
     src_hh_rlhf),
    ("safety-prompts",
     [("copy", RESEARCH / "Safety-Prompts" / "typical_safety_scenarios.json", "safety-prompts/typical_safety_scenarios.json"),
      ("copy", RESEARCH / "Safety-Prompts" / "instruction_attack_scenarios.json", "safety-prompts/instruction_attack_scenarios.json")],
     RAW / "safety-prompts",
     {"url": "https://github.com/thu-coai/Safety-Prompts",
      "license": "Apache-2.0 (thu-coai/Safety-Prompts repository LICENSE)",
      "domain": "sft", "lang": "zh",
      "note": "100K Chinese safety prompts with responses: 7 typical-safety "
              "categories x 10K + 6 instruction-attack categories x 5K "
              "(30K total). Converted from research clone (m2-research) to "
              "formal procurement. Attack-subset responses are template-era; "
              "generator side should prefer prompt+own-response."},
     src_safety_prompts),
    ("safemtdata",
     [("http", "https://hf-mirror.com/datasets/SafeMTData/SafeMTData/resolve/main/SafeMTData/Attack_600.json", "safemtdata/Attack_600.json"),
      ("http", "https://hf-mirror.com/datasets/SafeMTData/SafeMTData/resolve/main/SafeMTData/SafeMTData_1K.json", "safemtdata/SafeMTData_1K.json")],
     RAW / "safemtdata",
     {"url": "https://huggingface.co/datasets/SafeMTData/SafeMTData (via hf-mirror)",
      "license": "MIT (SafeMTData dataset card)",
      "domain": "sft", "lang": "en",
      "note": "ActorAttack-style multi-turn red-team: 600 attack dialogues "
              "(category/actor_name/relationship/plain_query/conversations) + "
              "1,680 multi-turn safety dialogues. Key material for "
              "separated-invariant multi-turn training."},
     src_safemtdata),
    ("advbench",
     [("copy", RESEARCH / "llm-attacks" / "data" / "advbench" / "harmful_behaviors.csv", "advbench/harmful_behaviors.csv"),
      ("copy", RESEARCH / "llm-attacks" / "data" / "advbench" / "harmful_strings.csv", "advbench/harmful_strings.csv")],
     RAW / "advbench",
     {"url": "https://github.com/llm-attacks/llm-attacks (data/advbench)",
      "license": "MIT (llm-attacks repository LICENSE)",
      "domain": "sft", "lang": "en",
      "note": "520 harmful behaviors (goal,target) + 575 harmful strings. "
              "Prompt side only; target prefixes not for training."},
     src_advbench),
    ("harmbench",
     [],  # clone 整仓后取 csv
     RAW / "harmbench",
     {"url": "https://github.com/centerforaisafety/HarmBench",
      "license": "MIT (HarmBench repository LICENSE)",
      "domain": "sft", "lang": "en",
      "note": "1,010 text test behaviors with semantic categories + context "
              "variants (Behavior,FunctionalCategory,SemanticCategory,Tags,"
              "ContextString,BehaviorID)."},
     src_harmbench),
    ("strongreject",
     [("copy", RESEARCH / "strongreject" / "strongreject_dataset" / "strongreject_dataset.csv", "strongreject/strongreject_dataset.csv"),
      ("copy", RESEARCH / "strongreject" / "strongreject_dataset" / "strongreject_small_dataset.csv", "strongreject/strongreject_small_dataset.csv")],
     RAW / "strongreject",
     {"url": "https://github.com/alexandrasouly/strongreject",
      "license": "MIT (strongreject repository LICENSE)",
      "domain": "sft", "lang": "en",
      "note": "313 forbidden prompts (category,source,forbidden_prompt) + "
              "small variant; StrongREJECT rubric for eval reuse."},
     src_strongreject),
    ("maliciousinstruct",
     [("http", "https://hf-mirror.com/datasets/walledai/MaliciousInstruct/resolve/main/data/train-00000-of-00001.parquet", "maliciousinstruct/train-00000-of-00001.parquet")],
     RAW / "maliciousinstruct",
     {"url": "https://huggingface.co/datasets/walledai/MaliciousInstruct (via hf-mirror)",
      "license": "CC-BY-SA-4.0 (walledai/MaliciousInstruct dataset card)",
      "domain": "sft", "lang": "en",
      "note": "100 malicious instruction prompts; source paper arXiv "
              "2310.06987 (Catastrophic Jailbreak of Open-source LLMs)."},
     src_maliciousinstruct),
    ("xstest",
     [("copy", RESEARCH / "xstest" / "xstest_prompts.csv", "xstest/xstest_prompts.csv")],
     RAW / "xstest",
     {"url": "https://github.com/paul-rottger/xstest",
      "license": "CC-BY-4.0 (xstest repository LICENSE: Attribution 4.0 International)",
      "domain": "sft", "lang": "en",
      "note": "250 safe-adjacent prompts for exaggerated-safety (false "
              "refusal) measurement: id,prompt,type,label,focus,note."},
     src_xstest),
    ("or-bench",
     [("http", "https://hf-mirror.com/datasets/bench-llms/or-bench/resolve/main/or-bench-80k.csv", "or-bench/or-bench-80k.csv"),
      ("http", "https://hf-mirror.com/datasets/bench-llms/or-bench/resolve/main/or-bench-hard-1k.csv", "or-bench/or-bench-hard-1k.csv"),
      ("http", "https://hf-mirror.com/datasets/bench-llms/or-bench/resolve/main/or-bench-toxic.csv", "or-bench/or-bench-toxic.csv")],
     RAW / "or-bench",
     {"url": "https://huggingface.co/datasets/bench-llms/or-bench (via hf-mirror)",
      "license": "CC-BY-4.0 (bench-llms/or-bench dataset card)",
      "domain": "sft", "lang": "en",
      "note": "Over-refusal benchmark: 80K rejected-prompt pool + hard-1k + "
              "toxic-999 (prompt,category)."},
     src_or_bench),
    ("trustllm-safety",
     [],  # copy 整个 dataset/ 目录(safety+privacy 子集)
     RAW / "trustllm",
     {"url": "https://github.com/HowieHwong/TrustLLM",
      "license": "MIT (TrustLLM repository LICENSE)",
      "domain": "sft", "lang": "en",
      "note": "Safety + privacy subsets: jailbreak 1,400, exaggerated_safety "
              "200, privacy_leakage 400 (context-embedded PII extraction, "
              "synthetic gt-email/gt-name), privacy_awareness_query 560."},
     src_trustllm),
    ("cvalues",
     [("http", "https://hf-mirror.com/datasets/Skepsun/cvalues_rlhf/resolve/main/harmless_train.json", "cvalues/harmless_train.json"),
      ("http", "https://hf-mirror.com/datasets/Skepsun/cvalues_rlhf/resolve/main/harmless_test.json", "cvalues/harmless_test.json"),
      ("http", "https://hf-mirror.com/datasets/Skepsun/cvalues_rlhf/resolve/main/helpful_train.json", "cvalues/helpful_train.json"),
      ("http", "https://hf-mirror.com/datasets/Skepsun/cvalues_rlhf/resolve/main/helpful_test.json", "cvalues/helpful_test.json")],
     RAW / "cvalues",
     {"url": "https://github.com/X-PLUG/CValues (data via hf-mirror.com/datasets/Skepsun/cvalues_rlhf)",
      "license": "Apache-2.0 (X-PLUG/CValues repository LICENSE; mirror tagged Apache-2.0)",
      "domain": "sft", "lang": "zh",
      "note": "CValues-Comparison ~145K Chinese value-alignment comparison "
              "pairs (harmless + helpful splits; prompt + dual responses + "
              "human preference labels)."},
     src_cvalues),
]

# 参照物料(永不入训练)
REF_SOURCES = [
    ("tc260",
     [("http", "https://hf-mirror.com/datasets/MuYi23/TC260-Chinese-Safety-Prompts/resolve/main/data/public/train.parquet", "tc260/public/train.parquet"),
      ("http", "https://hf-mirror.com/datasets/MuYi23/TC260-Chinese-Safety-Prompts/resolve/main/data/public/validation.parquet", "tc260/public/validation.parquet"),
      ("http", "https://hf-mirror.com/datasets/MuYi23/TC260-Chinese-Safety-Prompts/resolve/main/data/public/test.parquet", "tc260/public/test.parquet"),
      ("http", "https://hf-mirror.com/datasets/MuYi23/TC260-Chinese-Safety-Prompts/resolve/main/schema.json", "tc260/schema.json")],
     REF / "tc260",
     {"url": "https://huggingface.co/datasets/MuYi23/TC260-Chinese-Safety-Prompts (via hf-mirror)",
      "license": "Apache-2.0 (mirror) - official source TC260-003 test set, see note",
      "domain": "sft", "lang": "zh", "tier": "reference",
      "note": "EVAL-REFERENCE ONLY, NEVER INTO TRAINING (parent decision "
              "2026-09-25): TC260-003 is the official national cybersecurity "
              "standards committee test set - training on it would "
              "contaminate the industry benchmark. Procured solely as "
              "taxonomy reference (19-column attack metadata schema guides "
              "our own generator templates - influence without copying). "
              "Only data/public/ split mirrored; data/restricted/ NOT "
              "fetched. Physically separated under raw/m2-reference/."},
     src_tc260),
]

# 第三批(AI2 门控两件,2026-09-25 用户拍板纳入;token 经 hf-mirror 内联传递,
# 不落盘——物料已用 curl 直拉落地,本表 URL 仅作来源记录,curl_fetch 走存在性短路)
BATCH3_SOURCES = [
    ("wildjailbreak",
     [("http", "https://hf-mirror.com/datasets/allenai/wildjailbreak/resolve/main/train/train.tsv", "wildjailbreak/train/train.tsv"),
      ("http", "https://hf-mirror.com/datasets/allenai/wildjailbreak/resolve/main/eval/eval.tsv", "wildjailbreak/eval/eval.tsv")],
     RAW / "wildjailbreak",
     {"url": "https://huggingface.co/datasets/allenai/wildjailbreak (via hf-mirror, token auth)",
      "license": "ODC-By (allenai/wildjailbreak dataset card, Open Data Commons Attribution 1.0)",
      "domain": "sft", "lang": "en",
      "note": "D3 ledger: ODC-By requires attribution of the database; "
              "dataset itself open for adaptation. Gated (auto) - fetched "
              "via hf-mirror with user-provided read token (token used "
              "inline only, never persisted, discardable). Decision "
              "provenance: 2026-09-25 user-approved batch-2/3 inclusion. "
              "426K adversarial dialogues: vanilla/harmful prompt, "
              "adversarial (decomposed) rewrite, safe completion, "
              "data_type label."},
     src_wildjailbreak),
    ("wildguardmix",
     [("http", "https://hf-mirror.com/datasets/allenai/wildguardmix/resolve/main/train/wildguard_train.parquet", "wildguardmix/train/wildguard_train.parquet"),
      ("http", "https://hf-mirror.com/datasets/allenai/wildguardmix/resolve/main/test/wildguard_test.parquet", "wildguardmix/test/wildguard_test.parquet")],
     RAW / "wildguardmix",
     {"url": "https://huggingface.co/datasets/allenai/wildguardmix (via hf-mirror, token auth)",
      "license": "ODC-By (allenai/wildguardmix dataset card 'license: odc-by'; WildGuard project originally cited under AI2 OUFRA usage norms)",
      "domain": "sft", "lang": "en",
      "note": "D3 ledger: ODC-By requires attribution of the database. "
              "Gated (auto) - fetched via hf-mirror with user-provided read "
              "token (token used inline only, never persisted, "
              "discardable). Decision provenance: 2026-09-25 user-approved "
              "batch-2/3 inclusion. WildGuardTrain 92K mix (86,759 train + "
              "1,725 test): prompt/response with harm-refusal-harm triple "
              "labels + subcategory. allenai/wildguardtrain skipped as "
              "duplicate of this repo; allenai/WildTeaming deferred "
              "(external form required)."},
     src_wildguardmix),
]


def procure(sid, items, dest, spec, summarizer, skip_fetch, results):
    ok = True
    if not skip_fetch:
        if sid == "harmbench":
            repo = ROOT / "data" / "corpora" / "raw" / "m2" / "_repo_harmbench"
            ok = git_clone("centerforaisafety", "HarmBench", repo)
            if ok:
                src = repo / "data" / "behavior_datasets"
                dest.mkdir(parents=True, exist_ok=True)
                for f in ["harmbench_behaviors_text_test.csv",
                          "harmbench_behaviors_text_test_bonus.csv",
                          "harmbench_behaviors_text_val.csv"]:
                    if (src / f).exists():
                        shutil.copy2(src / f, dest / f)
        elif sid == "trustllm-safety":
            srcd = RESEARCH / "TrustLLM" / "dataset" / "_x" / "dataset"
            ok = srcd.exists()
            if ok:
                dest.mkdir(parents=True, exist_ok=True)
                for sub in ["safety", "privacy"]:
                    if (srcd / sub).exists():
                        shutil.copytree(srcd / sub, dest / "dataset" / sub,
                                        dirs_exist_ok=True)
        else:
            base = REF if dest.is_relative_to(REF) else RAW
            for kind, src, rel in items:
                target = base / rel
                if kind == "http":
                    ok = curl_fetch(src, target) and ok
                elif kind == "copy":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if Path(src).exists():
                        shutil.copy2(src, target)
                    else:
                        ok = False
                time.sleep(0.5)
    if not ok:
        results[sid] = {"status": "FETCH-FAIL"}
        print(f"  {sid}: FETCH-FAIL", flush=True)
        return
    inv = summarizer(dest)
    inv["status"] = "ok"
    inv["raw_path"] = str(dest.relative_to(ROOT))
    results[sid] = inv
    print(f"  {sid}: {inv.get('entries')} entries, redline_skipped="
          f"{inv.get('redline_skipped')}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="M2 SFT procurement (batches)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-manifest", action="store_true")
    ap.add_argument("--batch", default="1", choices=["1", "2", "3", "123"],
                    help="1=第一批(11 源+tc260 参照) 2=第二批(NC 两件) "
                         "3=第三批(AI2 门控两件) 123=全部")
    args = ap.parse_args(argv)

    groups = []
    if "1" in args.batch and args.batch in ("1", "123"):
        groups.append(("采购训练物料", SOURCES))
        groups.append(("采购参照物料(永不入训练)", REF_SOURCES))
    if args.batch in ("2", "123"):
        groups.append(("采购第二批训练物料(NC,2026-09-25 用户拍板)", BATCH2_SOURCES))
    if args.batch in ("3", "123"):
        groups.append(("采购第三批训练物料(AI2 门控,2026-09-25 用户拍板)", BATCH3_SOURCES))

    results = {}
    for title, table in groups:
        print(f"== {title} ==", flush=True)
        for sid, items, dest, spec, fn in table:
            procure(sid, items, dest, spec, fn, args.skip_fetch, results)

    # manifest
    if not args.skip_manifest:
        for title, table in groups:
            for sid, items, dest, spec, fn in table:
                if results.get(sid, {}).get("status") != "ok":
                    continue
                n = results[sid]["entries"]
                spec2 = dict(spec)
                spec2["files"] = [results[sid]["raw_path"]]
                upsert_manifest(sid, spec2, "procured", n, 0)
        print("manifest upserted", flush=True)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    merged = {}
    if REPORT.exists():
        try:
            merged = json.loads(REPORT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            merged = {}
    merged.update(results)
    REPORT.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"report -> {REPORT.relative_to(ROOT)} ({len(merged)} sources)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
