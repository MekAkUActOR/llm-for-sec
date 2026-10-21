# -*- coding: utf-8 -*-
"""M6 dev/chmirror 完整 emit（qa-m6 读数链入口）。

D 波后 dev 行集扩容（t* 视图 18,216 + pool 10,077）——v1-3/v2 读数统一走本脚本：
  dev     : t*/dev.jsonl（去重）∪ pool/dev.jsonl 多键合并 → <prefix>-dev-in/-labels
  chmirror: data/m6/_staging/challenge-mirror.jsonl → <prefix>-chmirror-in
用法：python -X utf8 scripts/m6_emit_dev.py --prefix v13 --data data/m6
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m6_acceptance import emit_batchlines, _pick_input  # noqa: E402

TASK_KEYS = ["T1", "T2", "T3", "T4", "T5", "T6"]


def _label_of(g) -> int:
    if isinstance(g, dict):
        g = g.get("label")
    return 1 if g in ("pos", 1, True) else 0


def collect(data_dir: Path):
    """返回 (rows: {id: row}, 顺序保持)。row: {id, labels{6}, ambiguous, payload}。"""
    rows: dict[str, dict] = {}
    order: list[str] = []

    def add(rid, labels, ambiguous, payload):
        if rid not in rows:
            rows[rid] = {"id": rid, "labels": {}, "ambiguous": ambiguous}
            order.append(rid)
        r = rows[rid]
        for t, v in labels.items():
            if t in TASK_KEYS and t not in r["labels"]:
                r["labels"][t] = v
        if "payload" not in r:
            r["payload"] = payload

    # 任务视图（金视图：单键权威）
    for tdir in sorted(data_dir.iterdir()):
        d = tdir / "dev.jsonl"
        if not (tdir.is_dir() and d.exists()):
            continue
        for line in d.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            lab = {}
            if r.get("labels"):
                for t, g in r["labels"].items():
                    if t in TASK_KEYS:
                        lab[t] = _label_of(g)
            add(r["id"], lab, bool((r.get("flags") or {}).get("ambiguous")),
                r.get("input") if isinstance(r.get("input"), dict) else r)
    # pool 多键联合视图（补充多键标签 + 独有行）
    pd = data_dir / "pool" / "dev.jsonl"
    if pd.exists():
        for line in pd.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            lab = {}
            if r.get("labels"):
                for t, g in r["labels"].items():
                    if t in TASK_KEYS:
                        lab[t] = _label_of(g)
            add(r["id"], lab, bool((r.get("flags") or {}).get("ambiguous")),
                r.get("input") if isinstance(r.get("input"), dict) else r)
    return rows, order


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="输出前缀（如 v13）→ <prefix>-dev-in.jsonl 等")
    ap.add_argument("--data", default="data/m6")
    ap.add_argument("--out-dir", default="reports/m6/preds")
    args = ap.parse_args()

    data_dir = Path(args.data)
    out = Path(args.out_dir)
    rows, order = collect(data_dir)

    in_rows, label_rows = [], []
    for rid in order:
        r = rows[rid]
        try:
            picked = _pick_input(r["payload"])
        except ValueError:
            continue
        o = {"id": rid}
        if "text" in picked:
            o["text"] = picked["text"]
        elif "turns" in picked:
            o["turns"] = picked["turns"]
        else:
            o["input"] = picked
        in_rows.append(o)
        label_rows.append({"id": rid, "labels": r["labels"], "ambiguous": r["ambiguous"]})

    dev_in = out / f"{args.prefix}-dev-in.jsonl"
    dev_lab = out / f"{args.prefix}-dev-labels.jsonl"
    (out / f"{args.prefix}-dev-in.tmp.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in in_rows) + "\n", encoding="utf-8")
    import shutil
    shutil.move(str(out / f"{args.prefix}-dev-in.tmp.jsonl"), str(dev_in))
    dev_lab.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in label_rows) + "\n", encoding="utf-8")
    print(f"dev emit: {len(in_rows)} 行 -> {dev_in.name} / {dev_lab.name}")

    from collections import Counter
    pos, neg = Counter(), Counter()
    for r in label_rows:
        for t, v in r["labels"].items():
            (pos if v else neg)[t] += 1
    print("dev pos:", dict(pos))
    print("dev neg:", dict(neg))

    # chmirror（_staging 优先，data 根次之）
    cm = data_dir / "_staging" / "challenge-mirror.jsonl"
    if not cm.exists():
        cm = data_dir / "challenge-mirror.jsonl"
    if cm.exists():
        cm_rows = []
        for line in cm.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            cm_rows.append({"id": r["id"], "text": r.get("text") or r.get("payload", {}).get("text", "")})
        n = emit_batchlines(cm_rows, out / f"{args.prefix}-chmirror-in.jsonl")
        print(f"chmirror emit: {n} 行 -> {args.prefix}-chmirror-in.jsonl")
    else:
        print("WARN: challenge-mirror 未找到")


if __name__ == "__main__":
    main()
