#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""M2.5 staging「结账完整性」（manifest reconciliation）不变量检查器。

对象：`data/sft/m2.5-staging/`（备料目录）。

## 与 check_m25_staging.py 的分工（互补，不重叠）

- `scripts/check_m25_staging.py` 查**数据本身**的硬断言（字段集 / 结构 /
  lang↔内容 / 唯一性 / 配比 / 与 v0+v0x 零同文 / 探针留出污染对照）。
- **本脚本**查**结账/可审计性**：目录里每个 `*.jsonl` 是否在结账产物
  （`stats.json` + `README.md`）里有对应记录，且反向亦闭合。

## 不变量（任一失败 → 打印缺失清单 + 非零退出）

I1  正向闭合：`data/sft/m2.5-staging/*.jsonl` 的每一个词干都必须
    (a) 是 `stats.json["families"]` 的键，且 (b) 在 `README.md` 里有
    「结账记录」——`| <stem>.jsonl | <行数> |` 表行，或含
    `<stem>.jsonl` 字面量的 `##`/`###` 章节标题。
I2  反向闭合：`stats.json["families"]` 的每个键、README 里出现的每个
    **裸** `*.jsonl` 文件名，都必须有对应实体文件（README 里带路径的
    引用如 `data/lf/sft_m25.jsonl` 不算裸名，见 EXTERNAL_ALLOW）。
I3  自洽：`stats.json["families"][f]["rows"]` == 现算行数（结账不许过期）。
I4  README 行数不许过期：结账表行的行数单元格可解析为整数时必须等于现算行数
    （`--no-readme-counts` 可关；单元格非纯数字时记为 unparsed，不判错）。
I5  向后兼容：`stats.json` 的旧键 `files` / `t1_by_lang` / `t1_by_pack` /
    `t1_by_verdict` / `t9_by_lang` / `t9_by_pack` / `t9_by_verdict` / `seed`
    必须原样存在。
I6  README 章节标记 `<!-- X SECTION BEGIN -->` / `<!-- X SECTION END -->`
    必须成对、键唯一，且每个标记块内至少含一个 `## ` 标题。

## 现算口径（不抄 README 旧数字）

逐行**流式**读（fG 34 MB / longctx 15 MB 等，不整份载入）：行数、空行数、
sha256、语言分布（`by_lang`）、政策包分布（`by_pack`）、VERDICT 动作/裁决分布
（`by_action` / `by_verdict`）、task 分段分布（`by_task_part2`）、内容级 CJK 行
占比（`content_zh_rows` / `content_zh_ratio`），以及**族间内容重叠**——
键 = `md5(user)`，另算 `md5(pack + "\x00" + user)`（= 组装器去重粒度）。
`--lf`（默认开）额外扫 `data/lf/sft_m25.jsonl`，算每族与**已训混料**的重叠
（备料 vs 已训边界；只上报，不判错）。

## 用法

    .venv\Scripts\python.exe scripts/check_staging_manifest.py               # 只检查
    .venv\Scripts\python.exe scripts/check_staging_manifest.py --write-stats # 重算 stats.json
    .venv\Scripts\python.exe scripts/check_staging_manifest.py --no-lf       # 跳过 data/lf 扫描

末行固定为 `STAGING-MANIFEST=PASS errors=0`（或 FAIL + 非零退出）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
README = STAGE / "README.md"
STATS = STAGE / "stats.json"
LF_MIX = ROOT / "data" / "lf" / "sft_m25.jsonl"

# 旧键：必须原样保留（下游可能仍在读）
LEGACY_KEYS = ("files", "t1_by_lang", "t1_by_pack", "t1_by_verdict",
               "t9_by_lang", "t9_by_pack", "t9_by_verdict", "seed")
