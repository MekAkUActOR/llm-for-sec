# 守候 M3 DPO 训练结束，自动接上「基线 chat needle → M3 后评测链 → 裁定」。
#
# 为什么需要它：训练约 1.5 h，而后评测链约 15 min。若等训练结束再手工发射，
# GPU 会空转。本项目纪律是「训练窗口必须用满」且**严格串行**——
# 因此本脚本只做一件事：**等到训练进程消失**，再调 eval_m3_post.ps1（后者自带
# 串行前置校验：命令行级 GPU 作业检测 + 显存 <2048 MiB）。
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\wait_then_post_m3.ps1
#   powershell ... -File scripts\wait_then_post_m3.ps1 -MaxWaitMin 240 -Tag m3-dpo
[CmdletBinding()]
param(
  [string]$Tag = 'm3-dpo',
  [string]$Model = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo',
  [string]$Baseline = 'soup-a050',
  [int]$MaxWaitMin = 300,
  [int]$PollSec = 60
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$logdir = "$root\reports\logs"
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory -Path $logdir -Force | Out-Null }
$log = "$logdir\wait-then-post-m3.log"

function Say($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding UTF8
}

function Get-GpuJobProcs {
  # 按**命令行**识别（不是按 exe 名）——本项目的既定教训
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'llamafactory|probe_|baseline_eval|score_heldout|train ' }
}

Say "守候开始：等待 M3 训练进程（$Tag）结束；最长 $MaxWaitMin min，每 $PollSec s 轮询。"
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
$lastLog = ''
while ((Get-Date) -lt $deadline) {
  $procs = Get-GpuJobProcs
  if (-not $procs) {
    Say "训练进程已消失（无 GPU 作业进程）。"
    break
  }
  # 顺带把训练进度抄进本日志（便于事后对账）
  $tl = "$Model\trainer_log.jsonl"
  if (Test-Path $tl) {
    $last = Get-Content $tl -Tail 1 -ErrorAction SilentlyContinue
    if ($last -and $last -ne $lastLog) {
      $lastLog = $last
      Say "训练中：$last"
    }
  }
  Start-Sleep -Seconds $PollSec
}
if (Get-GpuJobProcs) {
  Say "✗ 超时（$MaxWaitMin min）训练进程仍在 ⇒ 本守候器退出，不启动后评测（避免并发）。"
  exit 3
}

# ---- 产物完整性：训练真的落盘了吗 ----
Say "校验产物：$Model"
if (-not (Test-Path "$Model\config.json")) {
  Say "✗ 缺 $Model\config.json ⇒ 训练可能未正常落盘，拒绝启动后评测。"
  exit 2
}
$cks = @(Get-ChildItem $Model -Directory -Filter 'checkpoint-*' -ErrorAction SilentlyContinue |
         Sort-Object { [int]($_.Name -replace '\D', '') })
$hasFinal = (Test-Path "$Model\model.safetensors") -or
            ((Test-Path "$Model\model.safetensors.index.json") -and
             @(Get-ChildItem $Model -Filter '*.safetensors' -ErrorAction SilentlyContinue).Count -gt 1)
Say ("产物：checkpoint 数={0}，末档={1}，训练根含最终权重={2}" -f `
      $cks.Count, ($(if ($cks) { $cks[-1].Name } else { '无' })), $hasFinal)
if (-not $hasFinal -and $cks.Count -eq 0) {
  Say "✗ 既无最终权重也无 checkpoint ⇒ 无可用产物，拒绝启动。"
  exit 2
}

# ---- 启动后评测链（内含串行前置校验）----
Say "启动后评测链 eval_m3_post.ps1（Tag=$Tag, Baseline=$Baseline）"
try {
  powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_m3_post.ps1" `
    -Tag $Tag -Model $Model -Baseline $Baseline 2>&1 |
    Tee-Object -FilePath "$logdir\wait-then-post-m3-chain.log" |
    ForEach-Object { $_ }
  $rc = $LASTEXITCODE
  Say "后评测链退出码 = $rc"
} catch {
  Say "后评测链异常：$($_.Exception.Message)"
  exit 4
}
Say "守候器结束。判定报告：reports\topup-verdict-$Tag.json"
