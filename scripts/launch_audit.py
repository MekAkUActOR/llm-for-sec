# -*- coding: utf-8 -*-
"""P1.8 发射审计闸（launch audit gate，fail-closed ✓✓）。

权威口径：
- reports/m5-plan.md P1.8 行：「rebalance_design + verdict_contrast_audit 串成 launch_audit.py；
  无审计输出 = 拒绝发射（fail-closed ✓）」
- reports/retrospective-41.md 教训 #1：「两次训练花在未表征数据上 ✗ ⇒ 混料成分审计必须是发射门」
- reports/p1.6-calibration-design.md §4.5：「launch_audit.py 串接 check_p16_calibration.py 退出码 ——
  无 PASS 输出 = 拒绝发射（fail-closed ✓）」；§8.7：「集成时在 launch_audit 记录基座 sha256
  以保归因可溯」
- reports/m5a-preregistration.md §6 发射前置链（本件 = 第 3 项落地；双臂 sha256 冻结核验
  B1–B3 与双臂预注册核对 C1–C2 为 m5a 轮新增相）；data/m5a-run/manifest.json
  .g1_scan_interaction（G1 落点已裁决：m5a 混料在 checker 字节级扫描范围之外，串接复跑
  无交互、checker 零改动 ✗ —— 审计按当前落点跑即可，预注册 §6 已裁决 ✓）

检查一览（A1–A5 + B1–B3 + C1–C2，可扩展注册表 ✓）：
  A1  混料对比度审计：M5 混料 34,602 行（基座 28,842 + p16 5,760）VERDICT 双侧存在率/对比度
      + rebalance S/C/F 分 dpo_class 表（verdict_contrast_audit + rebalance_design 逻辑合并）；
      关键新读数 = p16 D 族（p16_verdict_honesty）是否造出对比度 ✗✓
  A2  p16 G 门：子进程跑 scripts/check_p16_calibration.py，退出码透传；
      且 stdout 必须含 P16-GATE=PASS（无标记 = 未登记 ⇒ 拒绝 ✗）；门禁报告产物
      （实名 reports/p1.6-gate-report.md —— 任务书 .json 为笔误、实查 .md ✗）须
      P16-GATE=PASS 在场 + P16-MERGE-GATE=DONE 收尾 + 本轮复跑新鲜
  A3  训练数据 schema/分布快照：行数/极性/语言/族分布 vs 预注册配比断言（冻结表）
  A4  谱系链核验：两 release sha256 vs manifest 冻结值 + 基座 sha256 冻结值（归因可溯 ✓）
  B1  M5A 数据臂冻结核验：data/m5a-run/train.jsonl sha256/行数/字节数 = m5a manifest 登记
      = 冻结锚点（ee181598…）；m5a manifest / p16 manifest 身份锚定 + lineage 交叉登记对账
      （发射审计基座登记 ✓）
  B2  RL 臂池冻结核验：data/rlvr/p2rl-pool-v01.jsonl sha256/行数 = p2rl-pool-v01.manifest.json
      登记 = 冻结锚点；pool_file 指向一致 + 池 manifest 自身锚定（RL 臂池冻结 ✓）
  B3  孪生混料 belt：m5a train.jsonl = data/m5-run/dpo_m5_calib.jsonl 字节恒等
      （m5a manifest twin_mix.sha256_asserted_equal 在场复核 —— 臂间可比机器证明 ✓）
  C1  M5A 预注册在场且含预测节（reports/m5a-preregistration.md：预测节标题 + M5A-PREREG=DONE
      钉死标记 + 钉死对象 train.jsonl sha256 在文）
  C2  P2-RL 预注册在场且含预测节（reports/p2rl-grpo-preregistration.md：预测节标题 +
      P2RL-PREREG=DONE 钉死标记 + RL 池路径在文）
  A5  审计输出落盘核验：reports/launch-audit-<tag>.json 存在/可解析/注册表闭合/判定一致
      —— 无审计输出 = 拒绝发射（fail-closed ✓✓）

fail-closed 铁律：任一检查缺失/失败/未登记 ⇒ 整体 LAUNCH-AUDIT=FAIL + 退出码非零 +
明确拒绝理由；报告仍完整落盘（含全部被审计文件 sha256 清单 sha256_registry ✓）。
结尾控制台标记 LAUNCH-AUDIT=PASS/FAIL 与 P18-LAUDIT=DONE（报告写入完成的机读标记，
与 PASS/FAIL 判定无关）。只读审计 ✗✓：唯一写出 = reports/launch-audit-<tag>.json；
子进程 checker 按其自身设计重写其自身产物 reports/p1.6-gate-report.md（m5a manifest
g1_scan_interaction 已裁决 ✓）；无交互（零 stdin 依赖）。

用法：
  .venv\\Scripts\\python.exe scripts\\launch_audit.py --tag m5
  .venv\\Scripts\\python.exe scripts\\launch_audit.py --list-checks
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]

# ================================================================ 路径常量 ==
DEFAULT_MIX = ROOT / "data" / "m5-run" / "dpo_m5_calib.jsonl"       # P2.9 物化件（与 m5a train 字节恒等，B3 复核 ✓）
M4_BASE = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
P16_DIR = ROOT / "data" / "dpo" / "p16-calibration"
P16_BENIGN = P16_DIR / "p16_benign_release.jsonl"
P16_MALICIOUS = P16_DIR / "p16_malicious_honest.jsonl"
P16_MANIFEST = P16_DIR / "manifest.json"
P16_CHECKER = ROOT / "scripts" / "check_p16_calibration.py"
REPORT_DIR = ROOT / "reports"

# ================================================================ 预注册冻结表 ==
# m4 基座（sha256 d4061d47… 冻结 ⇒ 分布随之冻结；2026-10-08 实测登记，不猜 ✓）
FROZEN_M4_SHA256 = "d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414"
M4_DIST = {
    "rows": 28842,
    "dpo_class": {"policy": 14688, "reserve": 5710, "carrier_inject_obedient": 2360,
                  "carrier_inject_hollow": 2320, "bt330_refusal": 1904,
                  "carrier_clean_overrefusal": 1320, "refusal_quality": 300, "calibration": 240},
    "lang": {"zh": 17319, "en": 11523},
    # S/C/F（retrospective-41 §二① + rebalance_design 同口径实测 ✓）
    "scf": {"S": 13179, "C": 1422, "F": 14241},
}
# p16 校准包（manifest.json 冻结 ⇒ 分布/对比度随之冻结；G1–G12 已全 PASS ✓）
P16_DIST = {
    "rows": 5760,
    "dpo_class": {"p16_benign_release": 1500, "p16_multiturn_benign": 480,
                  "p16_judgment_teaching": 360, "p16_verdict_honesty": 480,
                  "p16_dilution_judgment": 300, "p16_malicious_honest": 2640},
    "lang": {"en": 3438, "zh": 2322},
    "pack": {"professional": 2511, "default": 2387, "conservative": 862},
    "polarity": {"benign_release": 2880, "malicious_refuse": 2880},
    # S/C/F（2026-10-08 对冻结件实测；★D 族 = S 240 + C 240 + F 0 = 100% 内容对比 ✓）
    "scf": {"p16_benign_release": {"S": 1200, "C": 300, "F": 0},
            "p16_multiturn_benign": {"S": 480, "C": 0, "F": 0},
            "p16_judgment_teaching": {"S": 216, "C": 144, "F": 0},
            "p16_verdict_honesty": {"S": 240, "C": 240, "F": 0},
            "p16_dilution_judgment": {"S": 180, "C": 120, "F": 0},
            "p16_malicious_honest": {"S": 924, "C": 1716, "F": 0}},
}
TOTAL_ROWS = 34602                      # 28,842 + 5,760（§4.5 公式 ✓）
D_FAMILY = "p16_verdict_honesty"        # ★关键新读数的对象（§5.1 D 族 = VERDICT 诚实性双向）
# m4 基座实测 schema（2026-10-08，sha 冻结件上登记，不猜 ✓）：核心七键全行必有；
# 谱系键二选一 —— 21,228 行 src_task / 7,614 行 src+src_id（两变体均为合法基座形态）
CORE_KEYS = {"id", "dpo_class", "lang", "pack", "conversations",
             "chosen", "rejected"}
P16_KEYS = CORE_KEYS | {"src_task", "polarity", "rejected_form", "archetype_id"}   # 11 键（G2 口径）
P16_TIMEOUT_S = 3600                    # A2 子进程超时（G1 扫 7.9GB 混料，分钟级 ✓）

# ---- M5 双臂发射链路径（m5a 轮新增 B/C 相的对象，2026-10-08 实查 ✓） ----
M5A_TRAIN = ROOT / "data" / "m5a-run" / "train.jsonl"        # M5A 数据臂混料（BUILD-M5A-MIX ✓）
M5A_MANIFEST = ROOT / "data" / "m5a-run" / "manifest.json"
M5A_DSINFO = ROOT / "data" / "m5a-run" / "dataset_info.json"
M5_MANIFEST = ROOT / "data" / "m5-run" / "manifest.json"     # 孪生件登记（P2.9 集成件）
RLVR_POOL = ROOT / "data" / "rlvr" / "p2rl-pool-v01.jsonl"   # P2-RL GRPO 训练池（冻结 ✓）
RLVR_MANIFEST = ROOT / "data" / "rlvr" / "p2rl-pool-v01.manifest.json"
GATE_REPORT = REPORT_DIR / "p1.6-gate-report.md"   # checker 产物实名（任务书 .json 笔误，实查 .md ✗）
PREREG_M5A = REPORT_DIR / "m5a-preregistration.md"
PREREG_P2RL = REPORT_DIR / "p2rl-grpo-preregistration.md"
SPOTCHECK_REPORT = REPORT_DIR / "p16-spotcheck.md"  # 人工关口（本审计登记不设闸 ✗）
RLVR_POOL_REL = "data/rlvr/p2rl-pool-v01.jsonl"
PRED_HEAD_RE = re.compile(r"^#{1,6}\s[^\n]*预测[^\n]*$", re.M)   # 预测节标题（两臂预注册实查口径）
MARKER = "P18-LAUDIT=DONE"               # 报告写入完成的机读标记（与 PASS/FAIL 判定无关）

# ---- 冻结锚点（2026-10-08 冻结登记实测，不猜 ✓；belt：manifest 登记或文件被原地改 ⇒ FAIL ✗） ----
# p16 manifest sha256 另有 data/m5a-run/manifest.json lineage 交叉登记（B1 双向对账 ✓）
FROZEN_LAUNCH = {
    "p16_manifest_sha256": "e5d10d641d461d1d5b02a0f0359df305a8ce04fd71152b0135db3966cf7d1b35",
    "p16_release_entries": {
        "p16_benign_release.jsonl": {
            "sha256": "1636ba88c2f8834cdb581ea9c147e94990f28229c3665e5559375dd669daacc1",
            "rows": 2880, "bytes": 7304338},
        "p16_malicious_honest.jsonl": {
            "sha256": "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d",
            "rows": 2880, "bytes": 8172306},
    },
    "m5a_manifest_sha256": "e7d0a74a477d2ec51f95bc02b7b3b68ece77a2eb7de50db09f1c5b29a3ff1a89",
    "m5a_train": {"sha256": "ee181598af572a634394416c000c212e312bd00acc9bff8a0cedeb5a5b6d2e60",
                  "rows": 34602, "bytes": 75269919},   # 与 data/m5-run/dpo_m5_calib.jsonl 字节恒等
    "rlvr_pool": {"sha256": "77ff6cf1d05c0d5cbd93e7be48cc8104bd396fdc3627f3d4ea4bd09528851dd0",
                  "n": 3000},                          # p2rl 预注册 §4.2.4：池冻结后不增补
    "rlvr_manifest_sha256": "5c4676a7ae2412916f91b5e938d5970f857c1097e124b96ce6b7b65d1e692770",
}

# ---- 对比度口径（verdict_contrast_audit.py + rebalance_design.py 逐字移植 ✓）----
VRE = re.compile(r"VERDICT\s*:", re.I)
FIELD = re.compile(r'"([a-z_]+)"\s*:\s*("([^"]*)"|(-?[\d.]+)|(\[[^\]]*\]))')


def parse_verdict(t: str) -> dict:
    """宽容解析 VERDICT JSON（两先例脚本同款：json.loads 失败退正则字段抽取）。"""
    m = re.search(r"VERDICT\s*:\s*(\{.*\})", t or "", re.S)
    if not m:
        return {}
    s = m.group(1)
    k = s.rfind("}")
    s = s[:k + 1] if k >= 0 else s
    try:
        return json.loads(s)
    except Exception:
        out = {}
        for mm in FIELD.finditer(s):
            out[mm.group(1)] = (mm.group(3) if mm.group(3) is not None
                                else (mm.group(4) if mm.group(4) is not None
                                      else mm.group(5)))
        return out


def classify_pair(row: dict) -> str:
    """rebalance_design 三分：S 方向对（action 异）/ C 契约对 / F 风格对。"""
    ct = (row.get("chosen") or {}).get("value") or ""
    rt = (row.get("rejected") or {}).get("value") or ""
    cv, rv = parse_verdict(ct), parse_verdict(rt)
    ca, ra = cv.get("action"), rv.get("action")
    if not ca or ca != ra:
        return "S"
    diffs = any(str(cv.get(x)) != str(rv.get(x))
                for x in ("verdict", "findings", "confidence"))
    return "C" if diffs else "F"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name}:{ln} JSON 解析失败: {e}") from e
    return out


def count_rows(path: Path) -> int:
    """行数快计（非空行二进制计数；sha256 相同 ⇒ 内容相同，行数仅 belt ✓）。"""
    n = 0
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


# ================================================================ 配置与注册表 ==
@dataclass
class AuditConfig:
    """全部路径与预注册表可注入（测试用夹具替换 ✓，默认 = 真实发射对象）。"""
    tag: str = "m5"
    mix_path: Path = DEFAULT_MIX
    m4_base: Path = M4_BASE
    p16_benign: Path = P16_BENIGN
    p16_malicious: Path = P16_MALICIOUS
    p16_manifest: Path = P16_MANIFEST
    p16_checker: Path = P16_CHECKER
    report_dir: Path = REPORT_DIR
    m4_dist: dict = field(default_factory=lambda: copy.deepcopy(M4_DIST))
    p16_dist: dict = field(default_factory=lambda: copy.deepcopy(P16_DIST))
    frozen_m4_sha256: str = FROZEN_M4_SHA256
    total_rows: int = TOTAL_ROWS
    d_family: str = D_FAMILY
    p16_timeout_s: int = P16_TIMEOUT_S

    def p16_classes(self) -> set:
        return set(self.p16_dist["dpo_class"])

    def m4_classes(self) -> set:
        return set(self.m4_dist["dpo_class"])


@dataclass
class CheckResult:
    ok: bool
    reasons: list = field(default_factory=list)      # 拒绝理由（FAIL 时必非空 ✓）
    metrics: dict = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        return "PASS" if self.ok else "FAIL"


@dataclass
class CheckSpec:
    """可扩展注册表项：后续审计件挂入 = 追加一条 CheckSpec（报告/闭合校验自动纳入 ✓）。

    phase="data"  → fn(ctx: AuditContext) -> CheckResult（报告落盘前跑）
    phase="output"→ fn(cfg, registry, checks, report_path) -> CheckResult（落盘后核验）
    """
    cid: str                       # "A1"…
    title: str
    fn: Callable
    phase: str = "data"


class AuditContext:
    """检查共享上下文：配置 + 惰性缓存的混料行。"""

    def __init__(self, cfg: AuditConfig):
        self.cfg = cfg
        self._rows = None
        self._mix_mode = None       # "materialized" | "virtual-union"
        self._load_errors = []

    # ---- 混料装配：物化件优先；缺件 ⇒ 基座+p16 虚拟并集（模式显式登记 ✓） ----
    def mixture_rows(self) -> tuple:
        """返回 (rows, mode, errors)；rows=None 表示装配失败（fail-closed 由 A1/A3 裁决）。"""
        if self._rows is not None or self._mix_mode == "materialized":
            return self._rows, self._mix_mode, self._load_errors
        cfg = self.cfg
        if cfg.mix_path.exists():
            self._mix_mode = "materialized"
            try:
                self._rows = load_jsonl(cfg.mix_path)
            except ValueError as e:
                self._load_errors.append(str(e))
                self._rows = None
        else:
            rows, errs = [], []
            for p in (cfg.m4_base, cfg.p16_benign, cfg.p16_malicious):
                if not p.exists():
                    errs.append(f"缺输入 {p}")
                    continue
                try:
                    rows.extend(load_jsonl(p))
                except ValueError as e:
                    errs.append(str(e))
            self._load_errors = errs
            self._rows = rows if not errs else None
            self._mix_mode = "virtual-union"
        return self._rows, self._mix_mode, self._load_errors

    def manifest(self) -> dict:
        with open(self.cfg.p16_manifest, encoding="utf-8") as f:
            return json.load(f)


# ================================================================ A1 ==
def check_contrast(ctx: AuditContext) -> CheckResult:
    """混料对比度审计：VERDICT 双侧存在率/对比度 + S/C/F 分 dpo_class 表 + D 族关键读数。"""
    cfg = ctx.cfg
    rows, mode, errors = ctx.mixture_rows()
    if rows is None:
        return CheckResult(False, [f"混料装配失败（mode={mode}）：" + "；".join(errors)],
                           {"mode": mode})
    reasons, metrics = [], {"mode": mode, "rows": len(rows)}

    # ---- 基本结构（schema 细查在 A3，此处只保对比度计算可进行 ✓） ----
    struct_err = 0
    for r in rows:
        ct = (r.get("chosen") or {}).get("value") if isinstance(r, dict) else None
        rt = (r.get("rejected") or {}).get("value") if isinstance(r, dict) else None
        if not isinstance(ct, str) or not isinstance(rt, str) or not r.get("dpo_class"):
            struct_err += 1
    metrics["结构缺陷行"] = struct_err
    if struct_err:
        reasons.append(f"结构缺陷行 {struct_err}（chosen/rejected/dpo_class 缺失或非字符串）")

    # ---- 分 dpo_class 对比度表（verdict_contrast + rebalance 合并口径 ✓） ----
    per: dict[str, Counter] = {}
    marker_both = marker_contrast = 0
    for r in rows:
        dc = str(r.get("dpo_class"))
        d = per.setdefault(dc, Counter())
        ct = (r.get("chosen") or {}).get("value") or ""
        rt = (r.get("rejected") or {}).get("value") or ""
        d["n"] += 1
        d[classify_pair(r)] += 1
        cv, rv = bool(VRE.search(ct)), bool(VRE.search(rt))
        if cv and rv:
            d["both_v"] += 1
            marker_both += 1
        elif cv != rv:
            d["marker_contrast"] += 1
            marker_contrast += 1
        else:
            d["neither_v"] += 1
    table = {}
    for dc in sorted(per):
        d = per[dc]
        n = d["n"]
        table[dc] = {"n": n, "S": d["S"], "C": d["C"], "F": d["F"],
                     "both_v": d["both_v"], "marker_contrast": d["marker_contrast"],
                     "neither_v": d["neither_v"],
                     "content_contrast": d["S"] + d["C"],
                     "content_contrast_rate": round((d["S"] + d["C"]) / n, 4) if n else 0.0}
    metrics["per_dpo_class"] = table
    n = len(rows)
    metrics["marker_contrast_rate"] = round(marker_contrast / n, 6) if n else 0.0
    metrics["both_v_rate"] = round(marker_both / n, 6) if n else 0.0
    metrics["total_scf"] = {"S": sum(t["S"] for t in table.values()),
                            "C": sum(t["C"] for t in table.values()),
                            "F": sum(t["F"] for t in table.values())}

    # ---- 预注册断言 ①：总量（§4.5 公式 28,842 + 5,760 ✓） ----
    if n != cfg.total_rows:
        reasons.append(f"混料行数 {n:,} != 预注册 {cfg.total_rows:,}（28,842 基座 + 5,760 p16）")

    # ---- 预注册断言 ②：p16 各族 S/C/F == 冻结表（含 ★D 族对比度交付 ✓✓） ----
    for dc, want in cfg.p16_dist["scf"].items():
        got = table.get(dc)
        if got is None:
            reasons.append(f"预注册 p16 族 {dc} 在混料中缺失（未登记即拒绝 ✗）")
            continue
        for k in ("S", "C", "F"):
            if got[k] != want[k]:
                reasons.append(f"{dc} {k}={got[k]:,} != 预注册 {want[k]:,}（对比度漂移）")

    # ---- 预注册断言 ③：m4 基座 S/C/F 合计 == 冻结值（基座未被动过 ✓） ----
    m4_scf = {"S": 0, "C": 0, "F": 0}
    for dc in cfg.m4_classes():
        got = table.get(dc)
        if got:
            for k in m4_scf:
                m4_scf[k] += got[k]
    if m4_scf != cfg.m4_dist["scf"]:
        reasons.append(f"m4 基座 S/C/F {m4_scf} != 冻结 {cfg.m4_dist['scf']}")

    # ---- 预注册断言 ④：dpo_class 注册表闭合（未登记类 = 拒绝 ✗） ----
    registered = cfg.m4_classes() | cfg.p16_classes()
    unreg = sorted(set(table) - registered)
    missing = sorted(registered - set(table))
    if unreg:
        reasons.append(f"混料含未登记 dpo_class：{unreg}")
    if missing:
        reasons.append(f"预注册 dpo_class 在混料中缺失：{missing}")

    # ---- ★关键新读数：p16 D 族是否造出对比度（§5.1 D 族设计目的 ✓✓） ----
    d = table.get(cfg.d_family)
    if d:
        metrics["key_reading_d_family"] = {
            "dpo_class": cfg.d_family, "n": d["n"], "S": d["S"], "C": d["C"], "F": d["F"],
            "content_contrast": d["content_contrast"],
            "content_contrast_rate": d["content_contrast_rate"],
            "marker_contrast": d["marker_contrast"],
            "delivered": d["F"] == 0 and d["content_contrast"] == d["n"],
        }
        if not metrics["key_reading_d_family"]["delivered"]:
            reasons.append(f"★D 族（{cfg.d_family}）未交付 100% 内容对比度："
                           f"S={d['S']} C={d['C']} F={d['F']}")
    else:
        reasons.append(f"★D 族（{cfg.d_family}）缺失，无法读取关键新读数")
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ A2 ==
def check_p16_gate(ctx: AuditContext) -> CheckResult:
    """A2 p16 G 门：子进程复跑 check_p16_calibration.py（退出码透传 + P16-GATE=PASS 标记
    + 门禁报告产物完整 —— 实名 reports/p1.6-gate-report.md，任务书 .json 为笔误 ✗）。"""
    cfg = ctx.cfg
    if not cfg.p16_checker.exists():
        return CheckResult(False, [f"p16 检查器缺失：{cfg.p16_checker}"], {})
    t0 = time.time()
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"          # GBK 控制台 ✗ 教训（p0.7 §0）
    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            [sys.executable, str(cfg.p16_checker)], cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        return CheckResult(False, [f"p16 检查器无法执行：{e}"], {})

    def _pump() -> None:                       # 流式回显（G9 扫描 ~6 min，静默不可接受 ✗）
        stream = proc.stdout
        while True:
            line = stream.readline()
            if not line:
                break
            text = line.rstrip("\n")
            lines.append(text)
            print(f"    [p16-checker] {text}")

    th = threading.Thread(target=_pump, daemon=True)
    th.start()
    timeout_err = ""
    try:
        rc = proc.wait(timeout=cfg.p16_timeout_s)
        th.join(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        th.join(timeout=60)
        rc = None
        timeout_err = f"p16 检查器超时（>{cfg.p16_timeout_s}s，fail-closed 拒绝 ✗）"
    elapsed = round(time.time() - t0, 1)
    out = "\n".join(lines)
    marker = "P16-GATE=PASS" in out
    reasons, metrics = [], {
        "exit_code": rc, "elapsed_s": elapsed,
        "marker_p16_gate_pass": marker,
        "gate_report": GATE_REPORT.relative_to(ROOT).as_posix(),
    }
    gates: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^\[(G\d+)\]\s+(PASS|FAIL)\b", line)
        if m:
            gates[m.group(1)] = m.group(2)
    metrics["gate_lines"] = dict(sorted(gates.items()))
    metrics["stdout_lines"] = lines            # 串接证据全量落盘（G1–G12 逐门判定 ✓）
    if timeout_err:
        reasons.append(timeout_err)
    if rc != 0:
        reasons.append(f"check_p16_calibration.py 退出码 {rc} != 0（退出码透传 ✓）")
    if not marker:
        reasons.append("stdout 无 P16-GATE=PASS 标记（无 PASS 输出 = 拒绝发射，fail-closed ✗）")
    if "P16-GATE=FAIL" in out:
        reasons.append("stdout 含 P16-GATE=FAIL 标记")
    # ---- 门禁报告产物完整（写入完成机读标记 + 本轮复跑新鲜 belt ✓） ----
    if GATE_REPORT.exists():
        text = GATE_REPORT.read_text(encoding="utf-8")
        mtime = GATE_REPORT.stat().st_mtime
        metrics["p16_gate_report_sha256"] = sha256_file(GATE_REPORT)
        metrics["p16_gate_report_mtime"] = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        if "P16-GATE=PASS" not in text:
            reasons.append("门禁报告 p1.6-gate-report.md 未见 P16-GATE=PASS")
        if "P16-GATE=FAIL" in text:
            reasons.append("门禁报告 p1.6-gate-report.md 含 P16-GATE=FAIL")
        if not text.rstrip().endswith("P16-MERGE-GATE=DONE"):
            reasons.append("门禁报告未以 P16-MERGE-GATE=DONE 收尾（写入不完整 ✗）")
        if mtime + 2 < t0:
            reasons.append("门禁报告 mtime 早于本轮 checker 启动（陈旧产物冒充新证 ✗）")
    else:
        reasons.append(f"门禁报告缺失：{GATE_REPORT}")
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ A3 ==
def check_distribution(ctx: AuditContext) -> CheckResult:
    """训练数据 schema/分布快照：行数/极性/语言/族分布 vs 预注册配比断言。"""
    cfg = ctx.cfg
    rows, mode, errors = ctx.mixture_rows()
    if rows is None:
        return CheckResult(False, [f"混料装配失败（mode={mode}）：" + "；".join(errors)],
                           {"mode": mode})
    reasons, metrics = [], {"mode": mode, "rows": len(rows)}

    def is_p16(r) -> bool:
        return str(r.get("dpo_class", "")).startswith("p16_")

    # ---- 行数（预注册 §4.5 公式） ----
    if len(rows) != cfg.total_rows:
        reasons.append(f"总行数 {len(rows):,} != 预注册 {cfg.total_rows:,}")

    # ---- schema 快照 ----
    core_missing, prov_missing, p16_key_bad = [], [], []
    conv_bad = side_bad = 0
    keyset_union = Counter()
    for r in rows:
        ks = frozenset(r.keys())
        keyset_union["|".join(sorted(ks))] += 1
        miss = CORE_KEYS - ks
        if miss:
            core_missing.append((r.get("id"), sorted(miss)))
        if not (("src_task" in ks) or ("src" in ks and "src_id" in ks)):
            prov_missing.append(r.get("id"))
        if is_p16(r) and ks != P16_KEYS:
            p16_key_bad.append((r.get("id"), sorted(P16_KEYS ^ ks)))
        if not (isinstance(r.get("conversations"), list) and r["conversations"]):
            conv_bad += 1
        for side in ("chosen", "rejected"):
            d = r.get(side)
            if not (isinstance(d, dict) and d.get("from") == "gpt"
                    and isinstance(d.get("value"), str) and d["value"]):
                side_bad += 1
                break
    metrics["schema_keyset_variants"] = len(keyset_union)
    metrics["schema_core_missing"] = len(core_missing)
    metrics["schema_provenance_missing"] = len(prov_missing)
    metrics["schema_p16_keyset_bad"] = len(p16_key_bad)
    metrics["schema_conversations_bad"] = conv_bad
    metrics["schema_chosen_rejected_bad"] = side_bad
    if core_missing:
        reasons.append(f"核心七键缺失行 {len(core_missing)}：{core_missing[:5]}")
    if prov_missing:
        reasons.append(f"谱系键缺失行 {len(prov_missing)}（须 src_task 或 src+src_id 二选一）："
                       f"{prov_missing[:5]}")
    if p16_key_bad:
        reasons.append(f"p16 行键集不符（应为七核心+src_task+三审计）：{p16_key_bad[:5]}")
    if conv_bad:
        reasons.append(f"conversations 空/非列表行 {conv_bad}")
    if side_bad:
        reasons.append(f"chosen/rejected 非 {{from:'gpt', value:str}} 行 {side_bad}")

    # ---- 分布快照 vs 预注册（分源闭合 ✓） ----
    dc_m4 = Counter(str(r.get("dpo_class")) for r in rows if not is_p16(r))
    dc_p16 = Counter(str(r.get("dpo_class")) for r in rows if is_p16(r))
    lang_m4 = Counter(str(r.get("lang")) for r in rows if not is_p16(r))
    lang_p16 = Counter(str(r.get("lang")) for r in rows if is_p16(r))
    pack_p16 = Counter(str(r.get("pack")) for r in rows if is_p16(r))
    pol_p16 = Counter(str(r.get("polarity")) for r in rows if is_p16(r))
    metrics["m4"] = {"rows": sum(dc_m4.values()), "dpo_class": dict(sorted(dc_m4.items())),
                     "lang": dict(sorted(lang_m4.items()))}
    metrics["p16"] = {"rows": sum(dc_p16.values()), "dpo_class": dict(sorted(dc_p16.items())),
                      "lang": dict(sorted(lang_p16.items())), "pack": dict(sorted(pack_p16.items())),
                      "polarity": dict(sorted(pol_p16.items()))}
    # m4 断言
    if metrics["m4"]["rows"] != cfg.m4_dist["rows"]:
        reasons.append(f"m4 基座行数 {metrics['m4']['rows']:,} != 预注册 {cfg.m4_dist['rows']:,}")
    if dict(dc_m4) != cfg.m4_dist["dpo_class"]:
        reasons.append(f"m4 dpo_class 分布漂移：{dict(dc_m4)} != 预注册 {cfg.m4_dist['dpo_class']}")
    if dict(lang_m4) != cfg.m4_dist["lang"]:
        reasons.append(f"m4 lang 分布漂移：{dict(lang_m4)} != 预注册 {cfg.m4_dist['lang']}")
    # p16 断言
    if metrics["p16"]["rows"] != cfg.p16_dist["rows"]:
        reasons.append(f"p16 行数 {metrics['p16']['rows']:,} != 预注册 {cfg.p16_dist['rows']:,}")
    if dict(dc_p16) != cfg.p16_dist["dpo_class"]:
        reasons.append(f"p16 dpo_class 分布漂移：{dict(dc_p16)} != 预注册 {cfg.p16_dist['dpo_class']}")
    if dict(lang_p16) != cfg.p16_dist["lang"]:
        reasons.append(f"p16 lang 分布漂移：{dict(lang_p16)} != 预注册 {cfg.p16_dist['lang']}")
    if dict(pack_p16) != cfg.p16_dist["pack"]:
        reasons.append(f"p16 pack 分布漂移：{dict(pack_p16)} != 预注册 {cfg.p16_dist['pack']}")
    if dict(pol_p16) != cfg.p16_dist["polarity"]:
        reasons.append(f"p16 极性漂移：{dict(pol_p16)} != 预注册 {cfg.p16_dist['polarity']}"
                       f"（良:恶 50:50 契约 ✓）")

    # ---- 物化模式加验：id 集逐源闭合 + id 唯一（谱系级指纹 ✓） ----
    if mode == "materialized":
        all_ids = Counter(str(r.get("id")) for r in rows)
        dup_ids = sorted(i for i, c in all_ids.items() if c > 1)
        if dup_ids:
            reasons.append(f"物化混料 id 重复：{dup_ids[:5]}（共 {len(dup_ids)} 个）")
        m4_ids = {str(r.get("id")) for r in load_jsonl(cfg.m4_base)}
        p16_ids = set()
        for p in (cfg.p16_benign, cfg.p16_malicious):
            p16_ids |= {str(r.get("id")) for r in load_jsonl(p)}
        mix_m4 = {str(r.get("id")) for r in rows if not is_p16(r)}
        mix_p16 = {str(r.get("id")) for r in rows if is_p16(r)}
        metrics["id_closure"] = {"m4_only_in_mix": len(mix_m4 - m4_ids),
                                 "m4_missing_from_mix": len(m4_ids - mix_m4),
                                 "p16_only_in_mix": len(mix_p16 - p16_ids),
                                 "p16_missing_from_mix": len(p16_ids - mix_p16)}
        if mix_m4 != m4_ids:
            reasons.append(f"物化混料 m4 id 集与基座不闭合："
                           f"多 {len(mix_m4 - m4_ids)} / 少 {len(m4_ids - mix_m4)}")
        if mix_p16 != p16_ids:
            reasons.append(f"物化混料 p16 id 集与两 release 不闭合："
                           f"多 {len(mix_p16 - p16_ids)} / 少 {len(p16_ids - mix_p16)}")
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ A4 ==
def check_lineage(ctx: AuditContext) -> CheckResult:
    """谱系链核验：两 release sha256 vs manifest 冻结值 + 基座 sha256 冻结值（§8.7 归因 ✓）。"""
    cfg = ctx.cfg
    reasons, metrics = [], {}
    if not cfg.p16_manifest.exists():
        return CheckResult(False, [f"manifest 缺失：{cfg.p16_manifest}"], {})
    try:
        man = ctx.manifest()
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult(False, [f"manifest 不可解析：{e}"], {})
    metrics["manifest_sha256"] = sha256_file(cfg.p16_manifest)

    # 两 release sha256 vs manifest 冻结值（任务书 ④ ✓）
    for name, path in (("p16_benign_release.jsonl", cfg.p16_benign),
                       ("p16_malicious_honest.jsonl", cfg.p16_malicious)):
        entry = man.get("files", {}).get(name, {})
        want = entry.get("sha256")
        if not want:
            reasons.append(f"manifest 未登记 {name} 的 sha256（未登记即拒绝 ✗）")
            continue
        if not path.exists():
            reasons.append(f"release 缺失：{path}")
            continue
        got = sha256_file(path)
        metrics[name] = {"sha256": got, "rows": entry.get("rows"),
                         "bytes": path.stat().st_size}
        if got != want:
            reasons.append(f"{name} sha256 {got[:16]}… != manifest 冻结值 {want[:16]}…")
        if entry.get("rows") is not None:
            n = len(load_jsonl(path))
            if n != entry["rows"]:
                reasons.append(f"{name} 行数 {n:,} != manifest {entry['rows']:,}")

    # 基座 sha256 冻结值（§8.7：launch_audit 记录基座 sha256 保归因可溯 ✓）
    if not cfg.m4_base.exists():
        reasons.append(f"m4 基座缺失：{cfg.m4_base}")
    else:
        got = sha256_file(cfg.m4_base)
        metrics["m4_base_sha256"] = got
        if got != cfg.frozen_m4_sha256:
            reasons.append(f"m4 基座 sha256 {got[:16]}… != 冻结值 {cfg.frozen_m4_sha256[:16]}…"
                           f"（基座被替换 ⇒ 必须重登记预注册表 + 重跑本审计 ✗）")

    # 物化件 sha256 登记（P2.9 产出后的归因锚点 ✓）
    if cfg.mix_path.exists():
        metrics["mix_sha256"] = sha256_file(cfg.mix_path)
        metrics["mix_rows"] = len(load_jsonl(cfg.mix_path))
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ B1 ==
def check_m5a_freeze(ctx: AuditContext) -> CheckResult:
    """B1 M5A 数据臂冻结核验：train.jsonl / m5a manifest / p16 manifest 三重对账 + 冻结锚点。"""
    reasons, metrics = [], {}
    if not M5A_MANIFEST.exists():
        return CheckResult(False, [f"m5a manifest 缺失：{M5A_MANIFEST}"], {})
    if not M5A_TRAIN.exists():
        return CheckResult(False, [f"m5a 混料缺失：{M5A_TRAIN}（BUILD-M5A-MIX 产物）"], {})
    m5a_sha = sha256_file(M5A_MANIFEST)
    metrics["m5a_manifest_sha256"] = m5a_sha
    if m5a_sha != FROZEN_LAUNCH["m5a_manifest_sha256"]:
        reasons.append(f"m5a manifest sha256 {m5a_sha[:16]}… != 冻结锚点（版本纪律：修改 ⇒ "
                       f"新开版本目录，不得原地改 ✗）")
    try:
        m5a = json.loads(M5A_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult(False, reasons + [f"m5a manifest 不可解析：{e}"], metrics)

    # ---- train.jsonl：实测 = m5a manifest 登记 = 冻结锚点（三重一致 ✓） ----
    entry = (m5a.get("files") or {}).get("train.jsonl") or {}
    got = {"sha256": sha256_file(M5A_TRAIN), "rows": count_rows(M5A_TRAIN),
           "bytes": M5A_TRAIN.stat().st_size}
    metrics["m5a_train"] = dict(got)
    metrics["manifest_registered_train"] = {k: entry.get(k) for k in ("sha256", "rows", "bytes")}
    anchor = FROZEN_LAUNCH["m5a_train"]
    for k in ("sha256", "rows", "bytes"):
        if entry.get(k) is None:
            reasons.append(f"m5a manifest 未登记 train.jsonl 的 {k}（未登记即拒绝 ✗）")
        elif got[k] != entry[k]:
            reasons.append(f"train.jsonl {k} 实测 {got[k]} != m5a manifest 登记 {entry[k]}")
        if got[k] != anchor[k]:
            reasons.append(f"train.jsonl {k} 实测 {got[k]} != 冻结锚点 {anchor[k]}")
    pref = entry.get("sha256_prefix_16")
    metrics["sha256_prefix_16"] = pref
    if isinstance(pref, str) and got["sha256"][:16].upper() != pref.upper():
        reasons.append(f"sha256_prefix_16 登记 {pref} != 实测 sha256 前 16 位（登记内部不一致 ✗）")

    # ---- p16 manifest 身份锚定 + m5a lineage 交叉登记 + 登记值对锚点（发射审计基座登记 ✓） ----
    p16m_sha = sha256_file(P16_MANIFEST)
    metrics["p16_manifest_sha256"] = p16m_sha
    if p16m_sha != FROZEN_LAUNCH["p16_manifest_sha256"]:
        reasons.append(f"p16 manifest sha256 {p16m_sha[:16]}… != 冻结锚点（冻结纪律：修改 ⇒ "
                       f"新开 p16b 版本目录 ✗）")
    reg = ((m5a.get("lineage") or {}).get("p16_release_manifest") or {}).get("sha256")
    metrics["m5a_lineage_p16_manifest_sha256"] = reg
    if reg != FROZEN_LAUNCH["p16_manifest_sha256"]:
        reasons.append(f"m5a manifest lineage 交叉登记 {reg} != p16 manifest 冻结锚点"
                       f"（登记不一致 ✗）")
    try:
        man = ctx.manifest()
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult(False, reasons + [f"p16 manifest 不可解析：{e}"], metrics)
    for name, anc in FROZEN_LAUNCH["p16_release_entries"].items():
        e = (man.get("files") or {}).get(name) or {}
        metrics[f"p16_entry[{name}]"] = {k: e.get(k) for k in ("sha256", "rows", "bytes")}
        for k in ("sha256", "rows", "bytes"):
            if e.get(k) != anc[k]:
                reasons.append(f"p16 manifest 登记 {name} {k}={e.get(k)} != 冻结锚点 {anc[k]}"
                               f"（登记被原地改 ✗）")
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ B2 ==
def check_rl_pool_freeze(ctx: AuditContext) -> CheckResult:
    """B2 RL 臂池冻结核验：p2rl-pool-v01 池 sha256/行数对账 manifest + 冻结锚点。"""
    reasons, metrics = [], {}
    if not RLVR_MANIFEST.exists():
        return CheckResult(False, [f"RL 池 manifest 缺失：{RLVR_MANIFEST}"], {})
    if not RLVR_POOL.exists():
        return CheckResult(False, [f"RL 臂池缺失：{RLVR_POOL}"], {})
    try:
        mrl = json.loads(RLVR_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult(False, [f"RL 池 manifest 不可解析：{e}"], {})
    reg_path = str(mrl.get("pool_file") or "")
    metrics["manifest_pool_file"] = reg_path
    if Path(reg_path).as_posix() != RLVR_POOL_REL:
        reasons.append(f"manifest pool_file 登记 {reg_path!r} 指向不符（应为 {RLVR_POOL_REL}）")
    got_sha, got_n = sha256_file(RLVR_POOL), count_rows(RLVR_POOL)
    metrics["rlvr_pool"] = {"sha256": got_sha, "rows": got_n, "bytes": RLVR_POOL.stat().st_size}
    anchor = FROZEN_LAUNCH["rlvr_pool"]
    if mrl.get("sha256") != got_sha:
        reasons.append(f"RL 池 sha256 {got_sha[:16]}… != manifest 登记 "
                       f"{str(mrl.get('sha256'))[:16]}…")
    if mrl.get("n") != got_n:
        reasons.append(f"RL 池行数 {got_n:,} != manifest 登记 n={mrl.get('n')}")
    if got_sha != anchor["sha256"]:
        reasons.append("RL 池 sha256 != 冻结锚点（池冻结纪律：增补 = 新版本号，不得原地改 ✗）")
    if got_n != anchor["n"]:
        reasons.append(f"RL 池行数 != 冻结锚点 {anchor['n']}")
    msha = sha256_file(RLVR_MANIFEST)
    metrics["rl_manifest_sha256"] = msha
    if msha != FROZEN_LAUNCH["rlvr_manifest_sha256"]:
        reasons.append(f"RL 池 manifest sha256 {msha[:16]}… != 冻结锚点（不得原地改 ✗）")
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ B3 ==
def check_twin_belt(ctx: AuditContext) -> CheckResult:
    """B3 孪生混料 belt：m5a train.jsonl 与 m5-run 物化件字节恒等（臂间可比机器证明复核 ✓）。"""
    cfg = ctx.cfg
    reasons, metrics = [], {}
    if not M5A_TRAIN.exists() or not cfg.mix_path.exists():
        miss = [str(p) for p in (M5A_TRAIN, cfg.mix_path) if not p.exists()]
        return CheckResult(False, [f"孪生对不完整（缺失：{miss}）"], {})
    a, b = sha256_file(M5A_TRAIN), sha256_file(cfg.mix_path)
    metrics["m5a_train_sha256"] = a
    metrics["materialized_mix_sha256"] = b
    metrics["identical"] = a == b
    if a != b:
        reasons.append(f"m5a train.jsonl {a[:16]}… 与 {cfg.mix_path.name} {b[:16]}… 字节不恒等"
                       f"（M5A vs m5-calib 训练数据分叉 ✗）")
    try:
        m5a = json.loads(M5A_MANIFEST.read_text(encoding="utf-8"))
        reg = ((m5a.get("mix") or {}).get("twin_mix") or {}).get("sha256_asserted_equal")
        metrics["registered_equal_sha256"] = reg
        if reg != a:
            reasons.append(f"m5a manifest twin_mix 登记值 {str(reg)[:16]}… != m5a train 实测"
                           f"（登记失真 ✗）")
    except (OSError, json.JSONDecodeError) as e:
        reasons.append(f"m5a manifest 不可解析（twin_mix 对照失败）：{e}")
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ C1/C2 ==
def _prereg_state(path: Path, arm: str, marker: str) -> tuple:
    """预注册三态核对：在场 / 预测节标题 / 钉死标记。返回 (reasons, metrics, text|None)。"""
    reasons, metrics = [], {}
    if not path.exists():
        return [f"{arm} 预注册缺失：{path}"], metrics, None
    text = path.read_text(encoding="utf-8")
    heads = PRED_HEAD_RE.findall(text)
    metrics["prediction_sections"] = heads
    metrics["done_marker"] = marker
    metrics["done_marker_is_tail"] = text.rstrip().endswith(marker)
    metrics["sha256"] = sha256_file(path)
    if not heads:
        reasons.append(f"{arm} 预注册未见预测节标题（markdown 标题含「预测」—— 预测先行纪律 ✗）")
    if marker not in text:
        reasons.append(f"{arm} 预注册未见钉死标记 {marker}")
    return reasons, metrics, text


def check_prereg_m5a(ctx: AuditContext) -> CheckResult:
    """C1 M5A 预注册在场且含预测节（+ 钉死对象 train.jsonl 冻结 sha256 在文）。"""
    reasons, metrics, text = _prereg_state(PREREG_M5A, "M5A", "M5A-PREREG=DONE")
    if text is not None:
        if FROZEN_LAUNCH["m5a_train"]["sha256"] not in text:
            reasons.append("M5A 预注册未见 train.jsonl 冻结 sha256（ee181598…）—— "
                           "钉死对象与审计对象脱钩 ✗")
        else:
            metrics["pins_train_sha256"] = True
    return CheckResult(not reasons, reasons, metrics)


def check_prereg_p2rl(ctx: AuditContext) -> CheckResult:
    """C2 P2-RL 预注册在场且含预测节（+ 钉死对象 RL 池路径在文）。"""
    reasons, metrics, text = _prereg_state(PREREG_P2RL, "P2-RL", "P2RL-PREREG=DONE")
    if text is not None:
        if RLVR_POOL_REL not in text:
            reasons.append(f"P2-RL 预注册未见 RL 池路径 {RLVR_POOL_REL} —— "
                           f"钉死对象与审计对象脱钩 ✗")
        else:
            metrics["pins_rl_pool_path"] = True
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ A5 ==
def build_sha256_registry(cfg: AuditConfig) -> dict:
    """全部被审计文件 sha256 清单（「全部 sha256」落盘 ✓；只读，不改任何文件）。"""
    spec = [
        (cfg.p16_checker, False), (Path(__file__).resolve(), False),
        (cfg.m4_base, True), (cfg.p16_benign, True), (cfg.p16_malicious, True),
        (cfg.p16_manifest, False),
        (cfg.mix_path, True), (M5_MANIFEST, False),
        (M5A_TRAIN, True), (M5A_MANIFEST, False), (M5A_DSINFO, False),
        (RLVR_POOL, True), (RLVR_MANIFEST, False),
        (GATE_REPORT, False), (PREREG_M5A, False), (PREREG_P2RL, False),
    ]
    out: dict = {}
    for path, with_rows in spec:
        entry: dict = {}
        if path.exists():
            entry["sha256"] = sha256_file(path)
            entry["bytes"] = path.stat().st_size
            if with_rows:
                entry["rows"] = count_rows(path)
        else:
            entry.update(sha256=None, bytes=None, missing=True)
        out[path.relative_to(ROOT).as_posix()] = entry
    return out


def build_registered_not_gated() -> dict:
    """登记不设闸项（随报告落盘，不进 PASS/FAIL 判定 —— 机检不可全代 ✗）。"""
    return {
        "p16_spotcheck_90": {
            "file": "reports/p16-spotcheck.md",
            "status": "PENDING_HUMAN_GATE" if not SPOTCHECK_REPORT.exists() else "PRESENT",
            "note": "p1.6 §6 人工关口（15 行/族 × 6 = 90 行，机检不可全代 ✗）；"
                    "m5a-prereg §6 第 2 项 —— 本审计登记不设闸，发射前由所有者闭环",
        },
        "g1_scan_interaction": {
            "status": "RESOLVED_BY_PLACEMENT",
            "note": "m5a 混料落点 data/m5a-run/（及孪生 data/m5-run/）在 checker G1 字节级"
                    "扫描范围（data/dpo|dpo-remediation-staging|m4-run|lf|sft）之外；训练混料"
                    "按设计含全部 5,760 个 p16 id = G1 判据的设计内合法内容而非污染；本审计按"
                    "当前落点串接复跑，无交互、checker 零改动 ✗（m5a manifest "
                    "g1_scan_interaction + m5a-prereg §6 第 5 项已裁决 ✓）",
        },
        "checker_stale_prose": "checker 报告「登记与待办」节仍含『launch_audit.py 尚不存在"
                               "（2026-10-08 实查）』历史快照文案 —— checker 冻结零改动纪律"
                               "（G1 落点裁决）✓，非门禁判据、不影响退出码；接线事实以本报告为准",
        "manifest_stale_prose": "三份冻结 manifest 仍登记『launch_audit.py 尚不存在 / "
                                "PENDING_REGISTRATION』历史快照（p16 manifest .launch_audit_wiring、"
                                "m5a manifest 与 m5-run manifest .launch_prerequisites）—— manifest "
                                "已冻结不得原地改（版本纪律 ✗），快照在 launch_audit 落地时即过时，"
                                "非门禁判据；接线事实以本报告为准",
        "preregistration_freeze": "两预注册 sha256 已入 sha256_registry 供漂移观测；预测节"
                                  "不得回改由所有者裁决（p2rl 预注册 §6/§8.9），本审计机检 = "
                                  "在场 + 预测节 + 钉死标记 + 钉死对象挂钩",
    }


def make_report(cfg: AuditConfig, registry: list, checks: dict, mixture_meta: dict,
                verdict: str) -> dict:
    by_id = {s.cid: s for s in registry}
    return {
        "gate": "launch-audit",
        "tag": cfg.tag,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "verdict": verdict,
        "fail_closed_rule": ("任一检查缺失/失败/未登记 ⇒ LAUNCH-AUDIT=FAIL + 退出码非零"
                             "（无审计输出 = 拒绝发射 ✗）"),
        "read_only_scope": "只读审计 ✗✓：本脚本唯一写出 = reports/launch-audit-<tag>.json；"
                           "被审计数据 / manifest / 预注册 / 检查器零改动；子进程 "
                           "check_p16_calibration.py 按其自身设计重写其自身产物 "
                           "reports/p1.6-gate-report.md（m5a manifest g1_scan_interaction "
                           "已裁决 ✓）；零 stdin 交互",
        "mixture": mixture_meta,
        "registry": [{"id": s.cid, "title": s.title, "phase": s.phase} for s in registry],
        "checks": {cid: {"title": (by_id[cid].title if cid in by_id else "!!未登记!!"),
                         "pass": res.ok, "verdict": res.verdict,
                         "reasons": res.reasons, "metrics": res.metrics}
                   for cid, res in checks.items()},
        "sha256_registry": build_sha256_registry(cfg),
        "registered_not_gated": build_registered_not_gated(),
        "marker": MARKER,
    }


def check_output(cfg: AuditConfig, registry: list, checks: dict,
                 report_path: Path) -> CheckResult:
    """A5：审计输出落盘核验（存在/可解析/注册表闭合/判定一致 = 无审计输出即拒绝 ✗✓）。

    校验对象 = 落盘中的在途报告（verdict=PENDING）：data 相检查必须全部在盘上；
    output 相检查随后合入终版（终版闭合由 run_audit 复读校验兜底 ✓）。
    """
    reasons, metrics = [], {"report_path": str(report_path)}
    if not report_path.exists():
        return CheckResult(False, [f"审计输出缺失：{report_path}（无审计输出 = 拒绝发射 ✗✓）"],
                           metrics)
    try:
        with open(report_path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult(False, [f"审计输出不可解析：{e}"], metrics)
    for k in ("tag", "generated_at", "verdict", "checks", "registry", "mixture",
              "fail_closed_rule"):
        if k not in doc:
            reasons.append(f"审计输出缺顶层字段 {k}")
    if doc.get("tag") != cfg.tag:
        reasons.append(f"审计输出 tag={doc.get('tag')!r} != 本次 {cfg.tag!r}")
    if doc.get("verdict") != "PENDING":
        reasons.append(f"在途审计输出 verdict={doc.get('verdict')!r} != 'PENDING'（非本次产物 ✗）")
    # 注册表闭合（双向 ✓：data 相缺登记 / 多未登记项均拒绝）
    reg_ids = {s.cid for s in registry}
    data_ids = {s.cid for s in registry if s.phase == "data"}
    doc_ids = set(doc.get("checks", {}))
    if data_ids - doc_ids:
        reasons.append(f"审计输出缺 data 相注册检查：{sorted(data_ids - doc_ids)}（未落盘 = 未执行 ✗）")
    if doc_ids - reg_ids:
        reasons.append(f"审计输出含未注册检查：{sorted(doc_ids - reg_ids)}")
    # 判定一致性（盘上各检查 pass 须与实测一致 ✓；不在盘上的检查留给终版闭合校验）
    for cid, res in checks.items():
        if cid not in doc.get("checks", {}):
            continue
        got = doc["checks"].get(cid, {})
        if got.get("pass") is not res.ok:
            reasons.append(f"审计输出 {cid} pass={got.get('pass')} != 实测 {res.ok}")
    metrics["checks_in_report"] = len(doc_ids)
    return CheckResult(not reasons, reasons, metrics)


# ================================================================ 注册表 ==
DEFAULT_REGISTRY: list[CheckSpec] = [
    CheckSpec("A1", "混料对比度审计（VERDICT 双侧存在率/S·C·F 分 dpo_class + ★D 族读数）",
              check_contrast),
    CheckSpec("A2", "p16 G 门（check_p16_calibration.py 退出码透传 + P16-GATE=PASS 标记 + 门禁报告产物完整）",
              check_p16_gate),
    CheckSpec("A3", "训练数据 schema/分布快照 vs 预注册配比断言", check_distribution),
    CheckSpec("A4", "谱系链核验（两 release sha256 vs manifest + 基座 sha256 冻结）",
              check_lineage),
    CheckSpec("B1", "M5A 数据臂冻结核验（train.jsonl/m5a manifest/p16 manifest 三重对账 + 冻结锚点）",
              check_m5a_freeze),
    CheckSpec("B2", "RL 臂池冻结核验（p2rl-pool-v01 池对账 manifest + 冻结锚点）",
              check_rl_pool_freeze),
    CheckSpec("B3", "孪生混料 belt（m5a train.jsonl = m5-run 物化件字节恒等）",
              check_twin_belt),
    CheckSpec("C1", "M5A 预注册在场且含预测节（+ 钉死 sha256 在文）", check_prereg_m5a),
    CheckSpec("C2", "P2-RL 预注册在场且含预测节（+ 钉死池路径在文）", check_prereg_p2rl),
    CheckSpec("A5", "审计输出落盘核验（存在/可解析/注册表闭合/判定一致）",
              check_output, phase="output"),
]


# ================================================================ 主流程 ==
def _mixture_meta(ctx: AuditContext) -> dict:
    cfg = ctx.cfg
    rows, mode, _ = ctx.mixture_rows()
    meta = {"mode": mode, "rows": len(rows) if rows is not None else None,
            "mix_path": str(cfg.mix_path),
            "formula": "m4 基座 28,842 + p16 5,760 = 34,602（p1.6 设计 §4.5 ✓）"}
    if mode == "virtual-union":
        meta["note"] = ("P2.9 物化件 data/m5-run/dpo_m5_calib.jsonl 尚未建 ⇒ 审计在"
                        " 基座+p16 冻结源上虚拟并集重算（模式显式登记 ✓，非缺失失败）")
    for k, p in (("m4_base", cfg.m4_base), ("p16_benign", cfg.p16_benign),
                 ("p16_malicious", cfg.p16_malicious)):
        if p.exists():
            meta[k] = {"path": str(p), "sha256": sha256_file(p)}
    return meta


def run_audit(cfg: AuditConfig, registry: list | None = None,
              log: Callable[[str], None] | None = print) -> dict:
    """跑全部注册检查（fail-closed ✓）；返回最终报告 dict（含 verdict 字段）。"""
    registry = registry if registry is not None else DEFAULT_REGISTRY
    data_specs = [s for s in registry if s.phase == "data"]
    out_specs = [s for s in registry if s.phase == "output"]
    ctx = AuditContext(cfg)
    checks: dict[str, CheckResult] = {}
    t_all = time.time()

    for spec in data_specs:
        t0 = time.time()
        try:
            res = spec.fn(ctx)
        except Exception as e:                                  # 任何异常 = FAIL（fail-closed ✓）
            import traceback
            traceback.print_exc()
            res = CheckResult(False, [f"检查执行异常：{type(e).__name__}: {e}"], {})
        checks[spec.cid] = res
        if log:
            log(f"[{spec.cid}] {res.verdict}  {spec.title}（{time.time()-t0:.1f}s）")
            for msg in res.reasons[:5]:
                log(f"    ✗ {msg}")

    report_path = cfg.report_dir / f"launch-audit-{cfg.tag}.json"

    def _verdict_of(cs: dict) -> str:
        return "PASS" if cs and all(r.ok for r in cs.values()) else "FAIL"

    # ---- 落盘（第一遍：data 相 + PENDING；写不进 = 硬拒绝 ✗） ----
    doc = make_report(cfg, registry, checks, _mixture_meta(ctx), "PENDING")
    try:
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
    except OSError as e:
        if log:
            log(f"[output] ✗ 审计输出无法落盘：{e}（无审计输出 = 拒绝发射 ✗✓）")
        return {"verdict": "FAIL", "write_error": str(e), "report_path": str(report_path),
                "checks": {c: r.verdict for c, r in checks.items()}}

    # ---- output 相（A5：落盘核验 ✓） ----
    for spec in out_specs:
        t0 = time.time()
        try:
            res = spec.fn(cfg, registry, checks, report_path)
        except Exception as e:                                  # fail-closed ✓
            import traceback
            traceback.print_exc()
            res = CheckResult(False, [f"检查执行异常：{type(e).__name__}: {e}"], {})
        checks[spec.cid] = res
        if log:
            log(f"[{spec.cid}] {res.verdict}  {spec.title}（{time.time()-t0:.1f}s）")
            for msg in res.reasons[:5]:
                log(f"    ✗ {msg}")

    # ---- 终判 + 复写（fail-closed：终版落盘/复读/闭合失败也必须显式 FAIL ✗） ----
    verdict = _verdict_of(checks)
    doc = make_report(cfg, registry, checks, _mixture_meta(ctx), verdict)
    doc["report_path"] = str(report_path)
    doc["elapsed_s"] = round(time.time() - t_all, 1)
    doc.pop("marker", None)
    doc["marker"] = MARKER                # 移至末键：报告以 P18-LAUDIT=DONE 收尾 ✓
    try:
        with open(report_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        with open(report_path, encoding="utf-8") as f:          # 复读 + 全注册表闭合校验 ✗
            final = json.load(f)
        reg_ids = {s.cid for s in registry}
        if set(final.get("checks", {})) != reg_ids:
            raise ValueError(f"终版注册表不闭合：{sorted(set(final.get('checks', {})) ^ reg_ids)}")
        if final.get("verdict") != verdict:
            raise ValueError(f"终版 verdict={final.get('verdict')!r} != {verdict!r}")
    except (OSError, ValueError, json.JSONDecodeError) as e:
        if log:
            log(f"[output] ✗ 终版审计输出落盘/复读/闭合失败：{e}（fail-closed ✗）")
        return {"verdict": "FAIL", "write_error": str(e), "report_path": str(report_path),
                "checks": {c: r.verdict for c, r in checks.items()}}
    if log:
        log(f"[output] report -> {report_path}（{doc['elapsed_s']}s）")
    return doc


def _check_verdicts(doc: dict) -> dict:
    """doc['checks'] → {cid: verdict}（兼容 run_audit 硬拒绝路径的精简 shape ✓）。"""
    return {cid: (c if isinstance(c, str) else c.get("verdict", "?"))
            for cid, c in doc.get("checks", {}).items()}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="P1.8 发射审计闸（fail-closed）")
    ap.add_argument("--tag", default="m5", help="审计标签（报告 = reports/launch-audit-<tag>.json）")
    ap.add_argument("--mix", default=str(DEFAULT_MIX),
                    help="M5 物化混料路径（缺省 data/m5-run/dpo_m5_calib.jsonl；"
                         "不存在 ⇒ 基座+p16 虚拟并集，模式显式登记）")
    ap.add_argument("--list-checks", action="store_true", help="打印注册表并退出")
    args = ap.parse_args(argv)

    if args.list_checks:
        print("=== ★launch_audit 注册表（可扩展 ✓：追加 CheckSpec 即挂入）===")
        for s in DEFAULT_REGISTRY:
            print(f"  {s.cid}  [{s.phase:<6}] {s.title}")
        return 0

    cfg = AuditConfig(tag=args.tag, mix_path=Path(args.mix))
    print(f"=== ★发射审计 LAUNCH-AUDIT（P1.8，fail-closed ✓✓；tag={cfg.tag}）===")
    print(f"  混料公式 = 基座 28,842 + p16 5,760 = 34,602（§4.5 ✓）"
          f"｜物化件 = {cfg.mix_path}（缺 ⇒ 虚拟并集 ✓）")
    doc = run_audit(cfg)
    verdict = doc.get("verdict", "FAIL")

    print("\n── 判定（fail-closed：任一缺失/失败/未登记 ⇒ 拒绝 ✗）──")
    for cid, v in sorted(_check_verdicts(doc).items()):
        print(f"  {cid}: {v}")
    if verdict == "FAIL":
        print("  拒绝理由：")
        we = doc.get("write_error")
        if we:
            print(f"    ✗ [output] {we}")
        for cid, c in sorted(doc.get("checks", {}).items()):
            if isinstance(c, dict):
                for r in c.get("reasons", []):
                    print(f"    ✗ {cid}: {r}")
    rp = doc.get("report_path") or str(cfg.report_dir / f"launch-audit-{cfg.tag}.json")
    print(f"  report -> {rp}")
    print(f"LAUNCH-AUDIT={verdict}")
    print(MARKER)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