# 旧键里其实是「按族统计」的键（= 本脚本 families 的前身），用于交叉核对
LEGACY_FAMILY_KEYS = {"files": "row_counts", "t1_by_lang": "t1_injection",
                      "t1_by_pack": "t1_injection", "t1_by_verdict": "t1_injection",
                      "t9_by_lang": "t9_phishing", "t9_by_pack": "t9_phishing",
                      "t9_by_verdict": "t9_phishing"}
# 结账文本里允许出现的「非本目录」jsonl 裸名（README 里带路径引用的不算裸名）
EXTERNAL_ALLOW = {"sft_m25.jsonl"}
CONTRACT_FIELDS = {"id", "task", "pack", "lang", "messages"}
PACKS = ("conservative", "default", "professional")

_BARE_JSONL = re.compile(r"(?<![\\/\w.\-])([A-Za-z0-9_][A-Za-z0-9_.\-]*\.jsonl)")
_TABLE_ROW = re.compile(r"^\s*\|\s*([A-Za-z0-9_.\-]+)\.jsonl\s*\|")
_HEADING = re.compile(r"^(#{2,4})\s+(.*\S)\s*$")
_MARK_BEGIN = re.compile(r"^\s*<!--\s*(.+?)\s+SECTION BEGIN\s*-->\s*$")
_MARK_END = re.compile(r"^\s*<!--\s*(.+?)\s+SECTION END\s*-->\s*$")
_FIRST_INT = re.compile(r"\d[\d,]*")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_MAX_ERR_PER_FAMILY = 10


# --------------------------------------------------------------- 小工具 ---
def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bump(d: dict, key) -> None:
    d[str(key)] = d.get(str(key), 0) + 1


def _rel(p: Path) -> str:
    """相对仓库根的显示路径；仓库外（如 --stage 指向临时目录）回退为绝对路径。"""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _verdict_of(row: dict):
    """从 assistant 末行 VERDICT 取 dict；取不到返回 None。"""
    try:
        asst = row["messages"][2]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if "VERDICT: " not in asst:
        return None
    try:
        v = json.loads(asst.rsplit("VERDICT: ", 1)[1])
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


# --------------------------------------------------------- 族级现算统计 ---
def family_stats(path: Path, collect_keys: bool = True,
                 errors: list | None = None) -> dict:
    """流式现算一个族的全部统计。collect_keys → 收集 md5 键集（供重叠计算）。"""
    errs = errors if errors is not None else []
    name = path.stem
    n_cap = [0]

    def add_err(msg: str) -> None:
        if n_cap[0] < _MAX_ERR_PER_FAMILY:
            errs.append(msg)
            n_cap[0] += 1

    st = {
        "rows": 0, "blank_lines": 0, "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "by_lang": {}, "by_pack": {}, "by_action": {}, "by_verdict": {},
        "by_task_prefix": {}, "by_task_part2": {},
        "ids_unique": 0, "pack_user_unique": 0, "user_unique": 0,
        "content_zh_rows": 0,
        "schema_violation_rows": 0, "no_verdict_rows": 0,
    }
    user_keys: set[str] = set()
    pack_user_keys: set[str] = set()
    ids: set[str] = set()
    seen_user: set[str] = set()

    with path.open("r", encoding="utf-8", newline="") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                st["blank_lines"] += 1
                continue
            st["rows"] += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                add_err(f"{name}:{lineno}: JSON 解析失败 {exc}")
                continue
            if not isinstance(row, dict):
                add_err(f"{name}:{lineno}: 顶层不是对象")
                continue
            if set(row) != CONTRACT_FIELDS:
                st["schema_violation_rows"] += 1
                add_err(f"{name}:{lineno}: 字段集 != m1 契约 {sorted(row)}")
            lang, pack = row.get("lang"), row.get("pack")
            task = str(row.get("task") or "")
            rid = str(row.get("id") or "")
            _bump(st["by_lang"], lang)
            _bump(st["by_pack"], pack)
            _bump(st["by_task_prefix"], task.split(":", 1)[0] or "<empty>")
            parts = task.split(":")
            if len(parts) > 1 and parts[1]:
                _bump(st["by_task_part2"], parts[1])
            if rid:
                if rid in ids:
                    add_err(f"{name}:{lineno}: id 重复 {rid}")
                ids.add(rid)
            msgs = row.get("messages")
            user = ""
            asst = ""
            if isinstance(msgs, list) and len(msgs) >= 3:
                try:
                    user = msgs[1].get("content") or ""
                    asst = msgs[2].get("content") or ""
                except AttributeError:
                    pass
            if _CJK.search(user) or _CJK.search(asst):
                st["content_zh_rows"] += 1
            if user:
                if collect_keys:
                    ukey = md5(user)
                    user_keys.add(ukey)
                    pack_user_keys.add(md5(f"{pack}\x00{user}"))
                if user in seen_user:
                    pass  # 跨包复用 user 是既定设计，不算错
                seen_user.add(user)
            v = _verdict_of(row)
            if v is None:
                st["no_verdict_rows"] += 1
            else:
                _bump(st["by_action"], v.get("action"))
                _bump(st["by_verdict"], v.get("verdict"))

    st["ids_unique"] = len(ids)
    st["user_unique"] = len(seen_user)
    st["pack_user_unique"] = len(pack_user_keys) if collect_keys else 0
    st["content_zh_ratio"] = (round(st["content_zh_rows"] / st["rows"], 4)
                              if st["rows"] else 0.0)
    st["_user_keys"] = user_keys
    st["_pack_user_keys"] = pack_user_keys
    return st


