"""M1.5 知识注入训练集组装（C2 知识层 ×3 epoch + 防遗忘回放 ~27M）。

M1.5 = 短针（knowledge injection）：在 C1-full 最终模型上以低 lr（2e-5）注入
C2 知识层（对齐/LLM 安全、隐私工程、恶意代码分析、内容审核文献与知识库），
预计 ~80 步 ≈ 1.5h（configs/m15.yaml）。

组成（manifest est_tokens 为准，全部运行时动态枚举——不硬编码 c2 文件名）：
- C2 知识层 × 3 epoch：manifest 中 files 含 clean/c2_*.jsonl 的全部源
  （当前 12 文件 ≈ 2.87M tokens；b 变体落地后的增量自动纳入）。
  写入顺序：C2 第 1 遍 → 回放 → C2 第 2、3 遍（沿用 build_c1_mix 的
  安全域-回放-安全域夹心模式，训练末段落在知识层上）。
- 防遗忘回放 ~25-30M（2026-09-26 改造，用户选 C 后）：**zhwiki 全文长文**
  （text >= 3000 字符，与 M1.6 恢复语料同标准）确定性子采样——
  md5("m15replay-zh:"+title) % 10000 < 5900（~27M tok，可复算）。
  原方案（enwiki 摘要补集）已废弃：摘要短文是 C1-full 32k 退化的机制元凶，
  M1.6 恢复后回放层必须维持长文档信号；zhwiki 全体在 C1 已训过 = 回放语义
  （防遗忘 + 长程注意力维持），en 遗忘风险低（C1 general_en 实测 -18.0%）。

红线：**绝不读写 sec_c1.jsonl / sec_c1_full.jsonl**；只写 sec_m15.jsonl。

输出：data/lf/sec_m15.jsonl + dataset_info.json 注册 sec_m15（其余条目原样保留）
用法：python scripts/build_m15_mix.py [--min-chars 3000] [--zh-keep 5900]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_c1_mix import CLEAN, ROOT, enwiki_keep  # noqa: E402  复用同键哈希

OUT = ROOT / "data" / "lf" / "sec_m15.jsonl"
DATASET_INFO = ROOT / "data" / "lf" / "dataset_info.json"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"


def c2_sources() -> dict[str, int]:
    """manifest 运行时枚举 C2 源：{相对 clean 的文件名: est_tokens}。

    - files 匹配 clean/c2_*.jsonl（路径分隔符归一化——manifest 中混用 \\ 与 /）；
    - 同一文件被多条目引用时取 est_tokens 最大值（防重复计数）；
    - 清洗文件不存在（b 变体未落地）→ 打印警告跳过。
    """
    by_file: dict[str, int] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        d = json.loads(line)
        for f in d.get("files", []):
            norm = f.replace("\\", "/")
            if "/clean/c2_" in norm and norm.endswith(".jsonl"):
                name = norm.rsplit("/", 1)[-1]
                est = int(d.get("est_tokens", 0))
                by_file[name] = max(by_file.get(name, 0), est)
    out = {}
    for name, est in sorted(by_file.items()):
        if (CLEAN / name).exists():
            out[name] = est
        else:
            print(f"WARN: manifest 列出但文件不存在，跳过：{name}")
    return out


def enwiki_title(line: str) -> str | None:
    try:
        text = json.loads(line)["text"]
        return text.split("\n", 1)[0][len("Wikipedia article: "):]
    except Exception:  # noqa: BLE001
        return None


def replay_keep(line: str, min_chars: int, zh_keep: int) -> bool:
    """回放采样（2026-09-26 改造，用户选 C 后）：zhwiki 全文长文确定性子采样。

    原 enwiki 摘要补集回放已废弃——摘要短文是 32k 退化的元凶（C1-full
    长上下文门禁未过的机制），M1.6 恢复后回放层必须维持长文档信号。
    zhwiki 全体在 C1 已训过 = 回放语义（防遗忘 + 长程注意力维持）。
    过滤：text >= min_chars（真长文）；采样：md5("m15replay-zh:"+title)。
    """
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return False
    text = d.get("text") or ""
    if len(text) < min_chars:
        return False
    title = d.get("title") or text[:64]
    h = int(hashlib.md5(("m15replay-zh:" + title).encode("utf-8"))
            .hexdigest()[:8], 16)
    return h % 10000 < zh_keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-chars", type=int, default=3000,
                    help="回放长文过滤阈值（字符，与 M1.6 同标准）")
    ap.add_argument("--zh-keep", type=int, default=5900,
                    help="zhwiki 长文回放采样万分比（5900 → ~27M tok）")
    args = ap.parse_args()

    c2 = c2_sources()
    if not c2:
        raise SystemExit("manifest 无 C2 源（b 变体未落地？）")
    for f in ("c1_zhwiki_gen.jsonl",):
        if not (CLEAN / f).exists():
            raise SystemExit(f"missing replay file: {f}")

    n_c2 = n_rep = n_zh_total = 0
    rep_chars = 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as out:
        # 1) C2 第一遍（开训即知识层）
        for f in c2:
            with open(CLEAN / f, encoding="utf-8") as g:
                for line in g:
                    out.write(line)
                    n_c2 += 1
        # 2) zhwiki 全文长文回放（2026-09-26 改造：护 M1.6 恢复成果）
        with open(CLEAN / "c1_zhwiki_gen.jsonl", encoding="utf-8") as g:
            for line in g:
                n_zh_total += 1
                if replay_keep(line, args.min_chars, args.zh_keep):
                    out.write(line)
                    n_rep += 1
                    rep_chars += len(json.loads(line).get("text") or "")
        # 3) C2 第二、三遍（训练末段落在知识层）
        for _ in range(2):
            for f in c2:
                with open(CLEAN / f, encoding="utf-8") as g:
                    for line in g:
                        out.write(line)
                        n_c2 += 1

    # --- dataset_info 注册（其余条目原样保留；红线：不动 c1 条目） ---
    info = json.loads(DATASET_INFO.read_text(encoding="utf-8"))
    info["sec_m15"] = {"file_name": "sec_m15.jsonl",
                       "columns": {"prompt": "text"}}
    DATASET_INFO.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")

    # --- 统计 + pyarrow 校验 + est_tokens 汇总（复用 build_c1_mix 校验段） ---
    size_mb = OUT.stat().st_size / 2**20
    print(f"C2 sources (manifest 枚举): {len(c2)} 个文件")
    for f, est in c2.items():
        print(f"  {f:40s} est={est:>10,}")
    print(f"C2 docs (x3): {n_c2}")
    print(f"replay docs: {n_rep}/{n_zh_total} zhwiki 长文(>= {args.min_chars} 字符) "
          f"({n_rep / max(n_zh_total, 1):.2%})")
    print(f"total lines: {n_c2 + n_rep}")
    print(f"file size: {size_mb:.0f} MB")

    import pyarrow.json as paj
    with open(OUT, "rb") as f:
        rows = paj.read_json(f, read_options=paj.ReadOptions(
            block_size=64 << 20)).num_rows
    print(f"pyarrow rows: {rows}")
    assert rows == n_c2 + n_rep, "行数与写入计数不符"

    c2_tok = sum(c2.values())
    rep_tok = int(rep_chars / 1.42)  # zhwiki 实测字符/token 比
    total = 3 * c2_tok + rep_tok
    print(f"C2 est_tokens (unique): {c2_tok:,}  x3 = {3 * c2_tok:,}")
    print(f"replay est: {rep_tok:,} (zhwiki 长文 {rep_chars:,} chars / 1.42)")
    print(f"TOTAL est_tokens: {total:,}  (~{total / 1e6:.0f}M)  "
          f"≈ {total // (32 * 16384)} 步 @bs1×32×16384")


if __name__ == "__main__":
    main()
