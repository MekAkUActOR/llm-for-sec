# -*- coding: utf-8 -*-
"""M5A-R3 训练配置生成 + 机器 diff 断言（纯 CPU）。

生成：configs/m5a-dpo-r3.yaml = configs/m5a-dpo-r2.yaml 字节级复制，仅
  ① 文件头部前置 12 行 r3 标识注释块（纯注释）
  ② 三行功能行替换（dataset_dir / dataset / output_dir → r3）
其余字节恒等（含继承的 r2/r1 注释块，历史语境保留——二轮先例）。

断言（reports/logs/m5a-dpo-r3-config-diff*.log）：
  - 非注释非空行 diff **恰 3 行**（dataset_dir / dataset / output_dir）
  - 其余全部非注释行（HP 面：sigmoid × 300 步 / lr 2.0e-6 / β 0.1 / cutoff 1024 /
    batch 1×16 / cosine + warmup 20 / save_steps 50 / save_total_limit 20 / bf16 /
    adamw_bnb_8bit / 起点 soup-needlefix-a050 等）逐行恒等 ⇒ DIFF-HP-ZERO=PASS
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = os.path.join(ROOT, "configs", "m5a-dpo-r2.yaml")
R3 = os.path.join(ROOT, "configs", "m5a-dpo-r3.yaml")
DIFF_LOG = os.path.join(ROOT, "reports", "logs", "m5a-dpo-r3-config-diff.log")

if os.path.exists(R3):
    print(f"[FATAL] 目标已存在（防覆写）：{R3}")
    sys.exit(1)

HEADER = """### ═══ M5A-R3 探针（P1.6 三轮 · 备选案 M2b「D 良单旋钮」）：r3 数据 + 一二轮配方零改动 ═══
#
# ★ 本件 = configs/m5a-dpo-r2.yaml 的三轮复制（2026-10-14，reports/p1.6-round2-design.md §七
#   M2b 预注册，配方与预测已冻结）。非注释功能行 diff 仅 3 行：dataset_dir（→ data\\m5a-r3-run）、
#   dataset（→ 三 r3 注册）、output_dir（→ checkpoints\\qwen3-06b-sec-m5a-dpo-r3）；
#   HP 零改动 ✗✓（单变量在数据侧）。三轮数据实况：m4 base 28,842 + p16-r3 5,616
#   （良 2,736 : 恶 2,880 = 48.7 : 51.3；A 1,500 原样全量、D 放行 240→96 确定性子选
#   seed=20261014m2b；B/C/E/F/D恶 逐字节不动；与一轮唯一差异 = D 良子选）= 34,458 行；
#   全 epoch = 2,154 步；校准对占比 16.3%（300 步 × batch 16 可见 ≈782 行，σ≈26）。
#   r3 全 sha / 行级断言 / 门禁时序（三轮不跑全 checker，快检替代）见
#   data/dpo/p16-calibration-r3/manifest.json + reports/p1.6-round3-build.md。
#   ⚠ 下方继承的 r2/r1 注释块为历史语境（其中 34,058 / 5,216 / 2,129 步 等 r2 数值与
#   34,602 / 5,760 / 2,163 步 等 r1 数值均不再适用三轮，以本节为准）。
#
"""

REPL = [
    (b"dataset_dir: J:\\Projects\\llm_for_sec\\data\\m5a-r2-run",
     b"dataset_dir: J:\\Projects\\llm_for_sec\\data\\m5a-r3-run"),
    (b"dataset: sec_dpo_m5a_r2_base_m4capfix,sec_dpo_m5a_r2_p16_benign,sec_dpo_m5a_r2_p16_malicious",
     b"dataset: sec_dpo_m5a_r3_base_m4capfix,sec_dpo_m5a_r3_p16_benign,sec_dpo_m5a_r3_p16_malicious"),
    (b"output_dir: J:\\Projects\\llm_for_sec\\checkpoints\\qwen3-06b-sec-m5a-dpo-r2",
     b"output_dir: J:\\Projects\\llm_for_sec\\checkpoints\\qwen3-06b-sec-m5a-dpo-r3"),
]

raw = open(R2, "rb").read()
assert raw.count(b"\r\n") == 0, "r2 配置非 LF（形态意外）"
for old, new in REPL:
    if raw.count(old) != 1:
        print(f"[FATAL] 替换源非唯一（{raw.count(old)} 处）：{old!r}")
        sys.exit(1)
    raw = raw.replace(old, new)
with open(R3, "wb") as f:
    f.write(HEADER.encode("utf-8") + raw)
print(f"[WRITE] configs/m5a-dpo-r3.yaml（r2 字节级复制 + 12 行 r3 注释头 + 3 行功能替换）")

# ---- 机器 diff 断言 ----
def functional_lines(path):
    out = []
    for ln in open(path, "rb").read().split(b"\n"):
        s = ln.strip()
        if s and not s.startswith(b"#"):
            out.append(ln.rstrip(b"\r"))
    return out


l2, l3 = functional_lines(R2), functional_lines(R3)
diff = [(a, b) for a, b in zip(l2, l3) if a != b]
n_tail = len(l3) - len(l2)
hdr = []
hdr.append(f"r2 功能行数 = {len(l2)} · r3 功能行数 = {len(l3)}（差 = {n_tail}，预期 0）")
hdr.append(f"逐位不等行数 = {len(diff)}（预期 3）")
for a, b in diff:
    hdr.append(f"  - {a.decode('utf-8')}")
    hdr.append(f"  + {b.decode('utf-8')}")
keys = sorted(b.split(b":")[0].decode() for _, b in diff)
ok = (len(l2) == len(l3) and len(diff) == 3 and keys == ["dataset", "dataset_dir", "output_dir"])
hdr.append(f"变更键 = {keys}（预期 ['dataset', 'dataset_dir', 'output_dir']）")
hdr.append("其余非注释行（HP 面 25 行：sigmoid × 300 步 / lr 2.0e-6 / pref_beta 0.1 / cutoff 1024 /")
hdr.append("batch 1×16 / cosine + warmup 20 / save_steps 50 / save_total_limit 20 / bf16 / adamw_bnb_8bit /")
hdr.append("起点 soup-needlefix-a050 等）逐行恒等 ⇒ HP 零改动")
hdr.append("DIFF-HP-ZERO=PASS" if ok else "DIFF-HP-ZERO=FAIL")
txt = "\n".join(hdr) + "\n"
print(txt)
with open(DIFF_LOG, "wb") as f:
    f.write(txt.encode("utf-8"))
if not ok:
    sys.exit(1)