# ----------------------------------------------------- README 结账解析 ---
def readme_records(text: str) -> dict:
    """→ {stem: [{"line","kind","count","raw"}]}；count 为可解析行数或 None。"""
    recs: dict = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _TABLE_ROW.match(line)
        if m:
            cells = [c.strip() for c in line.split("|")]
            raw = cells[2] if len(cells) > 2 else ""
            mi = _FIRST_INT.search(raw)
            count = int(mi.group(0).replace(",", "")) if mi else None
            recs.setdefault(m.group(1), []).append(
                {"line": lineno, "kind": "table", "count": count, "raw": raw})
        h = _HEADING.match(line)
        if h:
            # 只认**裸**文件名：标题里的 `data/lf/sft_m25.jsonl` 是外部引用，
            # 不是本目录的结账记录（与下方 I2 的裸名口径保持一致）。
            for tok in _BARE_JSONL.findall(h.group(2)):
                recs.setdefault(tok[:-len(".jsonl")], []).append(
                    {"line": lineno, "kind": "heading", "count": None,
                     "raw": h.group(2)})
    return recs


def readme_markers(text: str) -> tuple[list, list]:
    """→ (blocks, errors)；blocks = [{key, start, end, headings}]。"""
    blocks: list = []
    errs: list = []
    open_stack: list = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        mb, me = _MARK_BEGIN.match(line), _MARK_END.match(line)
        if mb:
            open_stack.append((mb.group(1), lineno))
        elif me:
            key = me.group(1)
            if not open_stack:
                errs.append(f"README:{lineno}: 未配对的 SECTION END <{key}>")
                continue
            okey, oline = open_stack.pop()
            if okey != key:
                errs.append(f"README:{lineno}: SECTION END <{key}> 与 "
                            f"BEGIN <{okey}>（第 {oline} 行）不匹配")
                continue
            blocks.append({"key": key, "start": oline, "end": lineno})
    for key, lineno in open_stack:
        errs.append(f"README:{lineno}: SECTION BEGIN <{key}> 未闭合")
    keys = [b["key"] for b in blocks]
    for k in sorted(set(keys)):
        if keys.count(k) > 1:
            errs.append(f"README: SECTION 键重复 <{k}> ×{keys.count(k)}")
    for b in blocks:
        b["headings"] = [ln for ln in lines[b["start"]:b["end"] - 1]
                         if _HEADING.match(ln)]
        if not b["headings"]:
            errs.append(f"README:{b['start']}: SECTION <{b['key']}> 块内无 ## 标题")
    return blocks, errs


