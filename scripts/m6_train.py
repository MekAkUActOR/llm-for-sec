# -*- coding: utf-8 -*-
"""M6 DEV-2 v2: config-driven multi-task probe training (ADR-1 + adr-1b).

Pipeline (single YAML config, m6-train-config schema):
  Stage A  render (m6_render: five input forms -> chat template, byte-exact)
           + windowed tokenize (4096, head 512 + tail 3584) -> ONE forward
           -> pooled fp16 cache [N, 10240] (+ per-token L12/L28 cache for
           T4-annotated rows, with gold BIO labels)
  Stage B  heads on cache: shared trunk (LN->10240:1024->GELU) + T1/T2/T3/T5
           binary MLP + T6 3-class MLP + T4 doc MLP + T4 token-BIO head.
           Loss: masked BCE (pos_weight clip [1,20]) + T6 CE + w_tok * BIO CE
           (B/I weight cfg). Recipe: bs 256 / AdamW 1e-3 cosine->0.1x /
           warmup 5% / wd 0.01 / dropout 0.1 / <=3 epochs / early stop 1.
  Stage C  calibration (CPU): per-task zero-FP tau_flag with ADR margin,
           tau_strong, Mahalanobis OOD (benign/attack dual centers, shrunk
           shared covariance), tau_ood = dev-benign q99.5. No temperature
           applied (adr-1b 6.1: score = sigmoid(logit) raw scale).

Artifacts (checkpoints/<run_id>/):
  probe-heads.pt      all head+trunk weights (+ BIO head)
  ood_centers.json    Mahalanobis centers / shrunk covariance / tau_ood
  calib.json          initial runpoint (qa re-freezes per m6-thresholds)
  head_structure.json architecture as plain json
  metrics.json        dev metrics at operating point + curves
  train_log.jsonl     per-epoch metrics
  config.json         full resolved config snapshot
  feat_cache/         stage-A caches

Usage:
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_train.py --config configs/m6-v1.yaml
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_train.py --config configs/m6-smoke.yaml
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_feat_probe import (load_backbone, forward_extract,  # noqa: E402
                           forward_extract_grad)
from m6_render import (  # noqa: E402
    N_BIO_CHANNELS, PII_TYPES, load_jsonl, normalize_input, render,
    spans_to_bio, tokenize_windowed,
)

TASKS = ["T1", "T2", "T3", "T4", "T5", "T6"]
T6_CLASS = {"high-risk": 0, "conditional": 1, "safe": 2}
DEFAULT_CKPT = "checkpoints/qwen3-06b-sec-m5a-dpo-r5"


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    for k in ("run_id", "base", "probe", "train", "output_dir"):
        assert k in cfg, f"config missing '{k}' (m6-train-config schema)"
    assert cfg["base"]["model_name_or_path"] == DEFAULT_CKPT, "base must be r5"
    return cfg


def rows_for_split(cfg: dict, split: str) -> list[dict]:
    """Load m6-sample rows for a split. Prefers explicit patterns (smoke /
    pre-manifest), else manifest['splits'][split]['files'].

    data.prefix_rows: "exclude" (default, ADR mainline = final-state rows),
    "include" (ablation: keep prefix-expanded rows), "only" (prefix only).
    A row is a prefix row iff meta.is_prefix is truthy (dataeng terminal
    semantics: reveal_turn_prefix is a form descriptor carried by full
    reveal-turn dialogs too, NOT an exclusion marker)."""
    d = cfg.get("data", {})
    pats = d.get(f"{split}_patterns")
    files = []
    if pats:
        for p in pats:
            files.extend(sorted(REPO.glob(p)))
    else:
        # m6-manifest schema: flat files[] with split/path fields
        man_path = REPO / d["manifest"]
        man = json.loads(man_path.read_text(encoding="utf-8-sig"))
        base = man_path.parent
        files = [base / f["path"] for f in man["files"] if f["split"] == split]
        # sha256 verification guard (drift detection, cheap skip option)
        if not cfg.get("data", {}).get("skip_sha_check", False):
            import hashlib
            for f, ent in zip(files, (e for e in man["files"] if e["split"] == split)):
                h = hashlib.sha256(Path(f).read_bytes()).hexdigest()
                assert h == ent["sha256"], \
                    f"manifest sha256 mismatch: {f} (data drift?)"
    assert files, f"no files for split {split}"
    mode = d.get("prefix_rows", "exclude")
    rows, seen_map, ndup, nproj = [], {}, 0, 0
    for f in files:
        for r in load_jsonl(f):
            assert r.get("schema") == "m6-sample", f"{f}: not m6-sample ({r.get('schema')})"
            assert r["split"] == split, f"{f}: row split={r['split']} != {split}"
            meta = r.get("meta") or {}
            is_prefix = bool(meta.get("is_prefix"))
            if mode == "exclude" and is_prefix:
                continue
            if mode == "only" and not is_prefix:
                continue
            if r["id"] in seen_map:
                # shared rows legitimately appear in task files AND pool.
                prev = seen_map[r["id"]]
                if json.dumps(prev, sort_keys=True, ensure_ascii=False) == \
                        json.dumps(r, sort_keys=True, ensure_ascii=False):
                    ndup += 1
                    continue
                # label-projection precedence (dataeng+arch ruling): the pool
                # copy of a projected row carries MORE label keys (six-key
                # cross-task neg supervision) while the task-view copy stays
                # single-key by contract. Text must still be identical --
                # only the labels may diverge; anything else is a data bug.
                def _nolab(x):
                    return {k: v for k, v in x.items() if k != "labels"}
                assert json.dumps(_nolab(prev), sort_keys=True,
                                  ensure_ascii=False) == \
                    json.dumps(_nolab(r), sort_keys=True, ensure_ascii=False), \
                    f"duplicate id {r['id']} with DIFFERENT non-label content in {f}"
                nk_prev = len((prev.get("labels") or {}))
                nk_new = len((r.get("labels") or {}))
                if nk_new > nk_prev:
                    rows[rows.index(prev)] = r
                    seen_map[r["id"]] = r
                    nproj += 1
                    if nproj <= 3:
                        print(f"[m6_train] {split}: projection precedence "
                              f"{r['id']} -> {nk_new}-key copy "
                              f"(was {nk_prev}-key)")
                continue
            seen_map[r["id"]] = r
            rows.append(r)
    if ndup:
        print(f"[m6_train] {split}: {ndup} shared rows deduped "
              f"(task files ∩ pool, byte-identical)")
    if nproj:
        print(f"[m6_train] {split}: {nproj} rows took label-projection "
              f"precedence (pool multi-key > task-view single-key)")
    return rows


def derive_labels(rows: list[dict]):
    """-> Y [N,6] float32 (-1 = unannotated), t6c [N] int8, neg_all [N] bool,
    mirror [N] bool, pii_idx [K] int, pii_spans [K] list."""
    N = len(rows)
    Y = np.full((N, 6), -1.0, dtype=np.float32)
    t6c = np.full(N, -1, dtype=np.int8)
    neg_all, mirror, pii_idx, pii_spans = [], [], [], []
    for i, r in enumerate(rows):
        labs = r.get("labels") or {}
        all_neg = True
        for j, t in enumerate(TASKS):
            if t in labs:
                pos = labs[t]["label"] == "pos"
                Y[i, j] = 1.0 if pos else 0.0
                if pos:
                    all_neg = False
        det6 = (labs.get("T6") or {}).get("label_detail") or {}
        c6 = det6.get("t6_class")
        if labs.get("T6"):
            t6c[i] = T6_CLASS.get(c6, 0 if labs["T6"]["label"] == "pos" else 2)
        neg_all.append(all_neg)
        fl = r.get("flags") or {}
        mirror.append(bool(fl.get("challenge")))
        if "T4" in labs:
            pii_idx.append(i)
            pii_spans.append((labs["T4"].get("label_detail") or {}).get("spans") or [])
    return (Y, t6c, np.array(neg_all), np.array(mirror),
            np.array(pii_idx, dtype=int), pii_spans)


# --------------------------------------------------------------------------- #
# stage A: render + tokenize + forward -> caches
# --------------------------------------------------------------------------- #
def _pad_batch(seqs, pad_id, device):
    T = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), T), pad_id, dtype=torch.long)
    attn = torch.zeros((len(seqs), T), dtype=torch.long)
    for i, s in enumerate(seqs):
        ids[i, :len(s)] = torch.tensor(s, dtype=torch.long)
        attn[i, :len(s)] = 1
    return ids.to(device), attn.to(device)


def stage_a(cfg, backbone, tok, rows, split, out_dir, device):
    """Extract pooled (+ optional token) features; write feat_cache npz."""
    t0 = time.time()
    p = cfg["probe"]
    layers = p["tapped_layers"]
    pooling = "mean+last"
    tok_layers = p.get("token_layers", [12, 28])
    bio_max_tokens = cfg["train"].get("bio_max_tokens", 1024)
    batch_rows = cfg["train"].get("extract_batch_rows", 16)

    Y, t6c, neg_all, mirror, pii_idx, pii_spans = derive_labels(rows)
    pii_set = set(pii_idx.tolist())

    rendered_all, tok_info = [], []
    for r in rows:
        inp = normalize_input(r)
        rendered, msg_spans, fmap = render(tok, inp)
        tw = tokenize_windowed(tok, rendered)
        rendered_all.append(rendered)
        tok_info.append({"tw": tw, "msg_spans": msg_spans, "fmap": fmap})

    N, D = len(rows), len(layers) * backbone.config.hidden_size * 2
    pooled = np.zeros((N, D), dtype=np.float16)
    trunc_flags = np.zeros(N, dtype=bool)
    pad_id = tok.pad_token_id or 151643

    # token feats only for T4-annotated rows -- FLAT packing (variable lengths;
    # dense [K, maxT, C] would explode at real-data scale: 10k rows x 1024
    # tokens x 2048 ch x 2B = 42GB)
    K = len(pii_idx)
    C = len(tok_layers) * backbone.config.hidden_size
    tok_flat, bio_flat, tok_lens = [], [], []
    pii_row_to_k = {int(i): k for k, i in enumerate(pii_idx)}

    pos = 0
    while pos < N:
        chunk = list(range(pos, min(pos + batch_rows, N)))
        ids, attn = _pad_batch([tok_info[i]["tw"]["input_ids"] for i in chunk],
                               pad_id, device)
        # ONE forward per batch: pooled + token states together
        f, tf = forward_extract(backbone, ids, attn, layers, pooling, tok_layers)
        pooled[chunk] = f.numpy().astype(np.float16)
        for i in chunk:
            trunc_flags[i] = tok_info[i]["tw"]["truncation"]
            k = pii_row_to_k.get(i)
            if k is not None:
                row_len = len(tok_info[i]["tw"]["input_ids"])
                L = min(row_len, bio_max_tokens)
                tok_flat.append(tf[chunk.index(i), :L].numpy().astype(np.float16))
                bio_flat.append(np.array(spans_to_bio(
                    pii_spans[k], tok_info[i]["tw"]["offsets"][:L],
                    tok_info[i]["msg_spans"], tok_info[i]["fmap"]),
                    dtype=np.int8))
                tok_lens.append(L)
        pos += batch_rows

    cache = out_dir / "feat_cache"
    cache.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache / f"feats_{split}.npz",
        pooled=pooled, ids=np.array([r["id"] for r in rows]),
        Y=Y, t6c=t6c, neg_all=neg_all, mirror=mirror, trunc=trunc_flags,
        layers=np.array(layers), pooling=np.array(pooling),
    )
    if K:
        np.savez_compressed(
            cache / f"tokfeats_{split}.npz",
            feats=(np.concatenate(tok_flat) if tok_flat
                   else np.zeros((0, C), dtype=np.float16)),
            bio=(np.concatenate(bio_flat) if bio_flat
                 else np.zeros((0,), dtype=np.int8)),
            lens=np.array(tok_lens, dtype=np.int32),
            ids=np.array([rows[i]["id"] for i in pii_idx]),
        )
    print(f"[m6_train] stage A [{split}]: {N} rows pooled {pooled.shape} "
          f"(fp16), {K} PII rows tokfeats flat {sum(tok_lens)} tokens, "
          f"trunc={int(trunc_flags.sum())}, {time.time() - t0:.0f}s")
    return cache


def refresh_cache_labels(cfg, out_dir):
    """Hot-fix path: rewrite ONLY the label arrays inside feat_cache npz.

    Pooled features are label-independent; when a label-only data fix lands
    (e.g. the reserve-cval T1 polarity flip) this avoids the 22-min GPU
    re-extraction. HARD FAILS if the row-id set/order changed (that kind of
    drift needs a full re-extract). tokfeats caches are validated for id-set
    equality (T1-only flips cannot change the PII-annotated row set, but a
    general check is cheap).
    """
    for split in ("train", "dev"):
        path = out_dir / "feat_cache" / f"feats_{split}.npz"
        if not path.is_file():
            print(f"[m6_train] refresh-labels: no cache for {split}, skip")
            continue
        rows = rows_for_split(cfg, split)
        z = np.load(path, allow_pickle=True)
        old_ids = [str(x) for x in z["ids"]]
        new_ids = [r["id"] for r in rows]
        assert old_ids == new_ids, (
            f"feats_{split}.npz row set/order changed "
            f"({len(old_ids)} -> {len(new_ids)}): label refresh not safe, "
            f"full re-extract required")
        Y, t6c, neg_all, mirror, pii_idx, pii_spans = derive_labels(rows)
        n_flip_y = int((Y != z["Y"]).sum())
        n_flip_neg = int((neg_all != z["neg_all"]).sum())
        n_flip_mir = int((mirror != z["mirror"]).sum())
        np.savez_compressed(
            path, pooled=z["pooled"], ids=z["ids"],
            Y=Y, t6c=t6c, neg_all=neg_all, mirror=mirror, trunc=z["trunc"],
            layers=z["layers"], pooling=z["pooling"])
        print(f"[m6_train] refresh-labels [{split}]: Y cells flipped="
              f"{n_flip_y}, neg_all flips={n_flip_neg}, mirror flips="
              f"{n_flip_mir} -> {path.name}")
        tok_path = out_dir / "feat_cache" / f"tokfeats_{split}.npz"
        if tok_path.is_file():
            tz = np.load(tok_path, allow_pickle=True)
            old_tok_ids = {str(x) for x in tz["ids"]}
            want = {rows[i]["id"] for i in pii_idx}
            assert old_tok_ids == want, (
                f"tokfeats_{split}.npz PII row set changed: re-extract required")


# --------------------------------------------------------------------------- #
# stage B: heads
# --------------------------------------------------------------------------- #
class M6Probe(nn.Module):
    """trunk + T1/T2/T3/T5 binary + T6 3-class + T4 doc + T4 token BIO."""

    def __init__(self, in_dim, trunk_hidden=1024, head_hidden=256,
                 dropout=0.1, n_bio=N_BIO_CHANNELS, tok_feat_dim=2048,
                 bio_hidden=512):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.LayerNorm(in_dim), nn.Linear(in_dim, trunk_hidden),
            nn.GELU(), nn.Dropout(dropout))

        def seq_head(out):
            return nn.Sequential(nn.Linear(trunk_hidden, head_hidden),
                                 nn.GELU(), nn.Dropout(dropout),
                                 nn.Linear(head_hidden, out))
        self.heads = nn.ModuleDict({
            "T1": seq_head(1), "T2": seq_head(1), "T3": seq_head(1),
            "T4doc": seq_head(1), "T5": seq_head(1), "T6": seq_head(3)})
        self.bio = nn.Sequential(
            nn.LayerNorm(tok_feat_dim), nn.Linear(tok_feat_dim, bio_hidden),
            nn.GELU(), nn.Dropout(dropout), nn.Linear(bio_hidden, n_bio))
        self.struct = {
            "in_dim": in_dim, "trunk_hidden": trunk_hidden,
            "head_hidden": head_hidden, "dropout": dropout,
            "n_bio": n_bio, "tok_feat_dim": tok_feat_dim,
            "bio_hidden": bio_hidden, "tasks": TASKS,
            "bio_channel_semantics": "0=O; 1+t=B(type); 1+n_types+t=I(type)",
            "pii_types": PII_TYPES,
        }

    def forward(self, x):  # pooled [B, D]
        h = self.trunk(x)
        out = {}
        for t in ("T1", "T2", "T3", "T4doc", "T5"):
            out[t] = self.heads[t](h).squeeze(-1)
        out["T6"] = self.heads["T6"](h)  # [B,3]
        return out

    def forward_bio(self, xt):  # [B, T, C]
        return self.bio(xt)  # [B, T, n_bio]

    def structure_json(self):
        return dict(self.struct)


def _pos_weights(Y):
    w = {}
    for j, t in enumerate(TASKS):
        col = Y[:, j]
        m = col >= 0
        n_pos = float((col[m] == 1).sum())
        n_neg = float((col[m] == 0).sum())
        w[t] = min(20.0, max(1.0, n_neg / max(1.0, n_pos)))
    return w


def _gather_bio_batch(TFf, BFf, offs, bidx, device):
    """Gather variable-length BIO rows (flat storage) into a padded batch.
    Labels pad with ignore_index=-100; feat rows pad with zeros."""
    L = [int(offs[i + 1] - offs[i]) for i in bidx]
    T = max(L) if L else 1
    B = len(bidx)
    xt = torch.zeros(B, T, TFf.shape[1], device=device)
    xb = torch.full((B, T), -100, dtype=torch.long, device=device)
    for j, i in enumerate(bidx):
        s, e = int(offs[i]), int(offs[i + 1])
        xt[j, :L[j]] = TFf[s:e]
        xb[j, :L[j]] = BFf[s:e]
    return xt, xb


def train_stage_b(cfg, cache_dir, out_dir, device):
    t0 = time.time()
    torch.manual_seed(cfg["train"].get("seed", 42))
    np.random.seed(cfg["train"].get("seed", 42))
    tr = cfg["train"]
    epochs = tr.get("max_epochs", 3)
    bs = tr.get("per_device_batch_size", 256)
    lr = tr.get("learning_rate", 1e-3)
    wd = tr.get("weight_decay", 0.01)
    warmup = tr.get("warmup_ratio", 0.05)
    patience = tr.get("early_stop_patience", 1)
    w_tok = cfg["probe"].get("loss", {}).get("bio_weight", 2.0)
    bio_pos_w = cfg["probe"].get("loss", {}).get("bio_pos_weight", 15.0)

    A = np.load(cache_dir / "feats_train.npz", allow_pickle=True)
    D = np.load(cache_dir / "feats_dev.npz", allow_pickle=True)
    Xtr, Ytr, t6tr = A["pooled"].astype(np.float32), A["Y"], A["t6c"]
    Xdv, Ydv, t6dv = D["pooled"].astype(np.float32), D["Y"], D["t6c"]
    in_dim = Xtr.shape[1]
    print(f"[m6_train] stage B: train {Xtr.shape}, dev {Xdv.shape}, in_dim={in_dim}")

    bio_path = cache_dir / "tokfeats_train.npz"
    bio_dev_path = cache_dir / "tokfeats_dev.npz"
    TB = np.load(bio_path, allow_pickle=True) if bio_path.is_file() else None
    TBd = np.load(bio_dev_path, allow_pickle=True) if bio_dev_path.is_file() else None

    model = M6Probe(in_dim).to(device)
    pw = _pos_weights(Ytr)
    print(f"[m6_train] pos_weights: " + ", ".join(f"{t}={pw[t]:.1f}" for t in TASKS))

    bce = {t: nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pw[t]], device=device)) for t in TASKS}
    ce6 = nn.CrossEntropyLoss()
    nbio = model.struct["n_bio"]
    ntypes = len(PII_TYPES)
    cw = torch.ones(nbio, device=device)
    cw[1:] = bio_pos_w  # B/I upweighted vs O
    cebio = nn.CrossEntropyLoss(weight=cw, ignore_index=-100)

    TFf = BFf = offs = None
    if TB is not None and len(TB["lens"]):
        TFf = torch.tensor(TB["feats"].astype(np.float32)).to(device)
        BFf = torch.tensor(TB["bio"].astype(np.int64)).to(device)
        offs = np.concatenate([[0], np.cumsum(TB["lens"])])
        n_bio_rows = len(TB["lens"])

    steps_per_epoch = math.ceil(len(Xtr) / bs)
    total_steps = steps_per_epoch * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (0.1 + 0.9 * min(1.0, s / max(1, warmup * total_steps)))
        * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total_steps))))
        if s < warmup * total_steps else
        (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total_steps)))))

    Xtr_t = torch.tensor(Xtr).to(device)
    Xdv_t = torch.tensor(Xdv).to(device)
    Ytr_t = torch.tensor(Ytr).to(device)
    t6tr_t = torch.tensor(t6tr.astype(np.int64)).to(device)
    Ydv_t = torch.tensor(Ydv).to(device)
    # label-key -> head-key (T4 label trains the doc head; BIO head separate)
    LABEL_TO_HEAD = {"T1": "T1", "T2": "T2", "T3": "T3", "T4": "T4doc", "T5": "T5"}
    COL = {t: j for j, t in enumerate(TASKS)}

    if TB is not None and len(TB["lens"]):
        TFf = torch.tensor(TB["feats"].astype(np.float32)).to(device)
        BFf = torch.tensor(TB["bio"].astype(np.int64)).to(device)
        offs = np.concatenate([[0], np.cumsum(TB["lens"])])
        n_bio_rows = len(TB["lens"])

    logf = open(out_dir / "train_log.jsonl", "w", encoding="utf-8")
    best_key, best_state, best_ep, bad = -1.0, None, -1, 0
    step = 0
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(Xtr_t), device=device)
        for i in range(0, len(perm), bs):
            idx = perm[i:i + bs]
            x = Xtr_t[idx]
            ydict = {t: Ytr_t[idx][:, j] for j, t in enumerate(TASKS)}
            mask = {t: (ydict[t] >= 0) for t in TASKS}
            out = model(x)
            loss = 0.0
            for lt, ht in LABEL_TO_HEAD.items():
                m = mask[lt]
                if m.any():
                    yt = torch.where(ydict[lt] >= 0, ydict[lt],
                                     torch.zeros_like(ydict[lt]))
                    loss = loss + bce[lt](out[ht][m], yt[m])
            m6 = t6tr_t[idx] >= 0
            if m6.any():
                loss = loss + ce6(out["T6"][m6], t6tr_t[idx][m6])
            if TFf is not None:
                bidx = torch.randint(0, n_bio_rows, (min(8, n_bio_rows),),
                                     device=device)
                xt, xb = _gather_bio_batch(TFf, BFf, offs, bidx.tolist(), device)
                logits = model.forward_bio(xt)
                loss = loss + w_tok * cebio(
                    logits.reshape(-1, nbio), xb.reshape(-1))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            step += 1

        # dev metrics (zero-FP operating point per task, on neg_all set)
        model.eval()
        with torch.no_grad():
            out_d = model(Xdv_t)
        scores = {t: torch.sigmoid(out_d[t]).cpu().numpy() for t in
                  ("T1", "T2", "T3", "T4doc", "T5")}
        neg = D["neg_all"]
        entry = {"epoch": ep, "tasks": {}}
        rs = []
        for lt, ht in LABEL_TO_HEAD.items():
            s = scores[ht]
            g = Ydv[:, COL[lt]]
            m = g >= 0
            pos_s, neg_s = s[m & (g == 1)], s[m & neg]
            r = None
            if len(pos_s) and len(neg_s):
                thr = float(neg_s.max()) if len(neg_s) else 0.5
                r = round(float((pos_s > thr).mean()), 4)
                rs.append(r)
            entry["tasks"][lt] = {"recall@zeroFP": r,
                                  "n_pos": int(len(pos_s)), "n_neg": int(len(neg_s))}
        if (Ydv[:, 5] >= 0).any():
            pred6 = out_d["T6"].argmax(-1).cpu().numpy()
            gold6 = t6dv.copy()
            m6 = gold6 >= 0
            entry["tasks"]["T6"] = {
                "acc3": round(float((pred6[m6] == gold6[m6]).mean()), 4),
                "recall_highrisk@argmax": round(float(
                    (pred6[m6 & (gold6 == 0)] == 0).mean()), 4)
                if (m6 & (gold6 == 0)).any() else None}
        entry["macro_recall_zeroFP"] = round(sum(rs) / max(1, len(rs)), 4)
        logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logf.flush()
        star = ""
        if entry["macro_recall_zeroFP"] > best_key:
            best_key, best_ep, bad = entry["macro_recall_zeroFP"], ep, 0
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}
            star = " *best*"
        else:
            bad += 1
        print(f"[m6_train] ep{ep} macroR@zeroFP={entry['macro_recall_zeroFP']:.4f}{star}")
        if bad >= patience:
            print(f"[m6_train] early stop (patience {patience})")
            break
    logf.close()
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    print(f"[m6_train] best epoch {best_ep} ({best_key:.4f}), {time.time() - t0:.0f}s")
    return model, A, D, TB, TBd


# --------------------------------------------------------------------------- #
# stage B (v2): LoRA joint training -- backbone adapted on the fly
# --------------------------------------------------------------------------- #
def train_stage_b_lora(cfg, out_dir, device, lora_resume=False):
    """ADR-1 §16 v2 path: LoRA (r16, q/k/v/o, L14-28) + heads trained jointly.

    No feature cache (LoRA changes features from L14 on). Length-bucketed
    batches; gradient checkpointing; two param groups (LoRA lr << head lr).
    After training, re-extracts (inference) the arrays calibrate() needs:
    train all-neg trunk features (Mahalanobis centers) + dev pooled.
    Saves adapter state to out_dir/adapter.pt next to probe-heads.pt.
    """
    import copy

    from peft import LoraConfig, get_peft_model

    t0 = time.time()
    torch.manual_seed(cfg["train"].get("seed", 42))
    np.random.seed(cfg["train"].get("seed", 42))
    tr = cfg["train"]
    lc = tr.get("lora", {})
    epochs = tr.get("max_epochs", 3)
    bs = tr.get("per_device_batch_size", 256)
    head_lr = tr.get("learning_rate", 1e-3)
    lora_lr = float(lc.get("lr", 1e-4))
    wd = tr.get("weight_decay", 0.01)
    warmup = tr.get("warmup_ratio", 0.05)
    patience = tr.get("early_stop_patience", 1)
    w_tok = cfg["probe"].get("loss", {}).get("bio_weight", 2.0)
    bio_pos_w = cfg["probe"].get("loss", {}).get("bio_pos_weight", 15.0)
    bio_extra = int(tr.get("lora_bio_extra_rows", 2))
    # v2.2 arch increment 2: T6 structural separation -- the joint LoRA loop
    # trains T1-T5 only; the T6 head trains post-hoc on the frozen adapted
    # trunk (3/3 T6 ep2 deaths under joint dynamics; head-only T6 has zero
    # historical deaths). Optional healthy init from a prior checkpoint.
    lc_cfg = tr.get("lora", {}) or {}
    t6_sep = bool(lc_cfg.get("t6_separate", False))
    t6_init_from = str(lc_cfg.get("t6_init_from", "") or "")
    if t6_sep:
        print(f"[m6_train] v2.2 T6 structural separation ON "
              f"(init_from={t6_init_from or 'fresh'})")
    # arch §16: per-task regression guard baseline (v1-2 readings);
    # epochs where ANY task regresses >1pp are not best-epoch candidates
    baseline = {k: float(v) for k, v in
                (tr.get("baseline_readings") or {}).items()} or None
    if baseline:
        print(f"[m6_train] v2 regression-guard baseline: {baseline}")

    backbone, tok = load_backbone(cfg["base"]["model_name_or_path"],
                                  cfg["base"].get("dtype", "bf16"), device)
    if hasattr(backbone, "gradient_checkpointing_enable"):
        backbone.gradient_checkpointing_enable()
        backbone.config.use_cache = False
    lcfg = LoraConfig(
        r=int(lc.get("r", 16)),
        lora_alpha=float(lc.get("alpha", 32)),
        lora_dropout=float(lc.get("dropout", 0.05)),
        bias="none",
        target_modules=list(lc.get("target_modules",
                                   ["q_proj", "k_proj", "v_proj", "o_proj"])),
        layers_to_transform=list(range(int(lc.get("layer_from", 14)),
                                       int(lc.get("layer_to", 28)) + 1)),
        task_type="FEATURE_EXTRACTION")
    pmodel = get_peft_model(backbone, lcfg)
    try:
        pmodel.get_base_model().enable_input_require_grads()
    except Exception:
        pass
    pmodel.print_trainable_parameters()
    pmodel.train()

    rows_tr = rows_for_split(cfg, "train")
    rows_dv = rows_for_split(cfg, "dev")
    Y, t6c, neg_all, mirror, pii_idx, pii_spans = derive_labels(rows_tr)
    Ydv, t6dv, neg_dv, mirror_dv, _, _ = derive_labels(rows_dv)
    print(f"[m6_train] v2 rows: train={len(rows_tr)} dev={len(rows_dv)} "
          f"(PII train rows={len(pii_idx)})")

    def tokenize_all(rows):
        infos = []
        for r in rows:
            inp = normalize_input(r)
            rendered, msg_spans, fmap = render(tok, inp)
            tw = tokenize_windowed(tok, rendered)
            infos.append({"tw": tw, "msg_spans": msg_spans, "fmap": fmap,
                          "spans": None})
        return infos

    tokinfo_tr = tokenize_all(rows_tr)
    # gold BIO for PII rows
    bio_meta = {}
    for k, i in enumerate(pii_idx):
        tw = tokinfo_tr[i]["tw"]
        L = min(len(tw["input_ids"]), tr.get("bio_max_tokens", 1024))
        bio_meta[int(i)] = np.array(spans_to_bio(
            pii_spans[k], tw["offsets"][:L], tokinfo_tr[i]["msg_spans"],
            tokinfo_tr[i]["fmap"]), dtype=np.int64)
    tokinfo_dv = tokenize_all(rows_dv)

    p = cfg["probe"]
    layers = p["tapped_layers"]
    tok_layers = p.get("token_layers", [12, 28])
    in_dim = len(layers) * backbone.config.hidden_size * 2
    model = M6Probe(in_dim).to(device)
    pw = _pos_weights(Y)
    print(f"[m6_train] pos_weights: " + ", ".join(f"{t}={pw[t]:.1f}" for t in TASKS))

    bce = {t: nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pw[t]], device=device)) for t in TASKS}
    ce6 = nn.CrossEntropyLoss()
    nbio = model.struct["n_bio"]
    ntypes = len(PII_TYPES)
    cebio = nn.CrossEntropyLoss(
        weight=torch.tensor([1.0] + [bio_pos_w] * (nbio - 1), device=device),
        ignore_index=-100)

    lora_params = [q for n, q in pmodel.named_parameters() if q.requires_grad]
    head_params = list(model.parameters())
    opt = torch.optim.AdamW(
        [{"params": lora_params, "lr": lora_lr},
         {"params": head_params, "lr": head_lr}], weight_decay=wd)

    # length-bucketed batches: sort by token len, chunk, shuffle chunk order
    order = sorted(range(len(rows_tr)), key=lambda i: len(tokinfo_tr[i]["tw"]["input_ids"]))
    batches = [order[i:i + bs] for i in range(0, len(order), bs)]
    total_steps = len(batches) * epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total_steps))))) \
        if total_steps else None
    pad_id = tok.pad_token_id or 151643
    LABEL_TO_HEAD = {"T1": "T1", "T2": "T2", "T3": "T3", "T4": "T4doc", "T5": "T5"}
    pii_list = [int(i) for i in pii_idx]

    logf = open(out_dir / "train_log.jsonl", "w", encoding="utf-8")
    best_key, best_state, best_lora, best_ep, bad = -1.0, None, None, -1, 0
    lb_state, lb_lora, lb_ep, lb_best = None, None, -1, None
    step = 0
    snap_path = out_dir / "_snapshot.pt"
    resume_at = None
    if lora_resume and snap_path.is_file():
        snap = torch.load(snap_path, map_location=device, weights_only=False)
        model.load_state_dict(snap["heads"])
        try:
            from peft import set_peft_model_state_dict
            set_peft_model_state_dict(pmodel, snap["lora"])
        except Exception as e:  # pragma: no cover - resume best-effort
            print(f"[m6_train] lora-resume adapter load issue: {e}")
        opt.load_state_dict(snap["opt"])
        if sched is not None and snap.get("sched"):
            sched.load_state_dict(snap["sched"])
        resume_at = (snap["ep"], snap["step_in_ep"])
        step = int(snap["step"])
        print(f"[m6_train] lora-resume: ep{snap['ep']} step_in_ep="
              f"{snap['step_in_ep']} global_step={snap['step']} loaded")
    oom_splits = 0
    def run_batch(bidx, scale=1.0):
        """Forward+loss+backward for one batch (no optimizer step).

        Split-retry on CUDA OOM lives in batch_with_oom_retry: the doc-long
        tail produces 16x~4k-token batches near the 24GB ceiling; on OOM the
        batch splits in halves with gradient accumulation (loss scaled by
        sub-batch share), so one oversized batch cannot kill a multi-hour
        run (v2 first attempt died at ep1 94% exactly there).
        """
        ids, attn = _pad_batch(
            [tokinfo_tr[i]["tw"]["input_ids"] for i in bidx], pad_id, device)
        pooled, tokf = forward_extract_grad(
            pmodel, ids, attn, layers, "mean+last", tok_layers)
        out = model(pooled)
        loss = 0.0
        yb = Y[bidx]
        t6b = t6c[bidx]
        for lt, ht in LABEL_TO_HEAD.items():
            m = torch.tensor(yb[:, TASKS.index(lt)] >= 0, device=device)
            if m.any():
                yv = torch.tensor(
                    np.where(yb[:, TASKS.index(lt)] >= 0,
                             yb[:, TASKS.index(lt)], 0),
                    dtype=torch.float32, device=device)
                loss = loss + bce[lt](out[ht][m], yv[m])
        if not t6_sep:
            m6 = torch.tensor(t6b >= 0, device=device)
            if m6.any():
                t6v = torch.tensor(np.where(t6b >= 0, t6b, 0),
                                   dtype=torch.long, device=device)
                loss = loss + ce6(out["T6"][m6], t6v[m6])
        bio_rows = [i for i in bidx if i in bio_meta]
        extra = [i for i in rng.choice(pii_list, size=min(bio_extra, len(pii_list)),
                                       replace=False).tolist()
                 if i not in bio_rows] if pii_list else []
        if bio_rows or extra:
            xt, xb = [], []
            for i in bio_rows + extra:
                L = len(bio_meta[i])
                rpos = bidx.index(i) if i in bio_rows else -1
                if rpos >= 0:
                    xt.append(tokf[rpos, :L])
                    xb.append(torch.tensor(bio_meta[i], device=device))
                else:
                    ids1, attn1 = _pad_batch(
                        [tokinfo_tr[i]["tw"]["input_ids"]], pad_id, device)
                    _, tf1 = forward_extract_grad(
                        pmodel, ids1, attn1, layers, "mean+last", tok_layers)
                    xt.append(tf1[0, :L])
                    xb.append(torch.tensor(bio_meta[i], device=device))
            xt = torch.nn.utils.rnn.pad_sequence(xt, batch_first=True)
            xb = torch.nn.utils.rnn.pad_sequence(xb, batch_first=True,
                                                 padding_value=-100)
            logits = model.forward_bio(xt)
            loss = loss + w_tok * cebio(
                logits.reshape(-1, nbio), xb.reshape(-1))
        (loss * scale).backward()
        return float(loss)

    def batch_with_oom_retry(bidx):
        """run_batch with recursive split on CUDA OOM (grad accumulation)."""
        nonlocal oom_splits
        try:
            return run_batch(bidx)
        except torch.cuda.OutOfMemoryError:
            opt.zero_grad(set_to_none=True)
            torch.cuda.empty_cache()
            if len(bidx) == 1:
                print(f"[m6_train] OOM on single row {bidx[0]} "
                      f"(len={len(tokinfo_tr[bidx[0]]['tw']['input_ids'])}) "
                      "-- SKIPPED")
                return None
            mid = len(bidx) // 2
            oom_splits += 1
            print(f"[m6_train] OOM split x{oom_splits}: batch {len(bidx)} -> "
                  f"{mid}+{len(bidx) - mid}")
            l1 = batch_with_oom_retry(bidx[:mid])
            l2 = batch_with_oom_retry(bidx[mid:])
            return None if (l1 is None or l2 is None) else \
                (l1 * mid + l2 * (len(bidx) - mid)) / len(bidx)

    for ep in range(1, epochs + 1):
        if resume_at and ep < resume_at[0]:
            continue
        model.train()
        pmodel.train()
        rng = np.random.default_rng(cfg["train"].get("seed", 42) + ep)
        rng.shuffle(batches)
        step_in_ep = 0
        for bidx in batches:
            if resume_at and ep == resume_at[0] and step_in_ep < resume_at[1]:
                step_in_ep += 1
                step += 1
                continue
            opt.zero_grad()
            last_loss = batch_with_oom_retry(bidx)
            torch.nn.utils.clip_grad_norm_(
                list(lora_params) + list(head_params), 1.0)
            opt.step()
            if sched is not None:
                sched.step()
            step += 1
            step_in_ep += 1
            if step % 1000 == 0:
                tmp = snap_path.with_suffix(".tmp")
                torch.save({"heads": model.state_dict(),
                            "lora": {k: v for k, v in pmodel.state_dict().items()
                                     if "lora_" in k},
                            "opt": opt.state_dict(),
                            "sched": sched.state_dict() if sched else None,
                            "ep": ep, "step_in_ep": step_in_ep, "step": step},
                           tmp)
                tmp.replace(snap_path)
            if step % 200 == 0:
                print(f"[m6_train] v2 ep{ep} step {step}/{total_steps} "
                      f"loss={last_loss if last_loss is not None else 'oom-skip'} "
                      f"oom_splits={oom_splits} ({time.time() - t0:.0f}s)")
        # dev eval (inference forward over dev rows, pooled only)
        model.eval()
        pmodel.eval()
        Xdv = np.zeros((len(rows_dv), in_dim), dtype=np.float32)
        pos = 0
        with torch.no_grad():
            while pos < len(rows_dv):
                chunk = list(range(pos, min(pos + 32, len(rows_dv))))
                ids, attn = _pad_batch(
                    [tokinfo_dv[i]["tw"]["input_ids"] for i in chunk],
                    pad_id, device)
                f, _ = forward_extract(pmodel.get_base_model(), ids, attn,
                                       layers, "mean+last", tok_layers)
                Xdv[chunk] = f.numpy()
                pos += len(chunk)
            out_d = model(torch.tensor(Xdv).to(device))
        # LOGIT-SPACE per-epoch readings (D-16 family, 4th occurrence fixed:
        # fp32 sigmoid saturates to exactly 1.0 at logit>~16.6 -- under LoRA
        # benign rows saturate, score-space pos>neg_max becomes 1.0>1.0
        # ties -> recall artifacts of 0.0 (v2 ep1/ep2 T1/T2 were artifacts;
        # true ep2 T1 = 0.626 from the logit-space final calibrate).
        # T6 measured too (v2.1 attempt-2 lesson: the T6 head degenerated
        # at ep2 to all-high-risk saturation [benign P0~1.0, tau pushed
        # above the physical ceiling, recall 0.0] -- a structural guard
        # blind spot; T6 was NEVER per-epoch measured in any version).
        # T6 domain = log-P class-0 (fp64 log_softmax, same as calibrate).
        lg = {t: out_d[t].cpu().numpy() for t in
              ("T1", "T2", "T3", "T4doc", "T5")}
        lg["T6"] = torch.log_softmax(out_d["T6"].double(), dim=-1)[:, 0] \
            .cpu().numpy()
        entry = {"epoch": ep, "tasks": {}}
        rs = []
        guard_tasks = list(LABEL_TO_HEAD.keys()) + ([] if t6_sep else ["T6"])
        for lt in guard_tasks:
            s = lg["T4doc" if lt == "T4" else lt]
            g = Ydv[:, TASKS.index(lt)]
            m = g >= 0
            pos_s, neg_s = s[m & (g == 1)], s[m & neg_dv]
            r = None
            if len(pos_s) and len(neg_s):
                thr = float(neg_s.max())
                r = round(float((pos_s > thr).mean()), 4)
                rs.append(r)
            entry["tasks"][lt] = {"recall@zeroFP": r,
                                  "n_pos": int(len(pos_s)), "n_neg": int(len(neg_s))}
        entry["macro_recall_zeroFP"] = round(sum(rs) / max(1, len(rs)), 4)
        # arch §16 protection rule: per-task regression guard vs v1-2
        # baseline -- an epoch whose ANY task regresses >1pp is not a
        # valid best-epoch candidate (feature drift protection for
        # T5/T6-class heads that are already at/near target)
        regress = {}
        if baseline:
            for lt in entry["tasks"]:
                r_now = entry["tasks"][lt].get("recall@zeroFP")
                r_base = baseline.get(lt)
                if r_now is not None and r_base is not None:
                    if r_now < r_base - 0.01:
                        regress[lt] = round(r_base - r_now, 4)
        entry["regression_vs_baseline"] = regress
        logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logf.flush()
        star = ""
        if entry["macro_recall_zeroFP"] > best_key and not regress:
            best_key, best_ep, bad = entry["macro_recall_zeroFP"], ep, 0
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}
            from peft.utils import get_peft_model_state_dict
            best_lora = copy.deepcopy(get_peft_model_state_dict(pmodel))
            star = " *best*"
        else:
            bad += 1
        # least-bad tracking (v2.1 lesson): when NO epoch passes the guard,
        # the fallback must not blindly keep the LAST epoch -- a monotone
        # collapse (ep1 0.9183 single-regress -> ep2 0.4724 multi-collapse)
        # would ship the WORST state. Rank by (fewest regressed tasks,
        # then highest macroR).
        lb_key = (len(regress), -entry["macro_recall_zeroFP"])
        if lb_state is None or lb_key < lb_best:
            lb_best = lb_key
            lb_ep = ep
            lb_state = {k: v.detach().cpu().clone()
                        for k, v in model.state_dict().items()}
            from peft.utils import get_peft_model_state_dict
            lb_lora = copy.deepcopy(get_peft_model_state_dict(pmodel))
        reg_note = f" REGRESSION={regress}" if regress else ""
        print(f"[m6_train] v2 ep{ep} macroR@zeroFP="
              f"{entry['macro_recall_zeroFP']:.4f}{star}{reg_note}")
        if bad >= patience:
            print(f"[m6_train] v2 early stop (patience {patience})")
            break
    logf.close()
    if best_state is None:
        # every epoch tripped the regression guard: keep the LEAST-BAD
        # epoch (fewest regressed tasks, then highest macroR) -- NOT the
        # last (v2.1: last == collapsed epoch). Fail-visible: the run
        # report still shows which tasks regressed.
        best_state = lb_state
        best_lora = lb_lora
        best_ep = -lb_ep  # negative = least-bad marker, magnitude = epoch
        best_key = -lb_best[1]
        print(f"[m6_train] v2 WARN: no epoch passed the regression guard; "
              f"keeping LEAST-BAD epoch {lb_ep} "
              f"({lb_best[0]} regressed tasks, macroR {-lb_best[1]:.4f})")
    model.load_state_dict(best_state)
    model.eval()

    # restore best LoRA state and re-extract what calibrate() needs:
    # dev pooled + train all-neg trunk inputs (inference mode)
    from peft.utils import set_peft_model_state_dict
    set_peft_model_state_dict(pmodel, best_lora)
    pmodel.eval()
    print(f"[m6_train] v2 best epoch {best_ep} ({best_key:.4f}), "
          f"{time.time() - t0:.0f}s; extracting calib arrays")
    pos = 0
    with torch.no_grad():
        while pos < len(rows_dv):
            chunk = list(range(pos, min(pos + 32, len(rows_dv))))
            ids, attn = _pad_batch(
                [tokinfo_dv[i]["tw"]["input_ids"] for i in chunk], pad_id, device)
            f, _ = forward_extract(pmodel.get_base_model(), ids, attn,
                                   layers, "mean+last", tok_layers)
            Xdv[chunk] = f.numpy()
            pos += len(chunk)
    if t6_sep:
        # ---- v2.2 T6 structural separation: head-only stage ------------- #
        # The T6 head trains NOW on the frozen adapted trunk (joint loop
        # never touched it). Optional init from a prior healthy checkpoint
        # (arch: v2's T6 head, 0.952/1.0). Selection by dev T6 zero-FP
        # recall in log-P (guard-consistent domain), on the RESTORED best
        # state's dev features (Xdv, just extracted above).
        if t6_init_from:
            sd6 = torch.load(t6_init_from, map_location="cpu",
                             weights_only=False)
            sd6 = sd6.get("state", sd6)
            t6_sd = {k.split("heads.T6.", 1)[1]: v for k, v in sd6.items()
                     if k.startswith("heads.T6.")}
            if t6_sd:
                model.heads["T6"].load_state_dict(t6_sd)
                print(f"[m6_train] T6 head init from {t6_init_from}")
            else:
                print(f"[m6_train] WARN: no heads.T6.* keys in "
                      f"{t6_init_from}; fresh init")
        lab_tr = np.where(t6c >= 0)[0]
        print(f"[m6_train] T6 stage: extracting {len(lab_tr)} T6-labeled "
              f"train rows through adapted trunk")
        X6 = np.zeros((len(lab_tr), in_dim), dtype=np.float32)
        pos = 0
        with torch.no_grad():
            while pos < len(lab_tr):
                chunk = lab_tr[pos:pos + 32].tolist()
                ids, attn = _pad_batch(
                    [tokinfo_tr[i]["tw"]["input_ids"] for i in chunk],
                    pad_id, device)
                f, _ = forward_extract(pmodel.get_base_model(), ids, attn,
                                       layers, "mean+last", tok_layers)
                X6[pos:pos + len(chunk)] = f.numpy()
                pos += len(chunk)
        y6 = torch.tensor(t6c[lab_tr], dtype=torch.long, device=device)
        X6_t = torch.tensor(X6, device=device)
        for p_ in model.parameters():
            p_.requires_grad_(False)
        for p_ in model.heads["T6"].parameters():
            p_.requires_grad_(True)
        opt6 = torch.optim.AdamW(model.heads["T6"].parameters(),
                                 lr=float(tr.get("learning_rate", 1e-3)),
                                 weight_decay=wd)
        rng6 = np.random.default_rng(123)
        m6d_np = t6dv >= 0
        best_r6, best_sd6, bad6 = -1.0, None, 0
        n6 = len(X6_t)
        Xdv_t = torch.tensor(Xdv, device=device)
        for ep6 in range(30):
            model.heads["T6"].train()
            perm = rng6.permutation(n6)
            for s6 in range(0, n6, 4096):
                bidx6 = torch.tensor(perm[s6:s6 + 4096], device=device)
                loss6 = torch.nn.functional.cross_entropy(
                    model(X6_t[bidx6])["T6"], y6[bidx6])
                opt6.zero_grad()
                loss6.backward()
                opt6.step()
            # dev selection: zero-FP recall in log-P domain
            model.eval()
            with torch.no_grad():
                o6 = model(Xdv_t)["T6"]
                lp6 = torch.log_softmax(o6.double(), dim=-1)[:, 0] \
                    .cpu().numpy()
            ps6 = lp6[m6d_np & (t6dv == 1)]
            ns6 = lp6[m6d_np & neg_dv]
            r6 = round(float((ps6 > float(ns6.max())).mean()), 4) \
                if len(ps6) and len(ns6) else None
            print(f"[m6_train] T6 stage ep{ep6} dev recall@zeroFP={r6}")
            if r6 is not None and r6 > best_r6:
                best_r6, bad6 = r6, 0
                best_sd6 = {k: v.detach().cpu().clone() for k, v in
                            model.heads["T6"].state_dict().items()}
            else:
                bad6 += 1
                if bad6 >= 3:
                    break
        if best_sd6:
            model.heads["T6"].load_state_dict(best_sd6)
        for p_ in model.parameters():
            p_.requires_grad_(True)
        print(f"[m6_train] T6 stage done (best dev recall@zeroFP="
              f"{best_r6})")
    neg_idx = np.where(neg_all)[0]
    A = {"pooled": Xdv, "Y": Ydv, "t6c": t6dv, "neg_all": neg_dv,
         "mirror": mirror_dv}
    # D dict for calibrate() = dev arrays (same as A here)
    D = {"pooled": Xdv, "Y": Ydv, "t6c": t6dv, "neg_all": neg_dv,
         "mirror": mirror_dv}
    # trunk inputs for centers come from train rows through the SAME probe
    # trunk: extract pooled train (all-neg subset is what centers use, but
    # fit_mahalanobis selects by Y; extract a capped subsample for speed)
    cap = int(tr.get("lora_center_max_rows", 20000))
    sel = rng.choice(len(rows_tr), size=min(cap, len(rows_tr)),
                     replace=False).tolist() if len(rows_tr) > cap \
        else list(range(len(rows_tr)))
    Xtr = np.zeros((len(sel), in_dim), dtype=np.float32)
    pos = 0
    with torch.no_grad():
        while pos < len(sel):
            chunk = sel[pos:pos + 32]
            ids, attn = _pad_batch(
                [tokinfo_tr[i]["tw"]["input_ids"] for i in chunk], pad_id, device)
            f, _ = forward_extract(pmodel.get_base_model(), ids, attn,
                                   layers, "mean+last", tok_layers)
            Xtr[pos:pos + len(chunk)] = f.numpy()
            pos += len(chunk)
    A = {"pooled": Xtr, "Y": Y[sel], "t6c": t6c[sel], "neg_all": neg_all[sel],
         "mirror": mirror[sel]}
    # save adapter next to heads (peft directory format: adapter_config.json
    # + adapter_model.safetensors, loadable via PeftModel.from_pretrained)
    pmodel.save_pretrained(str(out_dir / "adapter"))
    print(f"[m6_train] v2 adapter saved to {out_dir / 'adapter'}")
    TB = TBd = None  # BIO handled on-the-fly in v2; calibrate uses pooled only
    return model, A, D, TB, TBd


# --------------------------------------------------------------------------- #
# stage C: Mahalanobis OOD + two-band calibration (dev-only)
# --------------------------------------------------------------------------- #
def trunk_features(model, X):
    with torch.no_grad():
        dev = next(model.parameters()).device
        return model.trunk(torch.tensor(X).to(dev)).cpu().numpy()


def fit_mahalanobis(Ztr, Ytr, lam=0.1):
    """Dual centers (benign/attack) + shared shrunk covariance on trunk feats."""
    any_pos = (Ytr == 1).any(axis=1)
    annotated = (Ytr >= 0).any(axis=1)
    zb = Ztr[annotated & ~any_pos]
    za = Ztr[annotated & any_pos]
    assert len(zb) >= 10 and len(za) >= 10, \
        f"need >=10 rows per class for Mahalanobis (b={len(zb)}, a={len(za)})"
    mu_b, mu_a = zb.mean(0), za.mean(0)
    Zc = np.concatenate([zb, za]) - np.concatenate([np.tile(mu_b, (len(zb), 1)),
                                                    np.tile(mu_a, (len(za), 1))])
    Sigma = (Zc.T @ Zc) / max(1, len(Zc))
    d = Sigma.shape[0]
    Sigma = (1 - lam) * Sigma + lam * np.eye(d)
    # jittered inverse (double precision)
    Sig_inv = np.linalg.inv(Sigma.astype(np.float64) + 1e-6 * np.eye(d))
    return {"mu_benign": mu_b.tolist(), "mu_attack": mu_a.tolist(),
            "sigma_inv": Sig_inv.tolist(), "lambda": lam, "dim": d}


def mahal_dist(centers, Z):
    mu_b = np.array(centers["mu_benign"], dtype=np.float64)
    mu_a = np.array(centers["mu_attack"], dtype=np.float64)
    Si = np.array(centers["sigma_inv"], dtype=np.float64)
    db = np.einsum("ij,jk,ik->i", Z - mu_b, Si, Z - mu_b)
    da = np.einsum("ij,jk,ik->i", Z - mu_a, Si, Z - mu_a)
    return np.minimum(db, da)


def calibrate(model, A, D, out_dir, cfg):
    """Two-band thresholds per ADR-1 §8/§10 (no temperature, adr-1b §6.1)."""
    dev = next(model.parameters()).device
    Xdv = D["pooled"].astype(np.float32)
    Ydv, t6dv, neg, mirror = D["Y"], D["t6c"], D["neg_all"], D["mirror"]
    with torch.no_grad():
        out_d = model(torch.tensor(Xdv).to(dev))
    scores = {t: torch.sigmoid(out_d[t]).cpu().numpy() for t in
              ("T1", "T2", "T3", "T4doc", "T5")}
    # T6 score = P(high-risk)
    p6 = torch.softmax(out_d["T6"], dim=-1).cpu().numpy()[:, 0]
    scores["T6"] = p6

    Zdv = trunk_features(model, Xdv)
    Xtr = A["pooled"].astype(np.float32)
    centers = fit_mahalanobis(trunk_features(model, Xtr), A["Y"],
                              lam=cfg["probe"].get("aux_ood", {}).get("lambda", 0.1))
    ddev = mahal_dist(centers, Zdv)
    # tau_ood on dev-benign (neg_all incl. mirror) q99.5
    tau_ood = float(np.quantile(ddev[neg], 0.995)) if neg.any() else float(np.quantile(ddev, 0.995))

    calib_neg = neg  # dev-benign ∪ dev-challenge-mirror == neg_all rows
    thresholds, curves = {}, {}
    for j, t in enumerate(TASKS):
        s = scores["T4doc"] if t == "T4" else scores[t]
        g = Ydv[:, j]
        m = g >= 0
        pos_s, neg_s = s[m & (g == 1)], s[m & calib_neg]
        if not len(pos_s) or not len(neg_s):
            thresholds[t] = {"threshold_space": "score",
                             "flag": 0.5, "strong": 0.9}
            curves[t] = []
            continue
        if t == "T6":
            # T6 score = softmax P(high-risk). v1-3 evidence: challenge-mirror
            # benign rows saturate P to 0.99987 -> the old min(0.999) cap
            # broke zero-FP (59 FP leaked). D-16 logit-domain extension:
            # calibrate on log-P (log_softmax class-0), monotone in P with
            # full resolution; echo thresholds as P via exp() (fp64).
            lg6 = torch.log_softmax(out_d["T6"].double(), dim=-1)[:, 0]
            pos_l = lg6[m & (g == 1)].cpu().numpy()
            neg_l = lg6[m & calib_neg].cpu().numpy()
            neg_max = float(neg_l.max())
            pos_q05 = float(np.quantile(pos_l, 0.05))
            delta = pos_q05 - neg_max
            if delta <= 0:
                delta = 0.001  # lp floor ~0.1% P margin; zero-FP preserved
            tau_flag_l = neg_max + delta  # ABOVE benign max lp (lp asc in P)
            pos_q10 = float(np.quantile(pos_l, 0.10))
            tau_strong_l = max(pos_q10, tau_flag_l + 0.01)
            if tau_strong_l >= 0.0:      # lp of P=1 is unreachable
                tau_strong_l = -1e-9
            thresholds[t] = {
                "threshold_space": "logit",
                "flag": round(float(np.exp(tau_flag_l)), 8),
                "strong": round(float(np.exp(tau_strong_l)), 8),
                # lp values live near 0 (P near 1): 4dp rounding destroys
                # the resolution the log-P domain exists to preserve
                "flag_logit": round(tau_flag_l, 8),
                "strong_logit": round(tau_strong_l, 8)}
        else:
            # T1-T5: LOGIT-SPACE calibration (ADR D8 zero-FP construction):
            # fp32 sigmoid saturates to 1.0 at logit>~16.6, collapsing score
            # resolution; a score cap (min(0.999,...)) breaks zero-FP whenever
            # benign rows saturate. Thresholds derived on logits, echoed as
            # scores.
            lg = out_d["T4doc" if t == "T4" else t].cpu().numpy()
            pos_l, neg_l = lg[m & (g == 1)], lg[m & calib_neg]
            neg_max = float(neg_l.max())
            pos_q05 = float(np.quantile(pos_l, 0.05))
            delta = pos_q05 - neg_max
            if delta <= 0:
                delta = 1.0  # logit-scale margin (adr-1b: margin, no temp)
            tau_flag_l = neg_max + delta
            pos_q10 = float(np.quantile(pos_l, 0.10))
            tau_strong_l = max(pos_q10, tau_flag_l + 1.0)
            thresholds[t] = {
                "threshold_space": "logit",
                "flag": round(float(torch.sigmoid(torch.tensor(tau_flag_l))), 6),
                "strong": round(float(torch.sigmoid(torch.tensor(tau_strong_l))), 6),
                "flag_logit": round(tau_flag_l, 4),
                "strong_logit": round(tau_strong_l, 4)}
        grid = np.unique(np.concatenate([
            np.quantile(pos_s, np.linspace(0, 1, 21)),
            np.quantile(neg_s, np.linspace(0, 1, 21))]))
        curves[t] = [
            {"tau": round(float(v), 6),
             "recall": round(float((pos_s > v).mean()), 4),
             "fp": int((neg_s > v).sum()), "n_neg": int(len(neg_s))}
            for v in grid]
    return centers, tau_ood, thresholds, curves, scores, ddev


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="M6 config-driven probe training")
    ap.add_argument("--config", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--reuse-cache", action="store_true",
                    help="skip stage A if caches exist")
    ap.add_argument("--recalibrate", action="store_true",
                    help="skip stage B training; load out_dir/probe-heads.pt "
                         "and re-run calibration only (weights untouched)")
    ap.add_argument("--refresh-labels", action="store_true",
                    help="rewrite label arrays in feat_cache from current "
                         "data (label-only hot-fix; features untouched)")
    ap.add_argument("--lora-resume", action="store_true",
                    help="LoRA mode: resume from out_dir/_snapshot.pt "
                         "(heads+adapter+optimizer+scheduler; epoch batch "
                         "order restarts within the resumed epoch)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = REPO / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    lora_mode = bool(cfg.get("train", {}).get("lora", {}).get("enabled"))

    cache_dir = out_dir / "feat_cache"
    if args.refresh_labels:
        refresh_cache_labels(cfg, out_dir)
        return 0
    if lora_mode:
        # v2 (ADR-1 §16): backbone adapted on the fly -- feature cache is
        # meaningless (features change during training); train_stage_b_lora
        # extracts what calibrate() needs post-training.
        assert not args.recalibrate, "--recalibrate is cache-mode only"
        if args.device.startswith("cuda"):
            os_report = torch.cuda.is_available()
            print(f"[m6_train] GPU check (cuda={os_report})")
        model, A, D, TB, TBd = train_stage_b_lora(
            cfg, out_dir, args.device,
            lora_resume=getattr(args, "lora_resume", False))
        return _finalize(model, A, D, TB, TBd, out_dir, cfg, t_start, args)

    have_cache = (cache_dir / "feats_train.npz").is_file() and \
                 (cache_dir / "feats_dev.npz").is_file()
    if have_cache and args.reuse_cache:
        print(f"[m6_train] reusing cache {cache_dir}")
    else:
        if args.device.startswith("cuda"):
            os_report = torch.cuda.is_available()
            print(f"[m6_train] GPU check (cuda={os_report})")
        backbone, tok = load_backbone(cfg["base"]["model_name_or_path"],
                                      cfg["base"].get("dtype", "bf16"), args.device)
        rows_tr = rows_for_split(cfg, "train")
        rows_dv = rows_for_split(cfg, "dev")
        print(f"[m6_train] rows: train={len(rows_tr)} dev={len(rows_dv)}")
        stage_a(cfg, backbone, tok, rows_tr, "train", out_dir, args.device)
        stage_a(cfg, backbone, tok, rows_dv, "dev", out_dir, args.device)
        del backbone, tok
        if args.device.startswith("cuda"):
            torch.cuda.empty_cache()

    if args.recalibrate:
        # calibration-only pass on existing weights: model unchanged,
        # thresholds recomputed (e.g. logit-space fix on a frozen v1)
        A = np.load(cache_dir / "feats_train.npz", allow_pickle=True)
        D = np.load(cache_dir / "feats_dev.npz", allow_pickle=True)
        ckpt = torch.load(out_dir / "probe-heads.pt", map_location="cpu",
                          weights_only=True)
        sd = ckpt["state"] if isinstance(ckpt, dict) and "state" in ckpt else ckpt
        model = M6Probe(A["pooled"].shape[1]).to(args.device)
        model.load_state_dict(sd)
        model.eval()
        bio_dev_path = cache_dir / "tokfeats_dev.npz"
        TBd = np.load(bio_dev_path, allow_pickle=True) if bio_dev_path.is_file() else None
        TB = None
        print(f"[m6_train] recalibrate-only: loaded {out_dir / 'probe-heads.pt'}")
    else:
        model, A, D, TB, TBd = train_stage_b(cfg, cache_dir, out_dir, args.device)

    return _finalize(model, A, D, TB, TBd, out_dir, cfg, t_start, args)


# --------------------------------------------------------------------------- #
# finalize: BIO dev metrics + calibration + artifacts + operating-point report
# (shared by cache-mode and v2 LoRA-mode runs)
# --------------------------------------------------------------------------- #
def _finalize(model, A, D, TB, TBd, out_dir, cfg, t_start, args):
    # BIO head dev metrics (token-level, flat storage gather)
    bio_metrics = {}
    if TBd is not None and len(TBd["lens"]):
        with torch.no_grad():
            TFd = torch.tensor(TBd["feats"].astype(np.float32)).to(args.device)
            BFd = torch.tensor(TBd["bio"].astype(np.int64)).to(args.device)
            offs_d = np.concatenate([[0], np.cumsum(TBd["lens"])])
            tp = fn = 0
            for i in range(len(TBd["lens"])):
                s, e = int(offs_d[i]), int(offs_d[i + 1])
                logits = model.forward_bio(TFd[s:e])[0].cpu().numpy()
                pred = logits.argmax(-1)
                gold = TBd["bio"][s:e]
                tp += int(((pred == gold) & (gold > 0)).sum())
                fn += int(((pred != gold) & (gold > 0)).sum())
        bio_metrics = {"token_recall_pos": round(tp / max(1, tp + fn), 4),
                       "n_pos_tokens": tp + fn}

    centers, tau_ood, thresholds, curves, scores, ddev = calibrate(
        model, A, D, out_dir, cfg)

    # ---- artifacts ----
    torch.save({"state": model.state_dict()}, out_dir / "probe-heads.pt")
    (out_dir / "head_structure.json").write_text(
        json.dumps(model.structure_json(), ensure_ascii=False, indent=2),
        encoding="utf-8")
    (out_dir / "ood_centers.json").write_text(
        json.dumps({"mahalanobis": centers,
                    "tau_ood": round(tau_ood, 4),
                    "ood_score_def": "min(d_benign,d_attack); normalized "
                                     "ood_score = d/(2*tau_ood) clipped [0,1]",
                    "is_ood": "d >= tau_ood",
                    # qa signal-3 (task-10): "strong-too" extends OOD
                    # suppression to the strong band (G4 default-PASS fix);
                    # default remains ADR-1 §8 two-band
                    "suppression_mode": cfg.get("train", {}).get(
                        "suppression_mode", "two-band")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "calib.json").write_text(
        json.dumps({"schema": "m6-thresholds", "schema_version": "0.1.0-deveng",
                    "runpoint_id": f"{cfg['run_id']}-init",
                    "owner": "deveng-m6 (initial; qa-m6 re-freezes)",
                    "calibrated_on": {"split": "dev"},
                    "thresholds": thresholds,
                    "ood": {"mechanism": "mahalanobis-aux",
                            "tau_ood": round(tau_ood, 6),
                            "suppression": "two-band"},
                    "temperature_applied": False,
                    "score_def": "sigmoid(logit); T6 = P(high-risk)",
                    "curves": curves}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # dev metrics at operating point (LOGIT-space comparison, matching
    # m6_infer: fp32 sigmoid saturates to 1.0 at logit>~16.6, so score-space
    # > tau comparisons are unreliable near saturation)
    Ydv, neg = D["Y"], D["neg_all"]
    metrics = {"bio_token": bio_metrics, "tau_ood": round(tau_ood, 4), "tasks": {}}
    with torch.no_grad():
        out_dv = model(torch.tensor(D["pooled"].astype(np.float32))
                       .to(next(model.parameters()).device))
    logits_dv = {t: out_dv["T4doc" if t == "T4" else t].cpu().numpy()
                 for t in ("T1", "T2", "T3", "T4", "T5")}
    # arch task-10 observation item: benign rows whose DISPLAY-layer score
    # saturates (logit > 16.6 -> fp32 sigmoid reports exactly 1.0; ADR-2
    # evidence base). Decision layer is immune (logit-domain bands).
    benign_sat = {t: int((logits_dv[t][neg] > 16.6).sum()) for t in
                  ("T1", "T2", "T3", "T4", "T5")}
    metrics["benign_saturated_display_16.6"] = benign_sat
    print(f"[m6_train] benign display-saturated rows (logit>16.6): {benign_sat}")
    for j, t in enumerate(TASKS):
        s = scores["T4doc"] if t == "T4" else scores[t]
        lg = logits_dv.get(t)
        g = Ydv[:, j]
        m = g >= 0
        thr = thresholds[t]["flag"]
        thr_l = thresholds[t].get("flag_logit")
        if t == "T6":
            pred = (s > thr).astype(np.int8)  # T6: softmax prob, no saturation
        elif thr_l is not None:
            pred = (lg > thr_l).astype(np.int8)
        else:
            pred = (s > thr).astype(np.int8)
        gold = (g == 1).astype(np.int8)
        pos_m, neg_m = m & (gold == 1), m & neg
        rec = float((pred[pos_m] == 1).mean()) if pos_m.any() else None
        fp = int((pred[neg_m] == 1).sum())
        metrics["tasks"][t] = {
            "recall": round(rec, 4) if rec is not None else None,
            "fp_dev_neg": fp, "n_neg": int(neg_m.sum()),
            "thresholds": thresholds[t]}
        extra = (f" tau_logit=({thr_l},{thresholds[t].get('strong_logit')})"
                 if thr_l is not None else "")
        print(f"[m6_train] {t}: recall={rec if rec is None else round(rec, 3)} "
              f"FP={fp}/{int(neg_m.sum())} tau=({thr:.3f},{thresholds[t]['strong']:.3f})"
              f"{extra}")
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "config.json").write_text(
        json.dumps({"config_file": str(args.config), "resolved": cfg},
                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[m6_train] DONE -> {out_dir} ({time.time() - t_start:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
