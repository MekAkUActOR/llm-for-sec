# M3 DPO 发射器：按 C 路裁决结果自动选择起点，生成对应 yaml 后发射。
#
# 依据 reports/m3-launch-runbook.md §0 的条件分支（2026-09-30 改判）：
#   - 裁决 = "C 路成立"                → 起点 = C 路产物（--variant，默认 e1）
#   - 裁决 = "H0 成立 / 补齐无效"      → 起点 = checkpoints\qwen3-06b-sec-m2-calib（回退 A）
#   - 裁决 = "PENDING"                → 拒绝发射（fail-closed）
# 本脚本**不替你判断裁决**：它读 reports\topup-verdict-<variant>.json 的 decision 字段，
# 未指定 --variant 且无裁决文件时直接拒绝。
#
# 可中断无损续训：save_only_model=false + LF auto-resume（同命令重跑即续）；
# save_total_limit=3（docs/01 §7.3）。
# 用法：
#   powershell ... -File scripts\run_m3_dpo.ps1 -Variant m3base-topup-e1        # 读裁决自动定起点
#   powershell ... -File scripts\run_m3_dpo.ps1 -Base checkpoints\qwen3-06b-sec-m2-calib
#       ↑ 显式起点。**仅当已有裁决文书授权该起点时使用**（本例：
#         reports/c-path-topup-verdict.md 判定 H0 成立 → 回退选项 A → m2-calib）。
[CmdletBinding()]
param(
  [string]$Variant = 'm3base-topup-e1',
  [string]$Base = '',
  [switch]$Force,
  [switch]$DryRun,
  [double]$PrefBeta = 0.1
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$env:HF_HOME = "$root\.cache\huggingface"
$env:TORCH_HOME = "$root\.cache\torch"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
$cli = "$root\.venv\Scripts\llamafactory-cli.exe"
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

# ---- 1) 读裁决，决定起点（fail-closed）
$verdictPath = "$root\reports\topup-verdict-$Variant.json"
$startModel = $null
if ($Base -ne '') {
  # 显式起点：不查裁决，但**要求裁决文书存在**作为授权凭据（fail-closed 的弱化版）
  if (-not (Test-Path "$root\reports\c-path-topup-verdict.md")) {
    Write-Host "[m3] 显式 -Base 但缺裁决文书 reports\c-path-topup-verdict.md → 拒绝"
    exit 2
  }
  $startModel = if ($Base -match '^[A-Za-z]:') { $Base } else { "$root\$Base" }
  Write-Host "[m3] ★显式起点（已由 C 路裁决文书授权）：$startModel"
} elseif (Test-Path $verdictPath) {
  $v = Get-Content $verdictPath -Raw -Encoding UTF8 | ConvertFrom-Json
  Write-Host "[m3] 裁决 decision = $($v.decision)"
  if ($v.decision -like '*PENDING*') {
    Write-Host "[m3] 拒绝发射：裁决为 PENDING（缺输入，fail-closed）。"
    exit 2
  }
  if ($v.decision -like '*C 路成立*' -or $v.decision -like '*有条件成立*') {
    $startModel = "$root\checkpoints\qwen3-06b-sec-$Variant"
  } else {
    Write-Host "[m3] 裁决指向回退 A（直接以 m2-calib 进 M3）"
    $startModel = "$root\checkpoints\qwen3-06b-sec-m2-calib"
  }
} else {
  if (-not $Force) {
    Write-Host "[m3] 缺裁决文件 $verdictPath → 拒绝发射（用 -Force 明确覆盖）"
    exit 2
  }
  Write-Host "[m3] ★-Force：无裁决文件，起点按 -Variant 直取"
  $startModel = "$root\checkpoints\qwen3-06b-sec-$Variant"
}
if (-not (Test-Path $startModel)) {
  Write-Host "[m3] 起点不存在：$startModel → 中止"
  exit 2
}
Write-Host "[m3] 起点 = $startModel"

# ---- 2) 生成变体 yaml（本 LF 构建不接受 yaml + --key value 覆盖，见 run_topup.ps1 教训）
# 命名按**实际起点**的叶名，不按 $Variant —— 用 -Base 时二者可能不同（2026-09-30 事故教训：
# 误发射时生成的是 m3-dpo-from-m3base-topup-e1.yaml，但起点其实是 m2-calib，名字会误导）。
$leaf = Split-Path $startModel -Leaf
$leaf = $leaf -replace '^qwen3-06b-sec-', ''
$tpl = [System.IO.File]::ReadAllText("$root\configs\m3-dpo.yaml", [System.Text.Encoding]::UTF8)
$cfg = $tpl -replace '(?m)^model_name_or_path:.*$', "model_name_or_path: $startModel"
$cfg = $cfg -replace '(?m)^pref_beta:.*$', "pref_beta: $PrefBeta"
$outName = "m3-dpo-from-$leaf"
$cfgPath = "$root\configs\$outName.yaml"
[System.IO.File]::WriteAllText($cfgPath, $cfg, $utf8)
Write-Host "[m3] 生成配置：$cfgPath (pref_beta=$PrefBeta)"
Write-Host "[m3] 训练日志将写入：$logdir\m3-dpo-$leaf.log"
Write-Host "[m3] PREFLIGHT 摘要：base=$startModel | variant=$Variant | dryrun=$DryRun"

if ($DryRun) {
  Write-Host "[m3] ★-DryRun：只生成配置与预检，未发射训练（GPU 未被占用）。"
  Write-Host "[m3] DRYRUN-OK"
  exit 0
}

# ---- 3) 发射（串行，独占 GPU；训练期间禁止任何其他 GPU/大 IO 作业）
& $cli train $cfgPath 2>&1 |
  Tee-Object -FilePath "$logdir\m3-dpo-$leaf.log" |
  Select-String -Pattern "running training|total_optimization_steps|train_runtime|Saving model checkpoint|Error|Traceback|OutOfMemory|error:|'loss'" |
  ForEach-Object { $_.Line }
Write-Host "[m3] exit=$LASTEXITCODE"
Write-Host "[m3] ALL DONE"
