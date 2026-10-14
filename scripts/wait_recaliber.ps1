# 等口径重测结束并汇总产物。用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\wait_recaliber.ps1 -MaxWaitMin 90
[CmdletBinding()]
param([int]$MaxWaitMin = 90, [int]$MaxNewTokens = 256)
$root = 'J:\Projects\llm_for_sec'
$log = "$root\reports\logs\recaliber-mnt$MaxNewTokens.log"
Write-Host "等待口径重测结束（最长 $MaxWaitMin min）..."
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $log) -and (Select-String -Path $log -Pattern '口径重测结束' -Quiet)) { break }
  Start-Sleep -Seconds 20
}
Write-Host "`n===== 口径重测日志（max_new_tokens=$MaxNewTokens）====="
if (Test-Path $log) { Get-Content $log -Tail 40 } else { Write-Host "（无日志 $log）" }
Write-Host "`n===== 关键产物 ====="
foreach ($t in 'soup-a050','m3-dpo') {
  foreach ($pat in @("scored-chat-gen-$t-v2-mnt$MaxNewTokens.json",
                     "resp-chat-gen-$t-mnt$MaxNewTokens.jsonl",
                     "scored-chat-$t-v2-mnt$MaxNewTokens.json",
                     "scored-chat-to-$t-v2-mnt$MaxNewTokens.json",
                     "topup-verdict-$t-mnt$MaxNewTokens.json")) {
    $f = "$root\reports\$pat"
    if (Test-Path $f) {
      "{0,-52} 有 {1,10:N0} B" -f $pat, (Get-Item $f).Length | Write-Host
    } else {
      "{0,-52} 缺" -f $pat | Write-Host
    }
  }
}
Write-Host "`nRECALIBER-WAIT=DONE"
