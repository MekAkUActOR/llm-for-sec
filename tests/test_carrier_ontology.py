# -*- coding: utf-8 -*-
"""`data/ontology/carriers.json` + `scripts/check_carrier_ontology.py` 的回归锁定。

与仓库既有风格一致（tests/test_dpo_carriers.py）分两类：

1. **真数据**：对真实本体 + 真实磁盘事实跑全部硬断言（与 CI 同一入口）；
2. **故意做坏**：逐条破坏本体/事实，确认 checker 会拦下——防止"断言写宽了"
   或"断言写空了"这类静默失效（`docs/01 §11` 的评估纪律）。

跑法（unittest，无第三方依赖）：

    .venv\\Scripts\\python.exe -m unittest tests.test_carrier_ontology -v

注意：本套件会**只读**扫描 `data/lf/*.jsonl`（≈6.9 GB）+ `data/sft/**` +
`data/dpo/**` + `data/heldout/**`。`setUpModule` 扫一次并缓存；CLI 子进程测试
各扫一次。总耗时约 1–3 分钟，纯 CPU、不涉 GPU。
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_carrier_ontology as C  # noqa: E402

ONTOLOGY = ROOT / "data" / "ontology" / "carriers.json"
PY = sys.executable

_FACTS = None
_ONT = None


def setUpModule():  # noqa: N802（unittest 约定名）
    global _FACTS, _ONT
    _FACTS = C.collect_facts()
    _ONT = json.loads(ONTOLOGY.read_text(encoding="utf-8"))


def errs(ontology, facts=None):
    e, _ = C.run_check(ontology, facts if facts is not None else _FACTS)
    return e


def has(errors, prefix):
    return any(x.startswith(prefix) for x in errors), errors


class TestRealOntology(unittest.TestCase):
    """真数据：本体必须与磁盘逐格一致。"""

    def test_ontology_file_exists_and_parses(self):
        self.assertTrue(ONTOLOGY.exists(), f"缺件：{ONTOLOGY}")
        self.assertIsInstance(_ONT, dict)

    def test_top_level_required_keys(self):
        for k in C.REQUIRED_TOP_LEVEL:
            self.assertIn(k, _ONT, f"缺顶层键 {k}")

    def test_every_carrier_has_required_fields_and_unique_id(self):
        ids = [c["id"] for c in _ONT["carriers"]]
        self.assertEqual(len(ids), len(set(ids)), f"id 不唯一：{ids}")
        for c in _ONT["carriers"]:
            for f in C.REQUIRED_CARRIER_FIELDS:
                self.assertIn(f, c, f"{c['id']} 缺字段 {f}")

    def test_full_check_passes_with_zero_errors(self):
        errors, detail = C.run_check(_ONT, _FACTS)
        self.assertEqual(errors, [], f"真数据下不应有错误：{errors}")
        self.assertEqual(C.banner(errors), C._OK_SENTINEL)
        self.assertGreaterEqual(detail["counts"]["ontology_carriers"], 9)
        self.assertGreater(detail["counts"]["scanned_files"], 10)

    def test_all_observed_labels_are_inside_the_ontology(self):
        observed = set(_FACTS["observed_carriers"])
        ids = {c["id"] for c in _ONT["carriers"]}
        self.assertTrue(observed <= ids, f"本体外标签：{sorted(observed - ids)}")

    def test_unseen_gate_carriers_are_exactly_image_and_av_metadata(self):
        """最关键的一条：只有 image/av 元数据有达标的未见载体门禁。"""
        errors, detail = C.run_check(_ONT, _FACTS)
        self.assertEqual(detail["unseen_gate_carriers"],
                         ["av_metadata", "image_metadata"])
        self.assertEqual(
            sorted(detail["no_unseen_gate_carriers"]),
            ["code", "document", "email", "log", "text", "tool_output",
             "webpage"])
        self.assertEqual(_ONT["claims"]["unseen_carrier_gate_carriers"],
                         _ONT["claims"]["unseen_carrier_gate_carriers"])

    def test_claim_boundary_matches_computed_matrix(self):
        for cid, cols in _FACTS["coverage_matrix"].items():
            rb = cols["unseen_gate"]["robustness_n"]
            in_claims = cid in _ONT["claims"]["unseen_carrier_gate_carriers"]
            self.assertEqual(in_claims, rb >= C.MIN_UNSEEN_ROBUSTNESS_N,
                             f"{cid} 的结论边界与实算不符（robustness_n={rb}）")


class TestMissingField(unittest.TestCase):
    """字段缺失 → 报错。"""

    def test_missing_required_field(self):
        ont = copy.deepcopy(_ONT)
        del ont["carriers"][0]["gaps"]
        found, errors = has(errs(ont), f"missing_field:{ont['carriers'][0]['id']}:gaps")
        self.assertTrue(found, errors)

    def test_each_required_field_is_actually_needed(self):
        for f in C.REQUIRED_CARRIER_FIELDS:
            ont = copy.deepcopy(_ONT)
            cid = ont["carriers"][2]["id"]
            del ont["carriers"][2][f]
            want = "missing_field_id:carrier[2]" if f == "id" \
                else f"missing_field:{cid}:{f}"
            found, errors = has(errs(ont), want)
            self.assertTrue(found, f"删掉 {f} 后 checker 没报错：{errors}")

    def test_missing_top_level_section(self):
        ont = copy.deepcopy(_ONT)
        del ont["claims"]
        found, errors = has(errs(ont), "claims")
        self.assertTrue(found, errors)

    def test_empty_list_field(self):
        ont = copy.deepcopy(_ONT)
        ont["carriers"][1]["renderings"] = []
        found, errors = has(errs(ont), f"empty_list_field:{ont['carriers'][1]['id']}:renderings")
        self.assertTrue(found, errors)

    def test_duplicate_id(self):
        ont = copy.deepcopy(_ONT)
        ont["carriers"].append(copy.deepcopy(ont["carriers"][0]))
        found, errors = has(errs(ont), "duplicate_id:text")
        self.assertTrue(found, errors)


class TestUnknownCarrierLabel(unittest.TestCase):
    """未知载体标签 → 报错（并给出文件名 + 行号样本）。"""

    def test_unknown_label_from_injected_facts(self):
        facts = copy.deepcopy(_FACTS)
        facts["observed_carriers"]["hologram"] = 3
        facts["label_samples"]["hologram"] = [
            {"file": "data/lf/fake_corpus.jsonl", "line": 41},
            {"file": "data/heldout/v9/hologram.jsonl", "line": 2},
        ]
        found, errors = has(errs(_ONT, facts), "unknown_carrier_label:hologram")
        self.assertTrue(found, errors)
        msg = next(x for x in errors if x.startswith("unknown_carrier_label:hologram"))
        self.assertIn("data/lf/fake_corpus.jsonl:41", msg)
        self.assertIn("data/heldout/v9/hologram.jsonl:2", msg)
        self.assertIn("rows=3", msg)

    def test_unknown_label_in_coverage_matrix(self):
        """本体为一个不存在的载体声明了矩阵格 → 报错。"""
        ont = copy.deepcopy(_ONT)
        ont["coverage_matrix"]["cells"]["hologram"] = copy.deepcopy(
            ont["coverage_matrix"]["cells"]["text"])
        found, errors = has(errs(ont), "matrix_unknown_carrier:hologram")
        self.assertTrue(found, errors)


class TestNumberDrift(unittest.TestCase):
    """数字漂移 → 报错（数字必须现算，不得写死）。"""

    def test_train_rows_drift(self):
        ont = copy.deepcopy(_ONT)
        entry = next(c for c in ont["carriers"] if c["id"] == "text")
        entry["train_rows"]["sft_m25"] = 9999
        found, errors = has(errs(ont), "train_rows_mismatch:text:sft_m25")
        self.assertTrue(found, errors)
        self.assertNotEqual(errs(ont), [])

    def test_every_carrier_scope_pair_is_checked(self):
        """逐格抽查：任取一格的移动都必须被抓住（不许有"没被断言的格"）。"""
        for cid in ("email", "document", "av_metadata"):
            for scope in ("sft_m25", "sec_sft_topup", "lf_total"):
                ont = copy.deepcopy(_ONT)
                entry = next(c for c in ont["carriers"] if c["id"] == cid)
                entry["train_rows"][scope] += 1
                found, errors = has(errs(ont),
                                    f"train_rows_mismatch:{cid}:{scope}")
                self.assertTrue(found, f"{cid}/{scope} 漂移没被抓住：{errors}")

    def test_gate_items_drift(self):
        ont = copy.deepcopy(_ONT)
        entry = next(c for c in ont["carriers"] if c["id"] == "tool_output")
        entry["gate_items"]["v0.4-toolout"] = 0
        found, errors = has(errs(ont), "gate_items_mismatch:tool_output:v0.4-toolout")
        self.assertTrue(found, errors)

    def test_unknown_scope_key(self):
        ont = copy.deepcopy(_ONT)
        entry = next(c for c in ont["carriers"] if c["id"] == "code")
        entry["gate_items"]["v9-made-up"] = 5
        found, errors = has(errs(ont), "gate_items_unknown_scope:code")
        self.assertTrue(found, errors)

    def test_instrument_rows_drift(self):
        ont = copy.deepcopy(_ONT)
        ont["instruments"]["v0.3-gen"]["rows"] = 122
        found, errors = has(errs(ont), "instrument_mismatch:v0.3-gen:rows")
        self.assertTrue(found, errors)

    def test_instrument_per_carrier_drift(self):
        ont = copy.deepcopy(_ONT)
        ont["instruments"]["v0.3-gen"]["per_carrier_robustness"]["av_metadata"] = 88 + 1
        found, errors = has(errs(ont),
                            "instrument_mismatch:v0.3-gen:per_carrier_robustness")
        self.assertTrue(found, errors)


class TestCoverageMatrix(unittest.TestCase):
    """覆盖矩阵每一格与实算一致。"""

    def test_cell_count_drift(self):
        ont = copy.deepcopy(_ONT)
        ont["coverage_matrix"]["cells"]["webpage"]["in_dist_capability"]["n"] = 31
        found, errors = has(errs(ont), "matrix_mismatch:webpage:in_dist_capability:n")
        self.assertTrue(found, errors)

    def test_cell_basis_drift(self):
        ont = copy.deepcopy(_ONT)
        ont["coverage_matrix"]["cells"]["text"]["train"]["basis"] = "sft_m25"
        found, errors = has(errs(ont), "matrix_mismatch:text:train:basis")
        self.assertTrue(found, errors)

    def test_cell_linked_field_inconsistency(self):
        """矩阵格与条目字段是两处副本：任何一处漂移都要报（防各自漂移）。

        `train` 列的依据 scope 自 2026-09-30 晚起是 **`live_lineage`**
        （原为 `lf_total`；改因见 docs/01 §11.24 规则 24：`lf_total` 会把未使用文件与
        已废弃分支算成已训），因此这里动 `live_lineage`。
        """
        ont = copy.deepcopy(_ONT)
        entry = next(c for c in ont["carriers"] if c["id"] == "log")
        entry["train_rows"]["live_lineage"] += 1  # 只动条目，不动矩阵
        found, errors = has(errs(ont),
                            "matrix_linked_field_mismatch:log:train")
        self.assertTrue(found, errors)
        # 同时必须报出条目字段与磁盘事实的漂移
        found2, _ = has(errors, "train_rows_mismatch:log:live_lineage")
        self.assertTrue(found2, errors)

    def test_missing_cell(self):
        ont = copy.deepcopy(_ONT)
        del ont["coverage_matrix"]["cells"]["email"]["unseen_gate"]
        found, errors = has(errs(ont), "matrix_missing_cell:email:unseen_gate")
        self.assertTrue(found, errors)


class TestConclusionBoundary(unittest.TestCase):
    """结论边界的机械断言（docs/01 §11.2 每格 ≥34 的效力下限）。"""

    def test_power_below_floor_is_an_error(self):
        """本体不得把一个低于 docs/01 §11.2 底线的门禁写成可用门禁。"""
        ont = copy.deepcopy(_ONT)
        ont["coverage_matrix"]["cells"]["image_metadata"]["unseen_gate"]["robustness_n"] = 33
        found, errors = has(errs(ont),
                            "unseen_gate_power_below_floor:image_metadata")
        self.assertTrue(found, errors)

    def test_power_floor_applies_to_computed_facts_too(self):
        """现算事实低于底线同样要报（本体与事实同步漂移也不能过）。"""
        facts = copy.deepcopy(_FACTS)
        facts["coverage_matrix"]["image_metadata"]["unseen_gate"]["robustness_n"] = 10
        facts["instruments"]["v0.3-gen"]["per_carrier_robustness"]["image_metadata"] = 10
        ont = copy.deepcopy(_ONT)
        ont["coverage_matrix"]["cells"]["image_metadata"]["unseen_gate"]["robustness_n"] = 10
        ont["instruments"]["v0.3-gen"]["per_carrier_robustness"]["image_metadata"] = 10
        ont["claims"]["unseen_carrier_gate_carriers"] = ["av_metadata"]
        ont["claims"]["no_unseen_gate_carriers"] = sorted(
            set(ont["claims"]["no_unseen_gate_carriers"]) | {"image_metadata"})
        found, errors = has(errs(ont, facts),
                            "unseen_gate_power_below_floor:image_metadata")
        self.assertTrue(found, errors)

    def test_claims_list_drift(self):
        ont = copy.deepcopy(_ONT)
        ont["claims"]["unseen_carrier_gate_carriers"] = ["image_metadata"]
        found, errors = has(errs(ont), "claims_unseen_carrier_gate_carriers_mismatch")
        self.assertTrue(found, errors)

    def test_claims_no_gate_list_drift(self):
        ont = copy.deepcopy(_ONT)
        ont["claims"]["no_unseen_gate_carriers"] = ["code", "document"]
        found, errors = has(errs(ont), "claims_no_unseen_gate_carriers_mismatch")
        self.assertTrue(found, errors)


class TestMissionMapping(unittest.TestCase):
    def test_unknown_engineering_id(self):
        ont = copy.deepcopy(_ONT)
        ont["mission_to_engineering"]["webpage"]["engineering_ids"] = ["webpage", "nope"]
        found, errors = has(errs(ont), "mission_map_unknown_carrier:webpage->nope")
        self.assertTrue(found, errors)

    def test_unmapped_carrier(self):
        ont = copy.deepcopy(_ONT)
        ont["mission_to_engineering"]["code"]["engineering_ids"] = []
        found, errors = has(errs(ont), "mission_map_unmapped_carrier:code")
        self.assertTrue(found, errors)

    def test_unknown_mission(self):
        ont = copy.deepcopy(_ONT)
        ont["mission_to_engineering"]["telepathy"] = {"engineering_ids": ["text"]}
        found, errors = has(errs(ont), "mission_map_unknown_mission:telepathy")
        self.assertTrue(found, errors)


class TestCli(unittest.TestCase):
    """CLI 契约：末行格式与退出码。"""

    def _run(self, *args):
        return subprocess.run(
            [PY, str(ROOT / "scripts" / "check_carrier_ontology.py"), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT))

    def test_good_ontology_exit_0_and_pass_banner(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        last = [l for l in r.stdout.strip().splitlines() if l.strip()][-1]
        self.assertEqual(last, "CARRIER-ONTOLOGY-CHECK=PASS errors=0")

    def test_broken_ontology_exit_1_and_fail_banner(self):
        ont = copy.deepcopy(_ONT)
        next(c for c in ont["carriers"] if c["id"] == "code")["train_rows"]["sft_m25"] = 1
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps(ont, ensure_ascii=False), encoding="utf-8")
            r = self._run("--ontology", str(p), "--quiet")
        self.assertEqual(r.returncode, 1, r.stdout[-2000:])
        last = [l for l in r.stdout.strip().splitlines() if l.strip()][-1]
        self.assertTrue(last.startswith("CARRIER-ONTOLOGY-CHECK=FAIL errors="), last)
        self.assertNotIn("errors=0", last)

    def test_missing_ontology_fails_closed(self):
        r = self._run("--ontology", "reports/_definitely_missing_ontology.json",
                      "--quiet")
        self.assertEqual(r.returncode, 2, r.stdout[-2000:])
        self.assertIn("CARRIER-ONTOLOGY-CHECK=FAIL errors=1", r.stdout)

    def test_unparsable_ontology_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "broken.json"
            p.write_text("{not json", encoding="utf-8")
            r = self._run("--ontology", str(p), "--quiet")
        self.assertEqual(r.returncode, 2, r.stdout[-2000:])
        self.assertIn("CARRIER-ONTOLOGY-CHECK=FAIL errors=1", r.stdout)

    def test_census_mode_prints_matrix(self):
        r = self._run("--census")
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        self.assertIn("覆盖矩阵", r.stdout)
        self.assertIn("image_metadata", r.stdout)


class TestBannerFormat(unittest.TestCase):
    def test_banner_pass_and_fail(self):
        self.assertEqual(C.banner([]), "CARRIER-ONTOLOGY-CHECK=PASS errors=0")
        self.assertEqual(C.banner(["a"]), "CARRIER-ONTOLOGY-CHECK=FAIL errors=1")
        self.assertEqual(C.banner(["a", "b", "c"]),
                         "CARRIER-ONTOLOGY-CHECK=FAIL errors=3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
