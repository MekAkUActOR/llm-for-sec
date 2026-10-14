"""probe_ppl 滑窗切分逻辑单测。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from probe_ppl import chunk_windows


class TestChunkWindows(unittest.TestCase):
    def test_short_doc_single_window(self):
        self.assertEqual(chunk_windows([1, 2, 3], 2048, 1536), [[1, 2, 3]])

    def test_exact_boundary(self):
        ids = list(range(2048))
        self.assertEqual(chunk_windows(ids, 2048, 1536), [ids])

    def test_two_windows_masking(self):
        ids = list(range(3000))
        wins = chunk_windows(ids, 2048, 1536)
        self.assertEqual(len(wins), 2)
        # 首窗口全计分
        self.assertEqual(wins[0], ids[:2048])
        # 次窗口：与前窗重叠的 512 个 token 置 -100，其余计分
        self.assertEqual(wins[1][:512], [-100] * 512)
        self.assertEqual(wins[1][512:], ids[2048:3000])

    def test_no_double_counting(self):
        """所有窗口计分 token 之和 == 原始 token 数（无重复无遗漏）。"""
        ids = list(range(7300))
        wins = chunk_windows(ids, 2048, 1536)
        scored = sum(len([x for x in w if x >= 0]) for w in wins)
        self.assertEqual(scored, len(ids))

    def test_all_tokens_recovered(self):
        """计分 token 的值集合与原始去重位置一致（按序重建）。"""
        ids = list(range(5000))
        flat = [x for w in chunk_windows(ids, 2048, 1536) for x in w if x >= 0]
        self.assertEqual(flat, ids)


if __name__ == "__main__":
    unittest.main()
