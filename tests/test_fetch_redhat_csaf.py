"""fetch_redhat_csaf 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_redhat_csaf as fr  # noqa: E402


CSAF = {
    "document": {
        "title": "Red Hat Security Advisory: openvswitch2.17 security update",
        "tracking": {"id": "RHSA-2024:1234",
                     "initial_release_date": "2024-03-07T18:20:50+00:00"},
        "aggregate_severity": {"text": "Important"},
        "notes": [
            {"category": "summary",
             "text": "An update for openvswitch2.17 is now available for "
                     "Red Hat Enterprise Linux 9."},
            {"category": "general",
             "text": "Open vSwitch provides standard network bridging functions."},
            {"category": "legal_disclaimer",
             "text": "This content is licensed under the Creative Commons "
                     "Attribution 4.0 License."},
        ],
    },
    "product_tree": {
        "branches": [{
            "category": "product_family", "name": "RHEL",
            "branches": [{
                "category": "product_name", "name": "RHEL 9",
                "product": {
                    "name": "Red Hat Enterprise Linux 9",
                    "full_product_names": [
                        {"product_id": "PF-001",
                         "name": "Red Hat Enterprise Linux 9 (openvswitch2.17)"},
                        {"product_id": "PF-001",
                         "name": "Red Hat Enterprise Linux 9 (openvswitch2.17)"}],
                },
            }],
        }],
    },
    "vulnerabilities": [{
        "cve": "CVE-2023-3966",
        "title": "openvswitch: ovs-vswitch fails to recover after malformed "
                 "geneve metadata packet",
        "cwe": {"id": "CWE-248", "name": "Uncaught Exception"},
        "scores": [{"cvss_v3": {"baseScore": 7.5, "baseSeverity": "HIGH"}}],
        "product_status": {"fixed": ["PF-001"]},
        "threats": [{"category": "impact", "details": "Important"}],
    }],
}


class TestConvertRedhatCsaf(unittest.TestCase):
    def test_full_advisory(self):
        t = fr.convert_redhat_csaf(CSAF)
        self.assertIsNotNone(t)
        self.assertTrue(t.startswith(
            "Red Hat Security Advisory RHSA-2024:1234: "
            "Red Hat Security Advisory: openvswitch2.17 security update (2024-03-07)"))
        self.assertIn("Severity: Important", t)
        self.assertIn("An update for openvswitch2.17 is now available", t)
        self.assertIn("Vulnerability CVE-2023-3966: openvswitch: ovs-vswitch "
                      "fails to recover after malformed geneve metadata packet",
                      t)
        self.assertIn("[CWE: Uncaught Exception]", t)
        self.assertIn("CVSS base score: 7.5 (HIGH)", t)
        self.assertIn("Products: Red Hat Enterprise Linux 9 (openvswitch2.17)", t)

    def test_license_note_excluded_from_body(self):
        t = fr.convert_redhat_csaf(CSAF)
        self.assertNotIn("Creative Commons", t)
        self.assertNotIn("legal_disclaimer", t)

    def test_product_dedupe(self):
        # 两个 product_id 映射到同一名字 -> 只出现一次
        c2 = {
            "document": {"title": "T", "tracking": {"id": "RHSA-2024:2",
                                                    "initial_release_date": "2024-01-01"}},
            "product_tree": {"branches": []},
            "vulnerabilities": [{
                "cve": "CVE-1", "product_status": {"fixed": ["A", "B"]},
            }],
        }
        names = {"A": "Same Product", "B": "Same Product"}
        orig = fr._walk_products
        fr._walk_products = lambda node, out, depth=0: out.update(names)
        try:
            t = fr.convert_redhat_csaf(c2)
            self.assertEqual(t.count("Same Product"), 1)
        finally:
            fr._walk_products = orig

    def test_titleless_rejected(self):
        self.assertIsNone(fr.convert_redhat_csaf({}))
        self.assertIsNone(fr.convert_redhat_csaf({"document": {"tracking": {}}}))

    def test_walk_products_recursive(self):
        tree = {"relationships": [
            {"full_product_name": {"product_id": "R1", "name": "Product R1"}}]}
        out = {}
        fr._walk_products(tree, out)
        self.assertEqual(out, {"R1": "Product R1"})


if __name__ == "__main__":
    unittest.main()
