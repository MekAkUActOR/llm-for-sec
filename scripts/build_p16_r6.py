# build_p16_r6.py — round-6 生成器（父代理撰写；r6-build-brief；r5 driver 适配 + amb 分支）
# 用法: python -X utf8 scripts\build_p16_r6.py   （cwd = 项目根）
# 构成：2,400 bm 对（4,800 行，2×2 镜像）+ 600 amb 对（1,200 行，悬置 chosen 正样本）= 6,000 行
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, r"scripts\_p16_r5_paired")
from f6_combos import bm_combos, amb_combos  # noqa: E402
from f5_render import render_pair  # noqa: E402
from f6_render import render_amb  # noqa: E402

ROOT = Path(".")
OUT = ROOT / "data" / "dpo" / "p16-calibration-r6"
PARTS = OUT / "parts-r6"
SEED = "20261015r6"


def main() -> int:
    rng = random.Random(SEED)
    bm = bm_combos(rng, 2400)
    amb = amb_combos(rng, 600)
    assert len(bm) == 2400 and len(amb) == 600
    rows = []
    for idx, (sv, th, bi, mi) in enumerate(bm, 1):
        p = render_pair(sv, th, rng, idx, ben_idx=bi, mal_idx=mi)
        cb, cm = p["conversations_benign"], p["conversations_malicious"]
        rows.append({"id": f"{p['id']}-b", "conversations": cb,
                     "chosen": p["benign_pair"]["chosen"], "rejected": p["benign_pair"]["rejected"]})
        rows.append({"id": f"{p['id']}-m", "conversations": cm,
                     "chosen": p["malicious_pair"]["chosen"], "rejected": p["malicious_pair"]["rejected"]})
    n_bm = len(rows)
    for jdx, (sv, th, ar, ad) in enumerate(amb, 1):
        p = render_amb(sv, th, rng, jdx, ar, ad)
        rows.append({"id": f"{p['id']}-r", "conversations": p["conv_ref"],
                     "chosen": p["chosen"], "rejected": p["rejected_ref"]})
        rows.append({"id": f"{p['id']}-d", "conversations": p["conv_del"],
                     "chosen": p["chosen"], "rejected": p["rejected_del"]})
    # ---- fail-closed 断言 ----
    assert len(rows) == 6000, f"rows={len(rows)}"
    vocab = {"system", "human", "gpt"}
    prompts = set()
    for r in rows:
        for t in r["conversations"]:
            assert t["from"] in vocab, f"{r['id']} 非法角色 {t['from']}"
        assert r["conversations"][-1]["from"] == "human"
        prompts.add(json.dumps(r["conversations"], ensure_ascii=False, sort_keys=True))
        for side in ("chosen", "rejected"):
            assert r[side]["from"] == "gpt" and "VERDICT:" in r[side]["value"]
    assert len(prompts) == 6000, f"prompt 唯一数 {len(prompts)} != 6000"
    assert len({r["id"] for r in rows}) == 6000
    for i in range(0, n_bm, 2):  # bm 对结构
        cb, cm = rows[i]["conversations"], rows[i + 1]["conversations"]
        assert [t["value"] for t in cb[:-1]] == [t["value"] for t in cm[:-1]]
        assert cb[-1]["value"] != cm[-1]["value"]
    for i in range(n_bm, 6000, 2):  # amb 对结构：前缀逐字节同 + 悬置 chosen + 双 VERDICT 方向
        ra, rb = rows[i], rows[i + 1]
        assert [t["value"] for t in ra["conversations"][:-1]] == [t["value"] for t in rb["conversations"][:-1]]
        assert ra["conversations"][-1]["value"] != rb["conversations"][-1]["value"]
        assert '"deflect"' in ra["chosen"]["value"] and '"deflect"' in rb["chosen"]["value"]
    # ---- 分批落盘（300 对 = 600 行/批 × 10 批，对不跨批）----
    PARTS.mkdir(parents=True, exist_ok=True)
    manifest = {"files": {}, "seed": SEED,
                "design": "round-6 F5 扩容（bm 2400 对 2x2 镜像 + amb 600 对悬置 chosen 正样本；brief v2）",
                "batches": []}
    n_batch = 0
    for s in range(0, 6000, 600):
        batch = rows[s:s + 600]
        fp = PARTS / f"batch_{n_batch:02d}.jsonl"
        fp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in batch), encoding="utf-8")
        manifest["batches"].append({"file": fp.name, "pairs": 300})
        n_batch += 1
    full = OUT / "p16_r6_paired.jsonl"
    full.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    import hashlib
    for f in [full, *sorted(PARTS.glob("*.jsonl"))]:
        h = hashlib.sha256()
        h.update(f.read_bytes())
        manifest["files"][str(f.relative_to(OUT))] = {"sha256": h.hexdigest()[:16],
                                                      "lines": sum(1 for _ in f.open(encoding="utf-8"))}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    roles = Counter(t["from"] for r in rows for t in r["conversations"])
    n_amb_rows = 6000 - n_bm
    print("BUILD-P16-R6=OK")
    print(f"rows=6000 bm_pairs=2400({n_bm} rows) amb_pairs=600({n_amb_rows} rows) "
          f"batches={n_batch} prompt_unique=6000 roles={dict(roles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