def check_stats_closure(s_obj, families: dict, errors: list) -> None:
    """I1/I2/I3/I5：stats.json ↔ 实测族的双向闭合 + 旧键保留。"""
    if not isinstance(s_obj, dict):
        errors.append("[I1] stats.json 顶层不是对象")
        return
    fam_old = s_obj.get("families")
    if not isinstance(fam_old, dict):
        errors.append("[I1] stats.json 无 `families`（按族结账）块")
        fam_old = {}
    for stem in families:
        if stem not in fam_old:
            errors.append(f"[I1] stats.json 未结账 {stem}.jsonl"
                          f"（`families` 缺该键）")
            continue
        want = families[stem]["rows"]
        got = (fam_old[stem].get("rows")
               if isinstance(fam_old[stem], dict) else None)
        if got != want:
            errors.append(f"[I3] {stem}.jsonl stats.json 行数过期："
                          f"{got} != 现算 {want}")
    for stem in sorted(fam_old):
        if stem not in families:
            errors.append(f"[I2] stats.json 结账了不存在的族 `{stem}.jsonl`")
    for k in LEGACY_KEYS:
        if k not in s_obj:
            errors.append(f"[I5] stats.json 旧键丢失（下游可能仍在读）：{k}")


def legacy_agreement(old: dict, families: dict) -> dict:
    """旧键的值与现算值是否一致（只上报，不改旧键）。"""
    out = {}
    if not isinstance(old, dict):
        return out
    if isinstance(old.get("files"), dict):
        out["files"] = all(old["files"].get(n) == families.get(n, {}).get("rows")
                           for n in old["files"])
    for k, stem in (("t1_by_lang", "t1_injection"),
                    ("t9_by_lang", "t9_phishing")):
        v = old.get(k)
        if isinstance(v, dict) and stem in families:
            out[k] = v == families[stem]["by_lang"]
    for k, stem in (("t1_by_pack", "t1_injection"),
                    ("t9_by_pack", "t9_phishing")):
        v = old.get(k)
        if isinstance(v, dict) and stem in families:
            out[k] = v == families[stem]["by_pack"]
    for k, stem in (("t1_by_verdict", "t1_injection"),
                    ("t9_by_verdict", "t9_phishing")):
        v = old.get(k)
        if isinstance(v, dict) and stem in families:
            out[k] = v == families[stem]["by_verdict"]
    return out


