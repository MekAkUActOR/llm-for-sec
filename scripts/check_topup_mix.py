# -*- coding: utf-8 -*-
"""C 路定向补齐混料的独立校验（训练输入 ⇒ 必须与验收判据集零泄漏）。

为什么单独写：`scripts/check_m25_staging.py` 只认 `data/sft/m2.5-staging/` 下的文件，
而 C 路补齐把三族**合成了一个新的训练文件** `data/lf/sec_sft_topup.jsonl`。
验收判据（v0.3-gen 未见载体门禁）必须与该训练输入不相交，否则"泛化"读数被污染。
本脚本复用官方检查器的 8-gram 机制（不重写检测逻辑），只换输入。

用法：python scripts/check_topup_mix.py [--mix data/lf/sec_sft_topup.jsonl]
退出码：0 = 通过；1 = 有错误。
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_m25_staging as C  # noqa: E402  复用官方 8-gram/规范化实现

EXPECT_PACKS = {"conservative", "default", "professional"}
EXPECT_ROWS = 3300
ALLOWED_KEYS = {"id", "task", "pack", "lang", "messages",
                "source", "group", "meta", "notes"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default="data/lf/sec_sft_topup.jsonl")
    ap.add_argument("--expect-rows", type=int, default=EXPECT_ROWS)
    a = ap.parse_args()
    mix = ROOT / a.mix
    if not mix.exists():
        print(f"[topup-check] 缺文件：{mix}", file=sys.stderr)
        return 1

    rows, errors = [], []
    ids, seen_hash = set(), set()
    packs, langs, tasks = collections.Counter(), collections.Counter(), collections.Counter()
    for i, line in enumerate(mix.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append((i, r))

    for i, r in rows:
        extra = set(r.keys()) - ALLOWED_KEYS
        if extra:
            errors.append(f"row {i}: 未预期键 {sorted(extra)}")
        rid = r.get("id")
        if not rid:
            errors.append(f"row {i}: 缺 id")
        elif rid in ids:
            errors.append(f"row {i}: id 重复 {rid}")
        ids.add(rid)
        pk = str(r.get("pack"))
        if pk not in EXPECT_PACKS:
            errors.append(f"row {i}: pack 非法 {pk!r}")
        packs[pk] += 1
        langs[str(r.get("lang"))] += 1
        tasks[str(r.get("task")).split(":")[0]] += 1
        msgs = r.get("messages") or []
        if not msgs or msgs[0].get("role") != "system":
            errors.append(f"row {i}: 首条非 system（政策 system 区缺失）")
        asst = [m for m in msgs if m.get("role") == "assistant"]
        if not asst:
            errors.append(f"row {i}: 无 assistant 消息")
        elif "VERDICT: " not in (asst[-1].get("content") or ""):
            errors.append(f"row {i}: 末条 assistant 无 VERDICT（输出契约破坏）")

    # 结构/语言/包唯一性（官方函数）
    C.check_structure_lang_uniqueness(rows, "sec_sft_topup", errors)

    # 内容级 (pack,user) 唯一
    for i, r in rows:
        msgs = r.get("messages") or []
        u = "\x00".join((m.get("content") or "") for m in msgs if m.get("role") == "user")
        k = C.normalize(str(r.get("pack")) + "\x00" + u)
        if k in seen_hash:
            errors.append(f"row {i}: (pack,user) 内容重复")
        seen_hash.add(k)

    if len(rows) != a.expect_rows:
        errors.append(f"行数 {len(rows)} != 预期 {a.expect_rows}")

    # 8-gram 污染：探针 + heldout（**含 v0.3-gen**）
    probes, ais_titles, queries = C.load_baseline()
    print(f"[topup-check] 基线：probes {len(probes)} / ais {len(ais_titles)} / "
          f"heldout queries {len(queries)}")
    report = {"baseline": {"probes_unique": len(probes),
                           "ais_titles": len(ais_titles),
                           "queries": len(queries)}}
    n_flag = C.check_contamination({"sec_sft_topup": rows}, report)
    if n_flag:
        errors.append(f"污染命中 {n_flag} 行（见 report.contamination）")

    # v0.3-gen 专项：验收判据集必须与训练输入零重叠
    gen_dir = ROOT / "data" / "heldout" / "v0.3-gen"
    gen_q = set()
    for f in sorted(gen_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                if j.get("query"):
                    gen_q.add(C.normalize(j["query"]))
    hit_gen = [i for i, r in rows
               if C.normalize("".join((m.get("content") or "")
                                      for m in (r.get("messages") or []))) in gen_q]
    if hit_gen:
        errors.append(f"与 v0.3-gen 验收集完全同文 {len(hit_gen)} 行：{hit_gen[:5]}")
    report["v03_gen_exact_overlap"] = len(hit_gen)

    out = {"mix": str(mix.relative_to(ROOT)), "rows": len(rows),
           "packs": dict(packs), "langs": dict(langs), "task_families": dict(tasks),
           "errors": errors, "verdict": "PASS" if not errors else "FAIL",
           "baseline": report.get("baseline"),
           "contamination": report.get("contamination"),
           "v03_gen_exact_overlap": report["v03_gen_exact_overlap"]}
    (ROOT / "reports" / "topup-mix-check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[topup-check] rows={len(rows)} packs={dict(packs)} langs={dict(langs)}")
    print(f"[topup-check] task_families={dict(tasks)}")
    if errors:
        print(f"[topup-check] FAIL ({len(errors)} errors)")
        for e in errors[:20]:
            print("   -", e)
        return 1
    print("[topup-check] PASS：与探针/heldout（含 v0.3-gen）零泄漏")
    print("-> reports/topup-mix-check.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
