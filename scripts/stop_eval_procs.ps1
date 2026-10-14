# 评测进程的**取证式**查看与停止（docs/01 规则 19 的实践工具）。
#
# ★★ 为什么需要它（2026-10-06 第 17 轮事故）：
#   我曾把**一条正常评测链**读成"两个评测在抢 GPU" ✗，白杀了一次已经跑了 13 分钟的跑批。
#   原因是：`venv\Scripts\python.exe` 在 Windows 上是 **uv 的 trampoline**
#   ⇒ **一次调用会产生两个 `python.exe` 进程**：
#       一个 ~4 MB 的薄壳 + 一个持有模型的真 worker ~2 GB
#   再加上 launcher 会**调用子脚本 powershell**（`eval_needlefix.ps1`），
#   于是一条健康的单链会同时匹配 4 个进程 ✗。
#
# ★判据（这是本工具的核心）：
#   **并发与否，要看"重 worker 数量"和"GPU 是否被模型占满"，**
#   **不是看匹配进程数。**
#     - 正常：重 worker = 1，GPU ≈ 一个模型（0.6B ⇒ ~3.2 GB）
#     - 真并发：重 worker ≥ 2（或 GPU 明显超过单模型量级）
#
# 用法：
#   ... -File scripts\stop_eval_procs.ps1 -Tree            # 只看进程树（推荐先跑）
#   ... -File scripts\stop_eval_procs.ps1 -WhatIfOnly      # 看会杀谁，不真杀
#   ... -File scripts\stop_eval_procs.ps1 -Guard           # 若检测到重 worker ≥2 则 rc=1
#   ... -File scripts\stop_eval_procs.ps1                  # 停止（排除自身+祖先）
[CmdletBinding()]
param(
  [string]$Pattern = 'recaliber_mnt|eval_needlefix|baseline_eval|probe_longctx|score_heldout',
  [switch]$WhatIfOnly,
  [switch]$Tree,
  [switch]$Guard,
  [double]$HeavyMB = 500
)
$ErrorActionPreference = 'Continue'

$anc = New-Object System.Collections.Generic.HashSet[int]
$cur = $PID
for ($i = 0; $i -lt 12; $i++) {
  [void]$anc.Add($cur)
  try {
    $q = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction Stop
    if (-not $q -or -not $q.ParentProcessId) { break }
    $cur = [int]$q.ParentProcessId
  } catch { break }
}

$all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
$rel = @($all | Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern })

function Brief($cl, $n = 60) {
  if (-not $cl) { return '' }
  $s = ($cl -replace '\s+', ' ')
  if ($s.Length -gt $n) { $s = $s.Substring($s.Length - $n) }
  return $s
}

if ($Tree) {
  Write-Host "=== 匹配 '$Pattern' 的进程（含自身/祖先，标注是否受保护）$($rel.Count) 个 ==="
  foreach ($p in $rel | Sort-Object ProcessId) {
    $ws = [math]::Round($p.WorkingSetSize / 1MB)
    $prot = if ($anc.Contains([int]$p.ProcessId)) { ' [保护]' } else { '' }
    $tag = if ($ws -ge $HeavyMB) { '  ★重worker' } elseif ($p.Name -eq 'python.exe') { '  (trampoline?)' } else { '' }
    Write-Host ("  pid={0,-6} 父={1,-6} {2,-13} {3,6} MB{4}{5}" -f `
      $p.ProcessId, $p.ParentProcessId, $p.Name, $ws, $tag, $prot)
    Write-Host ("        {0}" -f (Brief $p.CommandLine 100))
  }
}

# ★核心判据：重 worker 数（不是匹配数）
$heavy = @($all | Where-Object {
  $_.Name -eq 'python.exe' -and $_.WorkingSetSize -gt ($HeavyMB * 1MB)
})
Write-Host ""
Write-Host "=== 判据：重 worker（>${HeavyMB}MB 的 python.exe）==="
Write-Host "  重 worker 数 = $($heavy.Count)  pid=$($heavy.ProcessId -join ',')"
Write-Host "  ⇒ $($heavy.Count) 个 ≈ 正常单链；≥2 个才是真并发 ✗"
Write-Host "  匹配进程数 = $($rel.Count)（★这个数不能用来判并发：trampoline/包装shell/子脚本都会计入）"

if ($Guard) {
  if ($heavy.Count -ge 2) {
    Write-Host "GUARD=FAIL 检测到 $($heavy.Count) 个重 worker ⇒ 真并发"
    exit 1
  }
  Write-Host "GUARD=PASS 无并发（重 worker ≤1）"
  exit 0
}

if ($Tree) { exit 0 }

$targets = @($rel | Where-Object { -not $anc.Contains([int]$_.ProcessId) })
if (-not $targets) { Write-Host "无可停目标"; exit 0 }
foreach ($t in $targets) {
  Write-Host ("  {0} pid={1}  {2}" -f `
    $(if ($WhatIfOnly) { '[dry]' } else { '[kill]' }), $t.ProcessId, (Brief $t.CommandLine 70))
  if (-not $WhatIfOnly) { Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue }
}
Write-Host "MATCHED=$($targets.Count)"
