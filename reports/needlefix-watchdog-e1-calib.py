#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""看门狗标定脚本 —— 把 needlefix-e1 的早停阈值从"推算"变成"标定"。

背景（reports/needlefix-preregistration.md §3 早停规则 1 + §7.3 修订）：
  原规则是"契约 eval_loss 连续两次比基线上升 >10%"。但本 run 首读基数极小
  （step25 = 0.05459），+10% 只有 +0.0055 nats，比该通道自身的正常运动尺度
  （实测单次 0.011~0.032 nats）还小 ⇒ 相对阈值过灵敏，会误杀。
  父代理裁定改用合取口径：连续两次 >= 滚动最小值 + 0.05 nats 且相对涨幅 >= +10%。
  其中 0.05 是**推算**的，本脚本用**已知档**在同一台仪器上把它标定出来。

仪器（与训练中每 25 步的 eval 完全同口径，docs/01 §11.8"同仪器"）：
  eval_dataset = sec_sft_v0_eval300  (data/lf/sft_v0_eval300.jsonl, 300 行留出集)
  template = qwen3_nothink, cutoff_len = 4096, per_device_eval_batch_size = 1, bf16 = true
  走 llamafactory 自身的 eval 路径（不是自己手搓 loss），保证口径与训练期读数可比。

已知档：
  (a) checkpoints/qwen3-06b-sec-m2-calib        —— 已知健康（契约保留 84/168），低值锚
  (b) checkpoints/qwen3-06b-sec-m3base-topup-e1 —— 已知坏（契约保留 8/168），高值锚
  (c) checkpoints/qwen3-06b-sec-m2calib-needlefix-e1 —— 本 run 终档（若已存在则一并测）

纪律：
  * 严格串行 —— 先确认无训练进程、显存 < 1024 MiB，否则直接退出（docs/01 §11.7 规则 5）。
  * 只读模型；输出写进 %TEMP%，不碰 checkpoints/ 与既有 reports/。
  * 不要用 `python -c` 内联（PowerShell 会破坏引号）；这就是那个 .py 文件。

用法：
  J:\Projects\llm_for_sec\.venv\Scripts\python.exe reports\needlefix-watchdog-e1-calib.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CLI = ROOT / ".venv" / "Scripts" / "llamafactory-cli.exe"
DATASET_DIR = ROOT / "data" / "lf"
EVAL_DATASET = "sec_sft_v0_eval300"

CANDIDATES = [
    ("m2-calib__known-healthy", ROOT / "checkpoints" / "qwen3-06b-sec-m2-calib"),
    ("m3base-topup-e1__known-broken", ROOT / "checkpoints" / "qwen3-06b-sec-m3base-topup-e1"),
    ("needlefix-e1__this-run-final", ROOT / "checkpoints" / "qwen3-06b-sec-m2calib-needlefix-e1"),
]

YAML_TMPL = """\
### 看门狗标定用（临时生成；eval-only，不训练、不保存模型）
model_name_or_path: {model}
stage: sft
do_train: false
do_eval: true
finetuning_type: full
template: qwen3_nothink

dataset_dir: {dataset_dir}
eval_dataset: {eval_dataset}
cutoff_len: 4096
overwrite_cache: true
preprocessing_num_workers: 4
per_device_eval_batch_size: 1

bf16: true
output_dir: {outdir}
report_to: none
plot_loss: false
save_strategy: "no"
"""


def vram_used_mib() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30,
        )
        return int(out.stdout.strip().splitlines()[0])
    except Exception as exc:  # noqa: BLE001
        print(f"[calib] WARN 无法读显存: {exc}")
        return None


