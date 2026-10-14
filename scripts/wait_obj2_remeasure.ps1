# 等待 objective ② 重测结束（供 DSH 后台作业追踪用）
#
# 背景：重测器 obj2_remeasure.ps1 是用 Start-Process 脱离启动的，
#       DSH 无法对其产生完成通知 ⇒ 用本作业**等到它结束并汇总结果**，
#       这样"每个后台作业都有 id 与结论"的纪律才成立。
[CmdletBinding()]
param([int]$MaxWaitMin = 90)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$log = "$root\reports\logs\obj2-remeasure.log"
$deadline = (Get-Date).AddMinutes($MaxWaitMin)

Write-Host "等待 objective ② 重测结束（最长 $MaxWaitMin min）..."
while ((Get-Date) -lt $deadline) {
  $running = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'obj2_remeasure\.ps1' })
  if ($running.Count -eq 0) { Write-Host "重测进程已消失。"; break }
  Start-Sleep -Seconds 30
}

Write-Host "`n===== 重测日志汇总 ====="
if (Test-Path $log) {
  Get-Content $log | Select-String -Pattern '重测启动|=====|rc=|PASS|FAIL|决策|MUST|阻断|未测|Traceback|中止' |
    ForEach-Object { $_.Line }
}
Write-Host "`n===== objective ② 关键产物 ====="
foreach ($t in 'm25full', 'm2full') {
  foreach ($pat in @("scored-chat-to-$t-v2.json", "longctx-$t-chat.json",
                     "ppl-$t-v0.4.json", "topup-verdict-$t-chatneedle.json")) {
    $p = "$root\reports\$pat"
    $e = Test-Path $p
    $sz = if ($e) { "{0,9:N0} B" -f (Get-Item $p).Length } else { '        -' }
    Write-Host ("  {0,-42} {1}  {2}" -f $pat, $(if ($e) { '有' } else { '缺' }), $sz)
  }
}
Write-Host "`nOBJ2-REMEASURE-WAIT=DONE"
