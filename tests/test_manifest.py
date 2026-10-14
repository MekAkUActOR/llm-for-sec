"""语料 manifest 校验测试（docs/04 §3）。"""

import json
import tempfile
import unittest
from pathlib import Path

from secfm.data.manifest import load, stats, validate


def _row(**kw):
    d = {"id": "x", "name": "Test", "tier": "public", "domain": "security",
         "lang": "en", "status": "planned"}
    d.update(kw)
    return d


class TestManifestValidate(unittest.TestCase):
    def test_valid_rows(self):
        rows = [
            _row(),
            _row(id="y", domain="privacy", status="ingested",
                 license="public-domain", est_tokens=1000),
        ]
        self.assertEqual(validate(rows), [])
        st = stats(rows)
        self.assertEqual(st["sources"], 2)
        self.assertEqual(st["ingested_tokens"], 1000)
        self.assertEqual(st["tokens_by_domain"], {"privacy": 1000})

    def test_ingested_needs_license(self):
        problems = validate([_row(status="ingested")])
        self.assertTrue(any("license" in p for p in problems))

    def test_restricted_must_not_register_training_files(self):
        """uplift 红线：restricted 层不进语言建模 token 目录（docs/04 §0）。"""
        problems = validate([_row(tier="restricted", status="ingested",
                                  license="MIT", files=["tokens/x.npy"])])
        self.assertTrue(any("restricted" in p for p in problems))

    def test_bad_enum(self):
        self.assertTrue(any("tier" in p for p in validate([_row(tier="secret")])))

    def test_duplicate_ids(self):
        problems = validate([_row(), _row()])
        self.assertTrue(any("duplicate" in p for p in problems))


class TestManifestLoad(unittest.TestCase):
    def test_roundtrip_and_bad_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.jsonl"
            lines = [json.dumps(_row(), ensure_ascii=False),
                     json.dumps(_row(id="y"), ensure_ascii=False),
                     "{not json"]
            p.write_text("\n".join(lines), encoding="utf-8")
            rows, problems = load(p)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(problems), 1)


if __name__ == "__main__":
    unittest.main()
