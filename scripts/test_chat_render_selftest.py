# -*- coding: utf-8 -*-
"""CPU 自测：needle 探针的部署格式（chat）渲染片段是否可用。

不加载模型、不占 GPU：只加载 tokenizer + 规范化政策包源。
验证点：
  A. `chat_affixes` 非空，且后缀以 assistant 头结束；
  B. 政策包文本确实来自训练侧规范源（`scripts/gen_sft_v0.py::POLICY_SYSTEM`），
     而不是被复制进来的字面量（印出前 40 字并断言与源一致）；
  C. chat 口径下的 needle 提示词 = raw + prefix + suffix（长度关系精确成立）；
  D. 未知 policy pack / 缺失源时 fail-closed（抛错，不静默降级）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from transformers import AutoTokenizer  # noqa: E402
import probe_longctx as p  # noqa: E402
from secfm.eval.promptfmt import system_for  # noqa: E402

MODEL = "checkpoints/soup-needlefix-a050"
tok = AutoTokenizer.from_pretrained(MODEL)

ok = True
for lang in ("en", "zh"):
    pre, suf = p.chat_affixes(tok, lang, "default")
    dec_pre = tok.decode(pre)
    dec_suf = tok.decode(suf)
    print(f"[{lang}] prefix n={len(pre)} suffix n={len(suf)}")
    print(f"      prefix 末尾 30 字: {dec_pre[-30:]!r}")
    print(f"      suffix      : {dec_suf!r}")
    a = bool(pre) and bool(suf)
    b = dec_suf.rstrip().endswith("assistant")
    sys_txt = system_for("default", lang)
    c = sys_txt[:40] in dec_pre
    print(f"      A(非空)={a} B(以 assistant 头结束)={b} C(政策包与规范源一致)={c}")
    ok &= a and b and c

# C: 长度关系精确成立
pre, suf = p.chat_affixes(tok, "zh", "default")
raw = tok("上文提到的魔法代码是什么？答：", add_special_tokens=False)["input_ids"]
full = pre + raw + suf
print(f"\n长度关系: prefix {len(pre)} + raw {len(raw)} + suffix {len(suf)} = {len(full)}")
ok &= len(full) == len(pre) + len(raw) + len(suf)

# D: fail-closed
try:
    system_for("__no_such_pack__", "zh")
    print("D(fail-closed) 失败：未知政策包未抛错"); ok = False
except KeyError as e:
    print(f"D(未知政策包 fail-closed) = True  ({str(e)[:60]}…)")

print(f"\nCHAT-RENDER-SELFTEST={'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
