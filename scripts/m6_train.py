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
from m6_feat_probe import load_backbone, forward_extract  # noqa: E402
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
    rows, seen_map, ndup = [], {}, 0
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
                # shared rows legitimately appear in task files AND pool
                # (verified byte-identical); a CONTENT mismatch is a data bug
                prev = seen_map[r["id"]]
                assert json.dumps(prev, sort_keys=True, ensure_ascii=False) == \
                    json.dumps(r, sort_keys=True, ensure_ascii=False), \
                    f"duplicate id {r['id']} with DIFFERENT content in {f}"
                ndup += 1
                continue
            seen_map[r["id"]] = r
            rows.append(r)
    if ndup:
        print(f"[m6_train] {split}: {ndup} shared rows deduped "
              f"(task files ∩ pool, byte-identical)")
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
            thresholds[t] = {"flag": 0.5, "strong": 0.9}
            curves[t] = []
            continue
        if t == "T6":
            # T6 score = softmax P(high-risk) (bounded, no sigmoid-style
            # saturation at benign max 0.947): score-space thresholds
            neg_max = float(neg_s.max())
            pos_q05 = float(np.quantile(pos_s, 0.05))
            delta = pos_q05 - neg_max
            if delta <= 0:
                delta = 0.02
            tau_flag = min(0.999, neg_max + delta)
            pos_q10 = float(np.quantile(pos_s, 0.10))
            tau_strong = min(0.9999, max(pos_q10, tau_flag + 0.02))
            thresholds[t] = {"flag": round(tau_flag, 6),
                             "strong": round(tau_strong, 6)}
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
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = REPO / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    cache_dir = out_dir / "feat_cache"
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
                    "is_ood": "d >= tau_ood"}, ensure_ascii=False, indent=2),
        encoding="utf-8")
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
