r"""分块 CE 补丁正确性测试（CPU，GPU 空闲时无需等待）。

核心断言：
1. 分块 loss == 原版 loss（mean 路径与 num_items_in_batch 路径，
   fp32 严格 / bf16 放宽容差）；
2. 前向+反向梯度一致（embed/lm_head/末层参数——含 tie_word_embeddings
   的共享参数梯度）；
3. 回退路径（labels None / logits_to_keep>0 / labels 长度不匹配）保持
   原版行为；
4. unpatch() 完全可逆；
5. eval(no_grad) 与全忽略标签边界。

微型 Qwen3 配置（vocab 512 / hidden 64 / 2 层），CPU 秒级。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import patch_chunked_ce as pce  # noqa: E402  import 即 patch

from transformers import Qwen3Config, Qwen3ForCausalLM  # noqa: E402


def _tiny_model(dtype=torch.float32, seed=7, tie=True):
    torch.manual_seed(seed)
    cfg = Qwen3Config(
        vocab_size=512, hidden_size=64, intermediate_size=128,
        num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
        head_dim=16, max_position_embeddings=512,
        tie_word_embeddings=tie, torch_dtype=dtype,
    )
    m = Qwen3ForCausalLM(cfg).to(dtype)
    m.eval()
    return m


def _batch(m, B=2, L=48, seed=13, ignore_frac=0.25):
    g = torch.Generator().manual_seed(seed)
    ids = torch.randint(0, m.config.vocab_size, (B, L), generator=g)
    labels = ids.clone()
    mask = torch.rand(B, L, generator=g) < ignore_frac
    labels[mask] = -100
    return ids, labels


class _Cmp:
    """一次对照实验：同参模型分别跑 原版/补丁 forward+backward。"""

    def __init__(self, dtype=torch.float32, chunk=16, seed=7, tie=True):
        self.model = _tiny_model(dtype, seed, tie)
        self.chunk = chunk

    def run(self, ids, labels, num_items=None):
        m = self.model
        m.train()
        # —— 原版 ——
        pce.unpatch()
        m.zero_grad(set_to_none=True)
        out_o = m(input_ids=ids, labels=labels,
                  num_items_in_batch=num_items)
        out_o.loss.backward()
        self.orig_loss = out_o.loss.detach()
        self.orig_logits = out_o.logits.detach().clone()
        self.orig_grads = {n: p.grad.detach().clone() for n, p in
                           m.named_parameters() if p.grad is not None}
        # —— 补丁 ——
        pce.patch(chunk=self.chunk)
        m.zero_grad(set_to_none=True)
        out_p = m(input_ids=ids, labels=labels,
                  num_items_in_batch=num_items)
        out_p.loss.backward()
        self.patch_loss = out_p.loss.detach()
        self.patch_logits = out_p.logits
        self.patch_grads = {n: p.grad.detach().clone() for n, p in
                            m.named_parameters() if p.grad is not None}
        pce.unpatch()
        return self


def _cmp(dtype=torch.float32, chunk=16, seed=7, tie=True):
    return _Cmp(dtype, chunk, seed, tie)


class TestChunkedCECorrectness(unittest.TestCase):

    def test_loss_equals_original_fp32(self):
        m = _tiny_model()
        ids, labels = _batch(m)
        c = _cmp().run(ids, labels)
        self.assertTrue(torch.isfinite(c.orig_loss))
        self.assertLess((c.patch_loss - c.orig_loss).abs().item(),
                        1e-4, "fp32 分块 loss 必须逐值等于原版")

    def test_loss_equals_original_num_items(self):
        m = _tiny_model()
        ids, labels = _batch(m)
        n_valid = int((labels[:, 1:] != -100).sum())
        num_items = torch.tensor(2 * n_valid)  # 跨累积批语义
        c = _cmp().run(ids, labels, num_items=num_items)
        # ① 补丁 == 原版（同 num_items 直接对照）
        self.assertLess((c.patch_loss - c.orig_loss).abs().item(), 1e-4)
        # ② num_items=2×本地有效数 ⇒ 补丁 loss = 无 num_items 均值的一半
        m.train()
        pce.unpatch()
        ref_mean = m(input_ids=ids, labels=labels).loss.item()
        self.assertAlmostEqual(
            c.patch_loss.item() * 2, ref_mean, places=4)

    def test_gradients_match_fp32(self):
        m = _tiny_model()
        ids, labels = _batch(m)
        c = _cmp().run(ids, labels)
        self.assertEqual(set(c.orig_grads), set(c.patch_grads))
        for n in c.orig_grads:
            d = (c.patch_grads[n] - c.orig_grads[n]).abs().max().item()
            self.assertLess(d, 2e-5, msg=f"grad mismatch @ {n}: {d}")

    def test_bf16_tolerance(self):
        m = _tiny_model(torch.bfloat16, 7)
        ids, labels = _batch(m)
        c = _cmp(dtype=torch.bfloat16).run(ids, labels)
        rel = ((c.patch_loss - c.orig_loss).abs()
               / c.orig_loss.abs().clamp(min=1e-6)).item()
        self.assertLess(rel, 5e-3, "bf16 分块 loss 相对偏差须 <0.5%")

    def test_tied_embedding_grad(self):
        m = _tiny_model()
        ids, labels = _batch(m)
        c = _cmp().run(ids, labels)
        self.assertIs(m.lm_head.weight, m.model.embed_tokens.weight)
        g = c.patch_grads["model.embed_tokens.weight"]
        go = c.orig_grads["model.embed_tokens.weight"]
        self.assertLess((g - go).abs().max().item(), 2e-5)


class TestFallbackPaths(unittest.TestCase):

    def test_no_labels_materializes_logits(self):
        m = _tiny_model()
        ids, _ = _batch(m)
        pce.patch()
        try:
            out = m(input_ids=ids)
            self.assertIsNotNone(out.logits)
            self.assertIsNone(out.loss)
        finally:
            pce.unpatch()

    def test_logits_to_keep_falls_back(self):
        # labels + logits_to_keep：上游本就位长不匹配崩溃——补丁忠实
        # 保留原版行为（含其报错）；无 labels 切片路径正常
        m = _tiny_model()
        ids, labels = _batch(m)
        pce.patch()
        try:
            with self.assertRaises(ValueError):
                m(input_ids=ids, labels=labels, logits_to_keep=8)
            out = m(input_ids=ids, logits_to_keep=8)
            self.assertIsNotNone(out.logits)
            self.assertEqual(out.logits.shape[1], 8)
        finally:
            pce.unpatch()

    def test_label_length_mismatch_crash_parity(self):
        # labels 短于位段：原版 ForCausalLMLoss 崩溃（batch_size 不匹配）
        # ——补丁回退原版路径 = 同样的崩溃（不静默错位）
        m = _tiny_model()
        ids, labels = _batch(m)
        pce.unpatch()
        with self.assertRaises(ValueError):
            m(input_ids=ids, labels=labels[:, :-3])
        pce.patch()
        try:
            with self.assertRaises(ValueError):
                m(input_ids=ids, labels=labels[:, :-3])
        finally:
            pce.unpatch()

    def test_chunked_path_logits_none(self):
        m = _tiny_model()
        ids, labels = _batch(m)
        pce.patch()
        try:
            out = m(input_ids=ids, labels=labels)
            self.assertIsNone(out.logits)
            self.assertIsNotNone(out.loss)
        finally:
            pce.unpatch()


class TestEdgeCases(unittest.TestCase):

    def test_all_labels_ignored(self):
        m = _tiny_model()
        ids, _ = _batch(m)
        labels = torch.full_like(ids, -100)
        pce.patch()
        try:
            out = m(input_ids=ids, labels=labels)
            self.assertEqual(out.loss.item(), 0.0)
        finally:
            pce.unpatch()

    def test_eval_no_grad(self):
        m = _tiny_model()
        ids, labels = _batch(m)
        pce.patch()
        try:
            m.eval()
            with torch.no_grad():
                out = m(input_ids=ids, labels=labels)
            self.assertTrue(torch.isfinite(out.loss))
        finally:
            pce.unpatch()

    def test_partial_ignore_chunks_skipped(self):
        m = _tiny_model()
        ids, labels = _batch(m, L=32)
        labels[:, :16] = -100  # 前两块（chunk=16）全忽略
        c = _cmp().run(ids, labels)
        self.assertLess((c.patch_loss - c.orig_loss).abs().item(), 1e-4)


class TestPatchManagement(unittest.TestCase):

    def test_patch_unpatch_roundtrip(self):
        from transformers.models.qwen3.modeling_qwen3 import \
            Qwen3ForCausalLM
        pce.unpatch()
        self.assertFalse(pce.is_patched(Qwen3ForCausalLM))
        applied = pce.patch()
        self.assertIn(Qwen3ForCausalLM, applied)
        self.assertTrue(pce.is_patched(Qwen3ForCausalLM))
        # 幂等
        self.assertEqual(pce.patch(), [])
        restored = pce.unpatch()
        self.assertIn(Qwen3ForCausalLM, restored)
        self.assertFalse(pce.is_patched())
        # import 即生效契约（模块重新 import 后应回到已补丁态）
        import importlib
        importlib.reload(pce)
        self.assertTrue(pce.is_patched(Qwen3ForCausalLM))
        pce.unpatch()
        pce.patch()  # 留下补丁态供其他测试类使用

    def test_env_disable(self):
        # CHUNKED_CE_DISABLE 在 import 时读取——此处只验证标志语义
        self.assertFalse(pce._DISABLED)


if __name__ == "__main__":
    unittest.main()
