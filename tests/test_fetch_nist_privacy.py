"""fetch_nist_privacy 纯函数测试（无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_nist_privacy as np  # noqa: E402

NS = "http://scap.nist.gov/schema/sp800-53/2.0"
XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<controls xmlns="{NS}">
  <control><number>AC</number><title>ACCESS CONTROL</title>
    <statement><description>The AC family overview.</description></statement>
  </control>
  <control><number>AC-2</number><title>ACCOUNT MANAGEMENT</title>
    <statement><description>Manage system accounts.</description></statement>
    <discussion><description><p>Discussion of account management.</p></description></discussion>
    <control-enhancement>
      <number>AC-2(1)</number><title>AUTOMATED SYSTEM ACCOUNT MANAGEMENT</title>
      <statement><description>Employ automated mechanisms.</description></statement>
    </control-enhancement>
  </control>
  <control><number>SC-8</number><title>TRANSMISSION CONFIDENTIALITY AND INTEGRITY</title>
    <statement><description>Protect confidentiality and integrity of transmitted information.</description></statement>
  </control>
  <control><number>AT-2</number><title>AWARENESS TRAINING</title>
    <statement><description>Train users.</description></statement>
  </control>
</controls>"""


class TestConvert80053(unittest.TestCase):
    def test_only_ac_and_sc_families(self):
        docs = np.convert_80053_controls(XML)
        nums = [d.split("\n")[0] for d in docs]
        self.assertEqual(len(docs), 3)        # AC, AC-2, SC-8;AT-2 排除
        self.assertIn("control AC:", nums[0])
        self.assertIn("control AC-2:", nums[1])
        self.assertIn("control SC-8:", nums[2])

    def test_control_doc_content(self):
        docs = np.convert_80053_controls(XML)
        ac2 = docs[1]
        self.assertIn("ACCOUNT MANAGEMENT", ac2)
        self.assertIn("Control: Manage system accounts.", ac2)
        self.assertIn("Discussion: Discussion of account management.", ac2)
        self.assertIn("Control enhancements:", ac2)
        self.assertIn("AC-2(1) AUTOMATED SYSTEM ACCOUNT MANAGEMENT", ac2)

    def test_family_filter_sc_only(self):
        docs = np.convert_80053_controls(XML, families=("SC",))
        self.assertEqual(len(docs), 1)
        self.assertIn("SC-8", docs[0])

    def test_missing_statement_falls_back_to_description(self):
        xml2 = XML.replace("<statement><description>Protect confidentiality "
                           "and integrity of transmitted information.</description></statement>",
                           "<description>Fallback description for SC-8.</description>")
        docs = np.convert_80053_controls(xml2)
        sc8 = [d for d in docs if "SC-8" in d.split("\n")[0]][0]
        self.assertIn("Fallback description for SC-8.", sc8)


class TestCleanPdfText(unittest.TestCase):
    def test_page_numbers_removed(self):
        self.assertNotIn("\n12\n", np.clean_pdf_text("line one\n12\nline two"))

    def test_repeated_headers_collapsed(self):
        out = np.clean_pdf_text("NIST SP 800-188 body text\nNIST SP 800-188 body text")
        self.assertEqual(out.count("NIST SP 800-188 body text"), 1)

    def test_empty_lines_dropped(self):
        self.assertNotIn("\n\n", np.clean_pdf_text("a\n\n\nb"))


if __name__ == "__main__":
    unittest.main()
