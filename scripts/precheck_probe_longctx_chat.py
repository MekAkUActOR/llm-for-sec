# -*- coding: utf-8 -*-
"""CPU 预检：probe_longctx 的 chat 口径在修好 sys.path 之后，还会不会撞第二个错误？

只做导入/签名级自证（不加载模型、不占 GPU）：
  1. 以**脚本自身所在目录**被调用的方式 import probe_longctx
  2. 确认 chat_affixes 可达且签名正确
  3. 确认 secfm.eval.promptfmt.system_for 存在
  4. 用**真实 tokenizer** 实调一次 chat_affixes（这才是真正会崩的地方）
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")

# 关键：**不**预先插入 ROOT——要让 probe_longctx 自己把 ROOT 插进去，
# syspath-hygiene: skip  （本文件故意不插 ROOT，见下一行说明）
# 从而验证我们加的修复真的起作用（否则只是验证了我的脚本）。
spec = importlib.util.spec_from_file_location("probe_longctx", ROOT / "scripts/probe_longctx.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("[1] probe_longctx 导入成功")
print(f"    ROOT = {mod.ROOT}")
print(f"    ROOT 在 sys.path 中 = {str(mod.ROOT) in sys.path}")

import inspect  # noqa: E402
print(f"[2] chat_affixes 签名 = {inspect.signature(mod.chat_affixes)}")

from secfm.eval.promptfmt import system_for  # noqa: E402
print("[3] secfm.eval.promptfmt.system_for 导入成功")
print(f"    system_for 签名 = {inspect.signature(system_for)}")

# [4] 真实 tokenizer 实调——真正会崩的那一步
tokdir = (ROOT / ".cache/huggingface/hub/models--Qwen--Qwen3-0.6B-Base/snapshots"
          / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
from transformers import AutoTokenizer  # noqa: E402
tok = AutoTokenizer.from_pretrained(str(tokdir), trust_remote_code=True)
print("[4] tokenizer 载入成功")

for lang in ("en", "zh"):
    for pack in (None, "sys"):
        try:
            pre, suf = mod.chat_affixes(tok, lang, pack)
            print(f"    chat_affixes(lang={lang}, pack={pack}) -> "
                  f"prefix {len(pre)} ids, suffix {len(suf)} ids  ✓")
        except Exception as e:  # noqa: BLE001
            print(f"    chat_affixes(lang={lang}, pack={pack}) -> ✗ {type(e).__name__}: {e}")

print("\nPROBE-LONGCTX-CHAT-PRECHECK=DONE")
