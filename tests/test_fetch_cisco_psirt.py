"""fetch_cisco_psirt 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_cisco_psirt as fc  # noqa: E402


CVRF = """<?xml version="1.0" encoding="UTF-8"?>
<cvrf:cvrfdoc xmlns:cvrf="http://docs.oasis-open.org/csaf/ns/csaf-cvrf/v1.2/cvrf"
              xmlns:vuln="http://docs.oasis-open.org/csaf/ns/csaf-cvrf/v1.2/vuln"
              xmlns:prod="http://docs.oasis-open.org/csaf/ns/csaf-cvrf/v1.2/prod">
  <cvrf:DocumentTitle>Cisco Example Product RCE Vulnerability</cvrf:DocumentTitle>
  <cvrf:DocumentType>Cisco Security Advisory</cvrf:DocumentType>
  <cvrf:DocumentNotes>
    <cvrf:Note Title="Summary" Type="Summary">A vulnerability in the web interface
    of Cisco Example Product could allow an unauthenticated, remote attacker to
    execute arbitrary code.</cvrf:Note>
    <cvrf:Note Title="Legal Disclaimers" Type="Legal Disclaimers">Contact
    psirt@cisco.com for details.</cvrf:Note>
  </cvrf:DocumentNotes>
  <prod:ProductTree>
    <prod:Branch Type="Product Family">
      <prod:FullProductName ProductID="CVRFPID-1">Cisco Example Product 1.0</prod:FullProductName>
      <prod:FullProductName ProductID="CVRFPID-2">Cisco Example Product 2.0</prod:FullProductName>
    </prod:Branch>
  </prod:ProductTree>
  <vuln:Vulnerability Ordinal="1" xmlns="http://docs.oasis-open.org/csaf/ns/csaf-cvrf/v1.2/vuln">
    <vuln:Title>Deserialization of Untrusted Data</vuln:Title>
    <vuln:ID System="Cisco Bug ID">CSCxx12345</vuln:ID>
    <vuln:Notes>
      <vuln:Note Title="Summary" Type="Summary">The vulnerability is due to
      improper validation of user-supplied input.</vuln:Note>
      <vuln:Note Title="Workaround" Type="Workaround">There are no workarounds.</vuln:Note>
    </vuln:Notes>
    <vuln:CVE>CVE-2026-99999</vuln:CVE>
    <vuln:ProductStatuses>
      <vuln:Status Type="Known Affected">CVRFPID-1 CVRFPID-2</vuln:Status>
    </vuln:ProductStatuses>
    <vuln:CVSSScoreSets>
      <vuln:ScoreSetV2>
        <vuln:BaseScoreV2>9.8</vuln:BaseScoreV2>
      </vuln:ScoreSetV2>
    </vuln:CVSSScoreSets>
  </vuln:Vulnerability>
</cvrf:cvrfdoc>
"""


class TestConvertCiscoCvrf(unittest.TestCase):
    def test_full_advisory(self):
        t = fc.convert_cisco_cvrf(CVRF)
        self.assertIsNotNone(t)
        self.assertIn("Cisco Security Advisory: Cisco Example Product RCE Vulnerability", t)
        self.assertIn("unauthenticated, remote attacker", t)  # 文档摘要
        self.assertIn("Vulnerability CVE-2026-99999: Deserialization of Untrusted Data", t)
        self.assertIn("CVSS base score: 9.8", t)
        self.assertIn("Workaround: There are no workarounds.", t)
        self.assertIn("Affected products: Cisco Example Product 1.0; Cisco Example Product 2.0", t)

    def test_contact_noise_excluded(self):
        t = fc.convert_cisco_cvrf(CVRF)
        self.assertNotIn("psirt@cisco.com", t)
        self.assertNotIn("Legal Disclaimers", t)

    def test_product_dedupe(self):
        # 同一产品名出现在两个 ProductID -> 只出现一次
        dup = CVRF.replace(
            '<prod:FullProductName ProductID="CVRFPID-2">Cisco Example Product 2.0'
            '</prod:FullProductName>',
            '<prod:FullProductName ProductID="CVRFPID-2">Cisco Example Product 1.0'
            '</prod:FullProductName>')
        t = fc.convert_cisco_cvrf(dup)
        self.assertEqual(t.count("Cisco Example Product 1.0"), 1)
        self.assertNotIn("2.0", t)

    def test_broken_xml_and_titleless_rejected(self):
        self.assertIsNone(fc.convert_cisco_cvrf("<not-xml"))
        stripped = CVRF.replace(
            "<cvrf:DocumentTitle>Cisco Example Product RCE Vulnerability"
            "</cvrf:DocumentTitle>", "")
        self.assertIsNone(fc.convert_cisco_cvrf(stripped))

    def test_product_cap(self):
        many = CVRF.replace(
            "</prod:Branch>",
            "".join(f'<prod:FullProductName ProductID="CVRFPID-{i}">Cisco P{i}'
                    f"</prod:FullProductName>" for i in range(3, 60)) + "</prod:Branch>")
        status = CVRF.split("<vuln:Status")[0]
        many = many.replace(
            '<vuln:Status Type="Known Affected">CVRFPID-1 CVRFPID-2</vuln:Status>',
            '<vuln:Status Type="Known Affected">'
            + " ".join(f"CVRFPID-{i}" for i in range(1, 60)) + "</vuln:Status>")
        t = fc.convert_cisco_cvrf(many, max_products=10)
        self.assertIn("(and 49 more)", t)


if __name__ == "__main__":
    unittest.main()
