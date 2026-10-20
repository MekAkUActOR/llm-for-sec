# -*- coding: utf-8 -*-
"""M6 红队集构建与校验脚本（qa-m6）。

将 scripts/m6_redteam_data_{a,b,c,d,e}.py 中手写的样本合并为
reports/m6/redteam/redteam-v1.jsonl，并执行一致性校验：
  - id 唯一性与命名模式
  - task_target 非空且 ∈ {T1..T6}，expected 与 task_target 一致
  - text/turns 二选一；turns 全为非空字符串
  - B 族编码样本可解码性断言（密文还原 == 预期明文）
  - 零武器化粗筛：无 http(s) 真实域名（只允许 RFC 2606/5737 保留段）、无真实 IP

用法：.venv\\Scripts\\python.exe -X utf8 scripts\\m6_redteam_build.py
"""
import base64
import codecs
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from m6_redteam_data_a import SAMPLES_A
from m6_redteam_data_b import SAMPLES_B
from m6_redteam_data_c import SAMPLES_C
from m6_redteam_data_d import SAMPLES_D
from m6_redteam_data_e import SAMPLES_E
from m6_redteam_data_f import SAMPLES_F

TASKS = {"T1", "T2", "T3", "T4", "T5", "T6"}
ALLOWED_HOSTS = re.compile(
    r"(example\.(com|org|net|info|biz|dev)|.*\.example\.(com|org|net|info|biz|dev)"
    r"|198\.51\.100\.\d+|203\.0\.113\.\d+|192\.0\.2\.\d+|10\.\d+\.\d+\.\d+|0\.0\.0\.0)"
)
IP_ANY = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

# B 族可解码性断言表：id -> (解码函数, 预期明文片段)
ENCODING_CHECKS = {
    "rt-b1-01": lambda s: base64.b64decode(s).decode("utf-8"),
    "rt-b1-02": lambda s: codecs.encode(s, "rot13"),
    "rt-b1-03": lambda s: bytes.fromhex(s.replace(" ", "")).decode("utf-8"),
    "rt-b1-04": lambda s: base64.b64decode(base64.b64decode(s)).decode("utf-8"),
    "rt-b1-05": lambda s: base64.b64decode(s.split("\n")[-1]).decode("utf-8"),
    "rt-b1-06": lambda s: codecs.encode(s, "rot13"),
    "rt-b1-07": lambda s: base64.b32decode(s.split("\n")[0]).decode("utf-8"),
    "rt-b1-08": lambda s: base64.b64decode(s.split("--- attached payload (base64) ---\n")[-1]).decode("utf-8"),
}
# 解码后必须包含的关键词（模式级请求语义锚）
DECODE_ANCHORS = {
    "rt-b1-01": ["路由器", "代理池"], "rt-b1-02": ["cloning", "payment cards"],
    "rt-b1-03": ["基站", "中间人"], "rt-b1-04": ["GSM interceptor"],
    "rt-b1-05": ["商务邮件欺诈", "CFO"], "rt-b1-06": ["ru he", "jia ting"],  # 拼音解码态锚
    "rt-b1-07": ["GPS tracker"], "rt-b1-08": ["勒索", "杀毒"],
}


def extract_payload_text(sample_text: str) -> str:
    """提取 B1 样本中的密文主体（去掉说明外壳）。"""
    lines = [ln.strip() for ln in sample_text.split("\n") if ln.strip()]
    # 取最长的那行（密文通常最长）
    return max(lines, key=len)


def check_zero_weaponization(text: str, sid: str, errs: list):
    """零武器化粗筛：URL 主机与 IP 只允许保留段。"""
    for m in re.finditer(r"https?://([^\s/>'\"]+)", text):
        host = m.group(1)
        if not ALLOWED_HOSTS.match(host):
            errs.append(f"{sid}: 非保留域 URL {host}")
    for m in IP_ANY.finditer(text):
        if not ALLOWED_HOSTS.match(m.group(0)):
            errs.append(f"{sid}: 非保留 IP {m.group(0)}")


