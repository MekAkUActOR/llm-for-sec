# M3 后评测链的**恢复器**（2026-09-30 晚，事故后新增）
#
# 事故：eval_needlefix.ps1 的守卫按**进程名**判定（任何 python.exe 即中止），
#       把纯 CPU 作业 build_document_gate.py --overlap 误判为 GPU 作业 ⇒
#       整条链在 step 1 被误杀；而 eval_m3_post.ps1 的 $ErrorActionPreference='Continue'
#       使其继续跑 step 6/7 ⇒ **step 0-5（全部行为门禁）被整段跳过**。
#       守卫已修（改按命令行识别，docs/01 §11.18 规则 19）。
#
# 本恢复器：等当前（残废的）链退出 → 等 GPU 真空闲 → **重跑整条链**。
#           eval_m3_post.ps1 对已存在的产物会跳过，故重跑 = 补齐缺失步骤，不重复计算。
#
# ★自身排除：本脚本命令行里含 'eval_m3_post'，若守卫只排除自身 PID 仍会匹配到
#   父壳（DSH 的 pwsh -Command）⇒ 必须排除**自身 + 全部祖先 PID**。
[CmdletBinding()]
param(
  [int]$MaxWaitMin = 90,
  [int]$PollSec = 30
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$log = "$root\reports\logs\m3-chain-recovery.log"
function Say($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding UTF8
}

# ---- 自身 + 全部祖先 PID（逐级上溯）----
$selfChain = New-Object System.Collections.Generic.HashSet[int]
$cur = $PID
for ($i = 0; $i -lt 12 -and $cur -gt 0; $i++) {
  [void]$selfChain.Add($cur)
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction SilentlyContinue
  if (-not $p) { break }
  $cur = [int]$p.ParentProcessId
}
Say ("自身+祖先 PID = " + (($selfChain | Sort-Object) -join ','))

function Get-ChainProcs {
  # 只匹配**真的在跑链**的进程；排除自身与祖先
  Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'eval_m3_post\.ps1' -and -not $selfChain.Contains([int]$_.ProcessId) }
}
function Get-GpuJobProcs {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'llamafactory|probe_|baseline_eval|score_heldout|pack_consistency|eval_family_indistribution' }
}
function Get-GpuUsedMiB {
  try { return [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '') }
  catch { return 0 }
}

Say "守候：等当前（残废的）链退出；最长 $MaxWaitMin min。"
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
while ((Get-Date) -lt $deadline) {
  $c = @(Get-ChainProcs)
  if ($c.Count -eq 0) { Say "链进程已消失。"; break }
  Say ("链仍在跑：PID " + (($c | ForEach-Object { $_.ProcessId }) -join ',') + "；等 $PollSec s")
  Start-Sleep -Seconds $PollSec
}

# 等 GPU 真空闲
Say "等 GPU 空闲（无 GPU 作业进程 且 memory.used < 2048）..."
$deadline = (Get-Date).AddMinutes(30)
while ((Get-Date) -lt $deadline) {
  $g = @(Get-GpuJobProcs)
  $used = Get-GpuUsedMiB
  if ($g.Count -eq 0 -and $used -lt 2048) { Say "GPU 空闲（used=$used MiB）。"; break }
  Say ("GPU 仍忙：作业 $($g.Count) 个，used=$used MiB；等 $PollSec s")
  Start-Sleep -Seconds $PollSec
}

# 重跑整条链（幂等：已有产物会跳过）
Say "===== 重跑 eval_m3_post.ps1（幂等补齐）====="
& powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_m3_post.ps1" 2>&1 |
  Tee-Object -FilePath "$root\reports\logs\m3-post-gates-recovery.log" |
  Select-String -Pattern 'm3-post|needlefix-eval|fam-ind|决策|MUST|Traceback|中止' |
  ForEach-Object { Say $_.Line }
Say "===== 恢复链结束（rc=$LASTEXITCODE）====="
