# 对给定的插值档跑未见载体门禁（v0.3-gen，部署格式 chat）+ 判分。
# 只做一件事，便于按需对少数几档付费（每档约 10 分钟）。
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_soup_gen.ps1 -Tags soup-a050,soup-a065
[CmdletBinding()]
param(
  # ★用逗号分隔的**单个字符串**：powershell -File 传数组不会按逗号拆分，
  #   写成 [string[]] 只会得到 @('a,b') 一个元素（实测：报"缺模型 a,b"或位置参数错误）
  [Parameter(Mandatory = $true)][string]$Tags
)
$tagList = @($Tags -split ',' | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
Set-Location $root
$logdir = "$root\reports\logs"
$gen = "$root\data\heldout\v0.3-gen"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

foreach ($tag in $tagList) {
  $model = if ($tag -like 'soup-*') { "$root\checkpoints\soup-needlefix-$($tag -replace '^soup-','')" }
           else { "$root\checkpoints\qwen3-06b-sec-$tag" }
  if (-not (Test-Path $model)) { Write-Host "[soup-gen] 缺模型 $model，跳过 $tag"; continue }
  if (Test-Path "$root\reports\scored-chat-gen-$tag-v2.json") {
    Write-Host "[soup-gen] 已有 $tag 读数，跳过"; continue
  }
  $used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
  if ($used -gt 2048) { Write-Host "[soup-gen] 显存 $used MiB 未清空 → 中止"; exit 2 }
  Write-Host "`n[soup-gen] ===== v0.3-gen 部署格式：$tag ====="
  & $py scripts\baseline_eval.py --model $model --heldout $gen --prompt-format chat `
      --out "$root\reports\heldout-chat-gen-$tag.json" `
      --dump-responses "$root\reports\resp-chat-gen-$tag.jsonl" 2>&1 |
    Tee-Object -FilePath "$logdir\soup-gen-$tag.log" |
    Select-String -Pattern 'prompt-format|report ->|Traceback' | ForEach-Object { $_.Line }
  if ($LASTEXITCODE -eq 0) {
    & $py scripts\score_heldout_v2.py --heldout $gen `
        --responses "$root\reports\resp-chat-gen-$tag.jsonl" `
        --out "$root\reports\scored-chat-gen-$tag-v2.json" 2>&1 |
      Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  } else {
    Write-Host "[soup-gen] $tag 生成失败（exit=$LASTEXITCODE），不判分"
  }
}
Write-Host "`n[soup-gen] GEN SWEEP DONE"
