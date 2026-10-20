# -*- coding: utf-8 -*-
"""M6 数据行契约校验器（sysdesign-m6；H6 冻结前滚动预检 + 冻结后审计复用）。

两种模式：
  --mode final     行已是 m6-sample 终稿格式，直接校验（data/m6/**/train|dev|...jsonl）
  --mode staging   data/m6/_staging/*.jsonl 中间格式，先按 SYS-1 对齐清单投影再校验：
                     label/label_detail(平铺) -> labels.{task}.{label,label_detail}
                     text                    -> input.text
                     turns[{role,content}]   -> input.messages
                     text 以 "<carrier " 开头 -> input.carrier（解析信封片段）
                     split_hint              -> split（pool 等未分配值计 warning，校验时临时记 train）
                     source_family           -> source.family
                     T5 label_detail.position-> carrier_site（终稿改名）
  输出：逐文件 {n/valid/invalid/warnings + 错误类型 top5（计数+示例 id）}，退出码 0=全过。

用法：
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_check_rows.py --mode staging data/m6/_staging
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_check_rows.py --mode final --all data/m6/t1-moderation
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from referencing import Registry, Resource
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[1]
SD = REPO / "docs" / "m6" / "schemas"
SCHEMA_VERSION = "0.3.2"
SPLITS = {"train", "dev", "heldout", "challenge", "ood"}
CARRIER_RE = re.compile(r'^<carrier\s+type="(?P<type>[^"]+)"\s+trust="(?P<trust>[^"]+)"(?:\s+id="(?P<id>[^"]+)")?\s*>\s*<body>\n?(?P<body>.*?)\n?</body>\s*</carrier>\s*$', re.S)

_validator_cache: dict[str, Draft202012Validator] = {}


def get_validator(schema_name: str, entry: str | None = None) -> Draft202012Validator:
    key = f"{schema_name}#{entry}"
    if key not in _validator_cache:
        reg = Registry().with_resources(
            [(p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
             for p in SD.glob("*.schema.json")])
        schema = json.loads((SD / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
        if entry:
            schema = {"$ref": f"{schema_name}.schema.json#/{entry.lstrip('/')}"}
        _validator_cache[key] = Draft202012Validator(schema, registry=reg)
    return _validator_cache[key]


def project_staging(row: dict) -> tuple[dict, list[str]]:
    """staging 中间格式 -> m6-sample 终稿格式（返回 projected, warnings）。"""
    w = []
    task = row.get("task")
    out = {
        "schema": "m6-sample", "schema_version": SCHEMA_VERSION,
        "id": row.get("id"), "task": task,
        "split": row.get("split_hint"), "lang": row.get("lang"),
        "kind": row.get("kind"), "labels": {}, "flags": {},
        "source": {"family": row.get("source_family")},
    }
    # split：pool 等未分配值 → warning（H6 终稿必须落枚举）
    if out["split"] not in SPLITS:
        w.append(f"split_pending:{out['split']}")
        out["split"] = "train"  # 占位过枚举，终稿前必须真分配
    # input 形态
    if isinstance(row.get("turns"), list):
        msgs = [{"role": t.get("role", "user"), "content": t.get("content", "")}
                for t in row["turns"]]
        out["input"] = {"messages": msgs}
    elif row.get("kind") == "carrier" and isinstance(row.get("text"), str):
        # 四变体载体行 -> input.carrier + envelope_style（SYS-1 §4.2.1 Option A）
        ld0 = row.get("label_detail") or {}
        style = ld0.get("envelope") or "std_tag"
        ctype = ld0.get("carrier") or "other"
        text = row["text"]
        body = None
        if style == "std_tag":
            m = CARRIER_RE.match(text)
            if m:
                body = m.group("body")
                ctype = m.group("type")
        elif style == "simple_tag":
            # 【载体中文名】\n{body} / [EN LABEL]\n{body}
            body = text.split("\n", 1)[1] if "\n" in text else text
        elif style == "markdown":
            # > 来源：…（不可信外部内容）\n> \n{body 逐行 "> " 前缀}
            lines = text.split("\n")
            body = "\n".join(
                (l[2:] if l.startswith("> ") else ("" if l == ">" else l))
                for l in lines[2:])
        elif style == "plain":
            body = text
        if body is None:
            out["input"] = {"text": text}
            w.append("carrier_fragment_unparsed")
        else:
            out["input"] = {
                "operator_task": (row.get("meta") or {}).get("operator_task")
                                 or "请给出整理结果。",
                "carrier": {"type": ctype, "trust": "untrusted",
                            "id": "c1", "envelope_style": style, "body": body},
                "user_turn": "请给出整理结果。",
            }
    else:
        out["input"] = {"text": row.get("text")}
    # labels（平铺 -> 嵌套）
    ld = dict(row.get("label_detail") or {})
    if task == "T5" and "position" in ld:
        ld["carrier_site"] = ld.pop("position")
    if task == "T6" and row.get("label") == "cond":
        # adr-1b 6.2：cond -> neg + t6_class=conditional（单一真源）
        w.append("t6_cond_projected")
        ld["t6_class"] = "conditional"
        out["labels"] = {"T6": {"label": "neg", "label_detail": ld}}
    elif task == "SHARED":
        # 共享负例池：task -> pool；六键全负展开（语义假设：共享池对全部任务为负
        # —— T4 例外看 meta.t4_pos：true 则该行含 PII，T4 应为 pos + 真 spans，
        # 由 dataeng 终稿提供；此处投影只报 warning）
        w.append("shared_neg_assumed_all_six")
        out["task"] = "pool"
        meta = row.get("meta") or {}
        t4_pos = bool(meta.get("t4_pos"))
        if t4_pos:
            w.append("t4_pos_row_needs_spans")
        out["labels"] = {t: {"label": "neg"} for t in
                         ("T1", "T2", "T3", "T5", "T6")}
        out["labels"]["T4"] = ({"label": "pos"} if t4_pos
                               else {"label": "neg", "label_detail": {"spans": []}})
        if row.get("labels"):
            for k, v in row["labels"].items():
                out["labels"][k] = v
    else:
        out["labels"] = {task: {"label": row.get("label"), "label_detail": ld}}
    if row.get("est_tokens") is not None:
        out["est_tokens"] = row["est_tokens"]
    return out, w


def err_path(e) -> str:
    loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
    return f"{loc}: {e.message[:110]}"


def _rel(path: Path) -> str:
    """相对 REPO 显示路径；外部路径原样（防 relative_to 崩，dataeng 报告）。"""
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def check_file(path: Path, mode: str, limit: int | None) -> dict:
    validator = get_validator("m6-sample")
    n = valid = invalid = 0
    warns: Counter = Counter()
    errs: Counter = Counter()
    err_examples: dict[str, str] = {}
    warn_examples: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if limit is not None and n >= limit:
                break
            n += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as ex:
                invalid += 1
                k = f"json_decode:{ex.msg[:40]}"
                errs[k] += 1
                continue
            if mode == "staging":
                row, ws = project_staging(row)
                for wk in ws:
                    warns[wk] += 1
                    warn_examples.setdefault(wk, str(row.get("id")))
            errs_seen = sorted(validator.iter_errors(row), key=lambda e: list(e.absolute_path))
            if errs_seen:
                invalid += 1
                for e in errs_seen[:3]:
                    k = err_path(e)
                    errs[k] += 1
                    err_examples.setdefault(k, str(row.get("id")))
            else:
                valid += 1
    return {"file": _rel(path), "n": n, "valid": valid,
            "invalid": invalid,
            "warnings": dict(warns.most_common(5)),
            "warn_examples": warn_examples,
            "errors": dict(errs.most_common(5)),
            "err_examples": {k: err_examples[k] for k in list(errs)[:5]}}


def main() -> int:
    ap = argparse.ArgumentParser(description="M6 row contract validator")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--mode", choices=["staging", "final"], default="final")
    ap.add_argument("--limit", type=int, default=400, help="per-file sample (0=all)")
    args = ap.parse_args()

    files: list[Path] = []
    for p in args.paths:
        pp = Path(p)
        if pp.is_dir():
            files += sorted(pp.rglob("*.jsonl"))
        else:
            files.append(pp)
    if args.mode == "final":
        # final 模式跳过下划线目录（_staging 等中间格式区，dataeng 报告：
        # 扫父目录时误入 staging 文件必然 FAIL）
        files = [f for f in files
                 if not any(part.startswith("_") for part in f.parts)]

    total_inv = 0
    for fp in files:
        if not fp.is_file():
            print(f"[SKIP] {fp} (not found)")
            continue
        r = check_file(fp, args.mode, None if args.limit == 0 else args.limit)
        total_inv += r["invalid"]
        status = "PASS" if r["invalid"] == 0 else "FAIL"
        print(f"[{status}] {r['file']}: n={r['n']} valid={r['valid']} invalid={r['invalid']}"
              + (f" warns={r['warnings']}" if r["warnings"] else ""))
        for k, c in r["errors"].items():
            print(f"    x{c} [{r['err_examples'].get(k,'?')}] {k}")
        for k, c in r["warnings"].items():
            print(f"    ~x{c} [{r['warn_examples'].get(k,'?')}] {k}")
    print(f"\nrow checks: files={len(files)} invalid_total={total_inv}")
    return 1 if total_inv else 0


if __name__ == "__main__":
    sys.exit(main())
