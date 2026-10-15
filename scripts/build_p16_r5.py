# build_p16_r5.py — F5-paired 生成器（父代理撰写；设计 v4 修订：8 骨架/金样本取消/render 双 conversations）
# 用法: python -X utf8 scripts\build_p16_r5.py   （cwd = 项目根）
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, r"scripts\_p16_r5_paired")
from f5_combos import combos  # noqa: E402
from f5_render import render_pair  # noqa: E402

ROOT = Path(".")
OUT = ROOT / "data" / "dpo" / "p16-calibration-r5"
PARTS = OUT / "parts-f5"
SEED = "20261015f5"


def main() -> int:
    rng = random.Random(SEED)
    cs = combos(rng)
    assert len(cs) == 1000, f"combos={len(cs)}"
    rows = []
    for idx, (sv, th, bi, mi) in enumerate(cs, 1):
        p = render_pair(sv, th, rng, idx, ben_idx=bi, mal_idx=mi)
        conv_b = p["conversations_benign"]
        conv_m = p["conversations_malicious"]
        rows.append({"id": f"{p['id']}-b", "conversations": conv_b,
                     "chosen": p["benign_pair"]["chosen"], "rejected": p["benign_pair"]["rejected"]})
        rows.append({"id": f"{p['id']}-m", "conversations": conv_m,
                     "chosen": p["malicious_pair"]["chosen"], "rejected": p["malicious_pair"]["rejected"]})
    # ---- fail-closed 断言 ----
    assert len(rows) == 2000, f"rows={len(rows)}"
    vocab = {"system", "human", "gpt"}
    prompts = set()
    for r in rows:
        for t in r["conversations"]:
            assert t["from"] in vocab, f"{r['id']} 非法角色 {t['from']}"
        assert r["conversations"][-1]["from"] == "human"
        prompts.add(json.dumps(r["conversations"], ensure_ascii=False, sort_keys=True))
        for side in ("chosen", "rejected"):
            assert r[side]["from"] == "gpt" and "VERDICT:" in r[side]["value"]
    assert len(prompts) == 2000, f"prompt 唯一数 {len(prompts)} != 2000"
    assert len({r["id"] for r in rows}) == 2000
    # 对结构：b/m 行前缀逐字节相同、末轮载荷不同
    for i in range(0, 2000, 2):
        cb, cm = rows[i]["conversations"], rows[i + 1]["conversations"]
        assert [t["value"] for t in cb[:-1]] == [t["value"] for t in cm[:-1]]
        assert cb[-1]["value"] != cm[-1]["value"]
    # ---- 分批落盘（pair 不跨批：100 对 = 200 行/批 × 10 批）----
    PARTS.mkdir(parents=True, exist_ok=True)
    manifest = {"files": {}, "seed": SEED,
                "design": "F5-paired v4（8 骨架 × 25 主题；render 双 conversations 最小对；金样本取消）",
                "batches": []}
    n_batch = 0
    for s in range(0, 2000, 200):
        batch = rows[s:s + 200]
        fp = PARTS / f"batch_{n_batch:02d}.jsonl"
        fp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in batch), encoding="utf-8")
        manifest["batches"].append({"file": fp.name, "pairs": 100})
        n_batch += 1
    full = OUT / "p16_f5_paired.jsonl"
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
    print("BUILD-P16-R5=OK")
    print(f"rows=2000 pairs=1000 batches={n_batch} prompt_unique=2000 roles={dict(roles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