def main():
    samples = SAMPLES_A + SAMPLES_B + SAMPLES_C + SAMPLES_D + SAMPLES_E + SAMPLES_F
    errs, warns = [], []
    seen_ids = set()
    fam_count, task_count, lang_count = {}, {}, {}

    for s in samples:
        sid = s["id"]
        # id 唯一 + 格式
        assert sid not in seen_ids, f"id 重复: {sid}"
        seen_ids.add(sid)
        assert re.fullmatch(r"rt-[a-z0-9]+-\d+", sid), f"id 格式非法: {sid}"
        # 任务目标
        tt = s["task_target"]
        assert isinstance(tt, list) and tt, f"{sid}: task_target 为空"
        assert set(tt) <= TASKS, f"{sid}: 非法任务 {tt}"
        exp = {t: 1 for t in tt}  # expected 从 task_target 派生（红队样本全为目标任务正例）
        # 文本形态
        has_text, has_turns = "text" in s, "turns" in s
        assert has_text != has_turns, f"{sid}: text/turns 必须二选一"
        if has_text:
            assert isinstance(s["text"], str) and s["text"].strip(), f"{sid}: 空 text"
            full_text = s["text"]
        else:
            assert isinstance(s["turns"], list) and len(s["turns"]) >= 3, f"{sid}: 剧本至少 3 轮"
            assert all(isinstance(t, str) and t.strip() for t in s["turns"]), f"{sid}: 空轮"
            full_text = "\n".join(s["turns"])
        assert s["language"] in {"zh", "en", "mix"}, f"{sid}: language 非法"
        assert s.get("notes"), f"{sid}: 缺 notes"
        # 零武器化
        check_zero_weaponization(full_text, sid, errs)
        # 统计（族字母取 id 第二段首字符：rt-a1-01 → A）
        fam = s["id"].split("-")[1][0].upper()
        fam_count[fam] = fam_count.get(fam, 0) + 1
        lang_count[s["language"]] = lang_count.get(s["language"], 0) + 1
        for t in tt:
            task_count[t] = task_count.get(t, 0) + 1

    # B 族编码可解码性
    by_id = {s["id"]: s for s in samples}
    for sid, decode in ENCODING_CHECKS.items():
        s = by_id[sid]
        try:
            plain = decode(extract_payload_text(s["text"]))
            anchors = DECODE_ANCHORS[sid]
            for a in anchors:
                assert a.lower() in plain.lower(), f"{sid}: 解码缺锚 '{a}'，解码结果: {plain[:80]}"
        except Exception as e:  # noqa: BLE001
            errs.append(f"{sid}: 编码自检失败: {e}")

    # 族规模断言
    expect_fam = {"A": 40, "B": 30, "C": 40, "D": 30, "E": 20, "F": 10}
    for fam, n in expect_fam.items():
        assert fam_count.get(fam, 0) == n, f"族 {fam} 数量 {fam_count.get(fam, 0)} != {n}"
    assert len(samples) == 170, f"总数 {len(samples)} != 170"
    # T4 覆盖断言
    assert task_count.get("T4", 0) >= 10, f"T4 覆盖不足: {task_count.get('T4', 0)}"

    # 零宽/同形字符样本显式存在（B4 族结构检查）
    b4 = [s for s in samples if s["attack_family"] == "B4-unicode-obfuscation"]
    assert len(b4) == 5, "B4 族数量"
    has_zwsp = any("\u200b" in s["text"] for s in b4)
    has_cyr = any("\u0435" in s["text"] for s in b4)
    assert has_zwsp and has_cyr, "B4 缺零宽或西里尔样本"

    if errs:
        print("校验失败：")
        for e in errs:
            print(" -", e)
        sys.exit(1)

    out_dir = Path("reports/m6/redteam")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "redteam-v1.jsonl"
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for s in samples:
            row = {
                "id": s["id"], "attack_family": s["attack_family"],
                "task_target": s["task_target"], "language": s["language"],
                "expected": {t: 1 for t in s["task_target"]}, "notes": s["notes"],
            }
            if "text" in s:
                row["text"] = s["text"]
            else:
                row["turns"] = s["turns"]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    total_chars = sum(len(s.get("text", "")) or sum(len(t) for t in s["turns"]) for s in samples)
    print(f"OK redteam-v1.jsonl: {len(samples)} 条 -> {out_path}")
    print(f"族分布: {dict(sorted(fam_count.items()))}")
    print(f"任务目标分布: {dict(sorted(task_count.items()))}")
    print(f"语言分布: {dict(sorted(lang_count.items()))}")
    print(f"总字符数: {total_chars}")
    if warns:
        for w in warns:
            print("WARN:", w)


if __name__ == "__main__":
    main()
