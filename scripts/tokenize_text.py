"""将文本语料 tokenize 成 .npy(供 pretrain_1b.py --data 使用)。

用法:
  .venv\\Scripts\\python.exe scripts\\tokenize_text.py --input data\\corpus --tokenizer Qwen/Qwen2.5-1.5B --output data\\tokens.npy

支持递归扫描 .txt / .md / .jsonl / .json(.jsonl 每行取 text 或 content 字段)。
文档之间自动插入 EOS(<|endoftext|>)分隔。
流式处理:任意大语料都不会撑爆 32GB 内存。
"""

import argparse
import json
import os
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from transformers import AutoTokenizer


def iter_docs(paths):
    """逐段产出文本:jsonl 按行,txt/md 按 8MB 块流式切分段落。"""
    for path in paths:
        if path.suffix.lower() == ".jsonl":
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        text = obj.get("text") or obj.get("content") or ""
                    except json.JSONDecodeError:
                        text = line
                    if text.strip():
                        yield text
        else:
            buf = ""
            with open(path, encoding="utf-8", errors="ignore") as f:
                while True:
                    chunk = f.read(8 * 2**20)
                    if not chunk:
                        break
                    buf += chunk
                    parts = buf.split("\n\n")
                    buf = parts.pop()
                    for para in parts:
                        if para.strip():
                            yield para
            if buf.strip():
                yield buf


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="语料文件或目录")
    ap.add_argument("--tokenizer", default="Qwen/Qwen2.5-1.5B", help="tokenizer(默认 Qwen2.5,zh+en 均优、无需申请)")
    ap.add_argument("--output", default="data/tokens.npy")
    ap.add_argument("--batch-chars", type=int, default=1_000_000, help="批编码字符数")
    args = ap.parse_args()

    root = Path(args.input)
    if root.is_dir():
        exts = {".txt", ".md", ".jsonl", ".json", ".text"}
        paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in exts and p.is_file())
    else:
        paths = [root]
    if not paths:
        raise SystemExit(f"未找到语料文件:{args.input}")
    print(f"待处理文件数:{len(paths)}")

    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    eos = tok.eos_token_id
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    bin_path = args.output + ".bin"

    state = {"tokens": 0, "docs": 0}

    def flush(batch):
        if not batch:
            return
        encoded = tok(batch, add_special_tokens=False)["input_ids"]
        with open(bin_path, "ab") as f:
            for ids in encoded:
                if eos is not None:
                    ids = ids + [eos]
                f.write(np.asarray(ids, dtype=np.uint32).tobytes())
                state["tokens"] += len(ids)
                state["docs"] += 1

    chars, buf = 0, []
    for doc in iter_docs(paths):
        buf.append(doc)
        chars += len(doc)
        if chars >= args.batch_chars:
            flush(buf)
            buf, chars = [], 0
            print(f"\r  已处理 {state['docs']:,} 文档 / {state['tokens']:,} tokens", end="", flush=True)
    flush(buf)
    print()

    # .bin → .npy(memmap 拷贝,内存占用极低)
    n = state["tokens"]
    npy = np.lib.format.open_memmap(args.output, mode="w+", dtype=np.uint32, shape=(n,))
    with open(bin_path, "rb") as f:
        i = 0
        while True:
            b = f.read(1 << 24)
            if not b:
                break
            chunk = np.frombuffer(b, dtype=np.uint32)
            npy[i : i + len(chunk)] = chunk
            i += len(chunk)
    npy.flush()
    del npy
    os.remove(bin_path)
    print(f"完成:{state['docs']:,} 文档 / {n:,} tokens -> {args.output}")
    print(f"按 seq_len=2048 可组成约 {n // 2048:,} 个训练序列")


if __name__ == "__main__":
    main()
