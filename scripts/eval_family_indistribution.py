# -*- coding: utf-8 -*-
r"""三族"在分布能力观测"接通脚本（本项目此前**从未接通**的观测项）。

背景：
  `reports/*topup*verdict*.py` 的观测项读 `reports/scored-chat-fam-<tag>-<fam>-v2.json`
  并算"攻击成功率"。但 `data/heldout/v0.5-topup-families/*.jsonl` 的实际 schema 是
  **SFT sharegpt**（`{id,task,pack,lang,messages[system,user,assistant]}`，assistant 以
  `VERDICT: {...}` 收尾），其 README 明确写着这是"在分布能力观测仪，不是泛化测试集"，
  且要求"按方向读、不做显著性检验"。因此 `baseline_eval.py`（要 `domain`/`query`/`expected`）
  必然失败 —— 这就是该观测项长期显示"缺失"的原因。

本脚本按**其设计意图**接通：用它作 LLaMA-Factory 的 **eval_dataset**，在**同一台仪器**上
（template qwen3_nothink、cutoff_len 4096、batch 1、bf16）测三族 eval_loss，
对照 baseline 与变体。口径与契约门禁 `sec_sft_v0_eval300` 完全一致（docs/01 §11.8 同仪器）。

判读（按 README）：只读**方向**，三族里 ≥2 族同向才算有信号；单族 27–30 行，不做显著性检验。

纪律：严格串行（跑前显存 <1024 MiB 且无训练进程）；副本写入 data/lf/eval_families/
并逐字节 sha256 校验，**绝不写入 data/heldout/**（只读源）。

用法：
  python scripts/eval_family_indistribution.py --tags soup-a050,m2calib,m2calib-needlefix-e1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / ".venv" / "Scripts" / "llamafactory-cli.exe"
SRC = ROOT / "data" / "heldout" / "v0.5-topup-families"
DST = ROOT / "data" / "lf" / "eval_families"
INFO = ROOT / "data" / "lf" / "dataset_info.json"
REPORT = ROOT / "reports" / "family-indistribution.json"
FAMS = ("t2_mechanism", "doc_structure", "t9_phish")

MODELS = {
    "m2calib": ROOT / "checkpoints" / "qwen3-06b-sec-m2-calib",
    "m2calib-needlefix-e1": ROOT / "checkpoints" / "qwen3-06b-sec-m2calib-needlefix-e1",
    "soup-a050": ROOT / "checkpoints" / "soup-needlefix-a050",
    "soup-a035": ROOT / "checkpoints" / "soup-needlefix-a035",
    "m3-dpo": ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo",
    # ★第 41 轮新增（探针全门禁补齐的三族观测 ✓）
    "m4-capfix-probe": ROOT / "checkpoints" / "qwen3-06b-sec-m4-capfix-probe",
}

YAML = """\
### 三族在分布能力观测（临时；eval-only，不训练、不保存模型）
model_name_or_path: {model}
stage: sft
do_train: false
do_eval: true
finetuning_type: full
template: qwen3_nothink

dataset_dir: {dset_dir}
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


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_copies() -> dict:
    """把三族逐字节复制进 data/lf/eval_families/ 并校验哈希（不写 data/heldout）。"""
    DST.mkdir(parents=True, exist_ok=True)
    prov = {}
    for fam in FAMS:
        s, d = SRC / f"{fam}.jsonl", DST / f"{fam}.jsonl"
        if not s.exists():
            raise SystemExit(f"缺源文件 {s}")
        shutil.copy2(s, d)
        hs, hd = sha256(s), sha256(d)
        if hs != hd:
            raise SystemExit(f"FAIL 副本哈希不一致 {fam}: {hs} != {hd}")
        prov[fam] = {"sha256": hs, "rows": sum(1 for x in s.read_text(
            encoding="utf-8").splitlines() if x.strip())}
    info = json.loads(INFO.read_text(encoding="utf-8"))
    for fam in FAMS:
        info[f"sec_fam_{fam}"] = {
            "file_name": f"eval_families/{fam}.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": {"role_tag": "role", "content_tag": "content", "user_tag": "user",
                     "assistant_tag": "assistant", "system_tag": "system"},
        }
    INFO.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return prov


