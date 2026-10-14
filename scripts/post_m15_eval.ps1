# M1.5 训练完成后自动评估链（探针 v0.3 优先，回退 v0.1.1；三基线对比；判分器 v2 首次实战）：
#   1. 等待训练结束（m15 自己的 train_results.json——勿用 trainer_log 的 train_loss 判据）
#   2. 探针版本选择：data/probes/v0.3 存在（含 jsonl）则用之，否则回退 v0.1.1；报告注明版本
#   3. 三基线 PPL：① base → m15（累计效果）② c1-full → m15（预训练谱系对照）
#      ③ m16-32k → m15（**M1.5 增量主读数**——2026-09-28 改：m15 起点已改为 m16-32k，
#      知识针的干净增量只能对恢复段产物测；m16-32k 的 PPL 若缺则本链现算）
#   4. heldout v0.2 复评 + 判分器 v2 闭环：c1-full 基线段（判分器 v2 登记
#      起点 + M1.5"行为不变"读数的参照侧，先跑）+ m15 首战段
#   5. 长上下文 32k 对照（m15 vs m16-32k——防知识针损伤 M1.6 恢复成果；
#      2026-09-28 改：守护基线从 c1-full 换为 m16-32k）
$ErrorActionPreference = 'Continue'
$py = 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe'
$m15 = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m15'
$m1632 = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m16-32k'
$c1full = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-c1-full'
$base = 'J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd'
$env:HF_HOME = 'J:\Projects\llm_for_sec\.cache\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'J:\Projects\llm_for_sec'

# --- 1. 等待训练完成（m15 自己的 train_results.json）---
$done = Join-Path $m15 'train_results.json'
Write-Host "[post-m15] waiting for m15 training to finish..."
while (-not (Test-Path $done)) {
    Start-Sleep -Seconds 300
}
Start-Sleep -Seconds 120  # 等最终文件落盘
Write-Host "[post-m15] training done, starting evals"

# --- 2. 探针版本选择（v0.3 优先，回退 v0.1.1；报告注明）---
$probeDir = $null
if ((Test-Path 'data\probes\v0.3') -and (Get-ChildItem 'data\probes\v0.3\*.jsonl' -ErrorAction SilentlyContinue)) {
    $probeDir = 'data\probes\v0.3'
    $probeVer = 'v0.3'
} else {
    $probeDir = 'data\probes\v0.1.1'
    $probeVer = 'v0.1.1'
}
Write-Host "[post-m15] probe version: $probeVer"
$probeVer | Out-File -FilePath 'reports\post-m15-probe-version.txt' -Encoding utf8

# --- 3. 双基线 PPL ---
# checkpoint 可能缺 tokenizer（save_only_model）→ 指向底座快照兜底（probe_ppl/baseline_eval 通用）
$tokArgs = @()
if (-not (Test-Path (Join-Path $m15 'tokenizer_config.json'))) {
    $tokArgs = @('--tokenizer', $base)
}
# base（同版本缺失则现算）
$basePpl = "reports\ppl-base-$probeVer.json"
if (-not (Test-Path $basePpl)) {
    & $py scripts\probe_ppl.py --model $base --name "base-$probeVer" --probes $probeDir --out $basePpl 2>&1
}
# c1-full（同版本缺失则现算）
$c1Ppl = "reports\ppl-c1-full-$probeVer.json"
if (-not (Test-Path $c1Ppl)) {
    & $py scripts\probe_ppl.py --model $c1full --name "c1-full-$probeVer" --probes $probeDir --out $c1Ppl 2>&1
}
# m16-32k（M1.5 增量主读数的基座；post_m16_eval 只测 longctx，PPL 在此现算）
$m16TokArgs = @()
if (-not (Test-Path (Join-Path $m1632 'tokenizer_config.json'))) {
    $m16TokArgs = @('--tokenizer', $base)
}
$m16Ppl = "reports\ppl-m16-32k-$probeVer.json"
if (-not (Test-Path $m16Ppl)) {
    & $py scripts\probe_ppl.py --model $m1632 @m16TokArgs --name "m16-32k-$probeVer" --probes $probeDir --out $m16Ppl 2>&1
}
# m15
& $py scripts\probe_ppl.py --model $m15 @tokArgs --name "m15-$probeVer" --probes $probeDir --out reports\ppl-m15-$probeVer.json 2>&1
# 对比 ①：base → m15（累计效果）
& $py scripts\compare_ppl.py $basePpl reports\ppl-m15-$probeVer.json 2>&1 | Tee-Object -FilePath reports\ppl-compare-base-m15.txt
# 对比 ②：c1-full → m15（预训练谱系对照）
& $py scripts\compare_ppl.py $c1Ppl reports\ppl-m15-$probeVer.json 2>&1 | Tee-Object -FilePath reports\ppl-compare-c1full-m15.txt
# 对比 ③：m16-32k → m15（M1.5 增量主读数——C2 知识针效果）
& $py scripts\compare_ppl.py $m16Ppl reports\ppl-m15-$probeVer.json 2>&1 | Tee-Object -FilePath reports\ppl-compare-m1632-m15.txt

