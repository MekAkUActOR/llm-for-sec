# -*- coding: utf-8 -*-
"""tests/test_topup_family_probe.py —— v0.5 三族观测仪探针集的单元测试。

两组：
  A. 正例：真实探针集必须 PASS（scripts/check_topup_family_probe.py 全硬闸）。
  B. 反例（**故意做坏事**，每条都必须被抓出来）：把探针集复制到 tmp 目录后注入
     下列缺陷，断言 run_checks 返回非空 errors 且命中对应闸门：
       B1 与训练侧 user 精确同文 / 长同文复制（C1、C2/C3、C3b）
       B2 负例被删光（负例占比 < 25%）
       B3 单一语言（zh/en 占比 < 40%）
       B4 id 与留出集重叠（跨留出集零重叠）
       B5 system 串被改动（schema 逐字一致）
       B6 只剩一个政策包（三包齐全）
       B7 真实域名（虚构性 / RFC2606）
       B8 政策三元组 user 文本被改坏（同一 user × 3 包）

跑法：python -m pytest tests/test_topup_family_probe.py -q
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_topup_family_probe as C  # noqa: E402

REAL = ROOT / "data" / "heldout" / "v0.5-topup-families"
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
FILES = ("t2_mechanism.jsonl", "doc_structure.jsonl", "t9_phish.jsonl")


def read_rows(p: Path):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_rows(p: Path, rows):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture()
def probe_dir(tmp_path: Path) -> Path:
    for fn in FILES:
        shutil.copy(REAL / fn, tmp_path / fn)
    return tmp_path


def errors_of(d: Path) -> list[str]:
    _rep, errs = C.run_checks(d)
    return errs


def test_real_probe_set_passes():
    rep, errs = C.run_checks(REAL)
    assert errs == [], errs
    assert rep["verdict"] == "PASS"
    assert sum(f["rows"] for f in rep["families"].values()) == 85
    for fam in C.FAMILIES:
        td = rep["families"][fam]["train_disjoint"]
        assert td["C1_exact_user_matches"] == 0
        assert td["C2_content_ngram_hits"] == 0
        assert td["C4_payload_hits"] == 0
        assert td["C3_max_contiguous_run_grams"] < C.RUN_MAX
        assert td["C3b_raw_max_contiguous_run_grams"] < C.RUN_RAW_MAX
    assert len(rep["policy_triplets"]) == 5


# ---------------------------------------------------------------- 反例 B1
def test_b1_training_user_text_copy_is_caught(probe_dir: Path):
    """把一行 T2 的 user 文本换成训练侧原文 ⇒ C1/C2/C3 必须报错。"""
    train = read_rows(STAGE / "t2_mechanism.jsonl")
    stolen = train[7]["messages"][1]["content"]
    p = probe_dir / "t2_mechanism.jsonl"
    rows = read_rows(p)
    rows[0]["messages"][1]["content"] = stolen
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("C1" in e for e in errs), errs
    # T2 的载荷区就是全文，直接照抄训练侧整行会被 C4 抓住（见 C4 命中列表）
    assert any("C2" in e or "C3" in e or "C4" in e for e in errs), errs


def test_b1c_t2_long_verbatim_run_is_caught(probe_dir: Path):
    """T2 注入一段 ≥80 规范化字符的训练侧原文 ⇒ C2/C3/C3b 必须报错。"""
    train = read_rows(STAGE / "t2_mechanism.jsonl")
    seg = C.normalize(train[11]["messages"][1]["content"])[60:170]
    p = probe_dir / "t2_mechanism.jsonl"
    rows = read_rows(p)
    rows[1]["messages"][1]["content"] += "\n评注：" + seg
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("C2" in e or "C3" in e or "C3b" in e for e in errs), errs


def test_b1b_long_verbatim_run_is_caught(probe_dir: Path):
    """注入训练侧一句真长文（≥60 规范化字符）⇒ C2/C3b 必须报错。"""
    train = read_rows(STAGE / "t9_phish_expand.jsonl")
    body = train[3]["messages"][1]["content"]
    seg = C.normalize(body)[120:220]
    p = probe_dir / "t9_phish.jsonl"
    rows = read_rows(p)
    u = rows[2]["messages"][1]["content"]
    rows[2]["messages"][1]["content"] = u + "\n<!-- " + seg + " -->"
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("C2" in e or "C3" in e or "C3b" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B2
def test_b2_missing_negatives_are_caught(probe_dir: Path):
    p = probe_dir / "t2_mechanism.jsonl"
    rows = [r for r in read_rows(p) if C.kind_of(r["id"]) not in ("neg", "poln")]
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("负例占比" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B3
def test_b3_single_language_is_caught(probe_dir: Path):
    p = probe_dir / "doc_structure.jsonl"
    rows = [r for r in read_rows(p) if r["lang"] != "en"]
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("占比" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B4
def test_b4_holdout_id_overlap_is_caught(probe_dir: Path):
    hold = ROOT / "data" / "heldout" / "v0.2.1"
    hid = None
    for f in sorted(hold.glob("*.jsonl")):
        for j in read_rows(f):
            if j.get("id"):
                hid = str(j["id"])
                break
        if hid:
            break
    assert hid, "留出集里应有 id"
    p = probe_dir / "t9_phish.jsonl"
    rows = read_rows(p)
    rows[0]["id"] = hid
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("留出集" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B5
def test_b5_system_prompt_tampering_is_caught(probe_dir: Path):
    p = probe_dir / "t2_mechanism.jsonl"
    rows = read_rows(p)
    rows[0]["messages"][0]["content"] += "\n（外加一句训练侧没有的政策行）"
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("system" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B6
def test_b6_missing_policy_pack_is_caught(probe_dir: Path):
    p = probe_dir / "t9_phish.jsonl"
    rows = [r for r in read_rows(p) if r["pack"] != "professional"]
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("政策包缺失" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B7
def test_b7_real_domain_is_caught(probe_dir: Path):
    p = probe_dir / "doc_structure.jsonl"
    rows = read_rows(p)
    rows[0]["messages"][1]["content"] += "\nurl: https://bank-of-example.com/login"
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("C5" in e or "虚构性" in e for e in errs), errs


def test_b7b_training_host_reuse_is_caught(probe_dir: Path):
    p = probe_dir / "t9_phish.jsonl"
    rows = read_rows(p)
    rows[0]["messages"][1]["content"] = rows[0]["messages"][1]["content"].replace(
        "sample-freight.example", "example-bank.cn")
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("C5" in e for e in errs), errs


# ---------------------------------------------------------------- 反例 B8
def test_b8_broken_policy_triplet_is_caught(probe_dir: Path):
    p = probe_dir / "t2_mechanism.jsonl"
    rows = read_rows(p)
    for r in rows:
        if C.kind_of(r["id"]) == "poln":
            r["messages"][1]["content"] += "\n（只在这一包里加的一句）"
            break
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("三元组" in e for e in errs), errs


# ---------------------------------------------------------------- 其它契约
def test_verdict_contract_is_checked(probe_dir: Path):
    p = probe_dir / "t2_mechanism.jsonl"
    rows = read_rows(p)
    a = rows[0]["messages"][2]["content"]
    rows[0]["messages"][2]["content"] = a.replace('"policy": "conservative"',
                                                  '"policy": "default"')
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("policy" in e for e in errs), errs


def test_meta_vocabulary_is_checked(probe_dir: Path):
    p = probe_dir / "doc_structure.jsonl"
    rows = read_rows(p)
    rows[0]["messages"][1]["content"] = rows[0]["messages"][1]["content"].replace(
        "macros: none-declared", "invented-meta-key: 7")
    write_rows(p, rows)
    errs = errors_of(probe_dir)
    assert any("词表" in e or "C6" in e for e in errs), errs
