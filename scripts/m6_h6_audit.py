# -*- coding: utf-8 -*-
"""M6 H6 冻结审计（sysdesign-m6）：一键四件套。

  1. 行契约全量滚（m6_check_rows.check_file，final 模式，--limit 0 语义）；
  2. label_counts（labels 键 × 文件 × split）+ 规模门断言；
  3. eval_family 覆盖率（dev-mirror 三文件 + pool/dev 行级必带，arch 裁定）；
  4. manifest 契约校验 + per-file sha256/rows/label_counts 与实际文件对数。

用法：
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_h6_audit.py [--skip-rows]
退出码：0=全过；1=有失败（fail-closed）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m6_check_rows import check_file  # noqa: E402

from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DM = ROOT / "data" / "m6"
SD = ROOT / "docs" / "m6" / "schemas"
TASKS = ("T1", "T2", "T3", "T4", "T5", "T6")
REG = Registry().with_resources(
    [(p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
     for p in SD.glob("*.schema.json")])


def split_of(p: Path) -> str:
    if "dev-mirror" in p.parts:
        return "dev-mirror"
    if "heldout-shared" in p.parts:
        return "heldout-shared"
    if "challenge" in p.parts:
        return "challenge"
    if "ood" in p.parts:
        return "ood"
    return p.stem


def is_view(p: Path) -> bool:
    """dev-mirror/* 是 pool/dev 的字节相同子集视图（manifest.dev_mirror_note）
    ——聚合统计跳过防双计，也不要求入 files[] 登记。"""
    return "dev-mirror" in p.parts


def scan_files() -> list[Path]:
    return sorted(f for f in DM.rglob("*.jsonl")
                  if not any(part.startswith("_") for part in f.parts))


def audit_rows(files: list[Path], fails: list[str]) -> None:
    inv_total = 0
    for fp in files:
        r = check_file(fp, "final", None)
        inv_total += r["invalid"]
        status = "PASS" if r["invalid"] == 0 else "FAIL"
        print(f"  [{status}] {r['file']}: n={r['n']} invalid={r['invalid']}"
              + (f" {r['errors']}" if r["errors"] else ""))
        for k, c in r["errors"].items():
            fails.append(f"rows:{r['file']}: {k} x{c}")
    print(f"  row contracts: files={len(files)} invalid_total={inv_total}")


def audit_counts(files: list[Path], fails: list[str]) -> dict:
    """聚合口径 = 训练装载器语义（m6_train.rows_for_split）：split 内按 id
    去重——pool 与任务文件的共享行是字节孪生（装载器同款去重，内容不一致
    即断言失败）；视图文件跳过。per_file 保留文件原值（manifest 对数用），
    聚合/规模门用去重值（arch 勘误 2026-10-21：双计口径曾虚报 T6 train pos
    4,100，真值 2,050）。"""
    agg: dict[tuple[str, str], Counter] = {}
    per_file = {}
    seen_ids: dict[str, dict[str, str]] = {}  # split -> id -> content hash
    twin_mismatch = 0
    for f in files:
        sp = split_of(f)
        if is_view(f):
            per_file[str(f.relative_to(DM)).replace("\\", "/")] = {
                "split": sp, "view": True}
            continue
        c: dict[str, Counter] = {}
        n = 0
        seen = seen_ids.setdefault(sp, {})
        with open(f, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n += 1
                row = json.loads(line)
                rid = row.get("id")
                # per_file 恒记文件原值（manifest 对数口径）
                for t, g in (row.get("labels") or {}).items():
                    d = c.setdefault(t, Counter())
                    d["pos" if g.get("label") == "pos" else "neg"] += 1
                # 聚合口径 = 装载器语义：split 内按 id 去重
                chash = hashlib.sha256(
                    json.dumps(row, sort_keys=True, ensure_ascii=False)
                    .encode("utf-8")).hexdigest()
                if rid in seen:
                    if seen[rid] != chash:
                        twin_mismatch += 1
                    continue
                seen[rid] = chash
                for t, g in (row.get("labels") or {}).items():
                    d = agg.setdefault((sp, t), Counter())
                    d["pos" if g.get("label") == "pos" else "neg"] += 1
        per_file[str(f.relative_to(DM)).replace("\\", "/")] = {
            "split": sp, "n": n,
            "label_counts": {t: {"pos": d["pos"], "neg": d["neg"]}
                             for t, d in sorted(c.items())}}
    if twin_mismatch:
        fails.append(f"counts: twin rows with DIFFERENT content: {twin_mismatch}")
    gates = {
        "train pos>=2000/task": all(agg.get(("train", t), Counter())["pos"] >= 2000
                                    for t in TASKS),
        "train neg>=2000/task": all(agg.get(("train", t), Counter())["neg"] >= 2000
                                    for t in TASKS),
        "heldout pos>=200/task": all(agg.get(("heldout", t), Counter())["pos"] >= 200
                                     for t in TASKS),
        "heldout neg>=1000/task": all(
            agg.get(("heldout", t), Counter())["neg"]
            + agg.get(("heldout-shared", t), Counter())["neg"] >= 1000
            for t in TASKS),
        "challenge>=1200": sum(d["pos"] + d["neg"] for (sp, t), d in agg.items()
                               if sp == "challenge") >= 1200,
        "ood>=500": sum(d["pos"] + d["neg"] for (sp, t), d in agg.items()
                        if sp == "ood") >= 500,
    }
    for k, ok in gates.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
        if not ok:
            fails.append(f"gate: {k}")
    print("  (unique-row caliber: split-level id dedup, loader semantics)")
    for (sp, t), d in sorted(agg.items()):
        print(f"    {sp:15s} {t}: pos={d['pos']:6d} neg={d['neg']:6d}")
    return per_file


def audit_eval_family(files: list[Path], fails: list[str]) -> None:
    """dev-mirror 三文件 100% 必带；pool/dev 仅镜像子集（flags.challenge/ood
    行 + benign 家族行）必带——常规任务 dev 行（含攻击正例）不属于任何
    eval_family，不要求（arch 裁定口径：定标家族材料）。"""
    for f in files:
        if "dev-mirror" in f.parts:
            n = miss = bad = 0
            with open(f, encoding="utf-8-sig") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    n += 1
                    ef = ((json.loads(line).get("meta") or {}).get("eval_family"))
                    if ef is None:
                        miss += 1
                    elif ef not in ("benign", "challenge", "ood"):
                        bad += 1
            ok = miss == 0 and bad == 0
            print(f"  [{'PASS' if ok else 'FAIL'}] eval_family {f.relative_to(DM)}: "
                  f"rows={n} missing={miss} bad={bad}")
            if miss or bad:
                fails.append(f"eval_family:{f.name}: missing={miss} bad={bad}")
        elif f.parent.name == "pool" and f.stem == "dev":
            n = flagged_bad = 0
            ef_benign = ef_challenge = ef_ood = 0
            flags_challenge = flags_ood = 0
            with open(f, encoding="utf-8-sig") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    n += 1
                    row = json.loads(line)
                    fl = row.get("flags") or {}
                    ef = ((row.get("meta") or {}).get("eval_family"))
                    if fl.get("challenge"):
                        flags_challenge += 1
                        if ef != "challenge":
                            flagged_bad += 1
                    if fl.get("ood"):
                        flags_ood += 1
                        if ef != "ood":
                            flagged_bad += 1
                    if ef == "benign":
                        ef_benign += 1
                    elif ef == "challenge":
                        ef_challenge += 1
                    elif ef == "ood":
                        ef_ood += 1
            ok = (flagged_bad == 0 and ef_challenge >= flags_challenge
                  and ef_ood >= flags_ood)
            print(f"  [{'PASS' if ok else 'FAIL'}] eval_family {f.relative_to(DM)}: "
                  f"rows={n} benign={ef_benign} challenge={ef_challenge} "
                  f"ood={ef_ood} flagged_mismatch={flagged_bad}")
            if not ok:
                fails.append(
                    f"eval_family:{f.name}: flagged_mismatch={flagged_bad} "
                    f"challenge={ef_challenge}/{flags_challenge} "
                    f"ood={ef_ood}/{flags_ood}")


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_manifest(per_file: dict, fails: list[str]) -> None:
    mp = DM / "manifest.json"
    if not mp.is_file():
        fails.append("manifest: data/m6/manifest.json not found")
        print("  [FAIL] manifest.json not found")
        return
    doc = json.loads(mp.read_text(encoding="utf-8-sig"))
    v = Draft202012Validator(
        json.loads((SD / "m6-manifest.schema.json").read_text(encoding="utf-8")),
        registry=REG)
    errs = sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path))
    print(f"  [{'PASS' if not errs else 'FAIL'}] manifest schema: "
          f"{len(errs)} violation(s)")
    for e in errs[:8]:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        fails.append(f"manifest schema {loc}: {e.message[:90]}")
        print(f"    - {loc}: {e.message[:110]}")
    # per-file cross-checks（视图文件免登记）
    by_path = {e["path"]: e for e in doc.get("files", [])}
    for rel, actual in per_file.items():
        if actual.get("view"):
            continue
        ent = by_path.get(rel)
        if ent is None:
            fails.append(f"manifest: file {rel} not registered")
            continue
        fp = DM / rel
        if "sha256" in ent:
            h = sha256_of(fp)
            if h != ent["sha256"]:
                fails.append(f"manifest: {rel} sha256 mismatch")
        n_actual = actual["n"]
        n_man = ent.get("n", ent.get("rows"))
        if n_man is not None and n_man != n_actual:
            fails.append(f"manifest: {rel} rows {n_man} != actual {n_actual}")
        lc = ent.get("label_counts")
        if lc:
            for t, d in lc.items():
                a = actual["label_counts"].get(t)
                if a and (a["pos"] != d.get("pos") or a["neg"] != d.get("neg")):
                    fails.append(
                        f"manifest: {rel} {t} label_counts "
                        f"({d.get('pos')}/{d.get('neg')}) != actual "
                        f"({a['pos']}/{a['neg']})")
    extra = set(by_path) - set(per_file)
    if extra:
        fails.append(f"manifest: registered but absent on disk: {sorted(extra)[:3]}")
    n_bad = sum(1 for f in fails if f.startswith("manifest"))
    print(f"  manifest cross-check: entries={len(by_path)} issues={n_bad}")


def main() -> int:
    ap = argparse.ArgumentParser(description="M6 H6 freeze audit")
    ap.add_argument("--skip-rows", action="store_true",
                    help="skip layer 1 (row contract full roll)")
    args = ap.parse_args()

    files = scan_files()
    print(f"H6 audit: {len(files)} files under data/m6 (final format)")
    fails: list[str] = []

    print("\n[1/4] row contracts (full roll)")
    if args.skip_rows:
        print("  (skipped)")
    else:
        audit_rows(files, fails)

    print("\n[2/4] label_counts + scale gates")
    per_file = audit_counts(files, fails)

    print("\n[3/4] eval_family coverage")
    audit_eval_family(files, fails)

    print("\n[4/4] manifest contract + cross-check")
    audit_manifest(per_file, fails)

    print(f"\nH6 audit: {'PASS' if not fails else f'FAIL ({len(fails)})'}")
    for m in fails[:20]:
        print(f"  - {m}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
