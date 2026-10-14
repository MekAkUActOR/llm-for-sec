"""fetch_aisafety_knowledge 转换器单测（纯函数）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_aisafety_knowledge import (  # noqa: E402
    convert_atlas,
    md_to_text,
)


class TestMdToText(unittest.TestCase):
    def test_images_stripped(self):
        t = md_to_text("# Head\n\n![alt](img.png)\n\nBody text.")
        self.assertNotIn("img.png", t)
        self.assertNotIn("![", t)
        self.assertIn("Body text.", t)

    def test_links_keep_text(self):
        t = md_to_text("See [the guide](https://x.org) for details.")
        self.assertEqual(t, "See the guide for details.")

    def test_whitespace_normalized(self):
        t = md_to_text("a   b\tc\n\nd")
        self.assertEqual(t, "a b c\n\nd")


class TestConvertAtlas(unittest.TestCase):
    """合成最小 ATLAS YAML → 转换（读临时文件）。"""

    def setUp(self):
        import tempfile
        import os
        self.tmp = tempfile.mkdtemp()
        base = Path(self.tmp) / "atlas" / "dist"
        base.mkdir(parents=True)
        self.yaml_path = base / "ATLAS.yaml"
        self.yaml_path.write_text(
            "id: atlas\nname: ATLAS\nversion: '1'\n"
            "matrices:\n- id: m\n  name: matrix\n"
            "  tactics:\n  - {id: AML.TA0002, name: Reconnaissance, "
            "description: Gathering info., object-type: tactic}\n"
            "  techniques:\n  - {id: AML.T0000, name: ML Recon, "
            "description: Search for ML artifacts., tactics: [AML.TA0002], "
            "object-type: technique}\n"
            "  mitigations:\n  - {id: AML.M0000, name: Limit Info, "
            "description: Limit release., object-type: mitigation, "
            "techniques: [{id: AML.T0000}]}\n"
            "case-studies:\n- id: AML.CS0000\n  name: Evasion Case\n"
            "  object-type: case-study\n  summary: An evasion happened.\n"
            "  incident-date: '2020-01-01'\n"
            "  procedure:\n  - {tactic: AML.TA0002, technique: AML.T0000, "
            "description: Searched artifacts.}\n"
            "  target: detector\n  actor: researchers\n",
            encoding="utf-8")

    def test_conversion_counts_and_content(self):
        import fetch_aisafety_knowledge as fk
        orig = fk.RAW
        fk.RAW = Path(self.tmp)
        try:
            docs = convert_atlas()
        finally:
            fk.RAW = orig
        self.assertEqual(len(docs), 4)  # 1 tactic + 1 tech + 1 mit + 1 case
        joined = "\n".join(docs)
        self.assertIn("MITRE ATLAS tactic AML.TA0002 (Reconnaissance)", joined)
        self.assertIn("tactics: Reconnaissance (AML.TA0002)", joined)
        self.assertIn("mitigates AML.T0000", joined)
        self.assertIn("Procedure (technique AML.T0000 ML Recon)", joined)
        self.assertIn("Target: detector", joined)


if __name__ == "__main__":
    unittest.main()
