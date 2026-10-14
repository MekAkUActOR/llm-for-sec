# -*- coding: utf-8 -*-
"""训练/评测提示格式统一入口（S0，2026-09-30）。

## 为什么需要
`scripts/baseline_eval.py` 的判分器自 M0 起把**原始 query** 直接喂模型
（`self.tok(item.query)`），无 chat 模板。该写法对 base 模型正确，但模型转为
指令微调后**从未更新** → G1/G3/G4 的绝对读数全部失真（详见
reports/ab-promptformat.md：裸续写口径把 m2-full 的 3/8 顺从夸大成 8/8）。

## 本模块的契约
**唯一**的部署格式渲染入口，与训练数据同分布：

    <|im_start|>system\\n{POLICY_SYSTEM[pack][lang]}<|im_end|>\\n
    <|im_start|>user\\n{query}<|im_end|>\\n
    <|im_start|>assistant\\n

- 政策包文本取自训练侧规范源 `scripts/gen_sft_v0.py` 的 `POLICY_SYSTEM`，
  **动态加载、不复制字面量**（避免两处漂移）；取不到即抛错（**fail-closed**，
  不静默降级为 raw——静默降级正是本次要修的病）。
- 不插思考块（与 LLaMA-Factory `qwen3_nothink` 一致）。

## 用法
    from secfm.eval.promptfmt import render, chat_prompt, item_lang
    prompt = render(item, "chat")      # item: EvalItem
    prompt = chat_prompt("查询", pack="conservative", lang="zh")
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

__all__ = ["MISSING_PACK_FALLBACK", "chat_prompt", "item_lang", "render",
           "system_for"]

ROOT = Path(__file__).resolve().parents[2]
_GEN_SFT_V0 = ROOT / "scripts" / "gen_sft_v0.py"

#: 政策包缺失时的兜底 system（**仅**在 item 未标注政策包时使用；不掩盖包文本缺失）
MISSING_PACK_FALLBACK = "你是安全感知助手。"

_POLICY_SYSTEM: dict | None = None


def _policy_system() -> dict:
    """动态加载训练侧政策包规范源（scripts/gen_sft_v0.py::POLICY_SYSTEM）。"""
    global _POLICY_SYSTEM
    if _POLICY_SYSTEM is None:
        if not _GEN_SFT_V0.exists():
            raise RuntimeError(
                f"政策包规范源不存在：{_GEN_SFT_V0}（fail-closed："
                "不允许静默退化到无 system 的裸续写口径）")
        spec = importlib.util.spec_from_file_location("_gen_sft_v0_packs",
                                                      _GEN_SFT_V0)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载政策包规范源：{_GEN_SFT_V0}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        table = getattr(mod, "POLICY_SYSTEM", None)
        if not isinstance(table, dict) or not table:
            raise RuntimeError(
                f"{_GEN_SFT_V0} 未导出非空 POLICY_SYSTEM（fail-closed）")
        _POLICY_SYSTEM = table
    return _POLICY_SYSTEM


def system_for(pack: str | None, lang: str = "zh") -> str:
    """政策包 → system 文本。pack 为空时返回兜底并**不报错**（调用方可审计）。"""
    if not pack:
        return MISSING_PACK_FALLBACK
    table = _policy_system()
    entry = table.get(pack)
    if not isinstance(entry, dict):
        raise KeyError(f"未知政策包 {pack!r}；可用：{sorted(table)}")
    key = "zh" if str(lang).lower().startswith("zh") else "en"
    text = entry.get(key)
    if not isinstance(text, str) or not text:
        raise KeyError(f"政策包 {pack!r} 缺 {key} 文本")
    return text


def item_lang(item) -> str:
    """从 EvalItem 取语言，缺省 zh。"""
    for attr in ("language", "lang"):
        v = getattr(item, attr, None)
        if v:
            return str(v)
    return "zh"


def chat_prompt(query: str, *, pack: str | None = None, lang: str = "zh",
                with_system: bool = True) -> str:
    """LF `qwen3_nothink` 等价渲染（assistant 头后不插思考块）。"""
    s = ""
    if with_system:
        s += f"<|im_start|>system\n{system_for(pack, lang)}<|im_end|>\n"
    s += f"<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
    return s


def render(item, fmt: str = "chat", lang: str | None = None) -> str:
    """EvalItem → 提示串。fmt ∈ {"raw", "chat"}；未知 fmt 抛错（fail-closed）。"""
    if fmt == "raw":
        return item.query
    if fmt == "chat":
        return chat_prompt(item.query, pack=getattr(item, "policy_pack", None),
                           lang=lang or item_lang(item))
    raise ValueError(f"未知 prompt-format {fmt!r}（可选 raw/chat）")
