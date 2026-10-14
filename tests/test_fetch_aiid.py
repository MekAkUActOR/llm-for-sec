"""fetch_aiid 转换器单测（纯函数）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_aiid import _clean, convert_incident  # noqa: E402


class TestClean(unittest.TestCase):
    def test_nan_and_placeholder(self):
        self.assertIsNone(_clean(float("nan")))
        self.assertIsNone(_clean("-"))
        self.assertIsNone(_clean(None))
        self.assertIsNone(_clean("   "))

    def test_bracket_list_flattened(self):
        self.assertEqual(_clean('["License Plate Recognition"]'),
                         "License Plate Recognition")
        self.assertEqual(_clean('["a", "b"]'), "a, b")

    def test_plain_string(self):
        self.assertEqual(_clean("  Flock Safety  camera "), "Flock Safety camera")


class TestConvertIncident(unittest.TestCase):
    def test_full_row(self):
        doc = convert_incident({
            "Incident ID": 1701, "date": "2026-03-01",
            "title": "Chatbot Misidentified Cargo",
            "description": "A chatbot reportedly misidentified ship cargo.",
            "deployer": "Acme", "developer": "Acme Labs",
            "harmed": "shipping company",
            "Implicated Systems": '["chatbot"]',
            "Risk Domain": "Information integrity",
            "Intent": "unintentional",
            "Harm Domain": "Reputation",
            "AI Harm Level": "minor",
        })
        self.assertTrue(doc.startswith(
            "AI Incident Database (AIID) incident 1701, date 2026-03-01: "
            "Chatbot Misidentified Cargo."))
        self.assertIn("A chatbot reportedly misidentified ship cargo.", doc)
        self.assertIn("Deployer: Acme;", doc)
        self.assertIn("Implicated systems: chatbot.", doc)
        self.assertIn("Risk domain: Information integrity;", doc)
        self.assertIn("AI harm level: minor", doc)

    def test_minimal_row(self):
        doc = convert_incident({"Incident ID": 1})
        self.assertTrue(doc.startswith(
            "AI Incident Database (AIID) incident 1, date unknown date: "
            "Untitled incident."))
        self.assertNotIn("Deployer", doc)
        self.assertNotIn("Risk domain", doc)

    def test_missing_values_skip_fields(self):
        doc = convert_incident({
            "Incident ID": 2, "date": "2020-01-01", "title": "T",
            "description": "D.", "deployer": "X", "developer": float("nan"),
            "harmed": None, "Risk Domain": "-",
        })
        self.assertIn("Deployer: X", doc)
        self.assertNotIn("Developer", doc)
        self.assertNotIn("Risk domain", doc)


if __name__ == "__main__":
    unittest.main()
