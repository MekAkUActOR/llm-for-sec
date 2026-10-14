"""fetch_msrc_cvrf 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_msrc_cvrf as fm  # noqa: E402


CVRF = """<?xml version="1.0" encoding="UTF-8"?>
<cvrf:cvrfdoc xmlns:cvrf="http://www.icasi.org/CVRF/schema/cvrf/1.1"
              xmlns:vuln="http://www.icasi.org/CVRF/schema/vuln/1.1"
              xmlns:prod="http://www.icasi.org/CVRF/schema/prod/1.1">
  <cvrf:DocumentTitle>January 2026 Security Update</cvrf:DocumentTitle>
  <cvrf:DocumentType>Security Update</cvrf:DocumentType>
  <cvrf:DocumentNotes>
    <cvrf:Note Title="Release Notes" Type="Details" Ordinal="0">&lt;p&gt;This release
    contains security updates for multiple Microsoft products released during the
    month of January 2026.&lt;/p&gt;</cvrf:Note>
  </cvrf:DocumentNotes>
  <prod:ProductTree>
    <prod:Branch Type="Product Family" Name="Office">
      <prod:FullProductName ProductID="1001">Microsoft Office 2016 (32-bit)</prod:FullProductName>
      <prod:FullProductName ProductID="1002">Microsoft Office 2016 (64-bit)</prod:FullProductName>
      <prod:FullProductName ProductID="1003">Microsoft Word 2016</prod:FullProductName>
    </prod:Branch>
  </prod:ProductTree>
  <vuln:Vulnerability Ordinal="1">
    <vuln:Title>Microsoft Word Remote Code Execution Vulnerability</vuln:Title>
    <vuln:Notes>
      <vuln:Note Title="Description" Type="Description" Ordinal="0" />
      <vuln:Note Title="FAQ" Type="FAQ" Ordinal="10">&lt;p&gt;&lt;strong&gt;How could
      an attacker exploit this vulnerability?&lt;/strong&gt;&lt;/p&gt;&lt;p&gt;An
      attacker could exploit the vulnerability by sending a specially crafted
      RTF file to the victim.&lt;/p&gt;</vuln:Note>
      <vuln:Note Title="Tag" Type="Tag" Ordinal="20">Office</vuln:Note>
      <vuln:Note Title="CNA" Type="CNA" Ordinal="30">mitre</vuln:Note>
    </vuln:Notes>
    <vuln:CVE>CVE-2026-0101</vuln:CVE>
    <vuln:CWE ID="CWE-416">Use After Free</vuln:CWE>
    <vuln:ProductStatuses>
      <vuln:Status Type="Known Affected">
        <vuln:ProductID>1001</vuln:ProductID>
        <vuln:ProductID>1002</vuln:ProductID>
        <vuln:ProductID>1003</vuln:ProductID>
      </vuln:Status>
    </vuln:ProductStatuses>
    <vuln:Threats>
      <vuln:Threat Type="Severity">
        <vuln:Description>Important</vuln:Description>
        <vuln:ProductID>1001</vuln:ProductID>
      </vuln:Threat>
      <vuln:Threat Type="Severity">
        <vuln:Description>Critical</vuln:Description>
        <vuln:ProductID>1002</vuln:ProductID>
      </vuln:Threat>
    </vuln:Threats>
    <vuln:Remediations>
      <vuln:Remediation Type="Vendor Fix">
        <vuln:Description>5001001 Security Update for Microsoft Office</vuln:Description>
        <vuln:ProductID>1001</vuln:ProductID>
      </vuln:Remediation>
      <vuln:Remediation Type="Vendor Fix">
        <vuln:Description>5001002 Security Update for Word</vuln:Description>
        <vuln:ProductID>1002</vuln:ProductID>
      </vuln:Remediation>
    </vuln:Remediations>
  </vuln:Vulnerability>
</cvrf:cvrfdoc>
"""


class TestConvertMsrcCvrf(unittest.TestCase):
    def test_full_doc(self):
        t = fm.convert_msrc_cvrf(CVRF)
        self.assertIsNotNone(t)
        self.assertTrue(t.startswith("Microsoft Security Update: January 2026 Security Update"))
        self.assertIn("month of January 2026", t)          # Details 文档注记（HTML 剥离）
        self.assertIn("Vulnerability CVE-2026-0101: Microsoft Word Remote Code Execution Vulnerability",
                      t)
        self.assertIn("[CWE: Use After Free]", t)
        self.assertIn("Maximum severity: Critical", t)     # 取最高而非第一条
        self.assertIn("specially crafted RTF file", t)     # FAQ HTML→文本
        self.assertIn("Remediation: 5001001 Security Update for Microsoft Office; "
                      "5001002 Security Update for Word", t)

    def test_html_and_noise_excluded(self):
        t = fm.convert_msrc_cvrf(CVRF)
        self.assertNotIn("<p>", t)
        self.assertNotIn("&lt;", t)
        self.assertNotIn("mitre", t)   # CNA 短注记剔除
        self.assertNotIn("Tag", t)

    def test_products_deduped_and_listed(self):
        t = fm.convert_msrc_cvrf(CVRF)
        self.assertIn("Affected products: Microsoft Office 2016 (32-bit); "
                      "Microsoft Office 2016 (64-bit); Microsoft Word 2016", t)

    def test_broken_and_titleless_rejected(self):
        self.assertIsNone(fm.convert_msrc_cvrf("<broken"))
        stripped = CVRF.replace(
            "<cvrf:DocumentTitle>January 2026 Security Update</cvrf:DocumentTitle>", "")
        self.assertIsNone(fm.convert_msrc_cvrf(stripped))

    def test_severity_ranking(self):
        low = CVRF.replace("<vuln:Description>Critical</vuln:Description>",
                           "<vuln:Description>Low</vuln:Description>")
        t = fm.convert_msrc_cvrf(low)
        self.assertIn("Maximum severity: Important", t)
        self.assertNotIn("Critical", t)


if __name__ == "__main__":
    unittest.main()
