# -*- coding: utf-8 -*-
"""`scripts/build_dpo_carriers.py` + `scripts/check_dpo_carriers.py` 的回归锁定。

两类测试：
1. **真数据**：对 `data/lf/dpo_m3_carriers_v1.jsonl` 跑全部硬断言（与 CI 同一入口）；
2. **故意做坏的 fixture**：把好批次按 6 种方式破坏，逐条确认 checker 会拦下——
   防止"断言写宽了/写空了"这类静默失效（docs/01 §11 的评估纪律）。
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_dpo_carriers as B  # noqa: E402
import check_dpo_carriers as C  # noqa: E402

ROWS = ROOT / "data" / "lf" / "dpo_m3_carriers_v1.jsonl"

# 测试用宽阈值：fixture 是"好批次的子集"，只关心被破坏的那条断言是否亮红
LOOSE = {"rows_min": 1, "min_per_carrier": 1, "min_clean_share": 0.0,
         "body_run_report_cap": 10 ** 9}


@pytest.fixture(scope="module")
def rows():
    return C.load_rows(ROWS)


@pytest.fixture(scope="module")
def tiny():
    """好批次的小切片（含三种错误类 + 良性负例）。"""
    all_rows = C.load_rows(ROWS)
    keep, seen = [], set()
    for r in all_rows:
        k = C.classify_rejected(r)
        if k not in seen or len(keep) < 40:
            seen.add(k)
            keep.append(r)
        if len(keep) >= 60 and len(seen) >= 3:
            break
    return keep


def failed(rows, spec=None, **kw):
    rep = C.run_assertions(rows, spec=spec or LOOSE, do_disjoint=False, **kw)
    return rep["failures"]


# ============================================================ 真数据 ===
def test_batch_passes_every_hard_assertion(rows):
    rep = C.run_assertions(rows, heldout=C.load_heldout())
    assert rep["failures"] == [], rep["failures"]


def test_batch_size_and_carrier_quotas(rows):
    rep = C.run_assertions(rows, spec={**LOOSE}, do_disjoint=False)
    c = rep["counts"]
    assert 4000 <= c["rows"] <= 8000
    for ctype in ("tool_output", "log", "webpage", "code", "document"):
        assert c["carriers"][ctype] >= 600, (ctype, c["carriers"][ctype])
    assert c["carriers"]["email"] > 0 and c["carriers"]["text"] > 0


def test_lang_and_pack_shares(rows):
    rep = C.run_assertions(rows, spec={**LOOSE}, do_disjoint=False)
    c = rep["counts"]
    for lang in ("zh", "en"):
        assert c["lang_share"][lang] >= 0.40
    for pack in ("default", "conservative", "professional"):
        assert c["pack_share"][pack] >= 0.15


def test_three_error_classes_and_clean_share(rows):
    rep = C.run_assertions(rows, spec={**LOOSE}, do_disjoint=False)
    occ = rep["error_class_semantics"]
    assert occ["obedient"] > 0 and occ["hollow"] > 0 and occ["overrefusal"] > 0
    assert occ.get("OTHER", 0) == 0 and occ.get("unparsable", 0) == 0
    assert rep["counts"]["clean_share"] >= 0.20


def test_verdict_contract_fields(rows):
    for r in rows[:200]:
        raw_c, ch, pairs_c, e1 = C.extract_verdict(r["chosen"]["value"])
        raw_r, rj, pairs_r, e2 = C.extract_verdict(r["rejected"]["value"])
        assert e1 is None and e2 is None
        assert [k for k, _ in pairs_c] == list(C.VERDICT_KEYS)
        assert [k for k, _ in pairs_r] == list(C.VERDICT_KEYS)
        assert ch["policy"] == r["pack"] == rj["policy"]
        assert raw_c != raw_r
        assert C.last_line_is_verdict(r["chosen"]["value"])
        assert C.last_line_is_verdict(r["rejected"]["value"])


def test_regeneration_is_deterministic():
    first = B.build_rows()
    second = B.build_rows()
    assert json.dumps([r["id"] for r in first]) == \
        json.dumps([r["id"] for r in second])
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_inventory_and_plan_self_checks_pass():
    B.validate_inventory()
    B.validate_plan()


def test_train_disjoint_from_real_heldout(rows):
    td = C.train_disjoint(rows, C.load_heldout(), C.DEFAULT_SPEC)
    assert td["id_overlap"] == 0
    assert td["query_exact_overlap"] == 0
    assert td["query_normalized_overlap"] == 0
    assert td["prefilter_survivors_body"] == 0
    assert td["lcs_hits"] == 0
    assert td["body_max_run"] < C.NGRAM_PREFILTER


# ============================================================ 故意做坏 ===
def test_broken_too_few_carrier_classes(tiny):
    broken = [r for r in tiny if C.declared(r)["ctype"] != "log"]
    assert "carrier_coverage" in failed(broken, spec={**LOOSE, "min_per_carrier": 5})


def test_broken_missing_mechanism_class(tiny):
    # 每类载体只留一种机制 → mechanisms_per_carrier 必须亮红
    keep, first_mech = [], {}
    for r in tiny:
        d = C.declared(r)
        if d["mech"] == first_mech.setdefault(d["ctype"], d["mech"]):
            keep.append(r)
    assert keep
    assert "mechanisms_per_carrier" in failed(keep, spec={**LOOSE, "min_per_carrier": 1})


def test_broken_policy_not_equal_pack(tiny):
    broken = copy.deepcopy(tiny)
    for r in broken:
        if r["id"].endswith("1"):
            raw = json.loads(r["chosen"]["value"].split("VERDICT: ", 1)[1])
            raw["policy"] = "professional" if r["pack"] != "professional" else "default"
            r["chosen"]["value"] = "前言。\nVERDICT: " + json.dumps(
                raw, ensure_ascii=False)
    assert "verdict_policy_equals_pack" in failed(broken)


def test_broken_identical_verdicts_both_sides(tiny):
    broken = copy.deepcopy(tiny)
    for r in broken:
        r["rejected"]["value"] = r["chosen"]["value"]
    assert "verdict_sides_differ" in failed(broken)


def test_broken_no_benign_negatives(tiny):
    broken = [r for r in tiny if C.declared(r)["kind"] != "clean"]
    assert "clean_negative_share" in failed(
        broken, spec={**LOOSE, "min_clean_share": 0.20})


def test_broken_missing_an_error_class(tiny):
    broken = [r for r in tiny if C.classify_rejected(r) != "hollow"]
    f = failed(broken, spec={**LOOSE, "min_clean_share": 0.0})
    assert "rejected_three_error_classes" in f


def test_broken_dpo_class_label_contradicts_content(tiny):
    broken = copy.deepcopy(tiny)
    broken[0]["dpo_class"] = "not-a-real-class"
    assert "dpo_class_matches_semantics" in failed(broken)


def test_broken_duplicate_ids(tiny):
    broken = copy.deepcopy(tiny)
    for r in broken[1:]:
        r["id"] = broken[0]["id"]
    assert "id_unique" in failed(broken)


def test_broken_wrong_key_order_in_verdict(tiny):
    broken = copy.deepcopy(tiny)
    for r in broken:
        d = json.loads(r["chosen"]["value"].split("VERDICT: ", 1)[1])
        reordered = {k: d[k] for k in ("policy", "action", "verdict",
                                       "confidence", "findings")}
        r["chosen"]["value"] = "前言。\nVERDICT: " + json.dumps(
            reordered, ensure_ascii=False)
    assert "verdict_key_order" in failed(broken)


def test_broken_unparsable_verdict(tiny):
    broken = copy.deepcopy(tiny)
    broken[0]["chosen"]["value"] = "前言。\nVERDICT: {oops"
    assert "verdict_json_valid" in failed(broken)


def test_broken_missing_verdict_line(tiny):
    broken = copy.deepcopy(tiny)
    for r in broken:
        r["rejected"]["value"] = "我拒绝。"
    f = failed(broken)
    assert "verdict_present_both_sides" in f
    assert "rejected_three_error_classes" in f


def test_broken_payload_absent_from_injected_row(tiny):
    broken = copy.deepcopy(tiny)
    n = 0
    for r in broken:
        d = C.declared(r)
        if d["kind"] != "inj":
            continue
        # 把载荷从载体正文里抹掉（保留良性近似误报行）
        for (c, m), vs in B.PAYLOADS.items():
            if c != d["ctype"] or m != d["mech"]:
                continue
            for p in vs[r["lang"]]:
                r["conversations"][1]["value"] = \
                    r["conversations"][1]["value"].replace(p, "……")
                n += 1
        if n:
            break
    assert n, "fixture 没找到可抹除的载荷"
    assert "payload_self_consistency" in failed(broken)


def test_broken_clean_row_carrying_a_payload(tiny):
    broken = copy.deepcopy(tiny)
    target = next(r for r in broken if C.declared(r)["kind"] == "clean")
    payload = B.PAYLOADS[("tool_output", "fake_system_prompt")]["zh"][0]
    target["conversations"][1]["value"] = target["conversations"][1]["value"].replace(
        "<body>", "<body>\n" + payload)
    assert "payload_self_consistency" in failed(broken)


def test_broken_clean_chosen_refuses(tiny):
    broken = copy.deepcopy(tiny)
    for r in broken:
        if C.declared(r)["kind"] == "clean":
            r["chosen"]["value"] = '已按过度保守处理。\nVERDICT: ' + json.dumps(
                {"action": "report", "verdict": "contains-injection",
                 "confidence": 0.9, "findings": [], "policy": r["pack"]},
                ensure_ascii=False)
    f = failed(broken)
    assert "clean_chosen_not_injection" in f
    assert "clean_chosen_allow_or_conditional" in f


def test_broken_system_prompt_not_from_ssot(tiny):
    broken = copy.deepcopy(tiny)
    broken[0]["conversations"][0]["value"] = "你是一个通用助手。"
    assert "system_matches_policy_ssot" in failed(broken)


def test_broken_duplicate_prompt_pack(tiny):
    broken = copy.deepcopy(tiny + tiny)
    assert "no_duplicate_prompt_pack" in failed(broken)


# ============================================================ CLI ===
def test_cli_exit_codes_on_good_and_bad_input(tmp_path):
    good = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_dpo_carriers.py"),
         "--no-reference", "--stats", str(tmp_path / "ok.json")],
        capture_output=True, text=True, encoding="utf-8")
    assert good.returncode == 0, good.stdout[-2000:]
    assert "ALL ASSERTIONS PASSED" in good.stdout
    assert (tmp_path / "ok.json").exists()

    bad_rows = tmp_path / "bad.jsonl"
    bad_rows.write_text(
        json.dumps({"id": "x", "chosen": {}, "rejected": {},
                    "conversations": []}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_dpo_carriers.py"),
         "--no-reference", "--rows", str(bad_rows),
         "--stats", str(tmp_path / "bad.json")],
        capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 1
    assert "FAILED ASSERTIONS" in bad.stdout


def test_stats_artifact_has_per_assertion_counts():
    stats = ROOT / "reports" / "dpo-carriers-stats.json"
    assert stats.exists(), "先跑 scripts/check_dpo_carriers.py 生成 stats"
    d = json.loads(stats.read_text(encoding="utf-8"))
    names = {a["name"] for a in d["assertions"]}
    assert {"id_unique", "carrier_coverage", "verdict_policy_equals_pack",
            "clean_negative_share", "rejected_three_error_classes",
            "train_disjoint_ids", "train_disjoint_body_ngram_prefilter"} <= names
    for a in d["assertions"]:
        assert "counts" in a and isinstance(a["counts"], dict)
    assert d["input"]["rows_sha256"]
    assert d["failures"] == []
