# -*- coding: utf-8 -*-
"""M6 DEV-3 v2: single-pass six-task inference runtime (m6-inference schema).

One forward pass per input through the r5 backbone -> pooled features ->
shared trunk + heads -> two-band decision + OOD suppression -> Response.

Output rows (JSONL) conform to docs/m6/schemas/m6-inference.schema.json:
  {schema, schema_version, request_id, abstain, abstain_reason, ood,
   tasks:{T1..T6:{flag,score,label,suppressed,findings,spans?,detail?}},
   thresholds_applied:{T1..T6:{flag,strong},source,tau_ood}, decision,
   latency_ms?, verdict_line}

Decision (ADR-1 §8, two-band; logit-space comparison, schema v0.3.13 /
arch §6.12 draft): when the runpoint provides flag_logit/strong_logit the
bands compare LOGITS (fp32 sigmoid saturates to 1.0 at logit>~16.6, which
collapses score resolution); the score fields are display values computed
in fp64 (interim measure pending ADR-2 full logit-domain unification):
  logit > strong_logit              -> flag (OOD cannot suppress; unless the
                                       runpoint sets suppression_mode=
                                       "strong-too" - qa signal-3, G4 fix)
  flag_logit < logit <= strong_logit-> flag unless is_ood (suppressed marker)
  logit <= flag_logit               -> pass
Without logit keys (legacy runpoints, T6 softmax prob): score-space bands.
D-7 discipline: a PARTIAL logit spec (flag_logit without strong_logit or
vice versa) hard-fails -- never silently fall back to score space.
  T4 flag = doc-band OR spans nonempty (spans = strong evidence)
  abstain = (decision==pass AND is_ood AND weak-band hit)   [ADR-1 §8;
    suppressed task markers stay as audit trail even when abstain=false]
  decision = flag if any task flag else pass (lowercase enum, D-2)
  score = sigmoid(logit) raw scale, fp64 compute (adr-1b 6.1: NO
  temperature applied); T6 score = P(high-risk) via softmax (fp64);
  ood.score = RAW Mahalanobis distance (>=0, unnormalized; sysdesign v0.3.0).

Threshold priority: request override (--thresholds-json, partial ok)
  > runpoint file (--runpoint, m6-thresholds schema)
  > checkpoint calib.json (config-default).

Determinism: fixed input-order batching, fp32 pooling aggregation, no
timing fields inside output rows.

Usage:
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_infer.py --head checkpoints\\m6-v1 \
      --input in.jsonl --output out.jsonl [--runpoint configs/m6-runpoint-*.json] \
      [--thresholds-json ovr.json] [--ood-threshold 0.9] [--determinism-check]
  stub (qa bring-up): --stub --head <any-empty-dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_feat_probe import load_backbone, forward_extract  # noqa: E402
from m6_render import (  # noqa: E402
    PII_TYPES, bio_to_spans, normalize_input, render, tokenize_windowed)
from m6_train import M6Probe, TASKS  # noqa: E402

DEFAULT_CKPT = "checkpoints/qwen3-06b-sec-m5a-dpo-r5"
SCHEMA_VERSION = "0.3.3"  # 0.3.3: optional per-task logit (sysdesign v0.3.22)


def _read_tau_ood(ood_cfg: dict, src: str) -> float:
    """D-7 fail-closed: read ood.tau_ood (contract key); legacy 'threshold'
    tolerated with a warning; missing entirely is a hard error (silent
    fallback would disable abstention -- raw-distance scale ~1.0 never fires).
    """
    if "tau_ood" in ood_cfg:
        return float(ood_cfg["tau_ood"])
    if "threshold" in ood_cfg:
        print(f"[m6_infer] WARN: {src} uses legacy key 'ood.threshold'; "
              f"contract key is 'ood.tau_ood' (read anyway)")
        return float(ood_cfg["threshold"])
    raise KeyError(f"{src}: missing ood.tau_ood (fail-closed, D-7)")
PRED_LABELS = {
    "T1": ("contains-risk", "clean"), "T2": ("jailbreak", "normal"),
    "T3": ("malicious", "benign"), "T4": ("contains-pii", "clean"),
    "T5": ("contains-injection", "clean"),
}
T6_CLASSES = ["high-risk", "safe", "conditional"]


def _band_of(score, logit, thr, is_t6=False):
    """Two-band decision for one task (pure; unit-tested).

    Logit-space comparison when the runpoint provides flag_logit/strong_logit
    (fp32 sigmoid saturates to 1.0 at logit>~16.6, collapsing score
    resolution); score-space otherwise (legacy runpoints). D-7: PARTIAL logit
    spec hard-fails (never silently fall back to score space on an
    incomplete logit runpoint). T6 with a full logit spec carries LOG-P
    thresholds (D-16 extension; softmax P saturates near 1.0 the same way
    sigmoid does) -- compare log(P), score is fp64. Returns (strong, mid).
    """
    fl, sl = thr.get("flag_logit"), thr.get("strong_logit")
    if (fl is None) != (sl is None):
        raise ValueError(
            f"partial logit spec (flag_logit={fl!r}, strong_logit={sl!r})"
            " -- fail-closed, D-7")
    if fl is None:
        return score > thr["strong"], thr["flag"] < score <= thr["strong"]
    if is_t6:
        import math
        lp = math.log(score) if score > 0 else float("-inf")
        return lp > sl, fl < lp <= sl
    return logit > sl, fl < logit <= sl


def _pad_batch(seqs, pad_id, device):
    T = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), T), pad_id, dtype=torch.long)
    attn = torch.zeros((len(seqs), T), dtype=torch.long)
    for i, s in enumerate(seqs):
        ids[i, :len(s)] = torch.tensor(s, dtype=torch.long)
        attn[i, :len(s)] = 1
    return ids.to(device), attn.to(device)


class M6Inferencer:
    def __init__(self, head_dir: str, backbone_ckpt: str = DEFAULT_CKPT,
                 runpoint: str | None = None, threshold_overrides: dict | None = None,
                 ood_threshold_override: float | None = None,
                 device: str = "cuda", dtype: str = "bf16", batch_size: int = 8,
                 stub: bool = False, stub_seed: int = 1234,
                 with_latency: bool = False):
        self.device = device
        self.batch_size = batch_size
        self.stub = stub
        self.with_latency = with_latency
        self._row_latency_ms = 0.0
        hd = Path(head_dir)

        # ---- heads ----
        if stub:
            hd.mkdir(parents=True, exist_ok=True)
            torch.manual_seed(stub_seed)
            self.model = M6Probe(in_dim=10240).to(device).eval()
            for p in self.model.parameters():
                torch.nn.init.normal_(p, 0.0, 0.05)
            self.model_id, self.heads_ref = "m6-stub", "stub"
        else:
            for need in ("probe-heads.pt", "head_structure.json",
                         "calib.json", "ood_centers.json"):
                assert (hd / need).is_file(), f"head ckpt missing {need} in {hd}"
            struct = json.loads((hd / "head_structure.json").read_text(encoding="utf-8"))
            self.model = M6Probe(**{k: struct[k] for k in
                                    ("in_dim", "trunk_hidden", "head_hidden",
                                     "dropout", "n_bio", "tok_feat_dim",
                                     "bio_hidden")}).to(device).eval()
            state = torch.load(hd / "probe-heads.pt", map_location="cpu",
                               weights_only=True)
            self.model.load_state_dict(state["state"])
            self.model_id = hd.name
            try:
                self.heads_ref = str((hd / "probe-heads.pt").resolve()
                                     .relative_to(REPO))
            except ValueError:
                self.heads_ref = str((hd / "probe-heads.pt").resolve())

        # ---- thresholds (priority: request > runpoint > config-default) ----
        calib = None if stub else json.loads(
            (hd / "calib.json").read_text(encoding="utf-8-sig"))
        base_thr = {t: dict(calib["thresholds"][t]) for t in TASKS} if calib else \
            {t: {"flag": 0.5, "strong": 0.9} for t in TASKS}
        self.ood_cfg = (calib or {}).get("ood", {})
        self.tau_ood = _read_tau_ood(self.ood_cfg, f"{hd}/calib.json") if calib \
            else 1.0
        if runpoint:
            rp = json.loads(Path(runpoint).read_text(encoding="utf-8-sig"))
            for t in TASKS:
                base_thr[t] = dict(rp["thresholds"][t])
            self.tau_ood = _read_tau_ood(rp.get("ood", {}), runpoint)
            self.source = "runpoint-file"
        else:
            self.source = "config-default" if not stub else "config-default"
        if threshold_overrides:
            for t, v in threshold_overrides.items():
                assert t in TASKS, f"unknown task key {t}"
                if isinstance(v, (int, float)):
                    base_thr[t] = {"flag": float(v),
                                   "strong": base_thr[t]["strong"]}
                else:
                    nt = {"flag": float(v["flag"]),
                          "strong": float(v["strong"])}
                    # logit keys pass through (schema v0.3.13 ThresholdBand)
                    if "flag_logit" in v or "strong_logit" in v:
                        nt["flag_logit"] = v.get("flag_logit")
                        nt["strong_logit"] = v.get("strong_logit")
                    base_thr[t] = nt
            self.source = "request-override"
        if ood_threshold_override is not None:
            self.tau_ood = float(ood_threshold_override)
        for t in TASKS:
            assert base_thr[t]["strong"] >= base_thr[t]["flag"] - 1e-9, \
                f"{t}: strong < flag violates ThresholdBand"
            fl, sl = base_thr[t].get("flag_logit"), base_thr[t].get("strong_logit")
            if fl is not None and sl is not None:
                assert sl >= fl, f"{t}: strong_logit < flag_logit violates band"
        self.thresholds = base_thr

        # ---- OOD Mahalanobis (disabled in stub); ood.score = RAW distance ----
        self.ood_centers = None
        # suppression mode from the runpoint (qa signal-3, task-10): default
        # "two-band" = strong band flags regardless of OOD (ADR-1 §8);
        # "strong-too" = strong band is also suppressed when is_ood (G4 fix:
        # OOD-suite rows that leak into the strong band keep default-PASS)
        self.ood_suppress_strong = False
        if not stub:
            oc = json.loads((hd / "ood_centers.json").read_text(
                encoding="utf-8-sig"))
            self.ood_centers = oc["mahalanobis"]
            self.ood_suppress_strong = \
                oc.get("suppression_mode") == "strong-too"

        # ---- backbone (real pipeline in stub mode too) ----
        self.backbone, self.tok = load_backbone(backbone_ckpt, dtype, device)
        self.pad_id = self.tok.pad_token_id or 151643
        # v2 LoRA checkpoints carry a peft adapter dir next to the heads:
        # load it onto the backbone (no-op for v1-class dirs without it)
        adapter_dir = hd / "adapter"
        if adapter_dir.is_dir():
            from peft import PeftModel
            pmodel = PeftModel.from_pretrained(self.backbone, str(adapter_dir))
            pmodel.eval()
            # forward through the peft-wrapped model (LoRA layers active);
            # .config proxies to the base transformer
            self.backbone = pmodel
            print(f"[m6_infer] loaded LoRA adapter from {adapter_dir}")

    # ------------------------------------------------------------------ #
    def _ood(self, Z):
        """Returns (raw_distance [N], is_ood [N] bool). ood.score = raw
        Mahalanobis distance (sysdesign v0.3.0: unnormalized, >=0)."""
        if self.ood_centers is None:
            return np.zeros(len(Z)), np.zeros(len(Z), dtype=bool)
        mu_b = np.array(self.ood_centers["mu_benign"], dtype=np.float64)
        mu_a = np.array(self.ood_centers["mu_attack"], dtype=np.float64)
        Si = np.array(self.ood_centers["sigma_inv"], dtype=np.float64)
        db = np.einsum("ij,jk,ik->i", Z - mu_b, Si, Z - mu_b)
        da = np.einsum("ij,jk,ik->i", Z - mu_a, Si, Z - mu_a)
        d = np.minimum(db, da)
        return d, d >= self.tau_ood

    # ------------------------------------------------------------------ #
    @torch.inference_mode()
    def infer_records(self, records: list[dict]) -> list[dict]:
        t0 = time.time()
        prepared = []
        for r in records:
            try:
                inp = normalize_input(r)
                rendered, msg_spans, fmap = render(self.tok, inp)
                tw = tokenize_windowed(self.tok, rendered)
                prepared.append({"ok": True, "inp": inp, "tw": tw,
                                 "msg_spans": msg_spans, "fmap": fmap,
                                 "kind": inp["kind"]})
            except Exception as e:  # conservative pass on render failure
                prepared.append({"ok": False, "err": str(e), "kind": "?"})

        rows = []
        pos = 0
        while pos < len(records):
            tb = time.time()
            chunk = prepared[pos:pos + self.batch_size]
            ok_idx = [i for i, p in enumerate(chunk) if p["ok"]]
            feats, tokfeats = None, None
            if ok_idx:
                ids, attn = _pad_batch([chunk[i]["tw"]["input_ids"] for i in ok_idx],
                                       self.pad_id, self.device)
                # SINGLE backbone forward for pooled + token states (mission
                # requirement: one forward pass per input)
                f, tf = forward_extract(self.backbone, ids, attn,
                                        [4, 12, 20, 24, 28], "mean+last", [12, 28])
                feats = f.numpy()
                tokfeats = tf.numpy()
            batch_ms = (time.time() - tb) * 1000 / max(1, len(chunk))
            for ci, p in enumerate(chunk):
                rec = records[pos + ci]
                self._row_latency_ms = batch_ms
                row = self._build_row(rec, p, ci, ok_idx, feats, tokfeats)
                rows.append(row)
            pos += self.batch_size
        dt = (time.time() - t0) * 1000
        print(f"[m6_infer] {len(records)} rows in {dt:.0f} ms "
              f"({dt / max(1, len(records)):.1f} ms/row)")
        return rows

    def _verdict_line(self, base, tasks, spans):
        """Single-source verdict_line (SYS-1 §3: same source, same values as
        the response body). decision mirrors the lowercase top-level enum;
        raw suppression audit lives in suppressed_any, never in abstain."""
        return json.dumps({
            "model": self.model_id,
            "decision": base["decision"],
            "abstain": base["abstain"],
            "abstain_reason": base["abstain_reason"],
            "suppressed_any": any(t.get("suppressed") for t in tasks.values()),
            "ood": base["ood"],
            "tasks": {t: {"label": tasks[t]["label"],
                          "score": tasks[t]["score"],
                          "flag": tasks[t]["flag"]} for t in TASKS},
            "pii": {"spans": spans}}, ensure_ascii=False)

    def _build_row(self, rec, p, ci, ok_idx, feats, tokfeats):
        rid = str(rec.get("id", rec.get("request_id", "")))
        base = {
            "schema": "m6-inference-response", "schema_version": SCHEMA_VERSION,
            "request_id": rid, "abstain": False, "abstain_reason": "none",
            "ood": {"is_ood": False, "score": 0.0,
                    "mechanism": "mahalanobis-aux"},
            "tasks": {}, "thresholds_applied": {
                # response band contract = flag/strong/flag_logit/strong_logit
                # only; threshold_space is calib-contract metadata (v0.3.18)
                **{t: {k: v for k, v in self.thresholds[t].items()
                       if k in ("flag", "strong", "flag_logit",
                                "strong_logit")} for t in TASKS},
                "source": self.source, "tau_ood": self.tau_ood},
            "decision": "pass",
        }
        if not p["ok"]:
            base.update(abstain=True, abstain_reason="input_error")
            for t in TASKS:
                base["tasks"][t] = {
                    "flag": False, "score": 0.0, "label": None,
                    "suppressed": False, "findings": [], "detail": None}
            base["verdict_line"] = self._verdict_line(
                base, base["tasks"], [])
            return base

        k = ok_idx.index(ci)
        x = torch.tensor(feats[k:k + 1], dtype=torch.float32).to(self.device)
        out = self.model(x)
        # fp64 sigmoid for reported scores: pushes fp saturation from
        # logit ~16.6 (fp32) to ~37 (arch interim measure pre-ADR-2);
        # band comparisons are logit-space (see _band_of).
        scores = {t: float(torch.sigmoid(out[t][0].double())) for t in
                  ("T1", "T2", "T3", "T4doc", "T5")}
        logits = {t: float(out[t][0]) for t in ("T1", "T2", "T3", "T4doc", "T5")}
        p6 = torch.softmax(out["T6"][0].double(), dim=-1).cpu().numpy()
        scores["T6"] = float(p6[0])
        pred6 = int(out["T6"][0].argmax())

        # PII spans from BIO head (slice to real token count; batch pads beyond)
        xt = torch.tensor(tokfeats[k:k + 1], dtype=torch.float32).to(self.device)
        bio_logits = self.model.forward_bio(xt)[0].cpu().numpy()  # [T_pad, n_bio]
        tw, msg_spans, fmap = p["tw"], p["msg_spans"], p.get("fmap")
        bio = bio_logits.argmax(-1)[:len(tw["input_ids"])].tolist()
        msgs = _addressable_messages(p["inp"])
        spans = bio_to_spans(
            bio, tw["offsets"], msg_spans,
            lambda mi: msgs[mi] if mi < len(msgs) else (msgs[0] if msgs else ""),
            fmap)

        # OOD on trunk features (raw distance)
        with torch.no_grad():
            Z = self.model.trunk(x).cpu().numpy()
        d_ood, is_ood = self._ood(Z)
        is_ood = bool(is_ood[0])

        any_suppressed = False
        tasks = {}
        for t in TASKS:
            s = scores["T4doc"] if t == "T4" else scores[t]
            thr = self.thresholds[t]
            strong, mid = _band_of(s, None if t == "T6" else
                                   (logits["T4doc"] if t == "T4" else logits[t]),
                                   thr, is_t6=(t == "T6"))
            if t == "T4":
                strong = strong or len(spans) > 0
            if strong:
                if self.ood_suppress_strong and is_ood:
                    # qa signal-3 mode: OOD strong-band hits are suppressed
                    # (default-PASS philosophy extends to the strong band)
                    flag, supp = False, True
                    any_suppressed = True
                else:
                    flag, supp = True, False
            elif mid:
                supp = is_ood
                flag = not is_ood
                any_suppressed = any_suppressed or supp
            else:
                flag, supp = False, False
            if t == "T6":
                label = T6_CLASSES[pred6]
            else:
                label = PRED_LABELS[t][0 if flag else 1]
            # D-6: T4 spans are a first-class field (detail reserved for
            # doc_score audit); T6 3-class IS the label (detail null)
            # per-task logit (qa/arch request, red-team A3 dual-mechanism
            # verification + B-family gradient records): T1-T5 = probe
            # logit (pre-sigmoid, unrounded -- saturated score rows carry
            # no resolution); T6 = ln(P) log-P (same semantics as the
            # D-16 threshold domain). Optional schema key.
            if t == "T6":
                t_logit = (math.log(s) if s > 0 else
                           -745.0)  # ln of fp64-denormal floor
            else:
                t_logit = logits["T4doc" if t == "T4" else t]
            entry = {"flag": bool(flag), "score": round(s, 6),
                     "logit": round(t_logit, 6),
                     "label": label, "suppressed": bool(supp),
                     "findings": []}
            if t == "T4":
                entry["spans"] = spans
                entry["detail"] = {"doc_score": round(s, 6)}
            else:
                entry["detail"] = None
            tasks[t] = entry

        decision = "flag" if any(r["flag"] for r in tasks.values()) else "pass"
        # ADR-1 §8: abstain = (decision==PASS ∧ is_ood ∧ weak-band hit).
        # If another task flags, the response is not an abstention; the
        # suppressed markers stay as task-level audit trail only.
        abstain = any_suppressed and decision == "pass"
        base.update(
            abstain=abstain,
            abstain_reason="ood" if abstain else "none",
            ood={"is_ood": is_ood, "score": round(float(d_ood[0]), 6),
                 "mechanism": "mahalanobis-aux"},
            tasks=tasks, decision=decision)
        if self.with_latency:
            # determinism note: only enabled for interactive use, never in
            # batch files (qa hashes byte-identical outputs)
            base["latency_ms"] = round(self._row_latency_ms, 3)
        base["verdict_line"] = self._verdict_line(base, tasks, spans)
        return base

    def infer_file(self, input_path: str, output_path: str) -> dict:
        records = []
        with open(input_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        rows = self.infer_records(records)
        with open(output_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return {"n": len(rows), "output": output_path}


def _addressable_messages(inp: dict) -> list[str]:
    """Original-text contents of user/assistant messages (span coordinates)."""
    k = inp["kind"]
    if k == "text":
        return [inp["text"]]
    if k == "turns":
        return list(inp["turns"])
    if k == "messages":
        return [m["content"] for m in inp["messages"]]
    if k == "protocol":
        return [inp["protocol_text"]]
    if k == "carrier":
        return [inp["carrier"]["body"]]
    return [""]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_overrides(path):
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    ap = argparse.ArgumentParser(description="M6 single-pass six-task inference")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--head", default="checkpoints/m6-v1")
    ap.add_argument("--backbone", default=DEFAULT_CKPT)
    ap.add_argument("--runpoint", default=None,
                    help="m6-thresholds runpoint json (priority over ckpt calib)")
    ap.add_argument("--thresholds-json", default=None,
                    help="request-level partial overrides {T?: float|{flag,strong}}")
    ap.add_argument("--ood-threshold", type=float, default=None)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--stub-seed", type=int, default=1234)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--dtype", default="bf16", choices=["bf16", "fp16", "fp32"])
    ap.add_argument("--determinism-check", action="store_true")
    ap.add_argument("--with-latency", action="store_true",
                    help="include latency_ms top-level (breaks byte determinism; "
                         "interactive use only)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    inf = M6Inferencer(args.head, args.backbone, args.runpoint,
                       load_overrides(args.thresholds_json), args.ood_threshold,
                       args.device, args.dtype, args.batch_size,
                       args.stub, args.stub_seed, args.with_latency)
    summary = inf.infer_file(args.input, args.output)
    digest = sha256_file(args.output)
    print(f"[m6_infer] {summary['n']} rows -> {args.output} sha256={digest}")
    if args.determinism_check:
        tmp = args.output + ".detcheck"
        inf.infer_file(args.input, tmp)
        d2 = sha256_file(tmp)
        ok = d2 == digest
        print(f"[m6_infer] determinism check: {'PASS' if ok else 'FAIL'} ({d2})")
        Path(tmp).unlink()
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
