# needle 修复发射器：生成 e1/e2 变体 yaml 后串行发射（可中断无损续训）。
#
# 判据见 reports/needlefix-preregistration.md（发射前已冻结）。
# 变体：e1 = 1 epoch（378 步）；e2 = 2 epoch（756 步）——用于"剂量不足"分支的续跑。
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_needlefix.ps1 -Variant e1
[CmdletBinding()]
param(
  [ValidateSet('e1', 'e2')][string]$Variant = 'e1',
  [switch]$DryRun
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$env:HF_HOME = "$root\.cache\huggingface"
$env:TORCH_HOME = "$root\.cache\torch"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
### ★2026-09-30 实测必加：expandable_segments 治显存碎片，是 98% 饱和下把步时
###   从 25-51 s 打到 4.88 s 的两个必要修改之一（另一个是 optim: adamw_bnb_8bit）。
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
Set-Location $root
$cli = "$root\.venv\Scripts\llamafactory-cli.exe"
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

# ---- 0) 前置：显存必须干净（PPL/baseline_eval 会独占 ~11GB，见 docs/01 §11.7）
$used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
Write-Host "[needlefix] 发射前显存占用 = $used MiB（应 < 2048）"
if ($used -gt 4096) {
  Write-Host "[needlefix] 显存未清空 → 中止（先确认无残留 python 作业）"
  exit 2
}
$other = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'probe_|baseline_eval|llamafactory' })
if ($other.Count -gt 0) {
  Write-Host "[needlefix] 检测到 $($other.Count) 个在跑 GPU 作业 → 中止（GPU 严格串行）"
  $other | ForEach-Object { Write-Host "   pid=$($_.ProcessId)" }
  exit 2
}

# ---- 1) 生成变体 yaml（本 LF 构建不接受 yaml + --key value 覆盖）
$epochs = if ($Variant -eq 'e2') { '2.0' } else { '1.0' }
$tpl = [System.IO.File]::ReadAllText("$root\configs\m2calib-needlefix.yaml", [System.Text.Encoding]::UTF8)
$cfg = $tpl -replace '(?m)^num_train_epochs:.*$', "num_train_epochs: $epochs"
$cfg = $cfg -replace '(?m)^output_dir:.*$', "output_dir: $root\checkpoints\qwen3-06b-sec-m2calib-needlefix-$Variant"
$cfgPath = "$root\configs\m2calib-needlefix-$Variant.yaml"
[System.IO.File]::WriteAllText($cfgPath, $cfg, $utf8)
Write-Host "[needlefix] 变体=$Variant epochs=$epochs 配置=$cfgPath"
if ($DryRun) { Write-Host "[needlefix] DRYRUN-OK"; exit 0 }

# ---- 2) 发射（独占 GPU；训练期间禁止任何其他 GPU/大 IO 作业）
& $cli train $cfgPath 2>&1 |
  Tee-Object -FilePath "$logdir\needlefix-$Variant.log" |
  Select-String -Pattern "running training|total_optimization_steps|train_runtime|'eval_loss'|Saving model checkpoint|Error|Traceback|OutOfMemory|error:" |
  ForEach-Object { $_.Line }
Write-Host "[needlefix] exit=$LASTEXITCODE"
Write-Host "[needlefix] ALL DONE"