def vram() -> int | None:
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=30)
        return int(o.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def preflight() -> bool:
    """★门槛修订（2026-09-30 实测）：WDDM 下 memory.used 含桌面合成等挂名占用，
    空闲基线会漂移（同日实测 866 → 928 → 1,382 MiB），且 nvidia-smi 的
    --query-compute-apps 会列出 used_memory=[N/A] 的非 CUDA 条目。
    真正的判别信号是"**没有任何 python 进程**"（并发才是 10× 退化的根因），
    故改为：无 python 进程 **且** 占用 < 2048 MiB。"""
    procs = []
    try:
        # ★看门狗自查第①条的同类教训：**按命令行而非可执行文件名**识别 GPU 作业。
        # 按 Name='python.exe' 会把本脚本自己/启动器/无关键子进程算进来（实测误报 pid 30168）。
        o = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                            "Where-Object { $_.CommandLine -match 'llamafactory|probe_|"
                            "baseline_eval|score_heldout|train ' } | "
                            "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
                           capture_output=True, text=True, timeout=60)
        me = str(os.getpid())
        procs = [x for x in o.stdout.splitlines()
                 if x.strip() and not x.strip().startswith(me + " ")]
    except Exception:  # noqa: BLE001
        pass
    u = vram()
    print(f"[fam-ind] 显存占用 = {u} MiB；python 进程 = {len(procs)} 个")
    if procs:
        print(f"[fam-ind] ✗ 仍有 python 进程（pid {procs}），拒绝并发（docs/01 §11.7）")
        return False
    if u is not None and u >= 2048:
        print("[fam-ind] ✗ 显存未清空，拒绝执行")
        return False
    return True


def run_one(model: Path, fam: str, workdir: Path) -> float | None:
    outdir = workdir / f"out_{model.name}_{fam}"
    outdir.mkdir(parents=True, exist_ok=True)
    cfg = workdir / f"{model.name}_{fam}.yaml"
    cfg.write_text(YAML.format(model=model, dset_dir=ROOT / "data" / "lf",
                               eval_dataset=f"sec_fam_{fam}", outdir=outdir),
                   encoding="utf-8")
    env = dict(os.environ)
    env.update({"HF_HOME": str(ROOT / ".cache" / "huggingface"),
                "TORCH_HOME": str(ROOT / ".cache" / "torch"),
                "HF_HUB_OFFLINE": "1", "PYTHONIOENCODING": "utf-8",
                "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"})
    log = workdir / f"{model.name}_{fam}.log"
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        rc = subprocess.call([str(CLI), "train", str(cfg)], stdout=fh,
                             stderr=subprocess.STDOUT, env=env, cwd=str(ROOT))
    text = log.read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"\{\s*'eval_loss'\s*:\s*'?([0-9.eE+-]+)'?", text)
    if not m:
        m = re.findall(r"^\s*eval_loss\s*=\s*([0-9.eE+-]+)\s*$", text, re.M)
    val = float(m[-1]) if m else None
    print(f"[fam-ind]   {model.name:24} {fam:16} eval_loss={val}  rc={rc}")
    return val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="m2calib,m2calib-needlefix-e1,soup-a050")
    args = ap.parse_args()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    print("[fam-ind] === 三族在分布能力观测（eval-only，同仪器 eval_loss）===")
    if not preflight():
        return 2
    prov = stage_copies()
    print(f"[fam-ind] 三族副本已就位并逐字节校验：{json.dumps({k: v['sha256'][:12] for k, v in prov.items()})}")
    workdir = Path(tempfile.mkdtemp(prefix="fam_ind_"))
    print(f"[fam-ind] 临时工作目录 = {workdir}")
    res: dict = {}
    for tag in tags:
        model = MODELS.get(tag)
        if model is None or not (model / "config.json").exists():
            print(f"[fam-ind] ⏭ 跳过 {tag}（无模型）")
            continue
        res[tag] = {fam: run_one(model, fam, workdir) for fam in FAMS}
    # ★第 41 轮修订：**合并写入**（加性纪律 ✓）—— 原实现整份覆写，
    # 会把未重测的历史 tag（m2calib 等）从报告里抹掉 ✗。
    # 新语义：新测量覆盖**同 tag** 的旧值 ✓，未重测的 tag **原样保留** ✓。
    prev: dict = {}
    if REPORT.exists():
        try:
            prev = json.loads(REPORT.read_text(encoding="utf-8")).get("eval_loss") or {}
        except Exception:  # noqa: BLE001
            prev = {}
    merged = {**prev, **res}
    rep = {"instrument": "data/heldout/v0.5-topup-families（只读，副本哈希已校验）",
           "provenance": prov, "reading_rule": "README：只读方向，三族≥2 族同向才算信号，不做显著性检验",
           "eval_loss": merged}
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n[fam-ind] ==== 汇总（eval_loss，越低越好；合并后全量 ✓）====")
    print(f"{'tag':26} " + " ".join(f"{f:>16}" for f in FAMS))
    for tag, d in merged.items():
        print(f"{tag:26} " + " ".join(
            f"{(d[f] if d.get(f) is not None else float('nan')):>16.6f}" for f in FAMS))
    print(f"\n[fam-ind] 报告 -> {REPORT.relative_to(ROOT)}（合并后 {len(merged)} 个 tag ✓，"
          f"其中本次新测 {len(res)} 个 ✓）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
