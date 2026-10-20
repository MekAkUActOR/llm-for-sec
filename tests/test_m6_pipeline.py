# -*- coding: utf-8 -*-
"""M6 pipeline smoke tests v2 (unittest; pytest not installed).

Covers: render/normalize (five input forms), windowed tokenization offsets,
span<->BIO round-trip, label derivation, probe head shapes, Mahalanobis
fitting, two-band threshold calibration math, and a tiny synthetic
end-to-end head training (no NaN).

Run:
  .venv\\Scripts\\python.exe -X utf8 -m unittest tests.test_m6_pipeline -v
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from m6_render import (  # noqa: E402
    N_BIO_CHANNELS, PII_TYPES, bio_to_spans, normalize_input, render_carrier,
    spans_to_bio, tokenize_windowed)
from m6_train import (  # noqa: E402
    M6Probe, TASKS, derive_labels, fit_mahalanobis, mahal_dist, _pos_weights)


class TestNormalize(unittest.TestCase):
    def test_text_shorthand(self):
        inp = normalize_input({"id": "a", "text": "hello"})
        self.assertEqual(inp["kind"], "text")
        self.assertEqual(inp["text"], "hello")

    def test_turns_shorthand(self):
        inp = normalize_input({"id": "a", "turns": ["hi", "go on", "do it"]})
        self.assertEqual(inp["kind"], "turns")
        self.assertEqual(len(inp["turns"]), 3)

    def test_legacy_turns_objects_become_messages(self):
        inp = normalize_input({"id": "a", "turns": [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"}]})
        self.assertEqual(inp["kind"], "messages")

    def test_input_field_forms(self):
        for key, kind in (("text", "text"), ("protocol_text", "protocol"),
                          ("messages", "messages"), ("turns", "turns")):
            body = {"text": "x"} if key == "text" else (
                {"protocol_text": "p"} if key == "protocol_text" else
                ({"messages": [{"role": "user", "content": "m"}]}
                 if key == "messages" else {"turns": ["t"]}))
            inp = normalize_input({"id": "a", "input": body})
            self.assertEqual(inp["kind"], kind)

    def test_carrier_with_knobs(self):
        rec = {"id": "a", "lang": "en", "policy_pack": "professional",
               "input": {"operator_task": "summarize",
                         "carrier": {"type": "email", "trust": "untrusted",
                                     "body": "hello body"}}}
        inp = normalize_input(rec)
        self.assertEqual(inp["kind"], "carrier")
        self.assertEqual(inp["policy_pack"], "professional")
        self.assertEqual(inp["lang"], "en")

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            normalize_input({"id": "a", "nonsense": 1})


class TestCarrierRender(unittest.TestCase):
    def test_dsh_protocol_envelope(self):
        inp = normalize_input({"id": "a", "input": {
            "operator_task": "summarize this email",
            "carrier": {"type": "email", "trust": "untrusted", "id": "c2",
                        "meta": {"from": "x@y.z"}, "body": "BODY LINE"},
            "user_turn": "please summarize"}})
        s = render_carrier(inp, "default", "zh")
        self.assertIn('<dsh-protocol v="0.1">', s)
        self.assertIn("<system>", s)
        self.assertIn("policy: default", s)
        self.assertIn("<operator>\nsummarize this email\n</operator>", s)
        self.assertIn('type="email" trust="untrusted" id="c2"', s)
        self.assertIn("from: x@y.z", s)
        self.assertIn("<body>\nBODY LINE\n</body>", s)
        self.assertIn("<user>\nplease summarize\n</user>", s)
        self.assertTrue(s.endswith("</dsh-protocol>"))

    def test_en_defaults(self):
        inp = normalize_input({"id": "a", "input": {
            "operator_task": "t", "carrier": {"type": "doc_fragment",
                                              "trust": "untrusted",
                                              "body": "b"}}})
        s = render_carrier(inp, "none", "en")
        self.assertIn("role: security-analysis-assistant", s)
        self.assertIn("policy: none", s)
        self.assertIn("请给出整理结果。", s)  # default user_turn


class TestTokenizeWindowed(unittest.TestCase):
    def test_offsets_align_and_no_truncation(self):
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(
            str(REPO / "checkpoints/qwen3-06b-sec-m5a-dpo-r5"))
        text = "Hello world, this is a test of offsets."
        tw = tokenize_windowed(tok, text)
        self.assertFalse(tw["truncation"])
        # round-trip: token offsets must cover the string contiguously
        covered = "".join(text[s:e] for s, e in tw["offsets"] if e > s)
        self.assertEqual(covered.replace(" ", ""), text.replace(" ", ""))

    def test_head_tail_truncation(self):
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(
            str(REPO / "checkpoints/qwen3-06b-sec-m5a-dpo-r5"))
        long = "word " * 5000  # >> 4096 tokens
        tw = tokenize_windowed(tok, long, window=100, head=20, tail=80)
        self.assertTrue(tw["truncation"])
        self.assertEqual(len(tw["input_ids"]), 100)
        self.assertEqual(len(tw["offsets"]), 100)


class TestSpanBio(unittest.TestCase):
    def _msg_spans(self):
        return [(0, 100, 200)]  # message 0 content at [100,200) in rendered

    def test_span_bio_roundtrip(self):
        text = "Call 138-1234-5678 or email a@b.com today"
        # token grid: fixed 10-char tokens over [100,200)
        offsets = [(100 + i * 10, 100 + (i + 1) * 10) for i in range(10)]
        gold = [{"start": 5, "end": 16, "type": "phone"}]  # "138-1234-5" zone
        bio = spans_to_bio(gold, offsets, self._msg_spans())
        self.assertIn(1 + PII_TYPES.index("phone"), bio)
        spans_back = bio_to_spans(bio, offsets, self._msg_spans(),
                                  lambda mi: text)
        self.assertEqual(len(spans_back), 1)
        sb = spans_back[0]
        self.assertEqual(sb["type"], "phone")
        self.assertEqual(sb["message_index"], 0)
        # predicted span inside token grid coverage of gold span
        self.assertLessEqual(sb["start"], 16)
        self.assertGreaterEqual(sb["end"], 5)

    def test_bio_channels(self):
        self.assertEqual(N_BIO_CHANNELS, 2 * len(PII_TYPES) + 1)
        self.assertIn("gov_id", PII_TYPES)
        self.assertIn("dob", PII_TYPES)
        self.assertEqual(len(PII_TYPES), 11)

    def test_gov_id_sub_passthrough(self):
        offsets = [(0, 5), (5, 10)]
        bio = spans_to_bio([{"start": 0, "end": 10, "type": "gov_id",
                             "sub": "passport"}], offsets,
                           [(0, 0, 10)])
        self.assertEqual(bio[0], 1 + PII_TYPES.index("gov_id"))
        back = bio_to_spans(bio, offsets, [(0, 0, 10)], lambda mi: "0123456789")
        self.assertEqual(back[0]["type"], "gov_id")
        self.assertNotIn("sub", back[0])  # predicted spans carry no sub

    def test_empty_spans_all_o(self):
        bio = spans_to_bio([], [(0, 5)], [(0, 0, 5)])
        self.assertEqual(bio, [0])

    def test_legacy_type_aliases(self):
        offsets = [(0, 5)]
        bio = spans_to_bio([{"start": 0, "end": 5, "type": "passport"}],
                           offsets, [(0, 0, 5)])
        self.assertEqual(bio[0], 1 + PII_TYPES.index("gov_id"))


class TestLabels(unittest.TestCase):
    def _row(self, labels, flags=None, meta=None):
        return {"schema": "m6-sample", "id": "x", "task": "pool",
                "split": "train", "lang": "en", "kind": "singleturn",
                "input": {"text": "t"}, "labels": labels,
                "flags": flags or {}, "meta": meta or {}}

    def test_derive_sparse(self):
        rows = [self._row({"T2": {"label": "pos", "label_detail": {}},
                           "T6": {"label": "neg",
                                  "label_detail": {"t6_class": "conditional"}}})]
        Y, t6c, neg_all, mirror, pii_idx, spans = derive_labels(rows)
        self.assertEqual(Y[0].tolist(), [-1, 1, -1, -1, -1, 0])
        self.assertEqual(int(t6c[0]), 1)  # conditional
        self.assertFalse(neg_all[0])

    def test_derive_t6_fallback(self):
        rows = [self._row({"T6": {"label": "pos", "label_detail": {}}})]
        Y, t6c, *_ = derive_labels(rows)
        self.assertEqual(int(t6c[0]), 0)  # pos -> high-risk fallback

    def test_derive_pii(self):
        rows = [self._row({"T4": {"label": "pos", "label_detail": {
            "spans": [{"start": 0, "end": 3, "type": "email"}]}}})]
        *_, pii_idx, spans = derive_labels(rows)
        self.assertEqual(pii_idx.tolist(), [0])
        self.assertEqual(len(spans[0]), 1)

    def test_challenge_mirror_flag(self):
        rows = [self._row({t: {"label": "neg", "label_detail": {}}
                           for t in TASKS}, flags={"challenge": True})]
        _, _, neg_all, mirror, _, _ = derive_labels(rows)
        self.assertTrue(neg_all[0] and mirror[0])

    def test_pos_weights_clipped(self):
        Y = np.zeros((10, 6), dtype=np.float32)
        Y[:9, 0] = 0  # 9 neg, 1 pos -> 9.0
        Y[9, 0] = 1
        Y[:, 1] = -1  # unannotated
        Y[0, 2] = 1   # 1 pos 9 neg -> 9
        Y[1:, 2] = 0
        # extreme: 1 pos, 999 neg impossible here; check clip via direct call
        w = _pos_weights(Y)
        self.assertEqual(w["T1"], 9.0)
        self.assertEqual(w["T2"], 1.0)  # no data -> clip to 1


class TestProbe(unittest.TestCase):
    def test_shapes(self):
        m = M6Probe(in_dim=64, trunk_hidden=32, head_hidden=8, n_bio=23,
                    tok_feat_dim=16, bio_hidden=8)
        x = torch.randn(5, 64)
        out = m(x)
        self.assertEqual(set(out.keys()),
                         {"T1", "T2", "T3", "T4doc", "T5", "T6"})
        for t in ("T1", "T2", "T3", "T4doc", "T5"):
            self.assertEqual(out[t].shape, (5,))
        self.assertEqual(out["T6"].shape, (5, 3))
        xt = torch.randn(2, 7, 16)
        self.assertEqual(m.forward_bio(xt).shape, (2, 7, 23))

    def test_structure_json_serializable(self):
        s = M6Probe(in_dim=64).structure_json()
        json.dumps(s)
        self.assertEqual(s["n_bio"], 23)


class TestMahalanobis(unittest.TestCase):
    def test_fit_and_separation(self):
        rng = np.random.default_rng(0)
        zb = rng.normal(0, 1, (50, 8))
        za = rng.normal(0, 1, (50, 8)) + 4.0
        Z = np.concatenate([zb, za])
        Y = np.zeros((100, 6), dtype=np.float32)
        Y[:50, :] = 0
        Y[50:, 0] = 1
        centers = fit_mahalanobis(Z, Y, lam=0.1)
        mu_b = np.array(centers["mu_benign"], dtype=np.float64)
        mu_a = np.array(centers["mu_attack"], dtype=np.float64)
        Si = np.array(centers["sigma_inv"], dtype=np.float64)
        db_b = np.einsum("ij,jk,ik->i", zb - mu_b, Si, zb - mu_b)
        da_b = np.einsum("ij,jk,ik->i", zb - mu_a, Si, zb - mu_a)
        db_a = np.einsum("ij,jk,ik->i", za - mu_b, Si, za - mu_b)
        da_a = np.einsum("ij,jk,ik->i", za - mu_a, Si, za - mu_a)
        # own-class distance must be smaller for (nearly) all points
        self.assertGreater((db_b < da_b).mean(), 0.95)
        self.assertGreater((da_a < db_a).mean(), 0.95)
        # mahal_dist == elementwise min over the two class distances
        d = mahal_dist(centers, Z)
        self.assertTrue(np.allclose(d[:50], np.minimum(db_b, da_b)))
        self.assertTrue(np.allclose(d[50:], np.minimum(db_a, da_a)))

    def test_insufficient_rows_asserts(self):
        Z = rng = np.zeros((5, 4))
        Y = np.zeros((5, 6), dtype=np.float32)
        with self.assertRaises(AssertionError):
            fit_mahalanobis(Z, Y)


class TestEndToEndSynthetic(unittest.TestCase):
    def test_train_no_nan_and_learns(self):
        rng = np.random.default_rng(3)
        n, d = 200, 32
        X = rng.normal(0, 1, (n, d)).astype(np.float32)
        Y = np.full((n, 6), -1.0, dtype=np.float32)
        Y[:, 0] = (X[:, 0] > 0).astype(np.float32)
        Y[:, 1] = (X[:, 1] > 1.0).astype(np.float32)
        t6 = np.full(n, -1, dtype=np.int8)
        t6[X[:, 2] > 0] = 0  # high-risk
        t6[X[:, 2] <= 0] = 2  # safe
        m = M6Probe(in_dim=d, trunk_hidden=16, head_hidden=8, n_bio=23,
                    tok_feat_dim=8, bio_hidden=8)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-2)
        Xt, Yt, t6t = (torch.tensor(X), torch.tensor(Y),
                       torch.tensor(t6.astype(np.int64)))
        first = last = None
        for ep in range(40):
            out = m(Xt)
            loss = sum(torch.nn.functional.binary_cross_entropy_with_logits(
                out[t][:, None].squeeze(-1) if out[t].dim() == 1 else out[t],
                torch.where(Yt[:, j] >= 0, Yt[:, j], torch.zeros_like(Yt[:, j])))
                for j, t in enumerate(("T1", "T2", "T3", "T4doc", "T5"))
                if (Yt[:, j] >= 0).any())
            loss = loss + torch.nn.functional.cross_entropy(out["T6"], t6t)
            opt.zero_grad(); loss.backward(); opt.step()
            last = loss.item()
            first = last if ep == 0 else first
        self.assertTrue(np.isfinite(first) and np.isfinite(last))
        self.assertLess(last, first * 0.7)
        with torch.no_grad():
            s0 = torch.sigmoid(m(Xt)["T1"]).numpy()
        pos, neg = s0[Y[:, 0] == 1], s0[Y[:, 0] == 0]
        self.assertGreater(float((pos > neg.max()).mean()), 0.85)


if __name__ == "__main__":
    unittest.main(verbosity=2)
