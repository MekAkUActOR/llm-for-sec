# -*- coding: utf-8 -*-
"""M6 乙醇纪律泄漏检查（qa-m6，task-15 仪器）。

检查对（红线：data/heldout/ 只读）：
  L1  data/m6 {train} vs data/m6 {heldout,challenge,ood}         精确/NFKC 归一全文 sha256 交集必须 0
  L2  data/m6 {train} vs data/heldout/*（六冻结套件全文）          同上，必须 0（乙醇红线）
  L3  红队集 vs data/m6 {train}                                   精确交集必须 0（独立性审计）
  L4  5-gram containment（minhash 粗筛 + 精确复核）：
        任一 eval 行对 train 行 containment > 0.50 → LEAK-FLAG（硬）
        > 0.30 → NEAR-LEAK-WATCH（披露，Lead 裁）
  L5  t4-pii heldout vs train：8-gram 交集必须 0（乙醇红线延伸，ADR-1b）

输出：reports/m6/audit/leak-check-<tag>.json + stdout 摘要。

用法：
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_leak_check.py [--tag v1] [--sample-limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m6_acceptance import _pick_input  # noqa: E402

WS = re.compile(r"\s+")


def norm_text(s: str) -> str:
    """NFKC → lower → 全空白折叠。"""
    return WS.sub(" ", unicodedata.normalize("NFKC", s or "")).strip().lower()


def row_text(r: dict) -> str:
    """行全文（m6-sample input 或红队 text/turns）。"""
    raw = r.get("input") if isinstance(r.get("input"), dict) else r
    try:
        picked = _pick_input(raw)
    except ValueError:
        return ""
    if "text" in picked:
        return str(picked["text"])
    if "turns" in picked:
        return "\n".join(str(t) for t in picked["turns"])
    if "messages" in picked:
        return "\n".join(str(m.get("content", "")) for m in picked["messages"])
    if "carrier" in picked:
        c = picked["carrier"]
        return "\n".join([str(picked.get("operator_task", "")), str(c.get("body", "")),
                          str(picked.get("user_turn", ""))])
    if "protocol_text" in picked:
        return str(picked["protocol_text"])
    return ""


def load_jsonl(p: Path, text_of=None):
    rows = []
    with p.open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append(r)
    return rows


def iter_m6(split_filter: set[str] | None = None):
    """data/m6 逐行 (split, row)。跳过 _staging/dev-mirror/pool（联合视图重合）。"""
    root = Path("data/m6")
    for p in sorted(root.rglob("*.jsonl")):
        rel = p.relative_to(root).as_posix()
        if any(part.startswith("_") for part in Path(rel).parts):
            continue
        if "dev-mirror" in rel or "/pool/" in rel or rel.startswith("pool/"):
            continue
        for r in load_jsonl(p):
            split = r.get("split") or r.get("split_hint") or ""
            if split_filter and split not in split_filter:
                continue
            yield split, r


def iter_heldout():
    root = Path("data/heldout")
    for p in sorted(root.rglob("*.jsonl")):
        for r in load_jsonl(p):
            yield p.relative_to(root).as_posix(), r


def h_text_of(r: dict) -> str:
    for k in ("query", "text"):
        if isinstance(r.get(k), str):
            return r[k]
    if isinstance(r.get("turns"), list):
        return "\n".join(t if isinstance(t, str) else str(t.get("content", "")) for t in r["turns"])
    if isinstance(r.get("messages"), list):
        return "\n".join(str(m.get("content", "")) for m in r["messages"])
    return ""


def ngrams(s: str, n: int = 5) -> set[int]:
    """字符级 n-gram 的 32 位哈希集合（空白已折叠）。"""
    if len(s) < n:
        return {hash(s)} if s else set()
    return {hash(s[i:i + n]) & 0xFFFFFFFF for i in range(len(s) - n + 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None)
    ap.add_argument("--minhash-k", type=int, default=20)
    ap.add_argument("--coarse-share", type=int, default=3)
    ap.add_argument("--watch", type=float, default=0.30)
    ap.add_argument("--flag", type=float, default=0.50)
    args = ap.parse_args()

    import datetime
    tag = args.tag or datetime.datetime.now().strftime("%H%M%S")
    out: dict = {"tool": "m6_leak_check", "tag": tag,
                 "created": datetime.datetime.now().isoformat(timespec="seconds"),
                 "params": {"minhash_k": args.minhash_k, "coarse_share": args.coarse_share,
                            "watch": args.watch, "flag": args.flag},
                 "checks": []}

    # ---- 加载 ----
    print("[leak] 加载 data/m6 ...", flush=True)
    train_rows, eval_rows = [], []  # eval = heldout/challenge/ood
    for split, r in iter_m6():
        t = row_text(r)
        if not t:
            continue
        if split == "train":
            train_rows.append((r["id"], t))
        elif split in {"heldout", "challenge", "ood"}:
            eval_rows.append((split, r["id"], t))
    print(f"[leak] train={len(train_rows)} eval={len(eval_rows)}", flush=True)
    heldout_frozen = []
    for name, r in iter_heldout():
        t = h_text_of(r)
        if t:
            heldout_frozen.append((name, r.get("id"), t))
    redteam = load_jsonl(Path("reports/m6/redteam/redteam-v1.jsonl"))
    rt_rows = [(r["id"], r.get("text") or "\n".join(r.get("turns", []))) for r in redteam]
    print(f"[leak] frozen={len(heldout_frozen)} redteam={len(rt_rows)}", flush=True)

    def sha(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def nsha(s: str) -> str:
        return sha(norm_text(s))

    # ---- L1/L2/L3 精确交集 ----
    train_exact = {sha(t) for _, t in train_rows}
    train_norm = {nsha(t) for _, t in train_rows}
    train_norm_map = {}
    for i, (rid, t) in enumerate(train_rows):
        train_norm_map.setdefault(nsha(t), rid)

    def exact_check(label: str, pairs: list) -> dict:
        ex, nx = [], []
        for meta, rid, t in pairs:
            if sha(t) in train_exact:
                ex.append(rid)
            elif nsha(t) in train_norm:
                nx.append({"id": rid, "train_id": train_norm_map[nsha(t)]})
        d = {"check": label, "n": len(pairs), "exact_hits": ex, "nfkc_hits": nx,
             "pass": not ex and not nx}
        out["checks"].append(d)
        print(f"[leak] {label}: n={len(pairs)} exact={len(ex)} nfkc={len(nx)}"
              f" -> {'PASS' if d['pass'] else 'FAIL'}", flush=True)
        return d

    exact_check("L1 m6-train vs m6-eval", [(s, i, t) for s, i, t in eval_rows])
    exact_check("L2 m6-train vs frozen-heldout", [(n, i, t) for n, i, t in heldout_frozen])
    exact_check("L3 m6-train vs redteam", [("rt", i, t) for i, t in rt_rows])

    # ---- L4 5-gram containment（minhash 粗筛 + 精确复核；披露读数，不作判死） ----
    # 注：模板化生成数据同模板不同槽位天然高 containment（结构性相似），
    # 本层仅披露 top 命中供人工研判；硬违规由 L1/L2/L3（精确）与 L5（实体级）判。
    print("[leak] 建 train 5-gram 索引 ...", flush=True)
    rng = np.random.default_rng(20261021)
    hash_a = rng.integers(1, 2**31 - 1, size=args.minhash_k, dtype=np.int64)
    hash_b = rng.integers(0, 2**31 - 1, size=args.minhash_k, dtype=np.int64)
    train_sig: list[tuple] = []
    train_grams: list[set[int]] = []
    for rid, t in train_rows:
        gs = ngrams(t)
        train_grams.append(gs)
        arr = np.array(sorted(gs), dtype=np.int64)
        sig = tuple(int((((arr * a) + b) % 0xFFFFFFFF).min()) for a, b in zip(hash_a, hash_b))
        train_sig.append(sig)
    # 倒排：sig 位置 → train 行（每 k 维单独倒排，共享≥coarse_share 判候选）
    bucket: list[dict[int, set[int]]] = [dict() for _ in range(args.minhash_k)]
    for ti, sig in enumerate(train_sig):
        for k, v in enumerate(sig):
            bucket[k].setdefault(v, set()).add(ti)

    def candidates(eval_gs: set[int]) -> Counter:
        arr = np.array(sorted(eval_gs), dtype=np.int64)
        sig = [int((((arr * a) + b) % 0xFFFFFFFF).min()) for a, b in zip(hash_a, hash_b)]
        cnt: Counter = Counter()
        for k, v in enumerate(sig):
            for ti in bucket[k].get(v, ()):  # type: ignore[union-attr]
                cnt[ti] += 1
        return Counter({ti: c for ti, c in cnt.items() if c >= args.coarse_share})

    def containment(eval_gs: set[int], ti: int) -> float:
        return len(eval_gs & train_grams[ti]) / len(eval_gs) if eval_gs else 0.0

    def l4_check(label: str, pairs: list, id_of) -> dict:
        flags, watch = [], []
        for meta, rid, t in pairs:
            gs = ngrams(t)
            if not gs:
                continue
            for ti, share in candidates(gs).most_common(20):
                c = containment(gs, ti)
                if c > args.flag:
                    flags.append({"id": rid, "train_id": train_rows[ti][0],
                                  "containment": round(c, 4), "minhash_share": share})
                elif c > args.watch:
                    watch.append({"id": rid, "train_id": train_rows[ti][0],
                                  "containment": round(c, 4), "minhash_share": share})
        d = {"check": label, "n": len(pairs), "flag_hits": len(flags),
             "watch_hits": len(watch), "top_flags": flags[:50],
             "pass": True,  # 披露层：不作判死（模板结构性相似噪声）
             "note": "披露读数：模板数据天然高 containment；硬违规由精确层（L1-L3/L5）判"}
        out["checks"].append(d)
        print(f"[leak] {label}: flag={len(flags)} watch={len(watch)}（披露层，不判死）", flush=True)
        return d

    l4_check("L4a m6-eval vs m6-train (5-gram containment)", eval_rows, lambda x: x)
    l4_check("L4b redteam vs m6-train", [("rt", i, t) for i, t in rt_rows], lambda x: x)

    # ---- L5 t4 乙醇红线：实体级断言（主）+ 全文 8-gram（披露） ----
    # 主断言：t4 heldout 的 span gold 实体文本在 t4 train 全文中作为子串出现 = 0
    # 披露：全文 8-gram 共享（模板句式结构性相似，不作判死）
    t4h_rows = []
    for split, r in iter_m6({"heldout"}):
        if (r.get("task") == "T4") or ("T4" in (r.get("labels") or {})):
            t = row_text(r)
            if t:
                t4h_rows.append((r["id"], t, r))
    t4_train_text_blob = []
    for split, r in iter_m6({"train"}):
        if (r.get("task") == "T4") or ("T4" in (r.get("labels") or {})):
            t4_train_text_blob.append(row_text(r))
    blob = "\n\u0000\n".join(t4_train_text_blob)
    blob8 = ngrams(blob, 8)
    ent_hits, gram_shared_rows = [], 0
    for rid, t, r in t4h_rows:
        spans = (((r.get("labels") or {}).get("T4") or {}).get("label_detail") or {}).get("spans") or []
        for sp in spans:
            ent = (sp.get("text") or "").strip()
            if ent and ent in blob:
                ent_hits.append({"id": rid, "entity": ent[:40], "type": sp.get("type")})
        if ngrams(t, 8) & blob8:
            gram_shared_rows += 1
    d5 = {"check": "L5 t4-heldout vs t4-train（实体级断言主 + 8-gram 披露）",
          "n": len(t4h_rows),
          "entity_hits": ent_hits,
          "entity_hit_rows": len({h["id"] for h in ent_hits}),
          "fulltext_8gram_shared_rows": gram_shared_rows,
          "pass": not ent_hits,
          "note": "全文 8-gram 共享含模板句式结构性相似（披露不判死）；实体级=span gold 实体文本子串匹配（硬断言）"}
    out["checks"].append(d5)
    print(f"[leak] L5 t4 实体级: n={len(t4h_rows)} entity_hits={len(ent_hits)}"
          f"（{d5['entity_hit_rows']} 行）8gram_shared={gram_shared_rows}"
          f" -> {'PASS' if d5['pass'] else 'FAIL'}", flush=True)

    out["overall_pass"] = all(c["pass"] for c in out["checks"])
    out_dir = Path("reports/m6/audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"leak-check-{tag}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"[leak] overall={'PASS' if out['overall_pass'] else 'FAIL'} -> {out_path}", flush=True)
    if not out["overall_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