def training_procs() -> list[str]:
    """返回仍在跑 llamafactory/train 的 python 进程描述（应为空）。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'train ' } | "
             "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=60,
        )
        return [ln for ln in out.stdout.splitlines() if ln.strip()]
    except Exception as exc:  # noqa: BLE001
        print(f"[calib] WARN 无法枚举进程: {exc}")
        return []


def preflight() -> bool:
    ok = True
    procs = training_procs()
    if procs:
        ok = False
        print("[calib] ✗ 仍有疑似训练的 python 进程，拒绝并发（§11.7 规则 5）：")
        for p in procs:
            print("        " + p[:160])
    used = vram_used_mib()
    print(f"[calib] 显存占用 = {used} MiB（要求 < 1024）")
    if used is not None and used >= 1024:
        ok = False
        print("[calib] ✗ 显存未清空，拒绝执行。")
    return ok


def run_one(label: str, model: Path, workdir: Path) -> dict:
    log = workdir / f"{label}.log"
    outdir = workdir / f"out_{label}"
    outdir.mkdir(parents=True, exist_ok=True)
    cfg = workdir / f"{label}.yaml"
    cfg.write_text(
        YAML_TMPL.format(model=model, dataset_dir=DATASET_DIR,
                         eval_dataset=EVAL_DATASET, outdir=outdir),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.update({
        "HF_HOME": str(ROOT / ".cache" / "huggingface"),
        "TORCH_HOME": str(ROOT / ".cache" / "torch"),
        "HF_HUB_OFFLINE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
    })

    print(f"[calib] ▶ {label}: {model}")
    t0 = time.time()
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        try:
            rc = subprocess.call([str(CLI), "train", str(cfg)],
                                 stdout=fh, stderr=subprocess.STDOUT,
                                 env=env, cwd=str(ROOT))
        except Exception as exc:  # noqa: BLE001
            print(f"[calib] ✗ 启动失败: {exc}")
            rc = -999
    dt = time.time() - t0

    text = log.read_text(encoding="utf-8", errors="replace")
    # 两种格式都要认（2026-10-06 实测教训）：
    #   (1) do_train=True 的训练内 eval  ->  {'eval_loss': '0.0055', 'eval_runtime': '11.8', ...}
    #   (2) do_train=False 的纯 eval     ->  ***** eval metrics ***** 表格：
    #                                        eval_loss                   =     0.0027
    #   只认 (1) 会把纯 eval 的三档全读成 None（本次实际踩到，读数其实一直在日志里）。
    m = re.findall(r"\{\s*'eval_loss'\s*:\s*'?([0-9.eE+-]+)'?", text)
    if not m:
        m = re.findall(r"^\s*eval_loss\s*=\s*([0-9.eE+-]+)\s*$", text, re.M)
    runtime = re.findall(r"'eval_runtime'\s*:\s*'?([0-9.eE+-]+)'?", text)
    if not runtime:
        runtime = re.findall(r"^\s*eval_runtime\s*=\s*([0-9.]+)\s*$", text, re.M)
    oom = bool(re.search(r"OutOfMemory|out of memory|Traceback", text))
    res = {
        "label": label,
        "model": str(model),
        "exit_code": rc,
        "eval_loss": float(m[-1]) if m else None,
        "eval_runtime_s": float(runtime[-1]) if runtime else None,
        "oom_or_traceback": oom,
        "wall_s": round(dt, 1),
        "log": str(log),
    }
    print(f"[calib]   → eval_loss={res['eval_loss']}  wall={res['wall_s']}s  rc={rc}  oom={oom}")
    return res


def main() -> int:
    print("[calib] === needlefix-e1 契约门禁阈值标定 ===")
    if not preflight():
        print("[calib] 前置未满足，退出（不改动任何东西）。")
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="wd_e1_calib_"))
    print(f"[calib] 工作目录（临时）= {workdir}")

    results = []
    for label, model in CANDIDATES:
        if not (model / "config.json").exists():
            print(f"[calib] ⏭ 跳过（无 config.json）: {model}")
            results.append({"label": label, "model": str(model), "skipped": True})
            continue
        results.append(run_one(label, model, workdir))

    print("\n[calib] ==== 标定读数汇总（同一仪器 eval_dataset=%s）====" % EVAL_DATASET)
    print(json.dumps(results, ensure_ascii=False, indent=2))

    summary = workdir / "calib-summary.json"
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[calib] 汇总已写入 {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
