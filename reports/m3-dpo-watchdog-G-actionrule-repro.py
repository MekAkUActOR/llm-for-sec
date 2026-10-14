# -*- coding: utf-8 -*-
"""M3 DPO watchdog G: 证明 score_heldout_v2.py 的默认路径逐位可复现。

对每个已有 resp-chat-to-<tag>.jsonl：
  * 用**默认** action_rule 重跑 CLI 到 $TEMP，与既有 reports/scored-chat-to-<tag>-v2.json
    做**逐字节**比较（这是"未破坏可复现性"的唯一可信证据）；
  * 再用显式 --action-rule selfreport 跑一次，确认与默认等价；
  * 顺带统计 strict 口径相对 selfreport 的标签变动条目（只读，不写产物）。
纯 CPU、只读既有产物，只往 $TEMP 写临时文件。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT / "scripts"))
import score_heldout_v2 as S  # noqa: E402

TOUT = ROOT / "data" / "heldout" / "v0.4-toolout"
R = ROOT / "reports"
OUT = R / "m3-dpo-watchdog-actionrule-repro.json"

TAGS = [p.name[len("resp-chat-to-"):-len(".jsonl")].strip()
        for p in sorted(R.glob("resp-chat-to-*.jsonl"))]


def run(tag: str, rule: str, dest: Path) -> int:
    argv = ["--heldout", str(TOUT),
            "--responses", str(R / f"resp-chat-to-{tag}.jsonl"),
            "--out", str(dest)]
    if rule != S.DEFAULT_ACTION_RULE:
        argv += ["--action-rule", rule]
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old = sys.stdout
        sys.stdout = devnull
        try:
            rc = S.main(argv)
        finally:
            sys.stdout = old
    return rc


def first_diff(a: bytes, b: bytes) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def main() -> int:
    tmp = Path(tempfile.gettempdir()) / "wd-actionrule-repro"
    tmp.mkdir(parents=True, exist_ok=True)
    res = {"tags": {}, "modules": {}}
    print(f"{'tag':14} {'ref_bytes':>10} {'default==ref':>13} "
          f"{'explicit==ref':>13} {'strict!=default(items)':>22}")
    for tag in TAGS:
        ref = R / f"scored-chat-to-{tag}-v2.json"
        if not ref.exists():
            res["tags"][tag] = {"error": "no reference scored file"}
            print(f"{tag:14} {'-':>10} {'(no ref)':>13}")
            continue
        d1 = tmp / f"default-{tag}.json"
        d2 = tmp / f"explicit-{tag}.json"
        rc1 = run(tag, S.DEFAULT_ACTION_RULE, d1)
        rc2 = run(tag, "selfreport", d2)
        a, b, c = ref.read_bytes(), d1.read_bytes(), d2.read_bytes()
        # strict 口径的标签变动（不落盘）
        doc_d = json.loads(a.decode("utf-8"))
        resp = {}
        for line in (R / f"resp-chat-to-{tag}.jsonl").read_text(
                encoding="utf-8-sig").splitlines():
            if line.strip():
                o = json.loads(line)
                resp[o["id"]] = o.get("text", "")
        changed = []
        for it in doc_d.get("items") or []:
            t = resp.get(it["id"])
            if t is None:
                continue
            ls = S.classify(t, "strict")["label"]
            if ls != it["label"]:
                changed.append({"id": it["id"], "kind": it["kind"],
                                "selfreport": it["label"], "strict": ls,
                                "note": S.classify(t, "strict")["note"]})
        rob_changed = [x for x in changed if x["kind"] == "robustness"]
        res["tags"][tag] = {
            "rc_default": rc1, "rc_explicit": rc2,
            "ref_bytes": len(a), "default_bytes": len(b),
            "identical_default": a == b,
            "identical_explicit": a == c,
            "first_diff_offset": (None if a == b else first_diff(a, b)),
            "n_items_changed_strict": len(changed),
            "n_rob_changed_strict": len(rob_changed),
            "changed_strict": changed,
        }
        print(f"{tag:14} {len(a):>10} {str(a == b):>13} {str(a == c):>13} "
              f"{len(changed):>8} / rob {len(rob_changed):>2}")

    import score_heldout_v2 as _s
    res["modules"] = {
        "ACTION_RULES": list(_s.ACTION_RULES),
        "DEFAULT_ACTION_RULE": _s.DEFAULT_ACTION_RULE,
        "all_default_identical": all(
            v.get("identical_default") for v in res["tags"].values()),
        "all_explicit_identical": all(
            v.get("identical_explicit") for v in res["tags"].values()),
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print("all_default_identical  =", res["modules"]["all_default_identical"])
    print("all_explicit_identical =", res["modules"]["all_explicit_identical"])
    print("WROTE", OUT)
    return 0 if res["modules"]["all_default_identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
