# needle 插值扫描：只跑 needle（每档约 3.5 分钟），先定位 needle 何时达标，
# 再对达标档付昂贵的泛化门禁（v0.3-gen，约 10 分钟/档）。
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sweep_soup_needle.ps1
[CmdletBinding()]
param(
  [string[]]$Alphas = @('0.20', '0.35', '0.50', '0.65', '0.80')
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

foreach ($a in $Alphas) {
  $n = $a.Replace('.', '')
  $tag = "soup-a$n"
  $model = "$root\checkpoints\soup-needlefix-a$n"
  if (-not (Test-Path $model)) { Write-Host "[soup] 缺 $model，跳过"; continue }
  if (Test-Path "$root\reports\longctx-$tag.json") { Write-Host "[soup] 已有 $tag needle，跳过"; continue }
  $used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
  if ($used -gt 2048) { Write-Host "[soup] 显存 $used MiB 未清空 → 中止"; exit 2 }
  Write-Host "`n[soup] ===== needle alpha=$a ($tag) ====="
  & $py scripts\probe_longctx.py --model $model --name $tag --lens 16384,32768 --n-docs 4 `
      --out "$root\reports\longctx-$tag.json" 2>&1 |
    Tee-Object -FilePath "$logdir\soup-needle-$tag.log" |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
}
Write-Host "`n[soup] NEEDLE SWEEP DONE"
