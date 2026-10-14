"""fetch_lolbas_gtfo 转换器单测（纯函数，不触网）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_lolbas_gtfo import convert_gtfobin, convert_lolbas  # noqa: E402


class TestConvertGtfobin(unittest.TestCase):
    def test_basic_function_with_contexts(self):
        doc = convert_gtfobin("awk", {
            "functions": {
                "shell": [{
                    "code": "awk 'BEGIN {system(\"/bin/sh\")}'",
                    "contexts": {"sudo": None, "suid": None},
                }],
            },
        })
        self.assertIn("GTFOBins reference entry: awk.", doc)
        self.assertIn("shell: awk 'BEGIN {system(\"/bin/sh\")}'", doc)
        self.assertIn("(works via sudo, via SUID bit)", doc)

    def test_alias(self):
        doc = convert_gtfobin("awk", {"alias": "mawk", "functions": {}})
        self.assertIn("Aliases: mawk.", doc)

    def test_comment_preserved(self):
        doc = convert_gtfobin("x", {
            "functions": {"file-read": [{
                "code": "cat /path/to/file",
                "comment": "This only works interactively.",
                "contexts": {"unprivileged": None},
            }]},
        })
        self.assertIn("Note: This only works interactively.", doc)
        self.assertIn("(works unprivileged)", doc)

    def test_multiline_code_normalized(self):
        doc = convert_gtfobin("bash", {
            "functions": {"file-read": [{
                "code": "bash -c 'echo\n  multi\nline'",
                "contexts": {"sudo": None},
            }]},
        })
        # 多行 code 压缩为单行空白规范文本
        self.assertIn("bash -c 'echo multi line'", doc)


class TestConvertLolbas(unittest.TestCase):
    def test_full_entry(self):
        doc = convert_lolbas({
            "Name": "code.exe",
            "Description": "VSCode binary, also portable (CLI) version",
            "Commands": [{
                "Command": "code.exe tunnel --name t",
                "Description": "Starts a reverse PowerShell connection",
                "Usecase": "Reverse PowerShell session",
                "Category": "Execute",
                "Privileges": "User",
                "MitreID": "T1219.001",
                "OperatingSystem": "Windows 10, Windows 11",
            }],
            "Full_Path": [{"Path": "C:\\Program Files\\Code.exe"}],
            "Detection": [{"IOC": "Websocket traffic to global.rel.tunnels"
                                 ".api.visualstudio.com"}],
        })
        self.assertIn("LOLBAS reference entry: code.exe.", doc)
        self.assertIn("Command: code.exe tunnel --name t", doc)
        self.assertIn("MitreID: T1219.001", doc)
        self.assertIn("Path: C:\\Program Files\\Code.exe", doc)
        self.assertIn("Detection IOC: Websocket traffic", doc)

    def test_minimal_entry(self):
        doc = convert_lolbas({"Name": "x.exe", "Commands": []})
        self.assertIn("LOLBAS reference entry: x.exe.", doc)
        self.assertIn("living-off-the-land", doc)


if __name__ == "__main__":
    unittest.main()
