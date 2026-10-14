# objective ② 的部署格式重测器（2026-10-06 新建）
#
# 背景：objective ② 要求「按部署格式重测 m25-full / m2-full（heldout 161 + needle + sec）」
#   并「产出修正后的 G3/G4/sec 读数并裁决 M3 起点」。
#
# 现状（`scripts/inventory_objective2_gaps.py` 的结论，已核对真实文件名）：
#   ✅ 已有：scored-chat-{t}-v2.json（v0.2.1）、scored-chat-gen-{t}-v2.json（v0.3-gen）
#   ❌ 缺：scored-chat-to-{t}-v2.json（toolout，**新 70 条仪器**）
#           longctx-{t}-chat.json（**chat 口径 needle**）
#           ppl-m2full-v0.4.json
#   ⇒ 两者**都不能作 M3 起点**（MUST-A：m25full 36/168、m2full 63/168，均 ★FAIL），
#     但两处裁定的 `decision` 仍为 PENDING，阻断项 =「缺 v0.4-toolout 鲁棒性读数」。
#     本脚本就是把该阻断项结清（在**新 70 条仪器**上重测，不得沿用旧 8 条读数）。
#
# ★为什么直接复用 eval_needlefix.ps1：
#   它按 $Tag/$Model 参数化、且**幂等**（产物存在即跳过），
#   故对 m25full/m2full 各跑一次，就精确补齐上面缺的那几项，
#   而且用的是**与 M3 完全相同的仪器与格式**（gen/v0.2.1/toolout 三步硬编码
#   `--prompt-format chat`），从构造上杜绝口径混比（docs/01 §11 规则 1）。
#
# ★GPU 严格串行：先等所有链退出、再等 GPU 真空闲，然后**逐个**跑，绝不并发。
# ★自身排除：排除自身 + 全部祖先 PID（否则会匹配到 DSH 的父壳）。
[CmdletBinding()]
param(
  [int]$MaxWaitMin = 120,
  [int]$PollSec = 30
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$log = "$root\reports\logs\obj2-remeasure.log"
Set-Location $root

function Say($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding UTF8
}

# ---- 自身 + 全部祖先 PID ----
$selfChain = New-Object System.Collections.Generic.HashSet[int]
$cur = $PID
for ($i = 0; $i -lt 12 -and $cur -gt 0; $i++) {
  [void]$selfChain.Add($cur)
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction SilentlyContinue
  if (-not $p) { break }
  $cur = [int]$p.ParentProcessId
}

function Get-ChainProcs {
  Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      ($_.CommandLine -match 'eval_m3_post\.ps1' -or $_.CommandLine -match 'eval_needlefix\.ps1') -and
      -not $selfChain.Contains([int]$_.ProcessId)
    }
}
function Get-GpuJobProcs {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'llamafactory|probe_|baseline_eval|score_heldout|pack_consistency|eval_family_indistribution' }
}
function Get-GpuUsedMiB {
  try { return [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '') }
  catch { return 0 }
}

Say "objective ② 重测启动；先等现有链退出（最长 $MaxWaitMin min）"
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
while ((Get-Date) -lt $deadline) {
  $c = @(Get-ChainProcs)
  if ($c.Count -eq 0) { Say "链进程已消失。"; break }
  Say ("链仍在跑：PID " + (($c | ForEach-Object { $_.ProcessId }) -join ',') + "；等 $PollSec s")
  Start-Sleep -Seconds $PollSec
}

Say "等 GPU 空闲（无 GPU 作业进程 且 memory.used < 2048）..."
$deadline = (Get-Date).AddMinutes(30)
while ((Get-Date) -lt $deadline) {
  $g = @(Get-GpuJobProcs)
  $used = Get-GpuUsedMiB
  if ($g.Count -eq 0 -and $used -lt 2048) { Say "GPU 空闲（used=$used MiB）。"; break }
  Say ("GPU 仍忙：作业 $($g.Count) 个，used=$used MiB；等 $PollSec s")
  Start-Sleep -Seconds $PollSec
}

# ---- 逐个 tag 跑（严格串行）----
$targets = @(
  @{ Tag = 'm25full'; Model = "$root\checkpoints\qwen3-06b-sec-m25-full" },
  @{ Tag = 'm2full'; Model = "$root\checkpoints\qwen3-06b-sec-m2-full" }
)

foreach ($t in $targets) {
  Say "===== eval_needlefix.ps1 -Tag $($t.Tag)（chat 口径，幂等补齐）====="
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_needlefix.ps1" `
      -Tag $t.Tag -Model $t.Model -NeedlePromptFormat chat 2>&1 |
    Tee-Object -FilePath "$root\reports\logs\obj2-needlefix-$($t.Tag).log" |
    Select-String -Pattern 'needlefix-eval|Traceback|中止|OK |ALL DONE|失败' |
    ForEach-Object { Say $_.Line }
  Say "----- $($t.Tag) rc=$LASTEXITCODE -----"

  # 重出裁定：★必须 --needle-format chat 且写入口径标注文件名（不覆盖历史 raw 裁定）
  Say "===== 重出裁定 $($t.Tag)（baseline=soup-a050，口径=chat）====="
  & $py scripts\topup_verdict.py --variant $t.Tag --baseline soup-a050 --family-base m15 `
      --needle-format chat --out "topup-verdict-$($t.Tag)-chatneedle.json" 2>&1 |
    Select-String -Pattern 'PASS|FAIL|决策|MUST|阻断|未测|Traceback' |
    ForEach-Object { Say $_.Line }
}

Say "===== objective ② 重测结束 ====="
