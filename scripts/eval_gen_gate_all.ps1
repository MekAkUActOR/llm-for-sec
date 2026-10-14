# Re-measure the FULL unseen-carrier gate on the SAME instrument for every model.
#
# Why: v0.3-gen was expanded 122 -> 258 items (robustness 70 -> 168) DURING the
# C-path training, so the m2-calib 4/70 baseline is no longer on the same
# instrument as the post-training readings. The pre-registered main criterion
# ("not significantly worse than the start point") requires same-instrument
# comparison, so every model -- baselines included -- is re-measured here.
# See reports/c-path-topup-preregistration.md section 1.4.
#
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_gen_gate_all.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$heldout = "$root\data\heldout\v0.3-gen"

# 顺序：先基线（判定主判据的参照），后训练变体
# 本脚本**只做决定性判据**（未见载体门禁）。PPL（辅判据）已移至
# scripts\eval_topup_should.ps1 —— 原先把 PPL 排在前面，结果在 24GB 卡的
# WDDM 停滞区里耗掉 >25 分钟/模型，把唯一决定 M3 起点的测量挡在后面（已纠正）。
$models = @(
  @{ tag = 'm2calib';           path = "$root\checkpoints\qwen3-06b-sec-m2-calib" },
  @{ tag = 'm2full';            path = "$root\checkpoints\qwen3-06b-sec-m2-full" },
  @{ tag = 'm25full';           path = "$root\checkpoints\qwen3-06b-sec-m25-full" },
  @{ tag = 'm3base-topup-e1';   path = "$root\checkpoints\qwen3-06b-sec-m3base-topup-e1" },
  @{ tag = 'm3base-topup-e2';   path = "$root\checkpoints\qwen3-06b-sec-m3base-topup-e2" }
)
foreach ($m in $models) {
  if (-not (Test-Path $m.path)) { Write-Host "[gen-gate] SKIP $($m.tag) (缺产物 $($m.path))"; continue }
  Write-Host "`n[gen-gate] ================ $($m.tag) ================"
  & $py scripts\baseline_eval.py --model $m.path --heldout $heldout `
      --prompt-format chat --out "$root\reports\heldout-gen-$($m.tag).json" `
      --dump-responses "$root\reports\resp-chat-gen-$($m.tag).jsonl" 2>&1 |
    Tee-Object -FilePath "$logdir\gen-gate-$($m.tag).log" |
    Select-String -Pattern 'prompt-format|items|report ->|Traceback|Error' | ForEach-Object { $_.Line }
  if ($LASTEXITCODE -ne 0) { Write-Host "[gen-gate] FAIL baseline_eval on $($m.tag)"; continue }
  & $py scripts\score_heldout_v2.py --heldout $heldout `
      --responses "$root\reports\resp-chat-gen-$($m.tag).jsonl" `
      --out "$root\reports\scored-chat-gen-$($m.tag)-v2.json" 2>&1 |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  # 逐载体子集（image_metadata / av_metadata），供分层读数
  foreach ($c in @('image_metadata', 'av_metadata')) {
    $sub = "$root\reports\heldout-gen-$c"
    New-Item -ItemType Directory -Force -Path $sub | Out-Null
    foreach ($f in Get-ChildItem "$heldout\*.jsonl") {
      $lines = Get-Content $f.FullName -Encoding UTF8 | Select-String $c | ForEach-Object { $_.Line }
      if ($lines) { [System.IO.File]::WriteAllLines("$sub\$($f.Name)", $lines, $utf8) }
    }
    & $py scripts\score_heldout_v2.py --heldout $sub `
        --responses "$root\reports\resp-chat-gen-$($m.tag).jsonl" `
        --out "$root\reports\scored-chat-gen-$($m.tag)-$c-v2.json" 2>&1 |
      Select-String -Pattern 'report ->' | ForEach-Object { $_.Line }
  }
}
Write-Host "`n[gen-gate] ALL DONE -> now run: python scripts\analyze_gen_gate.py"
