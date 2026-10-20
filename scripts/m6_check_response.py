# -*- coding: utf-8 -*-
"""M6 Response 契约校验器（sysdesign-m6）。

对 m6_infer.py 输出的 JSONL（每行一个 m6-inference Response）做三层检查：
  1. schema：每行过 m6-inference $defs/Response；
  2. 同源同值：verdict_line（单行 JSON 字符串）内 decision/abstain/abstain_reason/
     ood/tasks{flag,score,label}/pii.spans 与顶层同值（SYS-1 §3；D-11 回归锁）；
  3. 结构不变量：abstain ⇒ decision=pass ∧ 六 flag 全 false；decision vs flags
     一致；thresholds_applied 六带 + tau_ood + source。

用法：
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_check_response.py outputs/m6/xxx.jsonl
退出码：0=全过；1=有失败（fail-closed）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = pathlib.Path(__file__).resolve().parent.parent
SD = ROOT / "docs" / "m6" / "schemas"
TASKS = ("T1", "T2", "T3", "T4", "T5", "T6")

REG = Registry().with_resources(
    [(p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
     for p in SD.glob("*.schema.json")])
V = Draft202012Validator({"$ref": "m6-inference.schema.json#/$defs/Response"},
                         registry=REG)


def check_row(i: int, r: dict, fails: list[str]) -> None:
    rid = str(r.get("request_id", "?"))
    for e in V.iter_errors(r):
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        fails.append(f"row{i}({rid}) schema {loc}: {e.message[:100]}")
    vl_raw = r.get("verdict_line")
    if not isinstance(vl_raw, str):
        fails.append(f"row{i}({rid}) verdict_line missing/not string")
        return
    try:
        vl = json.loads(vl_raw)
    except json.JSONDecodeError as ex:
        fails.append(f"row{i}({rid}) verdict_line not JSON: {ex}")
        return
    for k in ("decision", "abstain", "abstain_reason", "ood"):
        if vl.get(k) != r.get(k):
            fails.append(f"row{i}({rid}) verdict_line.{k} drift")
    if not isinstance(vl.get("suppressed_any"), bool):
        fails.append(f"row{i}({rid}) suppressed_any not bool")
    for t in TASKS:
        vt, rt = (vl.get("tasks") or {}).get(t, {}), (r.get("tasks") or {}).get(t, {})
        for k in ("flag", "score", "label"):
            if vt.get(k) != rt.get(k):
                fails.append(f"row{i}({rid}) verdict_line.tasks.{t}.{k} drift")
    if (vl.get("pii") or {}).get("spans") != (r.get("tasks", {}).get("T4")
                                              or {}).get("spans", []):
        fails.append(f"row{i}({rid}) verdict_line.pii.spans drift")
    if r.get("abstain"):
        if r.get("decision") != "pass":
            fails.append(f"row{i}({rid}) abstain but decision!=pass")
        if any((r["tasks"][t] or {}).get("flag") for t in TASKS):
            fails.append(f"row{i}({rid}) abstain but some flag true")
    else:
        expect = "flag" if any((r["tasks"][t] or {}).get("flag") for t in TASKS) \
            else "pass"
        if r.get("decision") != expect:
            fails.append(f"row{i}({rid}) decision={r.get('decision')} vs flags={expect}")
    ta = r.get("thresholds_applied") or {}
    for t in TASKS:
        if t not in ta or not {"flag", "strong"} <= set(ta[t]):
            fails.append(f"row{i}({rid}) thresholds.{t} band missing")
            continue
        band = ta[t]
        if band["strong"] < band["flag"]:
            fails.append(f"row{i}({rid}) {t} band strong<flag (score space)")
        fl, sl = band.get("flag_logit"), band.get("strong_logit")
        if fl is not None and sl is not None and sl < fl:
            fails.append(f"row{i}({rid}) {t} band strong_logit<flag_logit")
        # logit 回显一致性：flag == sigma(flag_logit)（fp32 容差 1e-3——饱和
        # 区回显可为 1.0，容差覆盖；仅双方存在时校验）
        if fl is not None and abs(1.0 / (1.0 + 2.718281828459045 ** (-fl))
                                  - band["flag"]) > 1e-3:
            fails.append(f"row{i}({rid}) {t} flag != sigmoid(flag_logit)")
        if sl is not None and abs(1.0 / (1.0 + 2.718281828459045 ** (-sl))
                                  - band["strong"]) > 1e-3:
            fails.append(f"row{i}({rid}) {t} strong != sigmoid(strong_logit)")
    if "tau_ood" not in ta or "source" not in ta:
        fails.append(f"row{i}({rid}) thresholds tau_ood/source missing")


def main() -> int:
    ap = argparse.ArgumentParser(description="M6 Response contract validator")
    ap.add_argument("paths", nargs="+", help="response JSONL file(s)")
    ap.add_argument("--limit", type=int, default=0, help="per-file row cap (0=all)")
    args = ap.parse_args()

    total = bad = 0
    for p in args.paths:
        pp = pathlib.Path(p)
        if not pp.is_file():
            print(f"[SKIP] {pp} (not found)")
            continue
        n = 0
        fails = []
        with open(pp, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n += 1
                if args.limit and n > args.limit:
                    break
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as ex:
                    fails.append(f"row{n} not JSON: {ex}")
                    continue
                check_row(n, r, fails)
        total += n
        bad += len(fails)
        status = "PASS" if not fails else "FAIL"
        print(f"[{status}] {pp}: rows={n} issues={len(fails)}")
        for m in fails[:10]:
            print(f"    - {m}")
    print(f"\nresponse checks: rows={total} issues={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
