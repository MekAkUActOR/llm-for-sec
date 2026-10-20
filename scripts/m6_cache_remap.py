# -*- coding: utf-8 -*-
"""feat_cache remap for v1-2 (post hot-fix re-shuffle).

The reserve-cval fix re-shuffled splits; row ids largely survive but moved
between train/dev. Pooled features are content-keyed (label-independent), so
old caches (train+dev union) can serve most rows. This script:

  1. reads CURRENT rows via manifest (v1-2 data),
  2. builds new feats_{train,dev}.npz by id lookup across BOTH old caches,
  3. extracts the missing rows through the backbone (GPU, minutes),
  4. re-extracts a verification SAMPLE of "reused" ids and asserts fp16
     agreement (measurement, not assumption -- ethanol discipline),
  5. remaps tokfeats (PII rows) the same way.

Usage:
  python scripts/m6_cache_remap.py --config configs/m6-v1-2.yaml \
      --old-cache checkpoints/m6-v1/feat_cache [--device cuda] [--verify-frac 0.02]
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from m6_feat_probe import forward_extract, load_backbone  # noqa: E402
from m6_render import (normalize_input, render, spans_to_bio,  # noqa: E402
                       tokenize_windowed)
from m6_train import (_pad_batch, derive_labels, load_config,  # noqa: E402
                      rows_for_split)


def remap_split(split, rows, old, out_dir, cfg, backbone, tok, device,
                verify_frac):
    t0 = time.time()
    # rows may have moved across splits in the hot-fix re-shuffle: index
    # every cache file of BOTH splits by id
    pool_by_id = {}
    for src in old:
        for sp in ("train", "dev"):
            p = src / f"feats_{sp}.npz"
            if not p.is_file():
                continue
            z = np.load(p, allow_pickle=True)
            for i, rid in enumerate(z["ids"]):
                pool_by_id.setdefault(str(rid), (z, i))

    D = None
    N = len(rows)
    Y, t6c, neg_all, mirror, pii_idx, pii_spans = derive_labels(rows)
    layers = cfg["probe"]["tapped_layers"]
    tok_layers = cfg["probe"].get("token_layers", [12, 28])
    in_dim = len(layers) * backbone.config.hidden_size * 2

    reused = [i for i, r in enumerate(rows) if r["id"] in pool_by_id]
    missing = [i for i, r in enumerate(rows) if r["id"] not in pool_by_id]
    print(f"[remap:{split}] rows={N} reused={len(reused)} "
          f"missing(extract)={len(missing)}")

    pooled = np.zeros((N, in_dim), dtype=np.float16)
    trunc = np.zeros(N, dtype=bool)
    for i in reused:
        z, j = pool_by_id[rows[i]["id"]]
        pooled[i] = z["pooled"][j]
        trunc[i] = bool(z["trunc"][j])

    # ---- extract missing rows (+ verification sample) ----
    # verification compares fresh extraction against cached features; the
    # smoke fixture measured bf16 CPU-vs-GPU divergence at max|diff|~4 on
    # outlier dims (mean 0.028) -- cross-device verification is INVALID,
    # so it is fail-closed: cache-origin device must match.
    if verify_frac > 0 and not device.startswith("cuda"):
        raise SystemExit(
            "--verify-frac > 0 requires --device cuda: cached features are "
            "GPU-extracted and bf16 CPU extraction diverges on outlier dims "
            "(measured max|diff|~4). Use GPU, or --verify-frac 0 for a "
            "mechanics-only run.")
    rng = np.random.default_rng(7)
    n_verify = int(len(reused) * verify_frac)
    verify_ids = rng.choice(reused, size=n_verify, replace=False).tolist() \
        if n_verify else []
    todo = sorted(missing + verify_ids)
    if todo:
        if device.startswith("cuda"):
            print(f"[remap] GPU check (cuda={torch.cuda.is_available()})")
        infos = {}
        for i in todo:
            inp = normalize_input(rows[i])
            rendered, msg_spans, fmap = render(tok, inp)
            infos[i] = tokenize_windowed(tok, rendered)
        pad_id = tok.pad_token_id or 151643
        pos = 0
        while pos < len(todo):
            chunk = todo[pos:pos + 16]
            ids, attn = _pad_batch([infos[i]["input_ids"] for i in chunk],
                                   pad_id, device)
            f, _ = forward_extract(backbone, ids, attn, layers, "mean+last",
                                   tok_layers)
            for k, i in enumerate(chunk):
                pooled[i] = f[k].numpy().astype(np.float16)
                trunc[i] = infos[i]["truncation"]
            pos += len(chunk)
        # verification: reused-cache value vs fresh extraction must agree
        bad = 0
        for i in verify_ids:
            z, j = pool_by_id[rows[i]["id"]]
            a, b = pooled[i].astype(np.float32), z["pooled"][j].astype(np.float32)
            if not np.allclose(a, b, atol=2e-2, rtol=0):
                bad += 1
        assert bad == 0, (
            f"{split}: {bad}/{len(verify_ids)} verification rows disagree "
            f"with cache -- content drifted for reused ids, full re-extract "
            f"required")
        print(f"[remap:{split}] verification sample {len(verify_ids)} rows: "
              f"all agree (atol 2e-2)")

    cache = out_dir / "feat_cache"
    cache.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache / f"feats_{split}.npz",
        pooled=pooled, ids=np.array([r["id"] for r in rows]),
        Y=Y, t6c=t6c, neg_all=neg_all, mirror=mirror, trunc=trunc,
        layers=np.array(layers), pooling=np.array("mean+last"))
    print(f"[remap:{split}] wrote {cache / f'feats_{split}.npz'} "
          f"({time.time() - t0:.0f}s)")
    return pooled


def remap_tokfeats(split, rows, old, out_dir, cfg, backbone, tok, device):
    """PII token-feature cache remap (rows keyed by id)."""
    old_by_id = {}
    for src in old:
        for sp in ("train", "dev"):
            p = src / f"tokfeats_{sp}.npz"
            if not p.is_file():
                continue
            z = np.load(p, allow_pickle=True)
            offs = np.concatenate([[0], np.cumsum(z["lens"])])
            for i, rid in enumerate(z["ids"]):
                old_by_id.setdefault(str(rid), (z, int(offs[i]),
                                                int(offs[i + 1])))
    Y, t6c, neg_all, mirror, pii_idx, pii_spans = derive_labels(rows)
    pii_pos = {int(i): k for k, i in enumerate(pii_idx)}
    hits = [i for i in pii_idx if rows[i]["id"] in old_by_id]
    miss = [i for i in pii_idx if rows[i]["id"] not in old_by_id]
    print(f"[remap:{split}:tok] PII rows={len(pii_idx)} reused={len(hits)} "
          f"missing={len(miss)}")
    layers = cfg["probe"]["tapped_layers"]
    tok_layers = cfg["probe"].get("token_layers", [12, 28])
    C = len(tok_layers) * backbone.config.hidden_size
    bio_max = cfg["train"].get("bio_max_tokens", 1024)

    feats_flat, bio_flat, lens, ids_out = [], [], [], []
    for i in hits:
        z, s, e = old_by_id[rows[i]["id"]]
        feats_flat.append(z["feats"][s:e])
        bio_flat.append(z["bio"][s:e])
        lens.append(e - s)
        ids_out.append(rows[i]["id"])
    if miss:
        infos = {}
        for i in miss:
            inp = normalize_input(rows[i])
            rendered, msg_spans, fmap = render(tok, inp)
            infos[i] = (tokenize_windowed(tok, rendered), msg_spans, fmap)
        pad_id = tok.pad_token_id or 151643
        pos = 0
        while pos < len(miss):
            chunk = miss[pos:pos + 8]
            ids, attn = _pad_batch([infos[i][0]["input_ids"] for i in chunk],
                                   pad_id, device)
            _, tf = forward_extract(backbone, ids, attn, layers, "mean+last",
                                    tok_layers)
            for k, i in enumerate(chunk):
                tw, msg_spans, fmap = infos[i]
                L = min(len(tw["input_ids"]), bio_max)
                feats_flat.append(tf[k, :L].numpy().astype(np.float16))
                bio_flat.append(np.array(spans_to_bio(
                    pii_spans[pii_pos[int(i)]], tw["offsets"][:L],
                    msg_spans, fmap), dtype=np.int8))
                lens.append(L)
                ids_out.append(rows[i]["id"])
            pos += len(chunk)
    cache = out_dir / "feat_cache"
    np.savez_compressed(
        cache / f"tokfeats_{split}.npz",
        feats=(np.concatenate(feats_flat) if feats_flat
               else np.zeros((0, C), dtype=np.float16)),
        bio=(np.concatenate(bio_flat) if bio_flat
             else np.zeros((0,), dtype=np.int8)),
        lens=np.array(lens, dtype=np.int32),
        ids=np.array(ids_out))
    print(f"[remap:{split}:tok] wrote tokfeats ({sum(lens)} tokens)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--old-cache", required=True,
                    help="old feat_cache dir (single dir; both splits read)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available()
                    else "cpu")
    ap.add_argument("--verify-frac", type=float, default=0.02)
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = REPO / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    old = [Path(args.old_cache)]
    backbone, tok = load_backbone(cfg["base"]["model_name_or_path"],
                                  cfg["base"].get("dtype", "bf16"),
                                  args.device)
    for split in ("train", "dev"):
        rows = rows_for_split(cfg, split)
        remap_split(split, rows, old, out_dir, cfg, backbone, tok,
                    args.device, args.verify_frac)
        remap_tokfeats(split, rows, old, out_dir, cfg, backbone, tok,
                       args.device)
    print("[remap] DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
