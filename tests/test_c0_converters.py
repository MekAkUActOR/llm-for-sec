"""C0 语料转换器测试（scripts/fetch_c0.py 的纯函数部分，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_c0 as fc  # noqa: E402


class TestConverters(unittest.TestCase):
    def test_cve_accepted(self):
        d = {
            "cveMetadata": {"cveId": "CVE-2024-1234", "state": "Published"},
            "containers": {"cna": {
                "title": "Buffer overflow in X",
                "descriptions": [{"lang": "en",
                                  "value": "A heap overflow exists\nin product X."}],
                "affected": [{"vendor": "acme", "product": "widget"},
                             {"vendor": "acme", "product": "widget-pro"}],
                "references": [{"url": "https://example.com/a"},
                               {"url": "https://example.com/b"}],
            }},
        }
        t = fc.convert_cve_item(d)
        self.assertIn("CVE-2024-1234", t)
        self.assertIn("Buffer overflow in X", t)
        self.assertIn("heap overflow exists in product X", t)  # 空白归一
        self.assertIn("Affected products: acme/widget, acme/widget-pro", t)
        self.assertIn("https://example.com/a", t)

    def test_cve_rejected_and_no_desc(self):
        self.assertIsNone(fc.convert_cve_item(
            {"cveMetadata": {"cveId": "CVE-2024-1", "state": "REJECTED"}}))
        self.assertIsNone(fc.convert_cve_item(
            {"cveMetadata": {"cveId": "CVE-2024-2", "state": "Published"},
             "containers": {"cna": {"descriptions": [
                 {"lang": "es", "value": "x"}]}}}))

    def test_kev(self):
        doc = {"vulnerabilities": [{
            "cveID": "CVE-2021-44228", "vendorProject": "Apache",
            "product": "Log4j2", "dateAdded": "2021-12-10",
            "vulnerabilityName": "Log4Shell",
            "shortDescription": "Remote code execution in Log4j.",
            "knownRansomwareCampaignUse": "Known"}]}
        out = fc.convert_kev(doc)
        self.assertEqual(len(out), 1)
        self.assertIn("CISA KEV, known exploited, added 2021-12-10", out[0])
        self.assertIn("Known ransomware campaign use: Known", out[0])

    def test_attack(self):
        doc = {"objects": [
            {"type": "attack-pattern", "name": "Phishing",
             "description": "Adversary sends  fraudulent messages.",
             "external_references": [
                 {"source_name": "mitre-attack", "external_id": "T1566"}],
             "kill_chain_phases": [{"phase_name": "initial-access"}]},
            {"type": "course-of-action", "name": "User Training",
             "description": "Train users to spot phishing.",
             "external_references": [
                 {"source_name": "mitre-attack", "external_id": "M1017"}]},
            {"type": "identity", "description": "should be skipped"},
        ]}
        out = fc.convert_attack(doc)
        self.assertEqual(len(out), 2)
        self.assertIn("ATT&CK technique T1566 (Phishing)", out[0])
        self.assertIn("kill chain phase: initial-access", out[0])
        self.assertIn("ATT&CK mitigation M1017 (User Training)", out[1])

    def test_cwe(self):
        xml = """<Weaknesses xmlns="http://cwe.mitre.org/cwe-6">
        <Weakness ID="79" Name="Cross-site Scripting" Status="Stable">
          <Description>The product does not neutralize input.</Description>
          <Extended_Description>Attackers can inject scripts.</Extended_Description>
          <Common_Consequences><Consequence>
            <Scope>Confidentiality</Scope><Scope>Integrity</Scope>
          </Consequence></Common_Consequences>
          <Potential_Mitigations><Mitigation>
            <Phase>Implementation</Phase>
            <Description>Use output encoding.</Description>
          </Mitigation></Potential_Mitigations>
        </Weakness></Weaknesses>"""
        out = fc.convert_cwe(xml)
        self.assertEqual(len(out), 1)
        self.assertIn("CWE-79 Cross-site Scripting", out[0])
        self.assertIn("Confidentiality/Integrity", out[0])
        self.assertIn("Implementation: Use output encoding.", out[0])

    def test_capec(self):
        xml = """<AttackPatterns xmlns="https://capec.mitre.org/capec-3">
        <Attack_Pattern ID="66" Name="SQL Injection">
          <Description>The attacker injects SQL.</Description>
          <Solutions><Solution>Use prepared statements.</Solution></Solutions>
        </Attack_Pattern></AttackPatterns>"""
        out = fc.convert_capec(xml)
        self.assertEqual(len(out), 1)
        self.assertIn("CAPEC-66 SQL Injection", out[0])
        self.assertIn("Use prepared statements.", out[0])

    def test_arxiv(self):
        atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>On the Security of LLM Agents</title>
          <summary> We study prompt injection. </summary>
        </entry></feed>"""
        out = fc.convert_arxiv(atom)
        self.assertEqual(len(out), 1)
        self.assertIn("On the Security of LLM Agents", out[0])
        self.assertIn("We study prompt injection.", out[0])

    def test_html_to_text(self):
        html = ("<html><head><style>.x{}</style></head><body>"
                "<p>Hello &amp; world</p><script>bad()</script>"
                "<div>Second line</div></body></html>")
        t = fc.html_to_text(html)
        self.assertIn("Hello & world", t)
        self.assertIn("Second line", t)
        self.assertNotIn("bad()", t)
        self.assertNotIn(".x", t)


if __name__ == "__main__":
    unittest.main()
