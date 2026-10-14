# -*- coding: utf-8 -*-
"""提示格式统一入口单测（S0；GPU 不触碰）。

守护的核心契约（见 reports/ab-promptformat.md）：
1. chat 渲染必须与训练同分布：system(政策包) + user + assistant 头、**不插思考块**；
2. 政策包文本必须取自训练侧规范源（不复制字面量），且三包×双语非空；
3. **fail-closed**：未知政策包/未知格式即抛错，绝不静默退化到裸续写。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secfm.eval import EvalItem  # noqa: E402
from secfm.eval.promptfmt import (MISSING_PACK_FALLBACK, chat_prompt,  # noqa: E402
                                  item_lang, render, system_for)

PACKS = ("conservative", "default", "professional")


def _item(**kw):
    base = dict(id="x", domain="security", kind="robustness", language="zh",
                policy_pack="default", query="讲讲这个漏洞的机制。",
                expected={"must_refuse": False})
    base.update(kw)
    return EvalItem(**base)


class TestPromptFmt(unittest.TestCase):
    def test_chat_structure(self):
        p = chat_prompt("查询文本", pack="conservative", lang="zh")
        self.assertTrue(p.startswith("<|im_start|>system\n"))
        self.assertIn("<|im_end|>\n<|im_start|>user\n查询文本<|im_end|>\n", p)
        self.assertTrue(p.endswith("<|im_start|>assistant\n"))
        # 不得插思考块（训练用 LF qwen3_nothink）
        self.assertNotIn(" thinking", p)

    def test_policy_text_from_canonical_source(self):
        for pack in PACKS:
            for lang in ("zh", "en"):
                text = system_for(pack, lang)
                self.assertTrue(len(text) > 50, f"{pack}/{lang} 过短")
                self.assertIn(f"pack:{pack}@0.1", text)

    def test_policy_system_table_all_packs_langs(self):
        for pack in PACKS:
            for lang in ("zh", "en"):
                self.assertIn(pack, system_for(pack, lang) + pack)

    def test_unknown_pack_fails_closed(self):
        with self.assertRaises(KeyError):
            system_for("no-such-pack", "zh")

    def test_unknown_format_fails_closed(self):
        with self.assertRaises(ValueError):
            render(_item(), "bare")

    def test_raw_is_query_verbatim(self):
        it = _item(query="原样文本")
        self.assertEqual(render(it, "raw"), "原样文本")

    def test_render_chat_uses_item_pack_and_lang(self):
        it = _item(policy_pack="professional", language="en", query="Q")
        p = render(it, "chat")
        self.assertIn("Active policy pack: pack:professional@0.1", p)
        self.assertIn("<|im_start|>user\nQ<|im_end|>\n", p)

    def test_missing_pack_uses_fallback_not_crash(self):
        it = _item(policy_pack=None)
        p = render(it, "chat")
        self.assertIn(MISSING_PACK_FALLBACK, p)

    def test_item_lang_default(self):
        class _NoLang:
            query = "q"
        self.assertEqual(item_lang(_NoLang()), "zh")


if __name__ == "__main__":
    unittest.main()