# ------------------------------------------------------------ 主核对 ---
def reconcile(stage: Path = STAGE, readme: Path = README, stats: Path = STATS,
              lf_mix: Path = LF_MIX, do_lf: bool = True,
              check_readme_counts: bool = True, log=print) -> dict:
    t0 = time.time()
    errors: list = []
    warnings: list = []

    files = sorted(p for p in stage.glob("*.jsonl") if p.is_file())
    families: dict = {}
    keys: dict = {}
    log(f"[scan] {len(files)} 个语料族（流式逐行）…")
    for p in files:
        t1 = time.time()
        st = family_stats(p, collect_keys=True, errors=errors)
        keys[p.stem] = (st.pop("_user_keys"), st.pop("_pack_user_keys"))
        families[p.stem] = st
        log(f"  - {p.stem:<24} rows={st['rows']:<6} "
            f"({time.time() - t1:.1f}s, {st['bytes'] / 1e6:.1f} MB)")

    # ---- 族间内容重叠（md5(user) 与 md5(pack\\x00user) 两种粒度）
    names = list(families)
    overlap = {"by_user_md5": {}, "by_pack_user_md5": {}, "pairs": []}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ua, pa = keys[a]
            ub, pb = keys[b]
            inter_u = len(ua & ub)
            inter_p = len(pa & pb)
            if inter_u or inter_p:
                overlap["pairs"].append({"a": a, "b": b,
                                         "user_md5_shared": inter_u,
                                         "pack_user_md5_shared": inter_p})
    for n in names:
        u, p = keys[n]
        overlap["by_user_md5"][n] = {
            "unique_users": len(u),
            "shared_with_other_staging_families": sum(
                len(u & keys[m][0]) for m in names if m != n)}
        overlap["by_pack_user_md5"][n] = {
            "unique_pack_user": len(p),
            "shared_with_other_staging_families": sum(
                len(p & keys[m][1]) for m in names if m != n)}

    # ---- 与已训混料 data/lf/sft_m25.jsonl 的重叠（只上报，不判错）
    lf = {"scanned": False, "path": None, "rows": 0}
    if do_lf and lf_mix.exists():
        t1 = time.time()
        log(f"[scan] data/lf/{lf_mix.name}（已训混料，重叠口径）…")
        lf_user: set[str] = set()
        lf_pack_user: set[str] = set()
        rows = 0
        with lf_mix.open("r", encoding="utf-8", newline="") as f:
            for line in f:
                if not line.strip():
                    continue
                rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    user = row["messages"][1]["content"] or ""
                except (KeyError, IndexError, TypeError):
                    continue
                if not user:
                    continue
                lf_user.add(md5(user))
                lf_pack_user.add(md5(f"{row.get('pack')}\x00{user}"))
        lf = {"scanned": True, "path": _rel(lf_mix),
              "rows": rows, "unique_users": len(lf_user),
              "unique_pack_user": len(lf_pack_user),
              "bytes": lf_mix.stat().st_size, "seconds": round(time.time() - t1, 1),
              "family_overlap": {}}
        for n in names:
            u, p = keys[n]
            lf["family_overlap"][n] = {
                "rows": families[n]["rows"],
                "rows_user_in_lf": len(u & lf_user),
                "rows_pack_user_in_lf": len(p & lf_pack_user),
                "user_ratio": round(len(u & lf_user) / max(1, len(u)), 4),
            }
    elif do_lf:
        warnings.append(f"data/lf/{lf_mix.name} 不存在，跳过已训混料重叠扫描")
        log("[scan] 已训混料不存在，跳过")
    else:
        log("[scan] --no-lf：跳过已训混料重叠扫描")

    # ---- I1/I2/I4：README 结账
    rd_text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if not readme.exists():
        errors.append(f"README 不存在：{readme}")
    recs = readme_records(rd_text)
    blocks, mark_errs = readme_markers(rd_text)
    errors.extend(mark_errs)
    for stem in names:
        if stem not in recs:
            errors.append(f"[I1] {stem}.jsonl 缺 README 结账记录"
                          f"（无 `| {stem}.jsonl | 行数 |` 表行，也无含该"
                          f"文件名的章节标题）")
        elif check_readme_counts:
            for r in recs[stem]:
                if r["kind"] == "table" and r["count"] is not None and \
                        r["count"] != families[stem]["rows"]:
                    errors.append(
                        f"[I4] {stem}.jsonl README 行数过期：README 第 "
                        f"{r['line']} 行写 {r['count']}，现算 "
                        f"{families[stem]['rows']}")
    bare = set(_BARE_JSONL.findall(rd_text))
    for tok in sorted(bare):
        stem = tok[:-len(".jsonl")]
        if stem in families or stem in EXTERNAL_ALLOW:
            continue
        errors.append(f"[I2] README 引用了不存在的族文件 `{tok}`"
                      f"（staging 目录内无此文件，也不在 EXTERNAL_ALLOW）")
    # README 里记录数 > 文件数的族（例如同一族写了多张表）只提示
    for stem, rs in recs.items():
        if stem not in families and stem not in EXTERNAL_ALLOW:
            errors.append(f"[I2] README 结账了不存在的族 `{stem}.jsonl`")
    if readme.exists() and not blocks:
        warnings.append("README 无任何 SECTION 标记块（既有体例缺口，见报告）")

    # ---- I1/I2/I3/I5：stats.json 结账
    old = {}
    if stats.exists():
        try:
            old = json.loads(stats.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"stats.json JSON 解析失败：{exc}")
            old = {}
    else:
        errors.append(f"stats.json 不存在：{stats}")
    errors_readme = list(errors)
    errors_stats: list = []
    check_stats_closure(old, families, errors_stats)
    errors.extend(errors_stats)
    legacy_ok = legacy_agreement(old, families)

    report = {
        "stage_dir": _rel(stage),
        "families": families,
        "family_count": len(names),
        "rows_total": sum(f["rows"] for f in families.values()),
        "overlap": overlap,
        "lf_mix": lf,
        "readme": {
            "path": _rel(readme),
            "records": {k: v for k, v in sorted(recs.items())},
            "bare_jsonl_tokens": sorted(bare),
            "sections": blocks,
            "has_family_record": {n: (n in recs) for n in names},
        },
        "stats_previous": old,
        "legacy_keys_ok": legacy_ok,
        "warnings": warnings,
        "errors": errors,
        "errors_readme": errors_readme,
        "errors_stats_prewrite": errors_stats,
        "verdict": "PASS" if not errors else f"FAIL ({len(errors)})",
        "seconds": round(time.time() - t0, 1),
    }
    return report


