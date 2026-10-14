# -*- coding: utf-8 -*-
"""launch_audit（P1.8 发射审计闸）fail-closed 路径测试（纯 CPU、tmp_path 夹具、不触真实语料）。

覆盖：happy-path 全绿、各缺失/失败/未登记路径 ⇒ LAUNCH-AUDIT=FAIL、
A5 落盘核验、注册表可扩展、main 退出码契约（0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import launch_audit as la  # noqa: E402


# ================================================================ 夹具 ==
def _v(action, verdict="allow", conf=0.9, findings=None, policy="default"):
    return {"action": action, "verdict": verdict, "confidence": conf,
            "findings": findings if findings is not None else [], "policy": policy}


def _resp(action, verdict="allow", **kw):
    return {"from": "gpt",
            "value": "正文交付 body text 交付内容\nVERDICT: "
                     + json.dumps(_v(action, verdict, **kw), ensure_ascii=False)}


def _resp_raw(text):
    return {"from": "gpt", "value": text}


def _row(rid, dclass, lang, chosen, rejected, *, p16=False, polarity=None,
         form=None, arch=None, pack="default", drop_keys=(), prov="task"):
    r = {"id": rid, "dpo_class": dclass, "lang": lang, "pack": pack,
         "conversations": [{"from": "system", "value": "policy pack: default@0.1"},
                            {"from": "human", "value": f"query {rid}"}],
         "chosen": chosen, "rejected": rejected}
    if p16:
        r.update({"polarity": polarity, "rejected_form": form, "archetype_id": arch,
                  "src_task": f"task:{rid}"})          # p16 行固定 src_task（G2 口径 ✓）
    elif prov == "srcid":                              # m4 基座合法变体：src+src_id
        r.update({"src": "corpus-x", "src_id": f"sx-{rid}", "variant": "v1"})
    else:                                              # m4 基座主变体：src_task
        r.update({"src_task": f"task:{rid}", "variant": "v1"})
    for k in drop_keys:
        r.pop(k, None)
    return r


# S = action 异；C = action 同但 verdict/findings/confidence 异；F = 全同
def m4_rows():
    return [
        _row("m4-001", "policy", "en", _resp("answer"), _resp("refuse", "refuse")),
        _row("m4-002", "policy", "zh", _resp("refuse", "refuse"),
             _resp("refuse", "refuse")),
        _row("m4-003", "reserve", "en", _resp("refuse", "refuse", findings=["a"]),
             _resp("refuse", "refuse", findings=["b"]), prov="srcid"),
        _row("m4-004", "reserve", "zh", _resp("refuse", "refuse"),
             _resp("refuse", "refuse")),
    ]


def p16_rows():
    return [
        # A 良性放行（S）
        _row("p16-A-000001", "p16_benign_release", "en", _resp("answer"),
             _resp("refuse", "refuse"), p16=True, polarity="benign_release",
             form="policy_jargon_refuse", arch="A-x"),
        # D 放行向：同正文异自报（S，★D 族对比度来源）
        _row("p16-D-000001", "p16_verdict_honesty", "zh", _resp("answer"),
             _resp("refuse", "refuse"), p16=True, polarity="benign_release",
             form="deliver_but_selfreport_refuse", arch="D-rel", pack="professional"),
        # D 拒绝向：双侧 refuse/refuse 但 findings 异（C）
        _row("p16-D-000002", "p16_verdict_honesty", "en",
             _resp("refuse", "refuse", findings=["c1"]),
             _resp("refuse", "refuse", findings=["c2"]), p16=True,
             polarity="malicious_refuse", form="cd_transition_despite_refuse",
             arch="D-conv", pack="professional"),
        # F 恶意诚实（C）
        _row("p16-F-000001", "p16_malicious_honest", "zh",
             _resp("refuse", "refuse", findings=["f1"]),
             _resp("refuse", "refuse", findings=["f2"]), p16=True,
             polarity="malicious_refuse", form="lip_refuse_deliver", arch="F-x"),
    ]


M4_DIST_MINI = {"rows": 4, "dpo_class": {"policy": 2, "reserve": 2},
                "lang": {"en": 2, "zh": 2}, "scf": {"S": 1, "C": 1, "F": 2}}
P16_DIST_MINI = {"rows": 4,
                 "dpo_class": {"p16_benign_release": 1, "p16_verdict_honesty": 2,
                               "p16_malicious_honest": 1},
                 "lang": {"en": 2, "zh": 2},
                 "pack": {"default": 2, "professional": 2},
                 "polarity": {"benign_release": 2, "malicious_refuse": 2},
                 "scf": {"p16_benign_release": {"S": 1, "C": 0, "F": 0},
                         "p16_verdict_honesty": {"S": 1, "C": 1, "F": 0},
                         "p16_malicious_honest": {"S": 0, "C": 1, "F": 0}}}
STUB_PASS = "import sys\nprint('P16-GATE=PASS')\nsys.exit(0)\n"
STUB_EXIT1 = "import sys\nprint('P16-GATE=FAIL')\nsys.exit(1)\n"
STUB_NOMARK = "import sys\nprint('ok but no marker')\nsys.exit(0)\n"


def write_jsonl(path: Path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class Fixture:
    """最小发射夹具：m4 基座 4 行 + p16 两 release 2+2 行 + manifest + stub 检查器。"""

    def __init__(self, root: Path, checker_src: str = STUB_PASS):
        self.dir = root / "fix"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.m4 = self.dir / "m4.jsonl"
        self.ben = self.dir / "p16_benign_release.jsonl"
        self.mal = self.dir / "p16_malicious_honest.jsonl"
        self.man = self.dir / "p16-cal" / "manifest.json"
        self.man.parent.mkdir(parents=True, exist_ok=True)
        self.checker = self.dir / "stub_checker.py"
        self.checker.write_text(checker_src, encoding="utf-8")
        self.rows_m4 = m4_rows()
        self.rows_p16 = p16_rows()
        self.ben_rows = [r for r in self.rows_p16 if r["polarity"] == "benign_release"]
        self.mal_rows = [r for r in self.rows_p16 if r["polarity"] == "malicious_refuse"]
        self.rewrite()
        self.cfg = la.AuditConfig(
            tag="t", mix_path=self.dir / "dpo_m5_calib.jsonl",
            m4_base=self.m4, p16_benign=self.ben, p16_malicious=self.mal,
            p16_manifest=self.man, p16_checker=self.checker,
            report_dir=self.dir / "reports",
            m4_dist=json.loads(json.dumps(M4_DIST_MINI)),
            p16_dist=json.loads(json.dumps(P16_DIST_MINI)),
            frozen_m4_sha256=la.sha256_file(self.m4),
            total_rows=8, d_family="p16_verdict_honesty", p16_timeout_s=60)

    def rewrite(self):
        write_jsonl(self.m4, self.rows_m4)
        write_jsonl(self.ben, self.ben_rows)
        write_jsonl(self.mal, self.mal_rows)
        self.man.write_text(json.dumps(
            {"files": {"p16_benign_release.jsonl":
                       {"sha256": la.sha256_file(self.ben), "rows": len(self.ben_rows)},
                       "p16_malicious_honest.jsonl":
                       {"sha256": la.sha256_file(self.mal), "rows": len(self.mal_rows)}}},
            ensure_ascii=False, indent=1), encoding="utf-8")

    def resync_base_sha(self):
        """m4 内容变更为『已登记的新基座』：重算冻结 sha（A4 保持绿，隔离被测路径）。"""
        self.cfg.frozen_m4_sha256 = la.sha256_file(self.m4)

    def run(self, registry=None):
        return la.run_audit(self.cfg, registry=registry, log=None)

    def report(self):
        return json.loads((self.cfg.report_dir / "launch-audit-t.json")
                          .read_text(encoding="utf-8"))


def reasons_of(doc, cid):
    c = doc.get("checks", {}).get(cid, {})
    return c.get("reasons", []) if isinstance(c, dict) else []


# ================================================================ 测试 ==
class TestHappyPath(unittest.TestCase):
    def test_all_pass(self):
        """happy path：五检全绿 ⇒ PASS + 报告落盘且注册表闭合 ✓。"""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-happy-") as td:
            fx = Fixture(Path(td))
            doc = fx.run()
            self.assertEqual(doc["verdict"], "PASS")
            self.assertEqual(sorted(doc["checks"]), ["A1", "A2", "A3", "A4", "A5"])
            rp = Path(doc["report_path"])
            self.assertTrue(rp.exists())
            on_disk = json.loads(rp.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["verdict"], "PASS")
            self.assertEqual(sorted(on_disk["checks"]), ["A1", "A2", "A3", "A4", "A5"])
            self.assertEqual(on_disk["mixture"]["mode"], "virtual-union")
            self.assertEqual(on_disk["mixture"]["rows"], 8)

    def test_d_family_key_reading_delivered(self):
        """★关键新读数：D 族内容对比度交付（S+C = n，F = 0）✓。"""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-dfam-") as td:
            fx = Fixture(Path(td))
            doc = fx.run()
            kr = doc["checks"]["A1"]["metrics"]["key_reading_d_family"]
            self.assertEqual(kr["dpo_class"], "p16_verdict_honesty")
            self.assertEqual((kr["S"], kr["C"], kr["F"]), (1, 1, 0))
            self.assertTrue(kr["delivered"])
            # 全量对比度表 + 标记读数在盘
            self.assertIn("per_dpo_class", doc["checks"]["A1"]["metrics"])
            self.assertIn("marker_contrast_rate", doc["checks"]["A1"]["metrics"])

    def test_materialized_mix_mode(self):
        """物化模式：mix 文件存在 ⇒ materialized + id 集闭合 ✓。"""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-mat-") as td:
            fx = Fixture(Path(td))
            write_jsonl(fx.cfg.mix_path, fx.rows_m4 + fx.rows_p16)
            doc = fx.run()
            self.assertEqual(doc["verdict"], "PASS")
            self.assertEqual(doc["mixture"]["mode"], "materialized")

    def test_marker_contrast_is_reported_reading(self):
        """标记对比度为读数非门：仅 chosen 带 VERDICT 的行被如实计数 ✓。"""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-mark-") as td:
            fx = Fixture(Path(td))
            # m4-001（S 行）rejected 去掉 VERDICT：S/C/F 分类不变（仍 S）⇒ 不触发门禁
            fx.rows_m4[0]["rejected"] = _resp_raw("没有标记的拒绝正文")
            fx.rewrite()
            fx.resync_base_sha()          # 内容变更视为已登记基座（隔离 A4 谱系路径 ✗）
            doc = fx.run()
            self.assertEqual(doc["verdict"], "PASS")
            m = doc["checks"]["A1"]["metrics"]
            self.assertEqual(m["per_dpo_class"]["policy"]["marker_contrast"], 1)
            self.assertAlmostEqual(m["marker_contrast_rate"], 1 / 8)


class TestFailClosed(unittest.TestCase):
    """fail-closed 各路径：缺失/失败/未登记 ⇒ FAIL + 明确拒绝理由 ✗。"""

    def _fx(self, prefix):
        import tempfile
        td = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(td.cleanup)
        return Fixture(Path(td.name))

    def test_missing_sources_rejected(self):
        """混料源缺失 ⇒ A1/A3 FAIL（无数据 = 拒绝 ✗）。"""
        fx = self._fx("la-miss-")
        fx.m4.unlink()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        rs = reasons_of(doc, "A1")
        self.assertTrue(any("装配失败" in r and "缺输入" in r for r in rs), rs)

    def test_row_count_mismatch_rejected(self):
        """行数漂移 ⇒ A1（总量）+ A3（分布）双 FAIL ✗。"""
        fx = self._fx("la-rows-")
        fx.rows_m4.append(_row("m4-005", "policy", "en", _resp("answer"),
                               _resp("refuse", "refuse")))
        fx.rewrite()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("!= 预注册" in r for r in reasons_of(doc, "A1")))
        self.assertTrue(any("总行数" in r for r in reasons_of(doc, "A3")))

    def test_p16_gate_exit_code_passthrough(self):
        """A2 退出码透传：checker 退出 1 ⇒ FAIL ✗。"""
        fx = self._fx("la-gate1-")
        fx.checker.write_text(STUB_EXIT1, encoding="utf-8")
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("退出码 1" in r for r in reasons_of(doc, "A2")),
                        reasons_of(doc, "A2"))
        self.assertEqual(doc["checks"]["A2"]["metrics"]["exit_code"], 1)

    def test_p16_gate_marker_missing_rejected(self):
        """A2 标记缺失：退出 0 但无 P16-GATE=PASS ⇒ FAIL（无 PASS 输出 = 拒绝 ✗✓）。"""
        fx = self._fx("la-gate2-")
        fx.checker.write_text(STUB_NOMARK, encoding="utf-8")
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("P16-GATE=PASS" in r and "无" in r
                            for r in reasons_of(doc, "A2")), reasons_of(doc, "A2"))

    def test_p16_gate_checker_missing_rejected(self):
        """A2 检查器文件缺失 ⇒ FAIL ✗。"""
        fx = self._fx("la-gate3-")
        fx.checker.unlink()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("缺失" in r for r in reasons_of(doc, "A2")))

    def test_lineage_sha_mismatch_rejected(self):
        """A4 谱系：release 被动一字节 ⇒ sha256 != manifest 冻结值 ⇒ FAIL ✗。"""
        fx = self._fx("la-sha-")
        with open(fx.ben, "a", encoding="utf-8") as f:
            f.write("\n")                      # 行数不变，sha 变
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        rs = reasons_of(doc, "A4")
        self.assertTrue(any("sha256" in r and "manifest 冻结值" in r for r in rs), rs)

    def test_lineage_missing_manifest_rejected(self):
        """A4 manifest 缺失 ⇒ FAIL ✗。"""
        fx = self._fx("la-man-")
        fx.man.unlink()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("manifest 缺失" in r for r in reasons_of(doc, "A4")))

    def test_distribution_drift_rejected(self):
        """A3 分布漂移：p16 行 dpo_class 改动 ⇒ 配比断言 FAIL ✗。"""
        fx = self._fx("la-dist-")
        fx.rows_p16[1]["dpo_class"] = "p16_benign_release"   # D 行改挂 A 族
        fx.rewrite()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        rs = reasons_of(doc, "A3")
        self.assertTrue(any("p16 dpo_class 分布漂移" in r for r in rs), rs)
        self.assertTrue(any("对比度漂移" in r for r in reasons_of(doc, "A1")))

    def test_schema_violation_rejected(self):
        """A3 schema：m4 行缺核心键（pack）⇒ FAIL ✗。"""
        fx = self._fx("la-sch-")
        fx.rows_m4[0] = _row("m4-001", "policy", "en", _resp("answer"),
                             _resp("refuse", "refuse"), drop_keys=("pack",))
        fx.rewrite()
        fx.resync_base_sha()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("核心七键缺失" in r for r in reasons_of(doc, "A3")))

    def test_schema_provenance_missing_rejected(self):
        """A3 schema：谱系键两变体均缺 ⇒ FAIL ✗。"""
        fx = self._fx("la-prov-")
        fx.rows_m4[0] = _row("m4-001", "policy", "en", _resp("answer"),
                             _resp("refuse", "refuse"),
                             drop_keys=("src_task", "variant"))
        fx.rows_m4[0]["src"] = "corpus-x"          # 只有 src，缺 src_id（不构成合法变体）
        fx.rewrite()
        fx.resync_base_sha()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("谱系键缺失" in r for r in reasons_of(doc, "A3")))

    def test_unregistered_dpo_class_rejected(self):
        """A1 未登记类：混料出现注册表外 dpo_class ⇒ 拒绝 ✗。"""
        fx = self._fx("la-unreg-")
        fx.rows_m4.append(_row("m4-005", "mystery", "en", _resp("answer"),
                               _resp("refuse", "refuse")))
        fx.rewrite()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("未登记 dpo_class" in r for r in reasons_of(doc, "A1")))

    def test_d_family_contrast_loss_rejected(self):
        """★D 族对比度丢失（F 类出现）⇒ A1 FAIL（关键读数即门 ✗✓）。"""
        fx = self._fx("la-dloss-")
        # D-000002 双侧全同 ⇒ F 类 ⇒ D 族对比度不再 100%
        fx.rows_p16[2]["rejected"] = _resp("refuse", "refuse", findings=["c1"])
        fx.rewrite()
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        rs = reasons_of(doc, "A1")
        self.assertTrue(any("未交付 100% 内容对比度" in r for r in rs), rs)
        kr = doc["checks"]["A1"]["metrics"]["key_reading_d_family"]
        self.assertFalse(kr["delivered"])

    def test_materialized_mix_id_tamper_rejected(self):
        """物化模式 id 闭合：混料里混入外来 id ⇒ id 集不闭合 ⇒ FAIL ✗。"""
        import copy as _copy
        fx = self._fx("la-idt-")
        rogue = _copy.deepcopy(fx.rows_m4[0])
        rogue["id"] = "m4-999"                      # 外来 id（非基座集合成员）
        write_jsonl(fx.cfg.mix_path, fx.rows_m4 + fx.rows_p16 + [rogue])
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("id 集" in r and "不闭合" in r for r in reasons_of(doc, "A3")),
                        reasons_of(doc, "A3"))

    def test_materialized_mix_duplicate_id_rejected(self):
        """物化模式 id 唯一：同 id 复制一行 ⇒ id 重复 ⇒ FAIL ✗。"""
        import copy as _copy
        fx = self._fx("la-dup-")
        dup = _copy.deepcopy(fx.rows_m4[0])
        write_jsonl(fx.cfg.mix_path, fx.rows_m4 + fx.rows_p16 + [dup])
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertTrue(any("id 重复" in r for r in reasons_of(doc, "A3")),
                        reasons_of(doc, "A3"))

    def test_report_unwritable_hard_fail(self):
        """无审计输出 = 拒绝 ✗✓：报告路径不可写 ⇒ verdict=FAIL + write_error。"""
        fx = self._fx("la-nowrite-")
        fx.cfg.report_dir = fx.dir / "blocker"      # 同名文件挡住目录创建
        fx.cfg.report_dir.write_text("occupied", encoding="utf-8")
        doc = fx.run()
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertIn("write_error", doc)


class TestOutputGate(unittest.TestCase):
    """A5 落盘核验的直测路径。"""

    def _doc(self, **over):
        base = {"tag": "t", "generated_at": "x", "verdict": "PENDING",
                "checks": {"A1": {"pass": True}, "A3": {"pass": True},
                           "A2": {"pass": True}, "A4": {"pass": True}},
                "registry": [], "mixture": {}, "fail_closed_rule": "r"}
        base.update(over)
        return base

    def test_missing_report_rejected(self):
        res = la.check_output(la.AuditConfig(tag="t"), la.DEFAULT_REGISTRY,
                              {}, Path("Z:/nonexistent/launch-audit-t.json"))
        self.assertFalse(res.ok)
        self.assertTrue(any("审计输出缺失" in r for r in res.reasons))

    def test_tampered_report_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-a5-") as td:
            rp = Path(td) / "launch-audit-t.json"
            cfg = la.AuditConfig(tag="t")
            good_checks = {s.cid: la.CheckResult(True) for s in la.DEFAULT_REGISTRY
                           if s.phase == "data"}
            # ① tag 不符
            rp.write_text(json.dumps(self._doc(tag="other")), encoding="utf-8")
            res = la.check_output(cfg, la.DEFAULT_REGISTRY, good_checks, rp)
            self.assertFalse(res.ok)
            self.assertTrue(any("tag" in r for r in res.reasons))
            # ② 缺 data 相检查（未落盘 = 未执行 ✗）
            doc = self._doc()
            doc["checks"].pop("A2")
            rp.write_text(json.dumps(doc), encoding="utf-8")
            res = la.check_output(cfg, la.DEFAULT_REGISTRY, good_checks, rp)
            self.assertFalse(res.ok)
            self.assertTrue(any("缺 data 相注册检查" in r for r in res.reasons))
            # ③ 含未注册检查 ✗
            doc = self._doc()
            doc["checks"]["A9"] = {"pass": True}
            rp.write_text(json.dumps(doc), encoding="utf-8")
            res = la.check_output(cfg, la.DEFAULT_REGISTRY, good_checks, rp)
            self.assertFalse(res.ok)
            self.assertTrue(any("含未注册检查" in r for r in res.reasons))
            # ④ 判定不一致（盘上 A1 pass=False vs 实测 True）✗
            doc = self._doc()
            doc["checks"]["A1"]["pass"] = False
            rp.write_text(json.dumps(doc), encoding="utf-8")
            res = la.check_output(cfg, la.DEFAULT_REGISTRY, good_checks, rp)
            self.assertFalse(res.ok)
            self.assertTrue(any("A1 pass=False != 实测 True" in r for r in res.reasons))
            # ⑤ 非本次产物（verdict 非 PENDING）✗
            rp.write_text(json.dumps(self._doc(verdict="PASS")), encoding="utf-8")
            res = la.check_output(cfg, la.DEFAULT_REGISTRY, good_checks, rp)
            self.assertFalse(res.ok)
            self.assertTrue(any("PENDING" in r for r in res.reasons))
            # ⑥ 正常在途报告 ⇒ PASS ✓
            rp.write_text(json.dumps(self._doc()), encoding="utf-8")
            res = la.check_output(cfg, la.DEFAULT_REGISTRY, good_checks, rp)
            self.assertTrue(res.ok, res.reasons)

    def test_corrupt_json_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-a5b-") as td:
            rp = Path(td) / "launch-audit-t.json"
            rp.write_text("{not json", encoding="utf-8")
            res = la.check_output(la.AuditConfig(tag="t"), la.DEFAULT_REGISTRY,
                                  {}, rp)
            self.assertFalse(res.ok)
            self.assertTrue(any("不可解析" in r for r in res.reasons))


class TestRegistryExtensible(unittest.TestCase):
    """注册表可扩展：追加 CheckSpec 自动进报告与闭合校验 ✓。"""

    def test_extra_check_included(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-ext-") as td:
            fx = Fixture(Path(td))
            reg = list(la.DEFAULT_REGISTRY) + [
                la.CheckSpec("A6", "未来审计件（示例）", lambda ctx: la.CheckResult(True))]
            doc = fx.run(registry=reg)
            self.assertEqual(doc["verdict"], "PASS")
            self.assertIn("A6", doc["checks"])
            self.assertEqual([r["id"] for r in doc["registry"]][-1], "A6")

    def test_extra_check_failure_propagates(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-ext2-") as td:
            fx = Fixture(Path(td))
            reg = list(la.DEFAULT_REGISTRY) + [
                la.CheckSpec("A6", "未来审计件（失败例）",
                             lambda ctx: la.CheckResult(False, ["示例拒绝"]))]
            doc = fx.run(registry=reg)
            self.assertEqual(doc["verdict"], "FAIL")
            self.assertIn("示例拒绝", reasons_of(doc, "A6"))

    def test_data_check_exception_is_fail_closed(self):
        """检查函数抛异常 ⇒ 该检查 FAIL（异常即拒绝 ✗）。"""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="la-exc-") as td:
            fx = Fixture(Path(td))
            reg = [la.CheckSpec("A1", la.DEFAULT_REGISTRY[0].title,
                                lambda ctx: 1 / 0)] + list(la.DEFAULT_REGISTRY[1:])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):        # traceback.print_exc 噪声隔离
                doc = fx.run(registry=reg)
            self.assertEqual(doc["verdict"], "FAIL")
            self.assertTrue(any("ZeroDivisionError" in r for r in reasons_of(doc, "A1")))


class TestCliContract(unittest.TestCase):
    """main()：--list-checks / 退出码 0=PASS · 1=FAIL（fail-closed 契约 ✓）。"""

    def test_list_checks(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = la.main(["--list-checks"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        for cid in ("A1", "A2", "A3", "A4", "A5"):
            self.assertIn(cid, out)

    def test_exit_code_pass_fail(self):
        for verdict, want in (("PASS", 0), ("FAIL", 1)):
            doc = {"verdict": verdict, "checks": {"A1": {"verdict": verdict}},
                   "report_path": "x"}
            with mock.patch.object(la, "run_audit", return_value=doc):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = la.main(["--tag", "t"])
            self.assertEqual(rc, want)
            self.assertIn(f"LAUNCH-AUDIT={verdict}", buf.getvalue())

    def test_write_error_fail_exit(self):
        doc = {"verdict": "FAIL", "write_error": "disk full",
               "checks": {"A1": "FAIL"}, "report_path": "x"}
        with mock.patch.object(la, "run_audit", return_value=doc):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = la.main(["--tag", "t"])
        self.assertEqual(rc, 1)
        self.assertIn("LAUNCH-AUDIT=FAIL", buf.getvalue())
        self.assertIn("disk full", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
