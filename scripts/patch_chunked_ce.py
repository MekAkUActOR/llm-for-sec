r"""分块交叉熵补丁：32k 长上下文训练在 24GB 上的显存可行化。

## 问题（2026-09-27 23:40 OOM 实测）

Qwen3ForCausalLM.forward 物化完整 logits 再算 CE：
- bf16 logits [1, 32768, 151936] ≈ 10 GB（lm_head 输出）
- fp32 上转 ≈ 19.9 GB（ForCausalLMLoss 的 logits.float()）
- 静态占用（fp32 参数+梯度+Adam）≈ 9.6 GB
→ 无融合 CE 的硬上限 ~12k cutoff。liger-kernel 依赖 triton（无
Windows 轮子）死路。

## 方案

拦截点：backbone 输出 hidden_states 之后、lm_head 之前。按位置分块
（默认 4096/块）逐块 lm_head → CE(sum) → 累加；**绝不物化完整 logits**。

两个关键正确性设计：

1. **梯度语义（transformers 5.8 实测源码，非印象）**：
   `transformers/loss/loss_utils.py::fixed_cross_entropy` ——除法发生在
   **模型内部**（reduction="sum" 后 `loss / num_items_in_batch`），
   Trainer（trainer.py::compute_loss）只把 num_items_in_batch 作为
   forward kwarg 传入、不再除。故本补丁：
   - num_items_in_batch 给出 → 返回 Σ_chunk_CE_sum / num_items
   - 未给出（eval/自定义 trainer）→ 返回 Σ / 本地非忽略 token 数
     （与 fixed_cross_entropy 的 "mean" 归约逐值等价）

2. **防 autograd 保留每块 fp32 log_softmax**：F.cross_entropy 反传需
   softmax(logits)，其保存的 fp32 中间量逐块累积 = 8×2.5 GB = 20 GB
   ——重演原灾难。因此每块包裹 `torch.utils.checkpoint`（
   use_reentrant=False）：前向只保留 (hidden_chunk, W, bias, labels)
   （约 8 MB），反传时重算该块 logits。块内瞬态峰值 =
   4096×151936×(2+4) B ≈ 3.7 GB，与 C1 实测同量级（安全）。

## 语义契约（与原版逐项对齐）

| 路径 | 行为 |
|---|---|
| labels 给出 + logits_to_keep==0（训练全量位段） | 分块 CE；**logits=None**（pt 训练只消费 loss；物化即破功） |
| labels 为 None | 原版行为（完整 logits，生成/无标签推理） |
| logits_to_keep != 0 + labels | 回退原版（该路径 labels 对齐语义未定义于训练，且切片长度小） |
| num_items_in_batch | 透传语义见上 |

## 用法

    import scripts.patch_chunked_ce          # import 即生效（类级补丁）
    scripts.patch_chunked_ce.unpatch()       # 可逆

LF pt 流程：tuner→trainer→model(**inputs) 带 labels → 类级 forward
拦截自动生效，无需改 LF。环境旋钮：
- CHUNKED_CE_CHUNK（默认 4096，块位置数）
- CHUNKED_CE_DISABLE=1（import 但不生效）

红线：只动 loss 路径——backbone/优化器/调度器零改动；原始 forward
引用保底可逆。
"""
from __future__ import annotations

import os

import torch
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint

_PATCHED = []  # [(cls, original_forward)]

# 默认 1024：fp32 谱系（LF auto 加载）下单块瞬态 = logits+log_softmax
# 两份 fp32 ≈ 2×chunk×V×4B（1024 → ~1.25GB）；4096 在 fp32 下实达
# ~5GB，预留池会顶到 23.4GB（贴近 24GB 上限，违反安全余量纪律）。
# 谱系若改 bf16 加载可上调到 4096（瞬态 ~3.7GB）。
CHUNK = int(os.environ.get("CHUNKED_CE_CHUNK", "1024"))
_DISABLED = os.environ.get("CHUNKED_CE_DISABLE", "") == "1"
IGNORE_INDEX = -100


def _chunk_ce_sum(hs: torch.Tensor, weight: torch.Tensor,
                  bias: torch.Tensor | None, targets: torch.Tensor,
                  vocab_size: int) -> torch.Tensor:
    """单块 sum-CE（checkpoint 包裹执行）：lm_head → fp32 上转 → CE(sum)。

    与 ForCausalLMLoss 的单块数值路径逐算子一致（F.linear bf16 →
    .float() → cross_entropy(sum, ignore_index=-100)）。
    """
    logits = F.linear(hs, weight, bias)
    logits = logits.float()
    return F.cross_entropy(logits.view(-1, vocab_size), targets,
                           ignore_index=IGNORE_INDEX, reduction="sum")