# --------------------------------------------------------- stats.json 写 ---
def build_stats(report: dict, old: dict) -> dict:
    """旧键原样保留 + 新增 `families`（现算）与 `_meta`。"""
    out: dict = {}
    for k in LEGACY_KEYS:
        if k in old:
            out[k] = old[k]
    out["families"] = {}
    for stem, st in report["families"].items():
        out["families"][stem] = {
            "file": f"{stem}.jsonl",
            "rows": st["rows"],
            "blank_lines": st["blank_lines"],
            "bytes": st["bytes"],
            "sha256": st["sha256"],
            "lang": st["by_lang"],
            "pack": st["by_pack"],
            "action": st["by_action"],
            "verdict": st["by_verdict"],
            "task_prefix": st["by_task_prefix"],
            "task_part2": st["by_task_part2"],
            "content_zh_rows": st["content_zh_rows"],
            "content_zh_ratio": st["content_zh_ratio"],
            "ids_unique": st["ids_unique"],
            "user_unique": st["user_unique"],
            "pack_user_unique": st["pack_user_unique"],
            "schema_violation_rows": st["schema_violation_rows"],
            "no_verdict_rows": st["no_verdict_rows"],
        }
    out["overlap_within_staging"] = {
        "key": "md5(user) / md5(pack + NUL + user)",
        "pairs": report["overlap"]["pairs"],
        "per_family": report["overlap"]["by_user_md5"],
    }
    lf = report["lf_mix"]
    out["overlap_with_lf_mix"] = {
        "path": lf.get("path"),
        "scanned": lf.get("scanned"),
        "rows": lf.get("rows"),
        "unique_users": lf.get("unique_users"),
        "per_family": lf.get("family_overlap", {}),
        "note": "备料 vs 已训边界：这 11 个族已于 2026-09-30 并入 "
                "data/lf/sft_m25.jsonl（README 首段），故重叠≈行数是**预期**的；"
                "新族（t2_mechanism / doc_structure / t9_phish_expand）应≈0。",
    }
    out["_meta"] = {
        "generator": "scripts/check_staging_manifest.py",
        "invariants": ["I1 正向闭合", "I2 反向闭合", "I3 stats 行数自洽",
                       "I4 README 行数不许过期", "I5 旧键保留",
                       "I6 README 章节标记成对"],
        "rows_total": report["rows_total"],
        "family_count": report["family_count"],
        "legacy_keys_ok": report["legacy_keys_ok"],
        "legacy_note": "旧键原样保留供下游读取；其值已在 _meta."
                       "legacy_keys_ok 中与现算值逐键比对。",
    }
    return out


