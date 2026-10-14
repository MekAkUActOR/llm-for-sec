# 只跑三族在分布内观测探针（防伪通过项）：data/heldout/v0.5-topup-families 下的
# t2_mechanism(28) / doc_structure(27) / t9_phish(30)，对 baseline 与 variant 各一遍。
# topup_verdict.py 会读 reports/scored-chat-fam-<tag>-<fam>-v2.json。
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_family_probe.ps1 -Tags m2calib,soup-a050
[CmdletBinding()]
param(
  [string]$Tags = 'm2calib,soup-a050'
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
Set-Location $root
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$famDir = "$root\data\heldout\v0.5-topup-families"
$tagList = @($Tags -split ',' | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })

foreach ($tag in $tagList) {
  # tag → 目录名映射（注意 m2calib 的目录带连字符：qwen3-06b-sec-m2-calib）
  $model = if ($tag -like 'soup-*') { "$root\checkpoints\soup-needlefix-$($tag -replace '^soup-','')" }
           elseif ($tag -eq 'm2calib') { "$root\checkpoints\qwen3-06b-sec-m2-calib" }
           else { "$root\checkpoints\qwen3-06b-sec-$tag" }
  if (-not (Test-Path $model)) { Write-Host "[fam] 缺模型 $model，跳过 $tag"; continue }
  foreach ($f in Get-ChildItem "$famDir\*.jsonl") {
    $fam = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
    if (Test-Path "$root\reports\scored-chat-fam-$tag-$fam-v2.json") {
      Write-Host "[fam] 已有 $tag/$fam，跳过"; continue
    }
    $used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
    if ($used -gt 2048) { Write-Host "[fam] 显存 $used MiB 未清空 → 中止"; exit 2 }
    Write-Host "`n[fam] ==== $tag / $fam ===="
    $sub = "$root\reports\heldout-fam-$fam"
    New-Item -ItemType Directory -Force -Path $sub | Out-Null
    Copy-Item $f.FullName "$sub\$($f.Name)" -Force
    & $py scripts\baseline_eval.py --model $model --heldout $sub `
        --prompt-format chat --out "$root\reports\heldout-fam-$tag-$fam.json" `
        --dump-responses "$root\reports\resp-chat-fam-$tag-$fam.jsonl" 2>&1 |
      Tee-Object -FilePath "$logdir\fam-$tag-$fam.log" |
      Select-String -Pattern 'prompt-format|report ->|Traceback' | ForEach-Object { $_.Line }
    & $py scripts\score_heldout_v2.py --heldout $sub `
        --responses "$root\reports\resp-chat-fam-$tag-$fam.jsonl" `
        --out "$root\reports\scored-chat-fam-$tag-$fam-v2.json" 2>&1 |
      Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  }
}
Write-Host "`n[fam] FAMILY PROBE DONE"
