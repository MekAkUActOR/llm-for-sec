"""长上下文可用性探针（M1 出口，docs/05 §7）：16k/32k 整段 PPL + needle 检索抽查。

背景：Stage 1 以 packing cutoff 4096 训练，需验证原生 32k 上下文未退化。
达标线：32k 段 PPL 相对 base 不劣化超过 10%（16k 为观察项）；needle 各深度
检索成功率作行为侧信号（无门禁，逐档报告）。

设计要点：
- 长文档装配：从 data/probes/v0.1/general_{en,zh}.jsonl 出发，按文件顺序
  拼装出恰好 16384/32768 token 的文档（确定性，无随机）；PPL 文档要求
  token 数精确等于目标长度（超出部分丢弃并在 meta 中记录）。
- PPL：**单次整段前向**（非滑窗）——32k 整段过 transformer 主干，随后
  lm_head 分块计算 CE（避免 [32k, 152k] logits 整体物化 ~10GB）。
- needle：固定种子抽取 8 位十六进制 magic code，en/zh 各一套句式，在
  haystack 深度 25%/50%/75% 处插入，文末追问，greedy 解码 ≤32 token，
  归一化匹配（大小写/0x 前缀/空白宽松化）。
- 装配与 code 全部运行时确定性生成（固定 seed），base 与 checkpoint
  输入完全一致；报告记录每个文档的构成（来源区间/条目数/截断标记）。

用法：
    python scripts/probe_longctx.py --model <路径> --name <报告名> \
        [--probes data/probes/v0.1] [--lens 16384,32768] [--n-docs 4] \
        [--seed 20260924] [--max-new 32] [--out reports/longctx-<name>.json]
    python scripts/probe_longctx.py --compare <base.json> <other.json>   # 门禁对比
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
# ★★2026-09-30 晚修（严重，阻塞 objective ① 的"部署格式渲染 probe_longctx"）：
#   本文件是**全仓库唯一**没有把 ROOT 插入 sys.path 的脚本（house style 在 221 处出现）。
#   后果：只有 `--prompt-format chat` 会走 chat_affixes()，而它 `from secfm.eval.promptfmt
#   import system_for` ⇒ 按 `python scripts\probe_longctx.py` 方式调用时
#   **ModuleNotFoundError: No module named 'secfm'** ⇒ 长上下文探针的 chat 口径**从未成功运行过**，
#   而 `topup_verdict.py --needle-format chat` 正需要 `longctx-<tag>-chat.json`。
#   证据：reports/logs/nf-eval-needle-soup-a050-chat.log 的 traceback；
#   reports/ 下不存在任何 `longctx-*-chat.json`。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LANG_FILES = {"en": "general_en.jsonl", "zh": "general_zh.jsonl"}
# 2026-09-30 扩容：3 深度 → 8 深度 × 2 独立变体 = 16 次/格（2 lens × 2 lang × 16 = 64 次）。
# 理由（reports/s0-remediation-2026-09-30.md §7 / review §1.3）：12 次的仪器分辨率
# 只能分辨 ~0.75→0.10 级差异；门禁 G3 的口径同步改为**比率制**
# （cur_rate >= max(0.75, base_rate - 0.10)），因此不再依赖固定分母。
DEPTHS = (0.05, 0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.9)
NEEDLE_VARIANTS = 2
NEEDLE_TEMPLATES = {
    "en": "Note: the magic code for this document is {code}. Please remember it.",
    "zh": "注意：本文档的魔法代码是 {code}，请记住它。",
}
QUESTION_TEMPLATES = {
    "en": "\n\nWhat is the magic code mentioned above? Answer:",
    "zh": "\n\n上文提到的魔法代码是什么？答：",
}
HEX_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])")
_SQUEEZE_RE = re.compile(r"[\s:：,，.。'\"`*·\-—–]+")


# ---------------------------------------------------------------- 纯函数 --

def make_code(rng: random.Random) -> str:
    """从已播种的 RNG 生成 8 位小写十六进制 magic code（可复现）。"""
    return f"{rng.getrandbits(32):08x}"


def _strip_0x(s: str) -> str:
    """统一去掉 0x/0X 前缀痕迹并小写（对 code 与输出做同样处理）。"""
    return s.lower().replace("0x", "")


def extract_codes(text: str) -> set[str]:
    """从文本提取候选 8 位十六进制串（去 0x 前缀、小写、要求独立边界）。"""
    return set(HEX_RE.findall(_strip_0x(text)))


def code_in_output(code: str, output: str) -> bool:
    """宽松匹配：输出是否包含该 code（容忍大小写、0x 前缀、空白/标点分隔）。"""
    c = _strip_0x(code)
    if not c:
        return False
    if c in _strip_0x(output):
        return True
    squeezed = _SQUEEZE_RE.sub("", _strip_0x(output))
    return c in squeezed


def needle_position(base_len: int, depth: float) -> int:
    """插入位置：深度 fraction 相对 haystack（base）token 数，边界收敛。"""
    if base_len < 0:
        raise ValueError("base_len 不能为负")
    if not 0.0 <= depth <= 1.0:
        raise ValueError(f"depth 需在 [0,1]：{depth}")
    return min(int(base_len * depth), base_len)


def needle_prompt_target(total_len: int, max_new: int) -> int:
    """needle 提示词总长：为目标长度预留生成余量（防越界 max_position）。"""
    return total_len - max_new - 16


def assemble_doc(token_lists: list[list[int]], target_len: int,
                 start: int = 0) -> tuple[list[int], dict, int]:
    """从 token_lists[start:] 顺序拼装一篇恰好 target_len token 的文档。

    确定性：只依赖输入（顺序消费，无随机）。溢出条目的尾部 token 丢弃，
    记录在 meta.last_entry_truncated / discarded_tail_tokens。
    返回 (ids, meta, next_start)。
    """
    if target_len <= 0:
        raise ValueError(f"target_len 需为正：{target_len}")
    ids: list[int] = []
    first = last = None
    pos = start
    while len(ids) < target_len:
        if pos >= len(token_lists):
            raise ValueError(
                f"token 不足：已收集 {len(ids)}/{target_len}，条目在 {pos} 处耗尽")
        t = token_lists[pos]
        if t:
            if first is None:
                first = pos
            last = pos
            ids.extend(t)
        pos += 1
    overflow = len(ids) - target_len
    meta = {
        "first_entry": first,
        "last_entry": last,
        "n_entries": (last - first + 1) if first is not None else 0,
        "last_entry_truncated": overflow > 0,
        "discarded_tail_tokens": max(overflow, 0),
        "target_len": target_len,
    }
    return ids[:target_len], meta, pos


def assemble_stream(token_lists: list[list[int]],
                    plan: list[tuple[str, int]]) -> dict[str, tuple[list[int], dict]]:
    """按 plan（(键, 目标长度) 列表）在同一 token 流上顺序装配多篇文档。

    各文档条目区间互不重叠（消费游标单调前进），全流程确定性。
    """
    out: dict[str, tuple[list[int], dict]] = {}
    pos = 0
    for key, target_len in plan:
        ids, meta, pos = assemble_doc(token_lists, target_len, pos)
        out[key] = (ids, meta)
    return out


def load_probe_texts(probes_dir: Path, lang: str) -> list[str]:
    """读取探针 jsonl 的 text 字段（保持文件顺序 = 装配顺序的一部分）。"""
    p = probes_dir / LANG_FILES[lang]
    if not p.exists():
        raise SystemExit(f"探针文件不存在：{p}")
    return [json.loads(l)["text"]
            for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def compare_reports(base: dict, other: dict,
                    rise_limit: float = 0.10) -> dict:
    """门禁对比（纯函数）：32k 各语言 PPL 回升 ≤ rise_limit；16k 为观察项。"""
    cells: dict = {}
    verdict = True
    for L, langs in base.get("ppl", {}).items():
        for lang, b in langs.items():
            o = other.get("ppl", {}).get(L, {}).get(lang)
            key = f"{L}/{lang}"
            if not (o and o.get("ppl") and b.get("ppl")):
                cells[key] = {"ok": None, "reason": "missing"}
                if L == "32768":
                    verdict = False  # 门禁单元缺失 = 无法判定，保守判未通过
                continue
            delta = (o["ppl"] - b["ppl"]) / b["ppl"]
            gated = L == "32768"
            ok = (delta <= rise_limit) if gated else None
            if gated and ok is False:
                verdict = False
            cells[key] = {"base_ppl": b["ppl"], "other_ppl": o["ppl"],
                          "delta": delta, "ok": ok,
                          "gate": f"32k 回升 ≤{rise_limit:.0%}" if gated else "观察项"}
    return {"cells": cells, "verdict": verdict}


# ---------------------------------------------------------------- GPU 侧 --

def doc_ppl(model, ids: list[int], chunk: int = 4096) -> tuple[float, int]:
    """单篇长文档 PPL：整段前向过主干（长上下文注意力一次性生效），
    lm_head 与 CE 按块计算（有界显存）。返回 (平均 NLL, 计分 token 数)。"""
    import torch
    import torch.nn.functional as F
    t = torch.tensor([ids], device=model.device)
    with torch.no_grad():
        hidden = model.model(input_ids=t).last_hidden_state[0]  # [T, H]
        total_nll, total_tok = 0.0, 0
        for s in range(0, hidden.shape[0] - 1, chunk):
            e = min(s + chunk, hidden.shape[0] - 1)
            logits = model.lm_head(hidden[s:e]).float()  # [e-s, V]
            tgt = t[0, s + 1:e + 1]
            total_nll += float(F.cross_entropy(logits, tgt, reduction="sum"))
            total_tok += e - s
    return total_nll / total_tok, total_tok


def chat_affixes(tok, lang: str, pack: str | None = None) -> tuple[list[int], list[int]]:
    """部署格式（chat）的前缀/后缀 token 片段。

    ★S0 测量层修复（2026-09-30，目标①"部署格式渲染 probe_longctx"）：
    本探针此前**只有 raw 口径**（直接续写），而 docs/01 §11 规则 1 明定
    "门禁读数产自 raw 口径 ⇒ 不得作为放大依据"。needle 是 MUST-1/SHOULD-2 的仪器，
    因此必须在部署格式下可测。

    为什么用"前缀/后缀 token 片段拼装"而不是"整串 chat 模板后重新分词"：
    本探针需要在 **token 空间**精确控制 haystack 长度（要装配出恰好 32k-token 的
    haystack，并在指定深度插入 needle）。若先解码成文本再套模板重新分词，长度控制
    会因 BPE 边界效应漂移。模板片段由 `<|im_end|>` 等特殊 token 界定，边界效应被
    限制在片段内；规范化渲染源仍取自 `secfm/eval/promptfmt.py::system_for`
    （**动态加载**训练侧 `scripts/gen_sft_v0.py::POLICY_SYSTEM`，取不到即抛错）。
    """
    from secfm.eval.promptfmt import system_for
    sys_part = f"<|im_start|>system\n{system_for(pack, lang)}<|im_end|>\n<|im_start|>user\n"
    tail = "<|im_end|>\n<|im_start|>assistant\n"
    return (tok(sys_part, add_special_tokens=False)["input_ids"],
            tok(tail, add_special_tokens=False)["input_ids"])


def generate_answer(model, tok, prompt_ids: list[int], max_new: int) -> str:
    """greedy 解码 ≤ max_new token，返回生成文本（不含提示词）。"""
    import torch
    t = torch.tensor([prompt_ids], device=model.device)
    with torch.no_grad():
        out = model.generate(
            t, max_new_tokens=max_new, do_sample=False,
            attention_mask=torch.ones_like(t),
            pad_token_id=tok.pad_token_id if tok.pad_token_id is not None
            else tok.eos_token_id)
    return tok.decode(out[0][t.shape[1]:], skip_special_tokens=True)


def run_eval(args) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    probes_dir = ROOT / args.probes
    lens = [int(x) for x in args.lens.split(",")]
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    report: dict = {
        "model": args.model, "name": args.name, "seed": args.seed,
        "lens": lens, "n_docs": args.n_docs, "max_new": args.max_new,
        "prompt_format": args.prompt_format, "system_pack": args.system_pack,
        "needle_prompt_format": args.prompt_format,
        "ppl": {}, "needle": {}, "needle_success": {}, "assembly": {},
    }
    t0 = time.time()

    for lang in ("en", "zh"):
        print(f"[{lang}] 装配长文档 …", flush=True)
        texts = load_probe_texts(probes_dir, lang)
        tls = [tok(t, add_special_tokens=False)["input_ids"] for t in texts]
        tls = [t for t in tls if t]

        # 固定顺序抽取本语言全部 magic code（先于装配，长度可预算）
        rng = random.Random(args.seed)
        # 注意：rng 按 (语言循环顺序, len, depth) 消费；为使两语言间也可复现，
        # 每语言独立重播种，保证 en/zh 的 code 流互不影响模型运行顺序。
        codes: dict[str, str] = {}
        for L in lens:
            for depth in DEPTHS:
                for v in range(args.needle_variants):
                    codes[f"{L}/{depth}#{v}"] = make_code(rng)

        q_ids = tok(QUESTION_TEMPLATES[lang],
                    add_special_tokens=False)["input_ids"]
        needle_ids = {k: tok(NEEDLE_TEMPLATES[lang].format(code=c),
                             add_special_tokens=False)["input_ids"]
                      for k, c in codes.items()}
        max_nlen = max(len(v) for v in needle_ids.values())

        plan: list[tuple[str, int]] = []
        for L in lens:
            for i in range(args.n_docs):
                plan.append((f"ppl-{L}-{i}", L))       # PPL 文档：恰好 L
        for L in lens:                                  # needle haystack
            plan.append((f"needle-{L}",
                         needle_prompt_target(L, args.max_new)
                         - len(q_ids) - max_nlen))
        asm = assemble_stream(tls, plan)

        report["assembly"][lang] = {
            "file": LANG_FILES[lang], "n_probe_entries": len(tls),
            "docs": {k: m for k, (_, m) in asm.items()},
            "codes": codes,
        }

        # --- 长文档 PPL（整段前向） ---
        for L in lens:
            report["ppl"].setdefault(str(L), {})
            nll_sum, tok_sum, per_doc = 0.0, 0, []
            for i in range(args.n_docs):
                ids, _m = asm[f"ppl-{L}-{i}"]
                assert len(ids) == L, f"PPL 文档长度 {len(ids)} != {L}"
                nll, n = doc_ppl(model, ids)
                nll_sum += nll * n
                tok_sum += n
                per_doc.append(round(nll, 4))
                print(f"  ppl {L}/{lang} doc{i}: NLL={nll:.4f}", flush=True)
            ppl = math.exp(nll_sum / tok_sum)
            report["ppl"][str(L)][lang] = {
                "ppl": ppl, "tokens": tok_sum, "docs": args.n_docs,
                "per_doc_nll": per_doc,
            }
            print(f"  => {L}/{lang} PPL={ppl:.3f}", flush=True)

        # --- needle 检索（同一 haystack × 8 档深度 × N 变体） ---
        # 部署格式（chat）下，needle 也走规范化渲染：system(政策包) + user(haystack+问句) + assistant 头
        prefix_ids, suffix_ids = ([], [])
        if args.prompt_format == "chat":
            prefix_ids, suffix_ids = chat_affixes(tok, lang, args.system_pack)
        for L in lens:
            report["needle"].setdefault(str(L), {})
            report["needle"][str(L)].setdefault(lang, {})
            base_ids, _m = asm[f"needle-{L}"]
            succ = 0
            trials = 0
            for depth in DEPTHS:
                for v in range(args.needle_variants):
                    key = f"{L}/{depth}#{v}"
                    code = codes[key]
                    n_ids = needle_ids[key]
                    pos = needle_position(len(base_ids), depth)
                    prompt = (prefix_ids + base_ids[:pos] + n_ids
                              + base_ids[pos:] + q_ids + suffix_ids)
                    gen = generate_answer(model, tok, prompt, args.max_new)
                    ok = code_in_output(code, gen)
                    succ += int(ok)
                    trials += 1
                    report["needle"][str(L)][lang][f"{depth}#{v}"] = {
                        "code": code, "success": ok,
                        "insert_pos": pos, "prompt_len": len(prompt),
                        "generated": gen[:120],
                    }
                    print(f"  needle {L}/{lang} d={depth}#{v}: "
                          f"{'命中' if ok else '未命中'} (code={code})", flush=True)
            report["needle_success"].setdefault(str(L), {})
            report["needle_success"][str(L)][lang] = succ / trials
            report.setdefault("needle_counts", {}).setdefault(str(L), {})[lang] = {
                "k": succ, "n": trials}
            report["needle_trials_per_cell"] = trials

    report["elapsed_s"] = round(time.time() - t0, 1)
    out = Path(args.out) if args.out else ROOT / "reports" / f"longctx-{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"report -> {out}")


def run_compare(args) -> None:
    base = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
    other = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
    res = compare_reports(base, other)
    print(f"base: {base.get('model')}\nother: {other.get('model')}\n")
    for key, c in res["cells"].items():
        if c.get("ok") is None and c.get("reason") == "missing":
            print(f"  {key:12} [缺失]")
        else:
            v = "PASS" if c["ok"] else "FAIL" if c["ok"] is not None else "观察"
            print(f"  {key:12} {c['base_ppl']:>10.3f} -> "
                  f"{c['other_ppl']:>10.3f}  {c['delta']:+.1%}  "
                  f"[{v}] {c['gate']}")
    print(f"\n32k 门禁判定: {'通过 ✓' if res['verdict'] else '未通过 ✗'}")
    sys.exit(0 if res["verdict"] else 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="长上下文可用性探针")
    ap.add_argument("--model", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--probes", default="data/probes/v0.1")
    ap.add_argument("--lens", default="16384,32768")
    ap.add_argument("--n-docs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260924)
    ap.add_argument("--max-new", type=int, default=32)
    ap.add_argument("--needle-variants", type=int, default=NEEDLE_VARIANTS,
                    help="每深度独立变体数（默认 2；每格试验数 = 深度数 × 变体数）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--prompt-format", default="raw", choices=("raw", "chat"),
                    help="★部署格式口径。raw=历史行为（直接续写）；chat=规范化 chat 模板"
                         "（system 政策包 + user + assistant 头），与训练/部署同分布。"
                         "门禁读数必须用 chat（docs/01 §11 规则 1）")
    ap.add_argument("--system-pack", default="default",
                    help="chat 口径下的政策包名（scripts/gen_sft_v0.py::POLICY_SYSTEM）")
    ap.add_argument("--compare", nargs=2, metavar=("BASE", "OTHER"),
                    help="门禁对比模式：两份 longctx 报告")
    args = ap.parse_args()

    if args.compare:
        run_compare(args)
        return
    if not (args.model and args.name):
        ap.error("--model 与 --name 必填（或使用 --compare）")
    run_eval(args)


if __name__ == "__main__":
    main()