# ------------------------------------------------------------------ CLI ---
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M2.5 staging 结账完整性检查器")
    ap.add_argument("--stage", default=str(STAGE))
    ap.add_argument("--readme", default=None)
    ap.add_argument("--stats", default=None)
    ap.add_argument("--write-stats", action="store_true",
                    help="按现算结果重写 stats.json（旧键原样保留）")
    ap.add_argument("--json-out", default=None, help="额外落盘机器可读报告")
    ap.add_argument("--no-lf", action="store_true",
                    help="跳过 data/lf/sft_m25.jsonl 重叠扫描")
    ap.add_argument("--no-readme-counts", action="store_true",
                    help="不校验 README 表行行数（I4）")
    args = ap.parse_args(argv)

    stage = Path(args.stage)
    readme = Path(args.readme) if args.readme else stage / "README.md"
    stats = Path(args.stats) if args.stats else stage / "stats.json"

    report = reconcile(stage=stage, readme=readme, stats=stats,
                       do_lf=not args.no_lf,
                       check_readme_counts=not args.no_readme_counts)

    print("=" * 78)
    print("M2.5 staging 结账完整性（manifest reconciliation）")
    print("=" * 78)
    for stem, st in report["families"].items():
        langs = ",".join(f"{k}={v}" for k, v in sorted(st["by_lang"].items()))
        vd = ",".join(f"{k}={v}" for k, v in sorted(st["by_verdict"].items()))
        print(f"  {stem:<24} rows={st['rows']:<6} {langs:<16} verdict[{vd}]"
              f"  zh_content={st['content_zh_ratio']:.2%}")
    print(f"  合计 {report['family_count']} 族 / {report['rows_total']} 行")
    lf = report["lf_mix"]
    if lf.get("scanned"):
        hit = {k: v["rows_user_in_lf"] for k, v in lf["family_overlap"].items()
               if v["rows_user_in_lf"]}
        print(f"  [备料 vs 已训] data/lf/{Path(lf['path']).name} "
              f"{lf['rows']} 行；有重叠的族：{hit or '无'}")
    ov = report["overlap"]["pairs"]
    print(f"  [族间重叠] 有共享 user 的族对："
          f"{[(o['a'], o['b'], o['user_md5_shared']) for o in ov] or '无'}")
    rd = report["readme"]
    print(f"  [README] 结账记录 {len(rd['records'])} 族；"
          f"SECTION 标记块 {len(rd['sections'])} 个；"
          f"裸 jsonl 引用 {len(rd['bare_jsonl_tokens'])} 个")
    for w in report["warnings"]:
        print(f"  [warn] {w}")

    if args.write_stats:
        old = (report["stats_previous"]
               if isinstance(report["stats_previous"], dict) else {})
        stats.write_text(
            json.dumps(build_stats(report, old), ensure_ascii=False,
                       indent=2) + "\n", encoding="utf-8")
        stats_after = json.loads(stats.read_text(encoding="utf-8"))
        post: list = []
        check_stats_closure(stats_after, report["families"], post)
        report["errors_stats_postwrite"] = post
        report["errors"] = report["errors_readme"] + post
        report["verdict"] = ("PASS" if not report["errors"]
                             else f"FAIL ({len(report['errors'])})")
        print(f"  -> 重写 {stats}"
              f"（写前 stats 侧错误 {len(report['errors_stats_prewrite'])} 个，"
              f"写后复检 {len(post)} 个）")

    for e in report["errors"]:
        print(f"  [ERR] {e}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"  -> {args.json_out}")

    n_err = len(report["errors"])
    print(f"STAGING-MANIFEST={'PASS' if not n_err else 'FAIL'} errors={n_err}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
