"""fetch_arxiv_aisafety 纯函数单测（URL 编码 / 查询构建 / 文本格式）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_arxiv_aisafety import (  # noqa: E402
    _enc,
    format_doc_ais,
    q_url,
    title_noise,
)


class TestEnc(unittest.TestCase):
    def test_spaces_quotes_parens(self):
        self.assertEqual(_enc('(abs:"prompt injection")'),
                         "%28abs:%22prompt+injection%22%29")

    def test_no_mutation_of_brackets(self):
        # 方括号由 q_url 单独处理（TO 日期区间）
        self.assertNotIn("%5B", _enc("[x]"))


class TestQUrl(unittest.TestCase):
    def test_basic_query(self):
        u = q_url('(abs:jailbreak)', 0)
        self.assertIn("%28abs:jailbreak%29+AND+%28cat", u)
        self.assertIn("start=0", u)
        self.assertIn("max_results=200", u)

    def test_year_shard(self):
        u = q_url('(abs:guardrail)', 200, year=2023)
        self.assertIn("submittedDate:%5B202301010000+TO+202312312359%5D", u)
        self.assertIn("start=200", u)


class TestFormatDoc(unittest.TestCase):
    def test_format_embeds_id(self):
        d = format_doc_ais("2401.12345", "Jailbreaking LLMs", "We study attacks.")
        self.assertEqual(
            d, "arXiv AI safety research paper 2401.12345: "
               "Jailbreaking LLMs. We study attacks.")

    def test_distinct_from_c1_prefix(self):
        d = format_doc_ais("1", "T", "S.")
        self.assertTrue(d.startswith("arXiv AI safety research paper "))
        self.assertFalse(d.startswith("arXiv security research paper"))


class TestTitleNoise(unittest.TestCase):
    def test_pure_noise_dropped(self):
        self.assertTrue(title_noise(
            "Cross-lingual Word Alignment for Comparable Texts"))
        self.assertTrue(title_noise(
            "Multi-modal Sensor Registration for Vehicle Perception"))

    def test_safety_signal_rescues(self):
        # 命中排除词族但有安全信号 → 保留
        self.assertFalse(title_noise(
            "Adversarial Robustness of Vision-Language Models"))
        self.assertFalse(title_noise(
            "Multimodal LLM Safety Alignment Evaluation"))

    def test_clean_titles_pass(self):
        self.assertFalse(title_noise("RLHF Alignment from Human Feedback"))
        self.assertFalse(title_noise("Constitutional AI: Harmlessness"))


if __name__ == "__main__":
    unittest.main()
