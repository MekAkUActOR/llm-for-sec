# -*- coding: utf-8 -*-
"""S1 载体本体论的**机器可校验**实现（只读、纯 CPU）。

## 这个脚本解决什么问题

使命层说"感知信息载体中的安全属性"，但工程侧的判据、门禁、结论**必须能按载体索引**：
哪类载体训了多少行、哪类载体有门禁、哪类载体的结论**根本没有门禁支撑**。
本脚本把这三件事从"文档宣称"变成"现算 + 断言"：

1. **字段完整性 / id 唯一**：`data/ontology/carriers.json` 里每个条目必须齐备必需字段；
2. **标签闭合性（最重要）**：仓库里实际出现的**所有** `<carrier type="...">` 标签
   必须都在本体里 → 集合 ⊆ 本体 id 集合；出现本体外标签则**非零退出**并打印
   文件名 + 行号样本（这是"数据里冒出一个新载体而没人知道"的唯一机械防线）；
3. **数字一致**：本体里每条 `train_rows` / `gate_items` 必须与本脚本**现算**的数字
   逐格相等（数字由脚本现算，`carriers.json` 只存副本，漂移即报错）；
4. **覆盖矩阵一致**：载体 × 4 列（训练数据 / 未见载体门禁 / 在训载体回归 /
   在分布能力观测）的每一格必须与现算一致，且与条目内字段互相自洽。

末行固定输出 `CARRIER-ONTOLOGY-CHECK=PASS errors=0` 或 `...=FAIL errors=N`（N>0 时退出码 1）。

## 口径（唯一事实来源都在这个文件里，改口径必须改这里并留痕）

* **载体标记口径**：`<carrier type="X" ...>` 与 `<carrier=X ...>`；同一行的重复标记
  只按**行**计一次（`carrier_rows`）。数据文件里引号是 JSON 转义形态（`\\"`），
  正则同时容忍 0–2 层反斜杠。
* **训练侧范围**：`data/lf/*.jsonl` + `data/sft/**/*.jsonl` + `data/dpo/**/*.jsonl`。
  `data/lf/*.jsonl` 是任务规定的强制范围；另两个子树是**额外**范围（暂存族 + DPO），
  用于让"已注册·待入训"的差别可见。范围键见 `TRAIN_SCOPES`。
* **门禁范围**：`data/heldout/**/*.jsonl`，按 4 个仪器分列。见 `GATE_SCOPES`。
* **行为门禁只统计 `kind=="robustness"` 条目**（`docs/01 §11.2`），因此 v0.3-gen
  每格同时给 `n`（全部条目）与 `robustness_n`（行为门禁可用的分母）。

## 用法

    .venv\\Scripts\\python.exe scripts\\check_carrier_ontology.py
    .venv\\Scripts\\python.exe scripts\\check_carrier_ontology.py --census
    .venv\\Scripts\\python.exe scripts\\check_carrier_ontology.py --emit-counts reports\\carrier-ontology-counts.json
    .venv\\Scripts\\python.exe scripts\\check_carrier_ontology.py --ontology <other.json>

退出码：0 = PASS；1 = FAIL（有错误）；
2 = 本体/输入缺失（fail-closed：缺件不得静默通过，`docs/01 §11.3`）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ONTOLOGY = ROOT / "data" / "ontology" / "carriers.json"

# --------------------------------------------------------------- 扫描口径 ---
# 数据文件里 `<carrier type="email">` 以 JSON 转义形态出现（`carrier type=\"email\"`），
# 双重编码时为 `\\\"`。`\\*` 同时容忍这两种以及未转义形态。
CARRIER_TAG_RE = re.compile(rb'carrier\s+type=\\*"([A-Za-z_][A-Za-z0-9_]*)\\*"')
# 备用形态 `<carrier=text ...>`（实测 0 次，但口径要写死，否则将来冒出来会漏检）。
# 注意：转义形态 `⟨carrier ...⟩`（见 secfm/carriers/base.py::escape_region_markers）
# **不计**——它是被刻意中和的内容，不是标签。
CARRIER_ALT_RE = re.compile(rb'<\s*carrier\s*=\s*\\*"([A-Za-z_][A-Za-z0-9_]*)\\*"')
PROTOCOL_RE = re.compile(rb"dsh-protocol\s+v=\\*\"([0-9][0-9.]*)\\*\"")

#: 单标签最多记录多少条 (文件, 行号) 样本（报错时打印用）
MAX_SAMPLES_PER_LABEL = 20

#: 训练侧范围（键 = 本体里的 scope 名；值 = 相对 ROOT 的 glob）
TRAIN_SCOPES = OrderedDict([
    ("sft_m25", "data/lf/sft_m25.jsonl"),
    ("sft_m1", "data/lf/sft_m1.jsonl"),
    ("m2_5_staging", "data/sft/m2.5-staging/*.jsonl"),
    ("sec_sft_topup", "data/lf/sec_sft_topup.jsonl"),
    ("sec_sft_needlefix", "data/lf/sec_sft_needlefix.jsonl"),
    ("sec_sft_needlefix_carrier", "data/lf/sec_sft_needlefix_carrier.jsonl"),
    ("carrier_sft_slice", "data/lf/carrier_sft_slice.jsonl"),
    ("dpo_m3_final", "data/lf/dpo_m3_final.jsonl"),
    ("dpo_remediation_staging", "data/dpo-remediation-staging/*.jsonl"),
    ("lf_total", "data/lf/*.jsonl"),
    # ★活谱系（2026-09-30 晚新增，docs/01 §11.24 规则 24）：只含**被活产物消费**的文件。
    #   排除：未使用的候选（sec_sft_needlefix_carrier / carrier_sft_slice）、
    #   已废弃分支（sec_sft_topup，C 路 e1/e2 权重登记 discarded）、
    #   以及从未被 config 引用的文件。**"已训/未见"判定必须用本范围，不得用 lf_total。**
    ("live_lineage", ["data/lf/sft_m25.jsonl",
                      "data/lf/sec_sft_needlefix.jsonl",
                      "data/lf/dpo_m3_final.jsonl"]),
])
TRAIN_SCOPE_NOTE = {
    "sft_m25": "M2.5 SFT 混料（docs/01 §10.2 登记口径的本体）",
    "sft_m1": "M1 中期训练混料（SFT 形态）",
    "m2_5_staging": "暂存族（**已生成未混料**；注册 ≠ 已训）",
    "sec_sft_topup": "C 路定向补齐混料（configs/m3base-topup-*.yaml 在训）",
    "sec_sft_needlefix": "needle 修复混料（configs/m2calib-needlefix*.yaml 在训）",
    "sec_sft_needlefix_carrier": "needle 修复 + 载体增广候选混料（**训练绑定未验证**）",
    "carrier_sft_slice": "载体正向回放切片（R5 候选，**训练绑定未验证**）",
    "dpo_m3_final": "M3 DPO 载体批合并后的主混料",
    "dpo_remediation_staging": "DPO 长度混杂**修复候选**（`scripts/length_match_dpo.py` 产出；**尚未被任何训练消费**；注册 ≠ 已训）",
    "lf_total": "data/lf/*.jsonl 全部（含预训练 c0/c1/c2 与 SFT/DPO）——"
                "**仅作面量参考，不得用于「已训/未见」判定**（含未使用文件与已废弃分支）",
    "live_lineage": "**活谱系**：被活产物消费的训练文件并集（sft_m25 + sec_sft_needlefix "
                    "+ dpo_m3_final）。覆盖矩阵 train 列以此为准（docs/01 §11.24 规则 24）",
}

#: 门禁侧范围（键 = 仪器名；值 = glob）
GATE_SCOPES = OrderedDict([
    ("v0.2.1", "data/heldout/v0.2.1/*.jsonl"),
    ("v0.3-gen", "data/heldout/v0.3-gen/*.jsonl"),
    ("v0.4-toolout", "data/heldout/v0.4-toolout/*.jsonl"),
    ("v0.5-topup-families", "data/heldout/v0.5-topup-families/*.jsonl"),
    # ★2026-10-06 新增（用户裁决选项 B）：document 载体门禁。
    #   构建/检查/测试三项全绿：BUILD-DOCUMENT-GATE=PASS items=80、
    #   DOCUMENT-GATE-CHECK=PASS errors=0、TEST-DOCUMENT-GATE=PASS checks=all。
    ("v0.6-document", "data/heldout/v0.6-document/*.jsonl"),
])

#: 仪器的角色（决定覆盖矩阵的列）。
#:
#: 值的类型有两种（★2026-10-06 起支持，用户裁决选项 B）：
#:   str  —— 与模型无关的角色；
#:   dict —— **按模型分角色** `{模型 tag: 角色}`，用于同一仪器对不同模型
#:           充当不同角色的情形。此时矩阵列名取中性名，具体角色记录在
#:           `instruments[name]["role_by_model"]`。
#:
#: ★为什么必须支持按模型分角色（docs/01 §11.24 规则 24）：
#:   `v0.6-document` 对 `soup-a050` 是**未见载体门**（其训练语料无 document 载体），
#:   对 `m3-dpo` 则是**未见机制门**（M3 数据含 document 结构、但机制是新的）。
#:   若强行登记成单一角色，就会把一个真实的双角色仪器压扁——
#:   这正是我原先方案 C 被否的原因。
INSTRUMENT_ROLES = OrderedDict([
    ("v0.3-gen", "unseen_carrier_gate"),
    ("v0.2.1", "in_train_carrier_deployment_format"),
    ("v0.4-toolout", "in_train_carrier_regression"),
    ("v0.5-topup-families", "in_distribution_capability_observation"),
    ("v0.6-document", OrderedDict([
        ("soup-a050", "unseen_carrier_gate"),
        ("m3-dpo", "unseen_mechanism"),
    ])),
])


def role_of(instrument: str, model: str | None = None) -> str:
    """取某仪器（对某模型）的角色。

    ★规则 24 的操作化：双角色仪器**不得**被压成单角色字符串；
    未指定模型时返回合并串（形如 `a|b`）以保证**不丢信息**。
    """
    r = INSTRUMENT_ROLES.get(instrument)
    if r is None:
        return "unregistered"
    if isinstance(r, dict):
        if model is None:
            return "|".join(sorted(set(r.values())))
        return r.get(model, "unregistered_for_model")
    return r


#: 覆盖矩阵的列（列名 → 依据的 scope 集合，顺序即文档中的列序）
MATRIX_COLUMNS = OrderedDict([
    ("train", {"kind": "train", "scopes": ["live_lineage"], "label": "训练数据"}),
    ("unseen_gate", {"kind": "gate", "scopes": ["v0.3-gen"], "label": "未见载体门禁"}),
    ("in_train_regression",
     {"kind": "gate", "scopes": ["v0.2.1", "v0.4-toolout"], "label": "在训载体回归"}),
    ("in_dist_capability",
     {"kind": "gate", "scopes": ["v0.5-topup-families"], "label": "在分布能力观测"}),
    # ★2026-10-06 新增独立列（**不并入 unseen_gate**）：
    #   理由一：它是**另一个仪器**，并进 unseen_gate 会让该列的 basis 混两种仪器，
    #           违反规则 21（不同口径不得混比）；
    #   理由二：它的角色**按模型不同**，不能塞进"按载体一行"的既有列语义里。
    ("document_gate",
     {"kind": "gate", "scopes": ["v0.6-document"], "label": "文档载体门（角色按模型）"}),
])

REQUIRED_CARRIER_FIELDS = (
    "id",
    "mission_class",
    "definition",
    "renderings",
    "trust_boundary",
    "security_attributes",
    "attack_mechanisms",
    "train_rows",
    "gate_items",
    "gaps",
    "evidence",
)
REQUIRED_TOP_LEVEL = ("version", "mission_layer", "carriers",
                      "mission_to_engineering", "instruments",
                      "coverage_matrix", "claims")

#: 未见载体门禁的效力下限（`docs/01 §11.2`：每格 n < 34 时任何"通过/不通过"
#: 都不得作为决策依据）。本体必须显式声明哪些载体**有**达标的未见载体门禁。
MIN_UNSEEN_ROBUSTNESS_N = 34

_OK_SENTINEL = "CARRIER-ONTOLOGY-CHECK=PASS errors=0"


# ============================================================== 扫描/现算 ===
def _expand(pattern: str) -> list[Path]:
    """把相对 glob 展开为**排序**的现有文件列表（缺文件不报错，由上层断言）。"""
    if any(ch in pattern for ch in "*?["):
        return sorted(ROOT.glob(pattern))
    p = ROOT / pattern
    return [p] if p.exists() else []


def scan_file(path: Path) -> dict:
    """单文件扫描：行数、逐载体行数/命中数、协议块行数、标签样本位置。"""
    carrier_rows: Counter = Counter()
    carrier_hits: Counter = Counter()
    protocol_versions: Counter = Counter()
    protocol_rows = 0
    samples: dict[str, list] = {}
    rows = 0
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    with path.open("rb") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rows += 1
            tags = set()
            hits = 0
            for m in CARRIER_TAG_RE.finditer(line):
                tags.add(m.group(1).decode())
                hits += 1
            for m in CARRIER_ALT_RE.finditer(line):
                tags.add(m.group(1).decode())
                hits += 1
            for t in tags:
                carrier_rows[t] += 1
                bucket = samples.setdefault(t, [])
                if len(bucket) < MAX_SAMPLES_PER_LABEL:
                    bucket.append({"file": rel, "line": lineno})
            carrier_hits.update({t: 1 for t in tags})
            m = PROTOCOL_RE.search(line)
            if m:
                protocol_rows += 1
                protocol_versions[m.group(1).decode()] += 1
    return {
        "path": rel,
        "rows": rows,
        "carrier_rows": dict(sorted(carrier_rows.items())),
        "carrier_hits": dict(sorted(carrier_hits.items())),
        "protocol_rows": protocol_rows,
        "protocol_versions": dict(sorted(protocol_versions.items())),
        "_samples": samples,
    }


def scan_glob(pattern: str) -> dict:
    """扫一个 glob，返回 {relpath: scan_file 结果}。"""
    out = {}
    for p in _expand(pattern):
        out[str(p.relative_to(ROOT)).replace("\\", "/")] = scan_file(p)
    return out


def load_jsonl(path: Path) -> list:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_unparsable": True})
    return rows


def load_glob_jsonl(pattern: str) -> list:
    rows = []
    for p in _expand(pattern):
        for r in load_jsonl(p):
            r["_file"] = str(p.relative_to(ROOT)).replace("\\", "/")
            rows.append(r)
    return rows


def collect_facts() -> dict:
    """现算全部事实（唯一真相）。其余所有数字都必须是它的投影。"""
    # ★2026-10-06 第 18 轮：暂存/候选区也必须被扫描 ✓
    #   （此前漏了它 ⇒ 新增的 dpo_remediation_staging scope 会静默计为 0 ✗）
    scan_globs = ["data/lf/*.jsonl", "data/sft/**/*.jsonl", "data/dpo/**/*.jsonl",
                  "data/dpo-remediation-staging/*.jsonl",
                  "data/heldout/**/*.jsonl"]
    files: dict[str, dict] = {}
    samples: dict[str, list] = {}
    for g in scan_globs:
        for rel, blk in scan_glob(g).items():
            files[rel] = blk
            for label, loc in (blk.get("_samples") or {}).items():
                bucket = samples.setdefault(label, [])
                for item in loc:
                    if len(bucket) < MAX_SAMPLES_PER_LABEL:
                        bucket.append(item)
    for blk in files.values():
        blk.pop("_samples", None)

    observed = Counter()
    for blk in files.values():
        observed.update(blk["carrier_rows"])

    # --- 训练侧：逐 scope × 逐载体 ---
    train_rows: dict[str, dict[str, int]] = {}
    scope_carriers: dict[str, Counter] = {}
    for scope, pattern in TRAIN_SCOPES.items():
        c: Counter = Counter()
        # ★2026-09-30 晚（docs/01 §11.24 规则 24）：scope 支持**多 glob 并集**，
        #   以便表达"活谱系"（= 被活产物消费的文件）这种跨文件的组合范围。
        pats = pattern if isinstance(pattern, (list, tuple)) else [pattern]
        for _p in pats:
            for rel in _expand(_p):
                key = str(rel.relative_to(ROOT)).replace("\\", "/")
                blk = files.get(key)
                if blk:
                    c.update(blk["carrier_rows"])
        # ★2026-10-06 第 18 轮（规则 32 fail-closed）：
        #   若某 scope 的 glob 在**磁盘上确有匹配**，却在 `files` 里取不到，
        #   那是"scan_globs 与 TRAIN_SCOPES 不同步"的**缺陷** ✗，
        #   不得静默计为 0 ✓ —— 0 行看起来像"还没数据"，没人会去查 ✗✗。
        if not c:
            on_disk = 0
            for _p in pats:
                on_disk += len(_expand(_p))
            if on_disk > 0:
                raise SystemExit(
                    f"[fail-closed] scope `{scope}` 的模式 {pats} 在磁盘上匹配到 "
                    f"{on_disk} 个文件，但扫描集 `files` 里一个都没有 ⇒ "
                    f"`scan_globs` 与 `TRAIN_SCOPES` 不同步 ✗。"
                    f"请把该路径加入 collect_facts() 的 scan_globs ✓。")
        scope_carriers[scope] = c
        for label, n in c.items():
            train_rows.setdefault(label, {})[scope] = n
    for label in observed:
        per = train_rows.setdefault(label, {})
        for scope in TRAIN_SCOPES:
            per.setdefault(scope, 0)

    # --- 门禁侧：仪器统计 + 逐载体 ---
    instruments = OrderedDict()
    gate_items: dict[str, dict[str, int]] = {}
    for name, pattern in GATE_SCOPES.items():
        rows = load_glob_jsonl(pattern)
        kind = Counter(str(r.get("kind")) for r in rows if r.get("kind"))
        lang = Counter(str(r.get("language") or r.get("lang"))
                       for r in rows if (r.get("language") or r.get("lang")))
        per_carrier: Counter = Counter()
        per_carrier_robust: Counter = Counter()
        for r in rows:
            blob = json.dumps(r, ensure_ascii=False).encode("utf-8")
            tags = {m.group(1).decode() for m in CARRIER_TAG_RE.finditer(blob)}
            tags |= {m.group(1).decode() for m in CARRIER_ALT_RE.finditer(blob)}
            for t in tags:
                per_carrier[t] += 1
                if str(r.get("kind")) == "robustness":
                    per_carrier_robust[t] += 1
        for label, n in per_carrier.items():
            gate_items.setdefault(label, {})[name] = n
        instruments[name] = {
            # ★2026-10-06：role 可能是 str（与模型无关）或 dict（按模型分角色）。
            #   两者都保留原值，另加 role_by_model 与 role_merged 两个便于消费的字段，
            #   保证规则 24「双角色不得被压扁」在输出层也成立。
            "role": INSTRUMENT_ROLES[name],
            "role_by_model": (dict(INSTRUMENT_ROLES[name])
                              if isinstance(INSTRUMENT_ROLES[name], dict) else None),
            "role_merged": role_of(name),
            "glob": pattern,
            "rows": len(rows),
            "files": sorted({r["_file"] for r in rows}),
            "kind": dict(kind.most_common()),
            "lang": dict(lang.most_common()),
            "per_carrier": dict(per_carrier.most_common()),
            "per_carrier_robustness": dict(per_carrier_robust.most_common()),
            "untagged_rows": sum(1 for r in rows if not _row_tags(r)),
        }
    for label in observed:
        per = gate_items.setdefault(label, {})
        for name in GATE_SCOPES:
            per.setdefault(name, 0)

    # --- 覆盖矩阵（由 scope 计数现算，不由本体抄） ---
    matrix: dict[str, dict] = {}
    for label in sorted(set(observed) | set(train_rows) | set(gate_items)):
        cells = {}
        for col, spec in MATRIX_COLUMNS.items():
            src = train_rows if spec["kind"] == "train" else gate_items
            n = sum(src.get(label, {}).get(s, 0) for s in spec["scopes"])
            cell = {"n": n, "basis": "+".join(spec["scopes"]) if len(spec["scopes"]) > 1
                    else spec["scopes"][0]}
            if col == "unseen_gate":
                cell["robustness_n"] = sum(
                    instruments[s]["per_carrier_robustness"].get(label, 0)
                    for s in spec["scopes"])
            cells[col] = cell
        matrix[label] = cells

    return {
        "scanned_globs": scan_globs,
        "files": files,
        "observed_carriers": dict(observed.most_common()),
        "label_samples": {k: v for k, v in sorted(samples.items())},
        "train_scope_carriers": {k: dict(v.most_common())
                                 for k, v in scope_carriers.items()},
        "train_rows": {k: v for k, v in sorted(train_rows.items())},
        "gate_items": {k: v for k, v in sorted(gate_items.items())},
        "instruments": instruments,
        "coverage_matrix": matrix,
        "scope_meta": {
            "train_scopes": list(TRAIN_SCOPES),
            "train_scope_docs": TRAIN_SCOPE_NOTE,
            "gate_scopes": list(GATE_SCOPES),
            "matrix_columns": {k: v["label"] for k, v in MATRIX_COLUMNS.items()},
        },
    }


def _row_tags(row: dict) -> set:
    blob = json.dumps(row, ensure_ascii=False).encode("utf-8")
    tags = {m.group(1).decode() for m in CARRIER_TAG_RE.finditer(blob)}
    tags |= {m.group(1).decode() for m in CARRIER_ALT_RE.finditer(blob)}
    return tags


# ================================================================ 校验 =====
def run_check(ontology: dict, facts: dict) -> tuple[list[str], dict]:
    """核心校验。返回 (errors, report)。errors 为空即 PASS。"""
    errors: list[str] = []
    detail: dict = {}
    carriers = ontology.get("carriers")
    if not isinstance(carriers, list):
        errors.append("ontology.carriers 必须是 list（id 唯一性靠 list + id 字段检查）")
        return errors, detail

    ids: list[str] = []
    for i, c in enumerate(carriers):
        if not isinstance(c, dict):
            errors.append(f"carrier[{i}] 不是对象")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"missing_field_id:carrier[{i}]")
            continue
        ids.append(cid)
        for f in REQUIRED_CARRIER_FIELDS:
            if f not in c:
                errors.append(f"missing_field:{cid}:{f}")
        for f in ("mission_class", "renderings", "security_attributes",
                  "attack_mechanisms", "gaps", "evidence"):
            if f in c and (not isinstance(c[f], list) or not c[f]):
                errors.append(f"empty_list_field:{cid}:{f}")
    dup = [k for k, v in Counter(ids).items() if v > 1]
    for k in sorted(dup):
        errors.append(f"duplicate_id:{k}")

    id_set = set(ids)

    # --- 1. 标签闭合性：仓库里出现的标签 ⊆ 本体 id ---
    observed = facts.get("observed_carriers") or {}
    unknown = sorted(set(observed) - id_set)
    for label in unknown:
        hits = observed[label]
        locs = (facts.get("label_samples") or {}).get(label) or []
        loc_s = ", ".join(f"{x['file']}:{x['line']}" for x in locs) or "（无样本）"
        errors.append(f"unknown_carrier_label:{label} rows={hits} 样本: {loc_s}")
    missing_from_data = sorted(id_set - set(observed))
    detail["unknown_labels"] = unknown
    detail["ontology_only_labels"] = missing_from_data

    # --- 2. 数字一致：train_rows / gate_items 逐格 ---
    c_train = facts.get("train_rows") or {}
    c_gate = facts.get("gate_items") or {}
    for cid in ids:
        entry = next((c for c in carriers if c.get("id") == cid), {})
        tr = entry.get("train_rows")
        if isinstance(tr, dict):
            for scope in TRAIN_SCOPES:
                want = c_train.get(cid, {}).get(scope, 0)
                got = tr.get(scope)
                if got != want:
                    errors.append(
                        f"train_rows_mismatch:{cid}:{scope} ontology={got!r} "
                        f"computed={want}")
            extra = sorted(set(tr) - set(TRAIN_SCOPES))
            if extra:
                errors.append(f"train_rows_unknown_scope:{cid}:{extra}")
        gi = entry.get("gate_items")
        if isinstance(gi, dict):
            for name in GATE_SCOPES:
                want = c_gate.get(cid, {}).get(name, 0)
                got = gi.get(name)
                if got != want:
                    errors.append(
                        f"gate_items_mismatch:{cid}:{name} ontology={got!r} "
                        f"computed={want}")
            extra = sorted(set(gi) - set(GATE_SCOPES))
            if extra:
                errors.append(f"gate_items_unknown_scope:{cid}:{extra}")

    # --- 3. 覆盖矩阵逐格 ---
    cm = ontology.get("coverage_matrix")
    c_cm = facts.get("coverage_matrix") or {}
    if not isinstance(cm, dict) or not isinstance(cm.get("cells"), dict):
        errors.append("coverage_matrix.cells 缺失或不是对象")
    else:
        cells = cm["cells"]
        for cid in ids:
            for col in MATRIX_COLUMNS:
                want = c_cm.get(cid, {}).get(col)
                got = (cells.get(cid) or {}).get(col)
                if got is None:
                    errors.append(f"matrix_missing_cell:{cid}:{col}")
                    continue
                if not isinstance(got, dict):
                    errors.append(f"matrix_cell_not_object:{cid}:{col}")
                    continue
                if got.get("n") != want.get("n"):
                    errors.append(f"matrix_mismatch:{cid}:{col}:n "
                                  f"ontology={got.get('n')!r} "
                                  f"computed={want.get('n')!r}")
                if got.get("basis") != want.get("basis"):
                    errors.append(f"matrix_mismatch:{cid}:{col}:basis "
                                  f"ontology={got.get('basis')!r} "
                                  f"computed={want.get('basis')!r}")
                if col == "unseen_gate" and \
                        got.get("robustness_n") != want.get("robustness_n"):
                    errors.append(f"matrix_mismatch:{cid}:{col}:robustness_n "
                                  f"ontology={got.get('robustness_n')!r} "
                                  f"computed={want.get('robustness_n')!r}")
                # 内部自洽：矩阵格必须与条目字段一致（防止两处数字各自漂移）
                entry = next((c for c in carriers if c.get("id") == cid), {})
                spec = MATRIX_COLUMNS[col]
                if spec["kind"] == "train" and isinstance(entry.get("train_rows"), dict):
                    linked = sum(entry["train_rows"].get(s, 0) for s in spec["scopes"])
                    if linked != got.get("n"):
                        errors.append(f"matrix_linked_field_mismatch:{cid}:{col} "
                                      f"cell={got.get('n')!r} "
                                      f"train_rows={linked!r}")
                if spec["kind"] == "gate" and isinstance(entry.get("gate_items"), dict):
                    linked = sum(entry["gate_items"].get(s, 0) for s in spec["scopes"])
                    if linked != got.get("n"):
                        errors.append(f"matrix_linked_field_mismatch:{cid}:{col} "
                                      f"cell={got.get('n')!r} "
                                      f"gate_items={linked!r}")
        extra_cells = sorted(set(cells) - id_set)
        for k in extra_cells:
            errors.append(f"matrix_unknown_carrier:{k}")

    # --- 3b. 结论边界：未见载体门禁的效力下限 + 声明集合一致 ---
    #     这是全文最重要的一条断言：它把"哪几个载体的结论**无门禁支撑**"
    #     从文档措辞变成机械事实（`docs/01 §10.3` 规则 3 的表述纪律）。
    #     下限同时作用于**声明值**（本体不得把低于底线的门禁写成可用）与
    #     **现算值**（磁盘事实同样不得低于底线）。
    declared_cells = (cm.get("cells") or {}) if isinstance(cm, dict) else {}
    qualifying: set = set()
    for cid, cols in c_cm.items():
        ug = cols.get("unseen_gate") or {}
        d_ug = (declared_cells.get(cid) or {}).get("unseen_gate") or {}
        for rb, where in ((d_ug.get("robustness_n"), "ontology"),
                          (ug.get("robustness_n") or 0, "computed")):
            if (ug.get("n") or 0) > 0 and rb is not None and \
                    rb < MIN_UNSEEN_ROBUSTNESS_N:
                errors.append(
                    f"unseen_gate_power_below_floor:{cid} robustness_n={rb}"
                    f"[{where}] < {MIN_UNSEEN_ROBUSTNESS_N}"
                    f"（docs/01 §11.2 每格 n<34 不得作决策依据）")
        if (ug.get("robustness_n") or 0) >= MIN_UNSEEN_ROBUSTNESS_N:
            qualifying.add(cid)
    claims = ontology.get("claims")
    if not isinstance(claims, dict):
        errors.append("claims 缺失或不是对象")
    else:
        decl = claims.get("unseen_carrier_gate_carriers")
        if sorted(decl or []) != sorted(qualifying):
            errors.append("claims_unseen_carrier_gate_carriers_mismatch "
                          f"ontology={sorted(decl or [])} computed={sorted(qualifying)}")
        no_gate = sorted(set(c_cm) - qualifying)
        decl_no = claims.get("no_unseen_gate_carriers")
        if sorted(decl_no or []) != no_gate:
            errors.append("claims_no_unseen_gate_carriers_mismatch "
                          f"ontology={sorted(decl_no or [])} computed={no_gate}")
    detail["unseen_gate_carriers"] = sorted(qualifying)
    detail["no_unseen_gate_carriers"] = sorted(set(c_cm) - qualifying)

    # --- 4. 仪器统计一致 ---
    o_inst = ontology.get("instruments")
    if not isinstance(o_inst, dict):
        errors.append("instruments 缺失或不是对象")
    else:
        for name, want in (facts.get("instruments") or {}).items():
            got = o_inst.get(name)
            if not isinstance(got, dict):
                errors.append(f"instrument_missing:{name}")
                continue
            for key in ("rows", "kind", "lang", "per_carrier",
                        "per_carrier_robustness", "untagged_rows", "role"):
                if got.get(key) != want.get(key):
                    errors.append(f"instrument_mismatch:{name}:{key} "
                                  f"ontology={got.get(key)!r} "
                                  f"computed={want.get(key)!r}")
        for name in sorted(set(o_inst) - set(facts.get("instruments") or {})):
            errors.append(f"instrument_unknown:{name}")

    # --- 5. 使命层映射一致 ---
    m2e = ontology.get("mission_to_engineering")
    mission = ontology.get("mission_layer")
    if not isinstance(m2e, dict) or not isinstance(mission, dict):
        errors.append("mission_layer / mission_to_engineering 缺失或不是对象")
    else:
        referenced: set = set()
        for mid, m in m2e.items():
            if mid not in mission:
                errors.append(f"mission_map_unknown_mission:{mid}")
            eng = (m or {}).get("engineering_ids")
            if not isinstance(eng, list):
                errors.append(f"mission_map_bad_engineering_ids:{mid}")
                continue
            for e in eng:
                referenced.add(e)
                if e not in id_set:
                    errors.append(f"mission_map_unknown_carrier:{mid}->{e}")
        for cid in sorted(id_set - referenced):
            errors.append(f"mission_map_unmapped_carrier:{cid}")

    # --- 6. 结果横幅 ---
    detail["ontology_carriers"] = sorted(id_set)
    detail["observed_carriers"] = observed
    detail["counts"] = {
        "ontology_carriers": len(id_set),
        "observed_labels": len(observed),
        "scanned_files": len(facts.get("files") or {}),
    }
    return errors, detail


def banner(errors: list[str]) -> str:
    if errors:
        return f"CARRIER-ONTOLOGY-CHECK=FAIL errors={len(errors)}"
    return _OK_SENTINEL


# ================================================================= CLI =====
def _print_census(facts: dict) -> None:
    print("=== 训练侧：逐 scope × 载体（行数）===")
    labels = sorted(facts["observed_carriers"])
    header = f"{'scope':28}" + "".join(f"{l[:12]:>14}" for l in labels)
    print(header)
    for scope in TRAIN_SCOPES:
        row = facts["train_scope_carriers"][scope]
        print(f"{scope:28}" + "".join(f"{row.get(l, 0):>14,}" for l in labels))
    print()
    print(f"=== 门禁侧：4 个仪器（行为门禁分母 = kind==robustness）===")
    for name, blk in facts["instruments"].items():
        print(f"  {name:22} rows={blk['rows']:<5} role={blk['role']}")
        print(f"      kind={blk['kind']} lang={blk['lang']} "
              f"untagged={blk['untagged_rows']}")
        print(f"      per_carrier={blk['per_carrier']} "
              f"robustness={blk['per_carrier_robustness']}")
    print()
    print("=== 覆盖矩阵（现算）===")
    cols = list(MATRIX_COLUMNS)
    print(f"{'carrier':18}" + "".join(f"{MATRIX_COLUMNS[c]['label']:>22}" for c in cols))
    for label in labels:
        row = facts["coverage_matrix"][label]
        cells = []
        for c in cols:
            cell = row[c]
            s = f"{cell['n']:,}"
            if c == "unseen_gate":
                s += f" (rb {cell.get('robustness_n', 0):,})"
            cells.append(f"{s:>22}")
        print(f"{label:18}" + "".join(cells))
    print()
    print("覆盖矩阵列依据：", {c: v["scopes"] for c, v in MATRIX_COLUMNS.items()})
    print("观测到的标签：", json.dumps(facts["observed_carriers"], ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="S1 载体本体论校验（只读）")
    ap.add_argument("--ontology", default=str(DEFAULT_ONTOLOGY),
                    help="本体 JSON 路径（默认 data/ontology/carriers.json）")
    ap.add_argument("--census", action="store_true", help="额外打印普查与覆盖矩阵")
    ap.add_argument("--emit-counts", default=None,
                    help="把现算的 train_rows/gate_items/coverage_matrix 写到此 JSON")
    ap.add_argument("--quiet", action="store_true", help="只打印末行横幅")
    a = ap.parse_args(argv)

    op = Path(a.ontology)
    if not op.is_absolute():
        op = ROOT / op
    ontology = None
    if op.exists():
        try:
            ontology = json.loads(op.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[fail-closed] 本体 JSON 解析失败：{exc}", file=sys.stderr)
            print("CARRIER-ONTOLOGY-CHECK=FAIL errors=1")
            return 2
    elif not a.emit_counts:
        # fail-closed：缺件不得静默通过（docs/01 §11.3），且不必先花一次全量扫描
        print(f"[fail-closed] 本体文件不存在：{op}", file=sys.stderr)
        print("CARRIER-ONTOLOGY-CHECK=FAIL errors=1")
        return 2

    facts = collect_facts()
    if a.census and not a.quiet:
        _print_census(facts)
    if a.emit_counts:
        out = Path(a.emit_counts)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "note": ("本文件是**某次现算的快照**，不是权威来源；权威来源永远是 "
                     "`scripts/check_carrier_ontology.py` 的现算。数据一变它就会滞后，"
                     "不要拿它当判据——用 `check_carrier_ontology.py` 重新校验。"),
            "train_rows": facts["train_rows"],
            "gate_items": facts["gate_items"],
            "coverage_matrix": facts["coverage_matrix"],
            "instruments": facts["instruments"],
            "observed_carriers": facts["observed_carriers"],
            "train_scope_notes": TRAIN_SCOPE_NOTE,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"counts -> {out}")

    if ontology is None:
        print(f"[fail-closed] 本体文件不存在：{op}", file=sys.stderr)
        print("CARRIER-ONTOLOGY-CHECK=FAIL errors=1")
        return 2

    errors, detail = run_check(ontology, facts)
    if not a.quiet:
        if errors:
            print(f"\n[FAIL] {len(errors)} 个错误：")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"\n[PASS] 本体 {op.relative_to(ROOT) if op.is_relative_to(ROOT) else op} "
                  f"与磁盘事实逐格一致"
                  f"（载体 {detail['counts']['ontology_carriers']} 类 / "
                  f"扫描 {detail['counts']['scanned_files']} 个 jsonl）")
        missing_from_data = detail.get("ontology_only_labels") or []
        if missing_from_data:
            print(f"  [note] 本体有、数据中 0 次的标签：{missing_from_data}")
    print(banner(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
