r"""convert_sft_v0 测试：LF 真转换器往返（SharegptDatasetConverter 源码级）、
政策引用进 system、VERDICT 行保留在 assistant、注册完整性与条目保留。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import convert_sft_v0 as cv  # noqa: E402
from score_heldout_v2 import _extract_structured  # noqa: E402

lf = None
try:
    from llamafactory.data.converter import SharegptDatasetConverter
    from llamafactory.data.parser import DatasetAttr
    lf = True
except Exception:  # pragma: no cover - venv 无 LF 时跳过真转换器测试
    lf = None


def _run_convert(tmp: Path):
    """在临时目录跑一次完整转换（含注册），返回 (out_path, info_path, res)。"""
    out = tmp / "lf" / "sft_v0.jsonl"
    info = tmp / "lf" / "dataset_info.json"
    info.parent.mkdir(parents=True)
    info.write_text(json.dumps({"dummy_entry": {"file_name": "x.json"},
                                "sec_m15": {"file_name": "sec_m15.jsonl",
                                            "columns": {"prompt": "text"}}}),
                    encoding="utf-8")
    res = cv.convert(ROOT / "data" / "sft" / "v0", out, info)
    return out, info, res


class TestConvert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.out, cls.info, cls.res = _run_convert(tmp)
        cls.rows = [json.loads(l) for l in
                    cls.out.read_text(encoding="utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_all_rows_flow_through(self):
        src_total = 0
        for name in cv.SOURCES:
            src_total += sum(1 for l in
                             (ROOT / "data" / "sft" / "v0" / name)
                             .read_text(encoding="utf-8").splitlines() if l.strip())
        self.assertEqual(len(self.rows), src_total)
        self.assertEqual(self.res["total"], src_total)
        self.assertEqual(len({r["id"] for r in self.rows}), src_total)

    def test_row_shape(self):
        for r in self.rows:
            self.assertEqual([m["role"] for m in r["messages"]],
                             ["system", "user", "assistant"])
            self.assertIn("pack:", r["messages"][0]["content"])

    def test_registration_adds_entry_and_preserves_others(self):
        info = json.loads(self.info.read_text(encoding="utf-8"))
        self.assertIn(cv.DATASET_NAME, info)
        self.assertIn("dummy_entry", info)      # 既有条目保留
        self.assertIn("sec_m15", info)          # 红线：不动既有条目
        entry = info[cv.DATASET_NAME]
        self.assertEqual(entry["formatting"], "sharegpt")
        self.assertEqual(entry["columns"], {"messages": "messages"})
        self.assertEqual(entry["tags"]["role_tag"], "role")
        self.assertEqual(entry["tags"]["system_tag"], "system")
        self.assertEqual(entry["file_name"], "sft_v0.jsonl")

    def test_policy_citation_reaches_system_slot(self):
        """政策引用必须完整进入 LF 的 _system（template system 槽位）。"""
        for r in self.rows[:200]:
            self.assertIn(r["pack"] + "@0.1",
                          r["messages"][0]["content"])

    def test_verdict_line_survives_in_assistant(self):
        for r in self.rows:
            v = _extract_structured(r["messages"][2]["content"])
            self.assertIsNotNone(v, r["id"])
            self.assertEqual(v["policy"], r["pack"])


@unittest.skipIf(lf is None, "llamafactory 不可导入（venv 应为 LF 0.9.6 检出版）")
class TestTrueSharegptRoundtrip(unittest.TestCase):
    """用 LF 真转换器（训练将走的代码路径）验证注册条目语义正确。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.out, cls.info, cls.res = _run_convert(tmp)
        cls.rows = [json.loads(l) for l in
                    cls.out.read_text(encoding="utf-8").splitlines()]
        info = json.loads(cls.info.read_text(encoding="utf-8"))
        cls.attr = DatasetAttr(load_from="file", dataset_name=cv.DATASET_NAME)
        cls.attr.join(info[cv.DATASET_NAME])  # 与 parser.get_dataset_list 同路径

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_attr_parsed_as_expected(self):
        self.assertEqual(self.attr.formatting, "sharegpt")
        self.assertEqual(self.attr.messages, "messages")
        self.assertEqual(self.attr.role_tag, "role")
        self.assertEqual(self.attr.content_tag, "content")
        self.assertEqual(self.attr.user_tag, "user")
        self.assertEqual(self.attr.assistant_tag, "assistant")
        self.assertEqual(self.attr.system_tag, "system")
        self.assertIsNone(self.attr.system)  # 无独立 system 列（system 在消息里）

    def test_converter_routes_every_row_correctly(self):
        conv = SharegptDatasetConverter(self.attr, data_args=None)
        for r in self.rows:
            aligned = conv(r)
            self.assertEqual(aligned["_system"], r["messages"][0]["content"],
                             f"政策 system 区未进 _system: {r['id']}")
            self.assertEqual(len(aligned["_prompt"]), 1)
            self.assertEqual(aligned["_prompt"][0]["role"], "user")
            self.assertEqual(aligned["_prompt"][0]["content"],
                             r["messages"][1]["content"], r["id"])
            self.assertEqual(len(aligned["_response"]), 1)
            self.assertEqual(aligned["_response"][0]["role"], "assistant")
            self.assertEqual(aligned["_response"][0]["content"],
                             r["messages"][2]["content"], r["id"])
            self.assertIn("VERDICT:", aligned["_response"][0]["content"])

    def test_all_four_corpora_roundtrip(self):
        """四语料各抽一条（含协议包裹的注入样本）走真转换器。"""
        conv = SharegptDatasetConverter(self.attr, data_args=None)
        seen = set()
        for r in self.rows:
            corpus = r["id"].split("-")[1]
            if corpus in seen:
                continue
            seen.add(corpus)
            aligned = conv(r)
            self.assertEqual(aligned["_prompt"][0]["content"],
                             r["messages"][1]["content"])
            self.assertIn("VERDICT:", aligned["_response"][0]["content"])
        self.assertEqual(seen, {"A", "B", "C", "D"})


class TestIsolation(unittest.TestCase):
    """物理隔离（数据路径级）：转换器接触不到评估集/探针集的数据文件。
    注：导入判分器模块（score_heldout_v2）合法——VERDICT 契约校验器非数据路径。"""

    def test_converter_source_free_of_eval_data_paths(self):
        src = (ROOT / "scripts" / "convert_sft_v0.py").read_text(encoding="utf-8")
        for lit in ("data/heldout", "data\\heldout", "data/probes",
                    "data\\probes", "ais-500"):
            self.assertNotIn(lit, src)


if __name__ == "__main__":
    unittest.main()