# --- 4. heldout v0.2 复评 + 判分器 v2 闭环（c1-full 基线段 + m15 首战段）---
# c1-full 侧参照（先于 m15 跑）：①M1.5 是预训练针，行为预期不变（两侧 ASR 应都 ≈1.0）——
#   这个"不变"本身是 M1.5 的 heldout 读数，需 c1-full 侧参照呈现；
# ②判分器 v2 真实模型输出的登记起点——base 时代标签分布（comply/format_error 占比、
#   n_missing 率、report_finding 零命中）= M2 SFT 生效时标签迁移的参照系。
# 注意 --out 必显式（默认值会覆写 M0 基线登记报告 baseline-qwen3-0.6b-base.json）。
# 崩溃可续：终产物存在则跳过（与上方 PPL 段的复用模式一致）。
$c1TokArgs = @()
if (-not (Test-Path (Join-Path $c1full 'tokenizer_config.json'))) {
    $c1TokArgs = @('--tokenizer', $base)
}
if (-not (Test-Path 'reports\scored-c1full-v2.json')) {
    & $py scripts\baseline_eval.py --model $c1full @c1TokArgs --heldout data\heldout\v0.2 --out reports\heldout-c1full-v02.json --dump-responses reports\resp-c1full-v02.jsonl 2>&1
    & $py scripts\score_heldout_v2.py --heldout data\heldout\v0.2 --responses reports\resp-c1full-v02.jsonl --out reports\scored-c1full-v2.json 2>&1
}
# m15 侧（判分器 v2 首战主对象）
& $py scripts\baseline_eval.py --model $m15 @tokArgs --heldout data\heldout\v0.2 --out reports\heldout-m15.json --dump-responses reports\resp-m15.jsonl 2>&1
& $py scripts\score_heldout_v2.py --heldout data\heldout\v0.2 --responses reports\resp-m15.jsonl --out reports\scored-m15-v2.json 2>&1

# --- 5. 长上下文 32k 对照（m15 vs m16-32k，防知识针损伤 M1.6 恢复成果）---
# m16 侧 longctx 由 post_m16_eval 产出（--name m16 → longctx-m16.json）；缺则现算
if (-not (Test-Path 'reports\longctx-m16.json')) {
    & $py scripts\probe_longctx.py --model $m1632 --name m16 2>&1
}
& $py scripts\probe_longctx.py --model $m15 --name m15 2>&1
& $py scripts\probe_longctx.py --compare reports\longctx-m16.json reports\longctx-m15.json 2>&1 | Tee-Object -FilePath reports\longctx-compare-m16-m15.txt
Write-Host "[post-m15] ALL DONE"
