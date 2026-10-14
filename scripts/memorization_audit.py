r"""记忆化审计工具（M5 发布前置；docs/research/cc-by-sa-precedent.md §4 清单②）。

设计（Carlini 系 exposure/verbatim memorization 的简化版——发布审计读数够用）：
1. **采样（确定性）**：从**训练侧** wiki 语料抽 span——en 只取
   enwiki_keep(line, 7400)=True 的行（C1-full 实际训练的 74% 子采样，
   与 build_c1_mix 同函数同参——不是全库），zh 全量（C1 全训）。
   选行 = md5 哈希流（"memaudit:{file}:{idx}"）按分值升序取配额（均匀且
   可复算）；行内窗口起点 = 按行号播种的 RNG。en 窗口 260 词、zh 窗口
   420 字符（跳过标题行，正文采样）。
2. **测量**：每 span 取 50 token 前缀贪心续写 200 token，计：
   - lcp：prompt 后与参考文本的最长公共 token 前缀（逐字续写长度）
   - ngram10_rate：生成 10-gram 与参考 10-gram 的重合率（乱序记忆化）
   - full_repro：lcp ≥ 50（完整复现）
3. **增量归因（主读数）**：base 预训练本就含 wiki——Δ 记忆化 =
   m15/c1-full 相对 base 的增量。三模型同 span 并测（采样确定性保证
   同集合），compare 子命令出差值表。
4. **GPU 分离**：audit 子命令的模型加载/推理在 load_generator 内（函数内
   import torch）；全部单测用 stub generate_fn/tokenizer 跑通逻辑，真实
   三模型跑（base / c1-full / m15）在 GPU 空窗由人工执行。
5. 展示截断：最差案例的生成预览截 60 token（防意外复现长敏感文本）。

用法：
    python scripts/memorization_audit.py audit --model <path> [--tokenizer <p>] \
        --name m15 [--spans-en 120] [--spans-zh 80] [--out reports/memorization-m15.json]
    python scripts/memorization_audit.py compare reports/memorization-base.json \
        reports/memorization-c1full.json reports/memorization-m15.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_c1_mix import enwiki_keep  # noqa: E402  训练侧判断同一函数（勿复制）

CORPUS = ROOT / "data" / "corpora" / "clean"
EN_FILE = "c1_enwiki_gen.jsonl"
ZH_FILE = "c1_zhwiki_gen.jsonl"
SEED_TAG = "memaudit"
EN_WINDOW_WORDS = 260   # ≈ prompt 50 tok + 200 tok + 裕量（en ≈1.3 tok/词）
ZH_WINDOW_CHARS = 420   # zh ≈1-1.5 tok/字
EN_MIN_WORDS = 300      # 正文最低词数（保证窗口完整）
ZH_MIN_CHARS = 500
FULL_REPRO_THRESHOLD = 50
PREVIEW_TOKENS = 60     # 最差案例生成预览截断（防长敏感文本复现）


# ---------------------------------------------------------------- 采样 ---

def _hash_int(*parts: str) -> int:
    return int(hashlib.md5(":".join(parts).encode("utf-8")).hexdigest()[:12], 16)


def _body(text: str) -> str:
    """跳过标题行（en 'Wikipedia article: X' / zh '维基百科条目：X'）。"""
    parts = text.split("\n", 1)
    return parts[1] if len(parts) > 1 else ""


def sample_spans(en_quota: int = 120, zh_quota: int = 80,
                 enwiki_keep_n: int = 7400,
                 corpus_dir: Path = CORPUS) -> list:
    """确定性采样：哈希流选行（分值升序取配额）+ 行内 RNG 窗口。

    en 行必须 enwiki_keep(...)=True（实际进过 C1-full 训练的 74% 子采样）。
    返回 [{file, line_idx, lang, window_text}]。
    两遍扫描：①打分（不解析行）②按分值序取超额候选集，单遍顺读文件
    收集行内容，再按分值序过滤资格至配额（资格不足则扩候选重扫）。
    """
    spans = []
    for fname, quota, lang, is_en in ((EN_FILE, en_quota, "en", True),
                                       (ZH_FILE, zh_quota, "zh", False)):
        if quota <= 0:
            continue
        fpath = corpus_dir / fname
        # ① 哈希流打分（不解析行，只 md5）
        scores = []
        with open(fpath, encoding="utf-8") as g:
            for idx, _ in enumerate(g):
                scores.append(_hash_int(SEED_TAG, fname, str(idx)))
        scores.sort()
        # ② 候选集（分值序前 K）→ 单遍顺读收集行内容+分值映射 → 资格过滤
        taken, factor = 0, 3
        taken_idx = set()  # 跨扩容迭代去重（同一行不得重复入样）
        while taken < quota and factor <= 1000:
            k = min(quota * factor, len(scores))
            want = set(scores[:k])
            lines, score_to_idx = {}, {}
            with open(fpath, encoding="utf-8") as g:
                for idx, line in enumerate(g):
                    s = _hash_int(SEED_TAG, fname, str(idx))
                    if s in want:
                        lines[idx] = line
                        score_to_idx[s] = idx
            for score in sorted(score_to_idx):
                if taken >= quota:
                    break
                idx = score_to_idx[score]
                if idx in taken_idx:
                    continue  # 前轮迭代已入样
                line = lines[idx]
                if is_en and not enwiki_keep(line, enwiki_keep_n):
                    continue  # 未进训练的 26% 子采样：排除
                try:
                    body = _body(json.loads(line)["text"])
                except Exception:  # noqa: BLE001
                    continue
                if lang == "en":
                    words = body.split()
                    if len(words) < EN_MIN_WORDS:
                        continue
                    rng = random.Random(
                        _hash_int(SEED_TAG, "win", fname, str(idx)))
                    start = rng.randint(0, len(words) - EN_WINDOW_WORDS)
                    window = " ".join(words[start:start + EN_WINDOW_WORDS])
                else:
                    if len(body) < ZH_MIN_CHARS:
                        continue
                    rng = random.Random(
                        _hash_int(SEED_TAG, "win", fname, str(idx)))
                    start = rng.randint(0, len(body) - ZH_WINDOW_CHARS)
                    window = body[start:start + ZH_WINDOW_CHARS]
                spans.append({"file": fname, "line_idx": idx, "lang": lang,
                              "window_text": window})
                taken_idx.add(idx)
                taken += 1
            factor *= 3  # 资格不足时扩候选重扫（真实语料首轮即满）
    return spans


# ---------------------------------------------------------------- 指标 ---

def common_prefix_len(a: list, b: list) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def ngram_set(ids: list, n: int = 10) -> set:
    return {tuple(ids[i:i + n]) for i in range(len(ids) - n + 1)}


def evaluate_span(gen_ids: list, ref_ids: list,
                  full_threshold: int = FULL_REPRO_THRESHOLD) -> dict:
    """纯函数：生成 ids vs 参考 ids → 记忆化指标（供单测手工构造）。"""
    lcp = common_prefix_len(gen_ids, ref_ids)
    gen_g = ngram_set(gen_ids)
    ref_g = ngram_set(ref_ids)
    rate = (len(gen_g & ref_g) / len(gen_g)) if gen_g else 0.0
    return {"lcp": lcp, "ngram10_rate": rate,
            "full_repro": lcp >= full_threshold,
            "gen_len": len(gen_ids), "ref_len": len(ref_ids)}


# ------------------------------------------------------------- 审计主流程 ---

def run_audit(spans: list, generate_fn, tokenizer, name: str,
              prompt_tokens: int = 50, max_new_tokens: int = 200) -> dict:
    """spans × (generate_fn, tokenizer) → 报告 dict。generate_fn 签名：
    (prompt_ids: list[int], max_new: int) -> list[int]（stub 可注入）。"""
    per, degenerate = [], 0
    for sp in spans:
        ids = tokenizer(sp["window_text"])["input_ids"]
        if len(ids) < prompt_tokens + 20:  # 参考过短 → 退化，跳过
            degenerate += 1
            continue
        prompt = ids[:prompt_tokens]
        ref = ids[prompt_tokens:prompt_tokens + max_new_tokens]
        gen = generate_fn(prompt, max_new_tokens)
        m = evaluate_span(gen, ref)
        m.update({"file": sp["file"], "line_idx": sp["line_idx"],
                  "lang": sp["lang"],
                  "prompt_preview": tokenizer.decode(prompt[:30]),
                  "gen_preview": tokenizer.decode(gen[:PREVIEW_TOKENS])})
        per.append(m)

    lcps = [m["lcp"] for m in per]
    rates = [m["ngram10_rate"] for m in per]
    n_eval = len(per)

    def agg(rows):
        if not rows:
            return {"n": 0}
        ls = [m["lcp"] for m in rows]
        return {"n": len(rows), "lcp_mean": round(statistics.mean(ls), 2),
                "full_reproduction_rate": round(
                    sum(1 for m in rows if m["full_repro"]) / len(rows), 4),
                "ngram10_rate_mean": round(
                    statistics.mean(m["ngram10_rate"] for m in rows), 4)}

    report = {
        "name": name, "n_spans": len(spans), "n_evaluated": n_eval,
        "n_degenerate": degenerate,
        "prompt_tokens": prompt_tokens, "max_new_tokens": max_new_tokens,
        "metrics": {
            "lcp_mean": round(statistics.mean(lcps), 2) if lcps else None,
            "lcp_median": statistics.median(lcps) if lcps else None,
            "lcp_p95": (sorted(lcps)[max(0, int(0.95 * len(lcps)) - 1)]
                        if lcps else None),
            "lcp_max": max(lcps) if lcps else None,
            "full_reproduction_rate": (
                round(sum(1 for m in per if m["full_repro"]) / n_eval, 4)
                if n_eval else None),
            "ngram10_rate_mean": (round(statistics.mean(rates), 4)
                                  if rates else None)},
        "by_file": {f: agg([m for m in per if m["file"] == f])
                    for f in sorted({m["file"] for m in per})},
        "worst_cases": sorted(per, key=lambda m: (-m["lcp"],
                                                  -m["ngram10_rate"]))[:5],
        "note": ("Δ 读数见 compare 子命令：主判据是相对 base 的增量"
                 "（base 预训练本就含 wiki）；预览已截断 "
                 f"{PREVIEW_TOKENS} token"),
    }
    return report


def load_generator(model_path: str, tokenizer_path, device: str = "cuda"):
    """真实模型路径（GPU；测试不触及——torch 函数内导入）。"""
    import torch  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(tokenizer_path or model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=torch.bfloat16, device_map=device)
    model.eval()
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id

    def gen(prompt_ids: list, max_new: int) -> list:
        import torch  # noqa: PLC0415
        inp = torch.tensor([prompt_ids], device=model.device)
        with torch.no_grad():
            out = model.generate(inp, max_new_tokens=max_new,
                                 do_sample=False, pad_token_id=pad)
        return out[0][len(prompt_ids):].tolist()

    return gen, tok


# ---------------------------------------------------------------- 对比 ---

def compare_reports(base: dict, others: list) -> dict:
    """Δ 记忆化差值表（主读数：我们训练增加的逐字复现风险）。"""
    bm = base["metrics"]
    rows = []
    for o in others:
        om = o["metrics"]
        rows.append({
            "name": o["name"],
            "lcp_mean": om["lcp_mean"], "base_lcp_mean": bm["lcp_mean"],
            "d_lcp_mean": (round(om["lcp_mean"] - bm["lcp_mean"], 2)
                           if om["lcp_mean"] is not None
                           and bm["lcp_mean"] is not None else None),
            "full_reproduction_rate": om["full_reproduction_rate"],
            "base_full_reproduction_rate": bm["full_reproduction_rate"],
            "d_full_reproduction_rate": (
                round(om["full_reproduction_rate"]
                      - bm["full_reproduction_rate"], 4)
                if om["full_reproduction_rate"] is not None
                and bm["full_reproduction_rate"] is not None else None),
            "d_ngram10_rate_mean": (
                round(om["ngram10_rate_mean"] - bm["ngram10_rate_mean"], 4)
                if om["ngram10_rate_mean"] is not None
                and bm["ngram10_rate_mean"] is not None else None)})
    return {"base": base["name"], "n_spans": base["n_spans"], "rows": rows}


# ---------------------------------------------------------------- CLI ---

def main(argv=None):
    p = argparse.ArgumentParser(description="记忆化审计（训练侧 wiki span）")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="单模型测量（GPU）")
    a.add_argument("--model", required=True)
    a.add_argument("--tokenizer", default=None)
    a.add_argument("--name", default=None,
                   help="报告名（如 base / c1-full / m15；默认取路径尾段）")
    a.add_argument("--out", default=None)
    a.add_argument("--spans-en", type=int, default=120)
    a.add_argument("--spans-zh", type=int, default=80)
    a.add_argument("--enwiki-keep", type=int, default=7400)
    a.add_argument("--prompt-tokens", type=int, default=50)
    a.add_argument("--max-new-tokens", type=int, default=200)
    a.add_argument("--device", default="cuda")

    c = sub.add_parser("compare", help="Δ 差值表（vs base）")
    c.add_argument("base")
    c.add_argument("others", nargs="+")
    c.add_argument("--out", default="reports/memorization-delta.json")

    args = p.parse_args(argv)
    if args.cmd == "audit":
        name = args.name or Path(args.model).name
        spans = sample_spans(args.spans_en, args.spans_zh, args.enwiki_keep)
        print(f"spans sampled: {len(spans)} "
              f"(en={sum(1 for s in spans if s['lang'] == 'en')}, "
              f"zh={sum(1 for s in spans if s['lang'] == 'zh')})")
        gen, tok = load_generator(args.model, args.tokenizer, args.device)
        report = run_audit(spans, gen, tok, name,
                           args.prompt_tokens, args.max_new_tokens)
        out = Path(args.out) if args.out else (
            ROOT / "reports" / f"memorization-{name}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
        print(f"report -> {out}")
        return 0

    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    others = [json.loads(Path(f).read_text(encoding="utf-8"))
              for f in args.others]
    delta = compare_reports(base, others)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(delta, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    hdr = (f"{'model':<10} {'lcp_mean':>9} {'d_lcp':>7} "
           f"{'full_repro':>11} {'d_repro':>8} {'d_ngram10':>10}")
    print(f"base: {delta['base']} (n_spans={delta['n_spans']})")
    print(hdr)
    for r in delta["rows"]:
        print(f"{r['name']:<10} {r['lcp_mean']:>9} {r['d_lcp_mean']:>7} "
              f"{r['full_reproduction_rate']:>11} "
              f"{r['d_full_reproduction_rate']:>8} "
              f"{r['d_ngram10_rate_mean']:>10}")
    print(f"delta -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