def _chunked_ce_loss(lm_head, hidden: torch.Tensor, labels: torch.Tensor,
                     num_items_in_batch, chunk: int | None = None) -> torch.Tensor:
    """分块 CE 总损失（SUM 语义 + 模型内除法）。

    hidden: [B, L, H]（已按 logits_to_keep 切片后的完整位段）；
    labels: [B, L_orig] 原始标签——shift 语义与 ForCausalLMLoss 一致：
    pad(-100) 到 L+1 位再取 [..., 1:]，与 hidden 位段对齐。
    chunk=None → 用全局 CHUNK（注意不能用默认参数直接绑定 CHUNK，
    否则 patch(chunk=...) 修改全局后默认值仍冻结在旧值——已踩过坑）。
    """
    chunk = int(chunk) if chunk is not None else CHUNK
    vocab = lm_head.weight.shape[0]
    B, L, _ = hidden.shape
    labels = labels.to(hidden.device)
    shifted = F.pad(labels, (0, max(0, L + 1 - labels.shape[-1])),
                    value=IGNORE_INDEX)[..., 1:L + 1]
    # 注意：训练路径 logits_to_keep==0 ⇒ L == labels.shape[-1]，
    # pad 恰好补 1 位（末位 -100）——与原版 pad(labels,(0,1)) 等价。
    dbg = os.environ.get("CHUNKED_CE_DEBUG") == "1" and hidden.is_cuda

    def _dbgp(tag):
        if dbg:
            print(f"[chunked_ce] {tag}: alloc="
                  f"{torch.cuda.memory_allocated()/2**30:.2f}GB "
                  f"peak={torch.cuda.max_memory_allocated()/2**30:.2f}GB")

    _dbgp(f"enter L={L} chunk={chunk}")
    total = None
    for s in range(0, L, chunk):
        e = min(s + chunk, L)
        tgt = shifted[:, s:e].reshape(-1)
        if not bool((tgt != IGNORE_INDEX).any()):
            continue  # 全忽略块：跳过（纯性能优化，不影响语义）
        val = checkpoint(
            _chunk_ce_sum, hidden[:, s:e, :].contiguous(),
            lm_head.weight, lm_head.bias, tgt, vocab,
            use_reentrant=False)
        total = val if total is None else total + val
        _dbgp(f"chunk [{s}:{e}] done")
    _dbgp("all chunks done")
    if total is None:  # 全序列无有效标签：保持图连通的零损失
        return hidden.sum() * 0.0
    if num_items_in_batch is not None:
        if torch.is_tensor(num_items_in_batch):
            num_items_in_batch = num_items_in_batch.to(total.device)
        return total / num_items_in_batch
    n = (shifted != IGNORE_INDEX).sum()
    return total / n.clamp(min=1)


def _make_patched_forward(original_forward):
    """生成补丁版 forward（闭包持有原版，供回退路径复用）。"""

    def patched_forward(self, input_ids=None, attention_mask=None,
                        position_ids=None, past_key_values=None,
                        inputs_embeds=None, labels=None, use_cache=None,
                        logits_to_keep=0, **kwargs):
        # 提取 loss 语义参数（Trainer 经 **kwargs 注入），其余透传
        num_items = kwargs.pop("num_items_in_batch", None)
        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            use_cache=use_cache,
            **kwargs,
        )
        hidden_states = outputs.last_hidden_state
        slice_indices = (slice(-logits_to_keep, None)
                         if isinstance(logits_to_keep, int)
                         else logits_to_keep)
        hs = hidden_states[:, slice_indices, :]

        use_chunked = (labels is not None
                       and isinstance(logits_to_keep, int)
                       and logits_to_keep == 0
                       # shift 对齐契约：labels 位长 == hidden 位长
                       # （pt/packing 与 pad 路径均满足；不满足宁可回退
                       # 原版也不静默错位）
                       and labels.shape[-1] == hs.shape[1])
        if not use_chunked:
            # 原版行为：完整 logits（生成 / 无标签 / 切片路径）
            logits = self.lm_head(hs)
            loss = None
            if labels is not None:
                loss = self.loss_function(
                    logits=logits, labels=labels,
                    vocab_size=self.config.vocab_size,
                    num_items_in_batch=num_items, **kwargs)
            return _causal_lm_output(loss, logits, outputs)

        loss = _chunked_ce_loss(self.lm_head, hs, labels, num_items)
        # 训练路径不物化 logits（pt 只消费 loss；物化即回到 OOM）
        return _causal_lm_output(loss, None, outputs)

    patched_forward.__name__ = original_forward.__name__
    patched_forward.__doc__ = (original_forward.__doc__ or "") + (
        "\n\n[patch_chunked_ce] 分块 CE 激活：labels+全量位段时不物化"
        " logits（logits=None）；loss=sum-CE/num_items_in_batch。")
    return patched_forward


def _causal_lm_output(loss, logits, outputs):
    from transformers.modeling_outputs import CausalLMOutputWithPast
    return CausalLMOutputWithPast(
        loss=loss, logits=logits,
        past_key_values=outputs.past_key_values,
        hidden_states=outputs.hidden_states,
        attentions=outputs.attentions,
    )


def patch(chunk: int | None = None, classes=None) -> list:
    """对 Qwen3ForCausalLM（或指定类列表）应用分块 CE 补丁。幂等。"""
    global CHUNK
    if chunk is not None:
        CHUNK = int(chunk)
    if _DISABLED:
        return []
    if classes is None:
        from transformers.models.qwen3.modeling_qwen3 import \
            Qwen3ForCausalLM
        classes = [Qwen3ForCausalLM]
    applied = []
    for cls in classes:
        if any(c is cls for c, _ in _PATCHED):
            continue
        _PATCHED.append((cls, cls.forward))
        cls.forward = _make_patched_forward(cls.forward)
        applied.append(cls)
    return applied


def unpatch() -> list:
    """恢复所有已补丁类的原始 forward。幂等。"""
    restored = []
    while _PATCHED:
        cls, original = _PATCHED.pop()
        cls.forward = original
        restored.append(cls)
    return restored


def is_patched(cls=None) -> bool:
    if cls is None:
        return bool(_PATCHED)
    return any(c is cls for c, _ in _PATCHED)


# ------------------------------------------------------------------ import 即生效
patch()
