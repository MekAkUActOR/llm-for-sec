# -*- coding: utf-8 -*-
"""M1.6 长上下文恢复语料组装器（2026-09-26，用户选 C）。

背景：C1-full 32k 门禁未过（en +11.0% / zh +13.1%，needle 32k 深位 1/6）——
机制 = 短文档语料主导（enwiki 摘要 529M）+ cutoff 4096 的长程注意力去训练。
M1.6 = zhwiki 全文长文 @ cutoff 32768 的恢复短跑，本脚本只负责选料。

构成：c1_zhwiki_gen.jsonl（C1 同源 15% 采样，124.3M tokens 池）
  - 过滤：text >= MIN_CHARS 字符（默认 3000 ≈ 2000+ tokens 的真长文）
  - 确定性子采样：md5("m16:"+title) 分值升序取配额（哈希流选行，
    与 build_c1_mix/build_m15_mix 同纪律），目标 ~30M tokens
  - 输出：data/lf/sec_m16.jsonl（一行一文，LF packing:true @ cutoff 32768 自行拼接）

红线：不含任何探针/heldout/C2 素材；zhwiki 全体在 C1 已训过（回放语义，
恢复注意力模式不需要新知识）。复算：同输入文件 + 同参数 → 逐字节一致。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "corpora" / "clean" / "c1_zhwiki_gen.jsonl"
OUT = ROOT / "data" / "lf" / "sec_m16.jsonl"
DS_INFO = ROOT / "data" / "lf" / "dataset_info.json"

CHARS_PER_TOKEN = 1.42  # zhwiki 实测（176.2M chars / 124.3M tokens）


def doc_score(title: str) -> float:
    h = hashlib.md5(("m16:" + title).encode("utf-8")).hexdigest()
    return int(h[:16], 16) / float(1 << 64)  # [0,1) 确定性分值


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-chars", type=int, default=3000)
    ap.add_argument("--target-mtok", type=float, default=30.0)
    args = ap.parse_args()

    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    # 第一遍：过滤 + 统计池
    pool = []  # (score, title, text)
    total_chars = 0
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            text = d.get("text") or ""
            if len(text) < args.min_chars:
                continue
            title = d.get("title") or text[:64]  # 无标题行用正文前缀作哈希键，防分值坍缩
            pool.append((doc_score(title), title, text))
            total_chars += len(text)
    pool.sort(key=lambda x: x[0])  # 分值升序 = 哈希流顺序

    target_chars = int(args.target_mtok * 1e6 * CHARS_PER_TOKEN)
    # 第二遍：按配额截取（分值升序前 K 篇）
    kept, kept_chars = [], 0
    for score, title, text in pool:
        if kept_chars >= target_chars:
            break
        kept.append((title, text))
        kept_chars += len(text)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for title, text in kept:
            f.write(json.dumps({"title": title, "text": text}, ensure_ascii=True) + "\n")

    # 注册（沿既有条目风格；红线：不动其他条目）
    di = json.loads(DS_INFO.read_text(encoding="utf-8"))
    di["sec_m16"] = {"file_name": "sec_m16.jsonl", "columns": {"prompt": "text", "response": None}}
    DS_INFO.write_text(json.dumps(di, ensure_ascii=True, indent=2), encoding="utf-8")

    est_tok = kept_chars / CHARS_PER_TOKEN / 1e6
    print(f"pool: {len(pool)} docs >= {args.min_chars} chars, {total_chars/1e6:.1f}M chars "
          f"(~{total_chars/CHARS_PER_TOKEN/1e6:.1f}M tok)")
    print(f"kept: {len(kept)} docs, {kept_chars/1e6:.1f}M chars (~{est_tok:.1f}M tok)")
    print(f"steps est @cutoff 32768 x bs1 x accum16 (524k tok/step): {int(est_tok*1e6/524288)+1}")
    print(f"-> {OUT}")
    print("registered: sec_m16")


if __name__ == "__main__":
    main()
