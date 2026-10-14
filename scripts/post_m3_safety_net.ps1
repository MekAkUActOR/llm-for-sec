# M3 后评测链的**弹性安全网**：只在链未产出有效裁定时才动作，并先等 GPU 真正清空。
#
# 为什么需要它（不修改 eval_m3_post.ps1 的理由）：eval_m3_post.ps1 是本项目**唯一**的
# 评测路径（single source of truth），此刻已有守候器 wait_then_post_m3.ps1 武装着它。
# 直接改它，一旦引入语法/编码错误就会让整条链失效——**风险大于收益**。
# 因此把"重试"放在**外层**：本脚本只做三件事：
#   1) 若 `reports\topup-verdict-<Tag>.json` 已是**有效裁定**（非 PENDING/未测），直接退出 0；
#   2) 否则**等到 GPU 真正清空**（进程消失 + 显存 <2048 MiB，最多 $MaxWaitMin 分钟）；
#   3) 再调用 eval_m3_post.ps1（它自带同样校验；此时必然通过）。
#
# 这覆盖的真实失败模式：训练进程退出后显存因 WDDM 漂移未立即释放 ⇒
# 守候器一次性调用的链在串行前置校验处 exit 2 ⇒ M3 永不被评测。
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\post_m3_safety_net.ps1
#   ... -File scripts\post_m3_safety_net.ps1 -MaxWaitMin 240 -Tag m3-dpo
[CmdletBinding()]
param(
  [string]$Tag = 'm3-dpo',
  [string]$Model = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo',
  [string]$Baseline = 'soup-a050',
  [int]$MaxWaitMin = 240,
  [int]$PollSec = 30,
  [switch]$Force
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$logdir = "$root\reports\logs"
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory -Path $logdir -Force | Out-Null }
$log = "$logdir\post-m3-safety-net.log"

function Say($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding UTF8
}

function Get-GpuJobProcs {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'llamafactory|probe_|baseline_eval|score_heldout|train ' }
}

function Get-GpuUsedMiB {
  try {
    $s = (nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>$null) -join ' '
    return [int]($s -replace '[^0-9]', '')
  } catch { return -1 }
}

# ★安全护栏（必须在任何动作之前）：若**已有**一次 eval_m3_post 调用在跑，立即退出。
# 理由：本脚本与守候器 wait_then_post_m3.ps1 都会"等 GPU 清空后启动同一条链"。
# 若两者同时武装，GPU 一清空就会**各自**启动一次 ⇒ 并发评测 ⇒ 本项目实测 10× 退化
# （docs/01 §11.7 规则 5 严格串行）。因此本脚本自我保护：只在链未被调用时才动作。
$running = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'eval_m3_post' -and $_.ProcessId -ne $PID }
if ($running) {
  Say "已有 eval_m3_post 调用在跑（PID=$(@($running.ProcessId) -join ',')）⇒ 拒绝并发，退出 0（无需本安全网）。"
  exit 0
}

# ---- 1) 已有有效裁定则不动 ----
$vj = "$root\reports\topup-verdict-$Tag.json"
if ((Test-Path $vj) -and -not $Force) {
  $txt = Get-Content $vj -Raw -ErrorAction SilentlyContinue
  if ($txt -match '"decision"\s*:\s*"(ok|worse|undecidable|PASS|FAIL)"') {
    Say "已有有效裁定（$vj，decision=$($Matches[1])）⇒ 无需重跑。用 -Force 可强制。"
    exit 0
  }
  Say "存在 $vj 但 decision 非有效值（疑似 PENDING）⇒ 继续检查是否需要重跑。"
}

# ---- 2) 等 GPU 真正清空 ----
Say "等待 GPU 清空：进程消失 **且** 显存 <2048 MiB（最长 $MaxWaitMin min，每 $PollSec s）。"
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
$cleared = $false
while ((Get-Date) -lt $deadline) {
  $procs = Get-GpuJobProcs
  $used = Get-GpuUsedMiB
  if (-not $procs -and $used -ge 0 -and $used -lt 2048) {
    Say "GPU 已清空：无 GPU 作业进程，显存 = $used MiB。"
    $cleared = $true
    break
  }
  $pn = if ($procs) { @($procs).Count } else { 0 }
  Say "未清空：GPU 作业进程数=$pn，显存=$used MiB。"
  Start-Sleep -Seconds $PollSec
}
if (-not $cleared) {
  Say "✗ 超时（$MaxWaitMin min）GPU 仍未清空 ⇒ 退出，不启动评测（避免并发，docs/01 §11.7 规则 5）。"
  exit 3
}

# ---- 3) 产物完整性 ----
if (-not (Test-Path "$Model\config.json")) {
  Say "✗ 缺 $Model\config.json ⇒ 训练未正常落盘。若为崩溃，请先从 checkpoint 无损续跑。"
  exit 2
}

# ---- 4) 调链 ----
Say "启动 eval_m3_post.ps1（Tag=$Tag, Baseline=$Baseline）"
powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_m3_post.ps1" `
  -Tag $Tag -Model $Model -Baseline $Baseline 2>&1 |
  Tee-Object -FilePath "$logdir\post-m3-safety-net-chain.log" |
  ForEach-Object { $_ }
$rc = $LASTEXITCODE
Say "评测链退出码 = $rc"

if (Test-Path $vj) {
  $txt = Get-Content $vj -Raw -ErrorAction SilentlyContinue
  if ($txt -match '"decision"\s*:\s*"([^"]+)"') { Say "裁定 decision = $($Matches[1])" }
}
Say "结束。"
exit $rc
