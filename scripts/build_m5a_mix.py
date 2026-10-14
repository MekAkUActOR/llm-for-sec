# -*- coding: utf-8 -*-
"""M5A 数据轴（DPO 臂）混料构建器（纯 CPU，不训练 ✗）。

任务：M5 发射件三件套之一（预注册见 reports/m5a-preregistration.md §1 单变量声明）。
落点 data/m5a-run/（m4-run / m5-run 目录先例 ✓）：
  train.jsonl       = 34,602 行 = 基座 28,842（逐字节 ✓）+ p16 两 release 5,760
  manifest.json     = 行数 / sha256 / 配比 16.6% 校验 + 谱系链 + G1 落点裁决记录
  dataset_info.json = 注册 sec_dpo_m5a（LLaMA-Factory sharegpt ranking；条目逐字段
                      复制 data/m4-run/dataset_info.json 的 sec_dpo_m4_capfix，
                      仅 file_name 不同 —— m4-run 先例 ✓）

输入（fail-closed ✗ 任一不符即退出、零落盘）：
  1. 基座 data/m4-run/dpo_m4_capfix.jsonl（28,842 行，sha256 d4061d47…）。
     ⚠️ 任务书路径 data/dpo/m4/dpo_m4_capfix.jsonl 实查不存在（2026-10-08 glob ✗，
     任务书笔误，已报父代理并获认 ✗✓）；实际注册件 = data/m4-run/（母配方
     configs/m4-capfix-probe.yaml 的 dataset_dir+dataset ✓），与
     data/dpo-remediation-staging/dpo_m4_capfix.jsonl 孪生件逐字节一致（p16
     manifest lineage.m4_base 同判 ✓）。sha256/行数/字节数三重断言兜底 ✗。
  2. p16 最终 release（reports/p1.6-calibration-design.md §4.4 release 命名 ✓）：
     data/dpo/p16-calibration/p16_benign_release.jsonl（2,880 行）
     data/dpo/p16-calibration/p16_malicious_honest.jsonl（2,880 行）
     文件不存在 ⇒ fail-closed 报错（合并件由另一代理产出，等合并完成后重跑本脚本 ✗）。
  3. p16 冻结 manifest（data/dpo/p16-calibration/manifest.json）—— 两 release 的
     sha256 与其登记逐项核对（谱系交叉 ✓）。

断言（fail-closed，全部为可复现事实）：
  - 三输入 sha256 / 行数 / 字节数与冻结常量逐项一致；基座 sha256 前缀与
    data/m4-run/sha256-prefix.txt 登记一致；staging 孪生件逐字节一致。
  - 合并 = 字节级拼接（基座逐字节 ✓ 不重序列化、不改行尾：基座 CRLF / p16 LF 按
    冻结原样保留；LF 逐行解析不受影响，基座在 m4 探针/全长两轮即以 CRLF 原样消费 ✓）。
  - 合并件 sha256 必须等于 ee181598…（与 scripts/build_m5_mix.py 产物
    data/m5-run/dpo_m5_calib.jsonl 同三输入 ⇒ 字节恒等；data/m5-run/manifest.json
    登记 ✓）—— M5A 与 m5-calib-probe 两配置的训练数据全同，臂间可比 ✓；
    若该孪生件在场则再加逐字节 belt 复核。
  - 行级：总 34,602；id 全局唯一、基座∩p16 = 0、p16 id 命名空间 p16-[A-F]-\\d{6}；
    首轮 system / 末轮 human / chosen·rejected = gpt / 角色只含 system·human·gpt
    （出现 assistant 即 fail —— LF ranking 转换器会整行丢弃 ✗）；双侧末行 VERDICT
    （MUST-B）；基座行无 polarity 键、无 p16 id（防基座被混入校准件 ✗）。
  - 分布：p16 极性 benign_release 2,880 / malicious_refuse 2,880（50:50 ✓）；
    p16 lang en 3,438 / zh 2,322（≈60:40 ✓）；基座 lang zh 17,319 / en 11,523；
    p16 dpo_class 六类闭合（p16 冻结 manifest「distributions.overall」口径）；
    校准对占比 16.646% ≈ 16.6%（p1.6 §5.2 ✓）。

★ 落点裁决记录（G1 扫描交互，父代理 2026-10-08 裁决 ✓，登记于产物 manifest
  .g1_scan_interaction）：
  scripts/check_p16_calibration.py 的 G1 门禁对 data/dpo/**/*.jsonl（L316–L324，
  仅排除 p16-calibration 自身）做字节级扫描，断言 p16 id 格式字面量零命中。本混料
  按设计含全部 5,760 个 p16 id —— 对 G1 而言这是「下游消费件的合法内容」而非污染
  （G1 的职责 = 防 p16 泄漏到**不该含它**的文件 ✗✓）。因此：
  ① 落点选在扫描范围**外**的 data/m5a-run/（与同僚 build_m5_mix.py 落 data/m5-run/
    同理，其 docstring L30–32 登记）⇒ checker 重跑（launch_audit P1.8 串接）不受
    m5a 存在的影响 ✓；
  ② checker 零改动 ✗（加豁免更侵入，且 p16 manifest 已冻结 —— 不得原地改 ✗）。
  既有判定 P16-GATE=PASS（2026-10-08，reports/p1.6-gate-report.md）不受影响 ✓。

产出（PREFLIGHT 防覆写：已存在且字节不同 ⇒ 拒绝 ✗；一致 ⇒ 幂等 SKIP）。
预测零新增 ✗（预注册 = reports/m5a-preregistration.md；方向+幅度带逐字引自
p1.6 §7 ✓；五合取门是唯一裁决，训练曲线不作数 —— 规则 43.1 ✓）。

用法：.venv\\Scripts\\python.exe scripts\\build_m5a_mix.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M5A_DIR = os.path.join(ROOT, "data", "m5a-run")
BASE = os.path.join(ROOT, "data", "m4-run", "dpo_m4_capfix.jsonl")
BASE_PREFIX_FILE = os.path.join(ROOT, "data", "m4-run", "sha256-prefix.txt")
BASE_TWIN = os.path.join(ROOT, "data", "dpo-remediation-staging", "dpo_m4_capfix.jsonl")
P16_DIR = os.path.join(ROOT, "data", "dpo", "p16-calibration")
P16_BENIGN = os.path.join(P16_DIR, "p16_benign_release.jsonl")
P16_MALICIOUS = os.path.join(P16_DIR, "p16_malicious_honest.jsonl")
P16_MANIFEST = os.path.join(P16_DIR, "manifest.json")
SIBLING_MIX = os.path.join(ROOT, "data", "m5-run", "dpo_m5_calib.jsonl")
OUT_MIX = os.path.join(M5A_DIR, "train.jsonl")
OUT_MANIFEST = os.path.join(M5A_DIR, "manifest.json")
OUT_DSINFO = os.path.join(M5A_DIR, "dataset_info.json")

BUILT = "2026-10-08"
SPEC = ("reports/p1.6-calibration-design.md（§4.4 release 命名 / §4.5 发射接线 / "
        "§5.2 集成预算 / §7 预注册）")

# ---- 冻结输入身份（2026-10-08 实测；任一漂移 ⇒ fail-closed 零落盘） ----
FROZEN = {
    "base": {
        "path": "data/m4-run/dpo_m4_capfix.jsonl",
        "sha256": "d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414",
        "rows": 28842, "bytes": 59793275,
        "sha256_prefix_registered": "D4061D47DF903D91",   # data/m4-run/sha256-prefix.txt
        "task_path_note": "任务书路径 data/dpo/m4/dpo_m4_capfix.jsonl 实查不存在"
                          "（任务书笔误，父代理已认 ✗✓）；实际注册件 = data/m4-run"
                          "（母配方 dataset_dir ✓）",
    },
    "p16_benign_release": {
        "path": "data/dpo/p16-calibration/p16_benign_release.jsonl",
        "sha256": "1636ba88c2f8834cdb581ea9c147e94990f28229c3665e5559375dd669daacc1",
        "rows": 2880, "bytes": 7304338,
        "composition": "A 1,500 + B 480 + C 360 + E 300 + D放行 240",
    },
    "p16_malicious_honest": {
        "path": "data/dpo/p16-calibration/p16_malicious_honest.jsonl",
        "sha256": "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d",
        "rows": 2880, "bytes": 8172306,
        "composition": "F 2,640 + D拒绝 240（对话式 120 + 载体 120）",
    },
    "p16_manifest": {
        "path": "data/dpo/p16-calibration/manifest.json",
        "sha256": "e5d10d641d461d1d5b02a0f0359df305a8ce04fd71152b0135db3966cf7d1b35",
    },
}
P16_MANIFEST_SHA = FROZEN["p16_manifest"]["sha256"]

# ---- 合并件冻结身份：与 build_m5_mix.py 产物 data/m5-run/dpo_m5_calib.jsonl ----
# 同三输入 ⇒ 字节恒等（data/m5-run/manifest.json 登记 ✓）。
# M5A（m5a-dpo-probe）与 m5-calib-probe 训练数据全同 ⇒ 唯一配置差 = save_total_limit
# （保留策略，规则 43.5 非科学变量）—— 臂间可比的机器证明 ✗✓
MERGED_SHA256 = "ee181598af572a634394416c000c212e312bd00acc9bff8a0cedeb5a5b6d2e60"
MERGED_BYTES = 75269919

# ---- 分布契约（p16 冻结 manifest「distributions.overall」+ 基座实测；fail-closed） ----
EXPECT = {
    "total_rows": 34602,
    "p16_polarity": {"benign_release": 2880, "malicious_refuse": 2880},   # 50:50 ✓
    "p16_lang": {"en": 3438, "zh": 2322},                                  # ≈60:40 ✓
    "base_lang": {"zh": 17319, "en": 11523},
    "merged_lang": {"zh": 19641, "en": 14961},
    "p16_dpo_class": {
        "p16_benign_release": 1500, "p16_dilution_judgment": 300,
        "p16_judgment_teaching": 360, "p16_malicious_honest": 2640,
        "p16_multiturn_benign": 480, "p16_verdict_honesty": 480,
    },
    "p16_share_pct": round(5760 / 34602 * 100, 3),   # 16.646（设计口径 16.6 ✓）
}
ID_RE = re.compile(r"^p16-[A-F]-\d{6}$")

# ---- dataset_info 注册（新建单条目文件；字段逐项复制 data/m4-run/dataset_info.json
#      的 sec_dpo_m4_capfix 条目，仅 file_name 换为本目录 train.jsonl —— m4-run 先例 ✓） ----
DS_NAME = "sec_dpo_m5a"
DS_ENTRY = {
    "file_name": "train.jsonl",
    "formatting": "sharegpt",
    "ranking": True,
    "columns": {
        "messages": "conversations",
        "chosen": "chosen",
        "rejected": "rejected",
    },
    "tags": {
        "role_tag": "from",
        "content_tag": "value",
        "user_tag": "human",
        "assistant_tag": "gpt",
        "system_tag": "system",
    },
}


def die(msg: str) -> None:
    print(f"[FATAL] {msg}")
    print("BUILD-M5A-MIX=FAIL（fail-closed，未落盘）")
    sys.exit(1)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(raw: bytes, tag: str) -> list:
    out = []
    for ln, line in enumerate(raw.decode("utf-8").splitlines()):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"{tag} 第 {ln + 1} 行 JSON 解析失败：{e}")
    return out


# ================================================================ 启动断言 ==
def assert_inputs() -> tuple[bytes, bytes, bytes]:
    """三输入的存在性 / sha256 / 行数 / 字节数 / 谱系交叉核对（fail-closed）。"""
    for key, path in (("base", BASE), ("p16_benign_release", P16_BENIGN),
                      ("p16_malicious_honest", P16_MALICIOUS)):
        if not os.path.exists(path):
            hint = ""
            if key.startswith("p16_"):
                hint = ("（p16 最终 release 由另一代理产出；等合并完成后重跑本脚本 ✗"
                        " fail-closed）")
            die(f"输入缺失：{FROZEN[key]['path']}{hint}")
    if not os.path.exists(P16_MANIFEST):
        die(f"p16 冻结 manifest 缺失：{FROZEN['p16_manifest']['path']}")

    raws = {}
    for key, path in (("base", BASE), ("p16_benign_release", P16_BENIGN),
                      ("p16_malicious_honest", P16_MALICIOUS)):
        raw = open(path, "rb").read()
        sha = hashlib.sha256(raw).hexdigest()
        want = FROZEN[key]
        if sha != want["sha256"]:
            die(f"{want['path']} sha256 漂移：{sha[:16]}… != 冻结 {want['sha256'][:16]}…")
        if len(raw) != want["bytes"]:
            die(f"{want['path']} 字节数 {len(raw)} != 冻结 {want['bytes']}")
        if not raw.endswith(b"\n"):
            die(f"{want['path']} 未以换行收尾（字节拼接会粘连行 ✗）")
        rows = load_rows(raw, want["path"])
        if len(rows) != want["rows"]:
            die(f"{want['path']} 行数 {len(rows)} != 冻结 {want['rows']}")
        raws[key] = raw
        print(f"[OK] {os.path.basename(path)}: {len(rows)} 行 / {len(raw):,} B，"
              f"sha256 {sha[:16]}… 与冻结常量一致 ✓")

    # 基座谱系交叉核对 ①：data/m4-run/sha256-prefix.txt 登记的前缀
    prefix_txt = open(BASE_PREFIX_FILE, encoding="utf-8").read().strip().upper()
    if prefix_txt != FROZEN["base"]["sha256_prefix_registered"]:
        die(f"sha256-prefix.txt 登记 {prefix_txt} != 常量 "
            f"{FROZEN['base']['sha256_prefix_registered']}")
    if not FROZEN["base"]["sha256"].upper().startswith(prefix_txt):
        die("基座 sha256 与 sha256-prefix.txt 登记前缀不符")
    # 基座谱系交叉核对 ②：staging 孪生件逐字节一致（模板来源 = 训练注册件 ✓）
    if not os.path.exists(BASE_TWIN):
        die(f"基座孪生件缺失：{BASE_TWIN}")
    twin_sha = sha256_file(BASE_TWIN)
    if twin_sha != FROZEN["base"]["sha256"]:
        die(f"基座孪生件 {BASE_TWIN} sha256 {twin_sha[:16]}… 与训练注册件不一致")
    print(f"[OK] 基座谱系：sha256 前缀 {prefix_txt} 与 sha256-prefix.txt 一致 ✓；"
          f"staging 孪生件逐字节一致 ✓")

    # p16 谱系交叉核对：冻结 release manifest 登记的两文件 sha256 + manifest 自身 sha256
    m_sha = sha256_file(P16_MANIFEST)
    if m_sha != P16_MANIFEST_SHA:
        die(f"p16 manifest sha256 漂移：{m_sha[:16]}… != 冻结 {P16_MANIFEST_SHA[:16]}…")
    m16 = json.loads(open(P16_MANIFEST, encoding="utf-8").read())
    for fname, key in (("p16_benign_release.jsonl", "p16_benign_release"),
                       ("p16_malicious_honest.jsonl", "p16_malicious_honest")):
        reg = m16.get("files", {}).get(fname, {}).get("sha256", "")
        if reg != FROZEN[key]["sha256"]:
            die(f"p16 manifest 登记的 {fname} sha256 与实际文件不符")
    print(f"[OK] p16 谱系：release manifest sha256 {m_sha[:16]}… 冻结一致，"
          f"两 release 文件 sha256 与其登记逐项一致 ✓")
    return raws["base"], raws["p16_benign_release"], raws["p16_malicious_honest"]


# ================================================================ 结构与分布断言 ==
def assert_rows(base_rows: list, p16_rows: list) -> dict:
    """行级 fail-closed 断言：schema 口径 / id / 极性 / 语言 / 角色 / VERDICT。"""
    total = len(base_rows) + len(p16_rows)
    if total != EXPECT["total_rows"]:
        die(f"总行数 {total} != 预期 {EXPECT['total_rows']}")

    base_ids = [r["id"] for r in base_rows]
    p16_ids = [r["id"] for r in p16_rows]
    if len(set(base_ids)) != len(base_ids) or len(set(p16_ids)) != len(p16_ids):
        die("基座或 p16 内部 id 重复")
    if set(base_ids) & set(p16_ids):
        die(f"基座∩p16 id 重叠 {len(set(base_ids) & set(p16_ids))} 条（G1 口径零容忍 ✗）")
    for i in p16_ids:
        if not ID_RE.match(i):
            die(f"p16 id 不合命名空间：{i!r}")

    n_assistant = 0
    for r in base_rows + p16_rows:
        conv = r["conversations"]
        if conv[0]["from"] != "system":
            die(f"{r['id']}: 首轮不是 system")
        if conv[-1]["from"] != "human":
            die(f"{r['id']}: 末轮不是 human（ranking 口径 ✗）")
        if r["chosen"]["from"] != "gpt" or r["rejected"]["from"] != "gpt":
            die(f"{r['id']}: chosen/rejected 角色标签不是 gpt")
        for t in conv:
            if t["from"] not in ("system", "human", "gpt"):
                die(f"{r['id']}: 非法角色标签 {t['from']!r}（house 口径 system/human/gpt）")
            if t["from"] == "assistant":
                n_assistant += 1
        for side in ("chosen", "rejected"):
            if not r[side]["value"].rstrip().rsplit("\n", 1)[-1].startswith("VERDICT:"):
                die(f"{r['id']}: {side} 末行无 VERDICT（MUST-B 契约 ✗）")
    if n_assistant:
        die(f"发现 {n_assistant} 个 assistant 前缀轮（未按 CEF 先例归一为 gpt ✗——"
            f"LF ranking 转换器会整行丢弃）")
    print(f"[OK] 结构断言：{total} 行全部 system 开头 / human 收尾 / chosen·rejected=gpt /"
          f" 双侧 VERDICT 在场；assistant 轮 = 0（CEF 归一先例保持 ✓）")

    # 基座逐字节纪律 ⇒ 基座行不得携带 p16 审计键（防基座被混入校准件）
    if any("polarity" in r or str(r["id"]).startswith("p16-") for r in base_rows):
        die("基座行出现 polarity 键或 p16 id（基座被污染 ✗）")

    pol = Counter(r["polarity"] for r in p16_rows)
    if dict(pol) != EXPECT["p16_polarity"]:
        die(f"p16 极性分布 {dict(pol)} != 预期 {EXPECT['p16_polarity']}（50:50 ✗）")
    lang16 = Counter(r["lang"] for r in p16_rows)
    if dict(lang16) != EXPECT["p16_lang"]:
        die(f"p16 语言分布 {dict(lang16)} != 预期 {EXPECT['p16_lang']}")
    langb = Counter(r["lang"] for r in base_rows)
    if dict(langb) != EXPECT["base_lang"]:
        die(f"基座语言分布 {dict(langb)} != 冻结实测 {EXPECT['base_lang']}")
    dclass = Counter(r["dpo_class"] for r in p16_rows)
    if dict(dclass) != EXPECT["p16_dpo_class"]:
        die(f"p16 dpo_class 分布与冻结 manifest 不符：{dict(dclass)}")
    langm = langb + lang16
    if dict(langm) != EXPECT["merged_lang"]:
        die(f"合并语言分布 {dict(langm)} != 预期 {EXPECT['merged_lang']}")
    share = len(p16_rows) / total * 100
    if abs(share - EXPECT["p16_share_pct"]) > 0.005:
        die(f"p16 占比 {share:.4f}% != 预期 {EXPECT['p16_share_pct']}%")
    print(f"[OK] 分布断言：极性 {dict(pol)} = 50:50 ✓；p16 lang en:zh = "
          f"{lang16['en']}:{lang16['zh']}"
          f"（{lang16['en'] / len(p16_rows) * 100:.1f}%:"
          f"{lang16['zh'] / len(p16_rows) * 100:.1f}%）✓；"
          f"p16 占比 {share:.2f}%（设计 16.6% ✓）")
    return {"p16_polarity": dict(pol), "p16_lang": dict(lang16),
            "base_lang": dict(langb), "merged_lang": dict(langm),
            "p16_dpo_class": dict(sorted(dclass.items()))}


# ================================================================ 落盘（防覆写） ==
def write_guarded(path: str, data: bytes, label: str) -> bool:
    """PREFLIGHT 防覆写：存在且不同 ⇒ die；存在且一致 ⇒ 幂等 SKIP；不存在 ⇒ 写入。"""
    if os.path.exists(path):
        old = open(path, "rb").read()
        if old != data:
            die(f"防覆写：{label} 已存在且字节不同（冻结纪律：修改 ⇒ 新开版本目录，"
                f"如确需重建请先人工确认并移除旧文件）")
        print(f"[SKIP] {label} 已存在且字节一致（幂等）")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    print(f"[WRITE] {label}: {len(data):,} B")
    return True


def register_dataset_info() -> dict:
    """dataset_info.json 注册 sec_dpo_m5a（本目录新建单条目文件，零既有条目被动 ✓）。

    - 目标已存在（幂等重跑）⇒ 校验条目一致即 SKIP，不一致 ⇒ die（不得原地改 ✗）；
    - 目标不存在（本次实况：data/m5a-run/ 为新目录）⇒ 新建单条目文件；
      既有注册文件（data/m4-run、data/lf 的 dataset_info.json）零改动 ✓。
    - 返回值只含可复现事实（backup/entries/preexisting_entries）——不含随运行状态
      变化的散文，否则 manifest 字节不确定，幂等重跑会误触防覆写 ✗。
    """
    entry = {DS_NAME: DS_ENTRY}
    if os.path.exists(OUT_DSINFO):
        existing = json.loads(open(OUT_DSINFO, encoding="utf-8").read())
        if not isinstance(existing, dict):
            die("dataset_info.json 已存在但不是对象（LF 注册格式 ✗）")
        if existing == entry:
            print("[SKIP] dataset_info.json 已存在且条目一致（幂等）")
            return {"backup": None, "entries": 1, "preexisting_entries": 0}
        die(f"dataset_info.json 已存在且与冻结条目不同（不得原地改 ✗；"
            f"修改 ⇒ 新开版本目录）")
    os.makedirs(M5A_DIR, exist_ok=True)
    data = (json.dumps(entry, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    with open(OUT_DSINFO, "wb") as f:
        f.write(data)
    print(f"[WRITE] dataset_info.json：新建（{DS_NAME} 单条目；目标目录原无注册文件，"
          f"零既有条目被动 ✓ backup=None）")
    return {"backup": None, "entries": 1, "preexisting_entries": 0}


# ================================================================ 主流程 ==
def main() -> int:
    print("== M5A 数据轴（DPO 臂）混料构建（build_m5a_mix） ==")
    base_raw, ben_raw, mal_raw = assert_inputs()
    base_rows = load_rows(base_raw, "base")
    ben_rows = load_rows(ben_raw, "p16_benign")
    mal_rows = load_rows(mal_raw, "p16_malicious")
    p16_rows = ben_rows + mal_rows
    dists = assert_rows(base_rows, p16_rows)

    # ---- 字节级合并（基座逐字节 ✓：不重序列化、不改行尾） ----
    mix_raw = base_raw + ben_raw + mal_raw
    n_expect = FROZEN["base"]["bytes"] + FROZEN["p16_benign_release"]["bytes"] \
        + FROZEN["p16_malicious_honest"]["bytes"]
    if len(mix_raw) != n_expect:
        die(f"合并字节数 {len(mix_raw)} != 三输入之和 {n_expect}")
    if mix_raw[: len(base_raw)] != base_raw or mix_raw[len(base_raw):] != ben_raw + mal_raw:
        die("合并件字节切片与输入不一致（逐字节纪律破坏 ✗）")
    mix_rows = load_rows(mix_raw, "train.jsonl")
    if len(mix_rows) != EXPECT["total_rows"]:
        die(f"合并件复解析行数 {len(mix_rows)} != {EXPECT['total_rows']}")
    mix_sha = hashlib.sha256(mix_raw).hexdigest()
    if mix_sha != MERGED_SHA256 or len(mix_raw) != MERGED_BYTES:
        die(f"合并件身份漂移：sha256 {mix_sha[:16]}… / {len(mix_raw):,} B != "
            f"冻结 {MERGED_SHA256[:16]}… / {MERGED_BYTES:,} B"
            f"（须与 data/m5-run/dpo_m5_calib.jsonl 字节恒等 —— 同三输入 ⇒ "
            f"字节不同即输入被改动 ✗）")
    print(f"[OK] 字节级合并：{len(mix_rows)} 行 / {len(mix_raw):,} B，"
          f"基座前 {len(base_raw):,} B 逐字节 ✓，sha256 {mix_sha[:16]}…")
    print(f"[OK] 臂间可比：与 data/m5-run/dpo_m5_calib.jsonl（build_m5_mix.py 产物）"
          f"字节恒等 ✓（冻结 sha256 断言）")
    if os.path.exists(SIBLING_MIX):
        if open(SIBLING_MIX, "rb").read() != mix_raw:
            die(f"孪生混料 {SIBLING_MIX} 与本合并件字节不一致（belt 复核 ✗）")
        print("[OK] belt 复核：data/m5-run/dpo_m5_calib.jsonl 在场且逐字节一致 ✓")

    write_guarded(OUT_MIX, mix_raw, "train.jsonl")
    # 落盘后复验（读回磁盘实物，不信内存态 ✗）
    disk = open(OUT_MIX, "rb").read()
    if disk != mix_raw:
        die("落盘复验失败：磁盘内容与预期字节不一致")
    if len(load_rows(disk, "train.jsonl")) != EXPECT["total_rows"]:
        die("落盘复验失败：行数不符")
    print("[OK] 落盘复验：磁盘实物字节 = 预期，行数 34,602 ✓")

    reg = register_dataset_info()
    # 注册复验：条目可解析、指向的文件存在（LF parser.py 口径 dataset_dir+file_name）
    dsinfo = json.loads(open(OUT_DSINFO, encoding="utf-8").read())
    if DS_NAME not in dsinfo or dsinfo[DS_NAME] != DS_ENTRY:
        die("注册复验失败：条目缺失或漂移")
    if not os.path.exists(os.path.join(M5A_DIR, DS_ENTRY["file_name"])):
        die("注册复验失败：file_name 不在本目录")
    print(f"[OK] 注册复验：{DS_NAME} → {DS_ENTRY['file_name']}"
          f"（dataset_dir=data/m5a-run 解析可达 ✓）")

    # ---- manifest（行数 / sha256 / 配比校验 + 谱系链 + G1 落点裁决记录） ----
    manifest = {
        "name": "m5a-dpo-arm-mix",
        "built": BUILT,
        "builder": "scripts/build_m5a_mix.py",
        "spec": SPEC,
        "task": "M5A 数据轴（DPO 臂）发射混料（纯 CPU，不训练 ✗；预测零新增 ✗——"
                "预注册见 reports/m5a-preregistration.md，预测带逐字引自 p1.6 §7）",
        "files": {
            "train.jsonl": {
                "rows": EXPECT["total_rows"], "bytes": len(mix_raw), "sha256": mix_sha,
                "sha256_prefix_16": mix_sha[:16].upper(),
                "composition": "基座 dpo_m4_capfix 28,842（逐字节 ✓）"
                               " + p16 两 release 5,760（benign 2,880 + malicious 2,880）",
                "p16_share_pct": EXPECT["p16_share_pct"],
            },
        },
        "mix": {
            "base_rows": 28842, "p16_rows": 5760, "total_rows": EXPECT["total_rows"],
            "p16_share_pct": EXPECT["p16_share_pct"],
            "design_ref": "p1.6 §5.2：28,842 + 5,760 = 34,602，p16 占 16.6%"
                          "（实测 16.646% ✓）",
            "probe_visibility": "300 步 × batch 16 = 4,800 可见 ⇒ 期望校准对 ≈799 行"
                                "（p1.6 §5.2，二项 σ≈26）",
            "eol_note": "基座 CRLF / p16 LF，按冻结原样字节拼接（逐字节纪律优先）；"
                        "逐行 JSON 解析不受影响；基座在 m4 探针/全长两轮即以 CRLF"
                        " 原样消费 ✓",
            "token_budget": "cutoff_len 1024 不动（m5a-dpo-probe 单变量纪律 ✓）；"
                            "p16 全量已过 G8 部署 tokenizer ≤1,000 断言"
                            "（p1.6-gate-report）",
            "twin_mix": {
                "file": "data/m5-run/dpo_m5_calib.jsonl",
                "builder": "scripts/build_m5_mix.py（P2.9 集成件）",
                "sha256_asserted_equal": MERGED_SHA256,
                "note": "同三输入 ⇒ 字节恒等（构建时冻结断言 + 在场 belt 复核 ✓）；"
                        "M5A（m5a-dpo-probe）与 m5-calib-probe 训练数据全同，"
                        "唯一配置差 = save_total_limit 8→20（保留策略，规则 43.5"
                        " 非科学变量）—— 臂间可比的机器证明 ✗✓",
            },
        },
        "distributions": {
            "merged_lang": dists["merged_lang"],
            "base_lang": dists["base_lang"],
            "p16_lang": dists["p16_lang"],
            "p16_polarity": dists["p16_polarity"],
            "p16_dpo_class": dists["p16_dpo_class"],
        },
        "lineage": {
            "base": {
                "file": FROZEN["base"]["path"],
                "role": "M5A 基座（m4-capfix 唯一活候选；长度匹配 + capfix 修法）",
                "rows": FROZEN["base"]["rows"], "bytes": FROZEN["base"]["bytes"],
                "sha256": FROZEN["base"]["sha256"],
                "sha256_prefix_registered": FROZEN["base"]["sha256_prefix_registered"],
                "prefix_registry": "data/m4-run/sha256-prefix.txt（交叉核对 ✓）",
                "task_path_note": FROZEN["base"]["task_path_note"],
                "twin_identical": {
                    "file": "data/dpo-remediation-staging/dpo_m4_capfix.jsonl",
                    "sha256_asserted_equal": True,
                    "note": "staging 模板来源件与训练注册件逐字节一致（本次实测断言 ✓）",
                },
                "registered_as": "sec_dpo_m4_capfix @ data/m4-run/dataset_info.json",
                "provenance": "data/dpo-remediation-staging/README.md"
                              "（CAPFIX-VERIFY=PASS 7 项）"
                              " + reports/m3-mechanism-report-rejected-suppression.md",
            },
            "p16_benign_release": {
                "file": FROZEN["p16_benign_release"]["path"],
                "rows": FROZEN["p16_benign_release"]["rows"],
                "bytes": FROZEN["p16_benign_release"]["bytes"],
                "sha256": FROZEN["p16_benign_release"]["sha256"],
                "composition": FROZEN["p16_benign_release"]["composition"],
            },
            "p16_malicious_honest": {
                "file": FROZEN["p16_malicious_honest"]["path"],
                "rows": FROZEN["p16_malicious_honest"]["rows"],
                "bytes": FROZEN["p16_malicious_honest"]["bytes"],
                "sha256": FROZEN["p16_malicious_honest"]["sha256"],
                "composition": FROZEN["p16_malicious_honest"]["composition"],
            },
            "p16_release_manifest": {
                "file": FROZEN["p16_manifest"]["path"],
                "sha256": P16_MANIFEST_SHA,
                "gate": "reports/p1.6-gate-report.md（P16-GATE=PASS，G1–G12 全绿 ✓）",
                "deeper_chain": "该 manifest 内含 parts-abd/parts-cef 两级子件 sha256"
                                " 谱系链（本链到此转接，不再复制 ✓）",
            },
        },
        "registration": {
            "dataset_info": "data/m5a-run/dataset_info.json（新建单条目注册 "
                            "sec_dpo_m5a → train.jsonl；既有注册文件 data/m4-run/"
                            "dataset_info.json 与 data/lf/dataset_info.json 零改动 ✓）",
            "entry_format_source": "逐字段复制 data/m4-run/dataset_info.json 的"
                                   " sec_dpo_m4_capfix 条目（LLaMA-Factory sharegpt"
                                   " ranking 口径），仅 file_name 不同",
            "lf_resolution": "LLaMA-Factory src/llamafactory/data/parser.py："
                             "dataset_dir + dataset_info.json 解析；loader.py："
                             "dataset_dir + file_name 定位",
            "backup": reg,
            "config": "configs/m5a-dpo-probe.yaml（m4-capfix-probe 逐字段复制，仅改 "
                      "dataset_dir/dataset/output_dir + save_total_limit 8→20（规则 "
                      "43.5 保留策略，非科学变量）—— 单变量纪律 ✓）",
        },
        "g1_scan_interaction": {
            "status": "RESOLVED_BY_PLACEMENT",
            "decision": "落点 data/m5a-run/ 选在 check_p16_calibration.py G1 字节级"
                        "扫描范围（data/dpo/**/*.jsonl，L316–L324）之外（父代理"
                        " 2026-10-08 裁决 ✓；与同僚 build_m5_mix.py 落 data/m5-run/ "
                        "同理）；checker 零改动 ✗",
            "rationale": "本混料按设计含全部 5,760 个 p16 id —— 对 G1 而言是「下游"
                         "消费件的合法内容」而非污染（G1 的职责 = 防 p16 泄漏到"
                         "**不该含它**的文件 ✗✓）；加豁免更侵入且 p16 manifest 已"
                         "冻结（不得原地改 ✗），故落点出界优于改 checker",
            "consequence": "m5a 落盘后重跑 checker（launch_audit P1.8 串接）不受"
                           " m5a 存在的影响 ✓；既有判定 P16-GATE=PASS（2026-10-08，"
                           "reports/p1.6-gate-report.md）不受影响 ✓",
        },
        "launch_prerequisites": {
            "p16_gate": "P16-GATE=PASS ✓（reports/p1.6-gate-report.md）",
            "spotcheck": "PENDING_HUMAN_GATE（reports/p16-spotcheck.md 待人工抽查 "
                         "90 行 = 15 行/族 × 6，p1.6 §6 人工关口）",
            "launch_audit": "scripts/launch_audit.py 尚不存在（P1.8 待建；建成后须"
                            " 串接 check_p16_calibration.py 退出码，fail-closed ✓"
                            " —— m5a 已在 G1 扫描范围外，串接无交互）",
            "preregistration": "reports/m5a-preregistration.md（M5A 发射件专用钉死件；"
                               "预测带逐字引自 p1.6 §7，零新增 ✗）",
        },
        "version_discipline": "冻结 = 本 manifest sha256；任何修改 ⇒ 新开版本目录（如 "
                              "data/m5b-run/），不得原地改 ✗（p16/v0.6/v0.7 先例）",
    }
    mtxt = (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    write_guarded(OUT_MANIFEST, mtxt, "manifest.json")

    print("\n== 构建完成 ==")
    print(f"  train.jsonl = 28,842（基座逐字节）+ 5,760（p16 两 release）"
          f" = {EXPECT['total_rows']} 行；p16 占 {EXPECT['p16_share_pct']}%")
    print(f"  sha256 {mix_sha}（与 data/m5-run/dpo_m5_calib.jsonl 字节恒等 ✓）")
    print(f"  谱系：基座 …{FROZEN['base']['sha256'][:12]} · p16 manifest …"
          f"{P16_MANIFEST_SHA[:12]}")
    print(f"  注册：{DS_NAME} @ data/m5a-run/dataset_info.json"
          f"（backup={reg['backup']}）")
    print("BUILD-M5A-MIX=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
