# _tmp_r9_orchestrator.ps1 -- M5A-R9 post-train automation, DETACHED (r8 pattern + PhaseE Handle fix)
# Phases (fail-closed; every Die() writes FATAL + leaves lock for post-mortem):
#   A. wait TRAIN-RC=0 sentinel (cap 4h; regex over full file)
#   B. Guard x3 (GPU serial iron law)
#   C. adapter quick check (r9 = rank64 -> adapter ~4x r8; threshold >100MB safe lower bound)
#   D. export merge (CPU, cap 30min; Start-Process inline, HANDLE PINNED -- r8 PhaseE lesson)
#   E. merge check (_tmp_r9_merge_check.py)
#   F. r9 chain log header with merge sha256s (explicit UTF-8 no-BOM)
#   G. launch gates chain wrapper (WMI-style detach via Start-Process; confirm CHAIN-SPAWNED <=3min)
# Lock: reports\logs\m5a-dpo-r9-orch.lock ; heartbeat: m5a-dpo-r9-orch-heartbeat.log
$ErrorActionPreference = 'Continue'
$ROOT = 'J:\Projects\llm_for_sec'
$LOGD = "$ROOT\reports\logs"
$hbFile = "$LOGD\m5a-dpo-r9-orch-heartbeat.log"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) { [System.IO.File]::AppendAllText($hbFile, "$msg`r`n", $U8); Write-Host $msg }
function Die([string]$msg) {
  HB "ORCH-FATAL $msg"
  [System.IO.File]::WriteAllText("$LOGD\m5a-dpo-r9-orch-FATAL.txt", "ORCH-FATAL $msg @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
  exit 1
}
if (Test-Path "$LOGD\m5a-dpo-r9-orch.lock") { Die "orchestrator lock exists (previous run?)" }
[System.IO.File]::WriteAllText("$LOGD\m5a-dpo-r9-orch.lock", "pid=$PID start=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "ORCH-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') pid=$PID（r9 三杠杆轮；Lead 2026-10-20 00:2x 指令，全同 r8 纪律）"
Set-Location $ROOT

# ---------- Phase A: wait TRAIN-RC=0 ----------
$trainRc = "$LOGD\m5a-dpo-r9-train-rc.txt"
$deadline = (Get-Date).AddHours(4)
$matched = $false
while ((Get-Date) -lt $deadline) {
  if (Test-Path $trainRc) {
    $raw = Get-Content $trainRc -Raw -Encoding UTF8
    if ($raw -match 'TRAIN-RC=0') { $matched = $true; break }
    if ($raw -match 'TRAIN-RC=(-?\d+)') { Die "PhaseA: train rc=$($Matches[1]) (nonzero)" }
  }
  Start-Sleep -Seconds 180
}
if (-not $matched) { Die "PhaseA: TRAIN-RC sentinel not landed within 4h" }
HB "PHASE-A train rc=0 confirmed @ $(Get-Date -Format 'HH:mm:ss')"
Start-Sleep -Seconds 90  # buffer: filesystem settle

# ---------- Phase B: Guard x3 ----------
for ($i = 1; $i -le 3; $i++) {
  & powershell -ExecutionPolicy Bypass -File "$ROOT\scripts\stop_eval_procs.ps1" -Guard | Out-Null
  if ($LASTEXITCODE -ne 0) { Die "PhaseB: Guard FAIL (round $i)" }
  Start-Sleep -Seconds 20
}
HB 'PHASE-B GUARD=PASS x3'

# ---------- Phase C: adapter quick check ----------
$adapt = Get-ChildItem "$ROOT\checkpoints\qwen3-8b-sec-m5a-dpo-r9\adapter_model.safetensors" -ErrorAction SilentlyContinue
if (-not $adapt) { Die 'PhaseC: adapter_model.safetensors missing' }
if ($adapt.Length -lt 100MB) { Die "PhaseC: adapter too small ($([math]::Round($adapt.Length/1MB))MB < 100MB)" }
HB "PHASE-C adapter ok ($([math]::Round($adapt.Length/1MB))MB, rank64 expect ~4x r8)"

# ---------- Phase D: export merge (CPU, Handle pinned) ----------
HB 'PHASE-D launching export (CPU)'
$exp = Start-Process "$ROOT\.venv\Scripts\llamafactory-cli.exe" -ArgumentList 'export',"$ROOT\configs\m5a-dpo-r9-export.yaml" -RedirectStandardOutput "$LOGD\m5a-dpo-r9-export.log" -RedirectStandardError "$LOGD\m5a-dpo-r9-export.log.err" -PassThru -WindowStyle Hidden
$null = $exp.Handle  # PS5.1 PassThru Handle pin (r8 PhaseE lesson: unpinned ExitCode reads empty)
if (-not $exp.WaitForExit(1800000)) { Die 'PhaseD: export timeout 30min' }
$erc = $exp.ExitCode
HB "PHASE-D export exit=$erc"
if ($erc -ne 0) { Die "PhaseD: export rc=$erc" }

# ---------- Phase E: merge check ----------
& "$ROOT\.venv\Scripts\python.exe" -X utf8 "$ROOT\scripts\_tmp_r9_merge_check.py" *> "$LOGD\m5a-dpo-r9-mergecheck.log"
if ($LASTEXITCODE -ne 0) { Die "PhaseE: merge check rc=$LASTEXITCODE" }
HB 'PHASE-E MERGE-CHECK=PASS'

# ---------- Phase F: chain log header (merge sha; UTF-8 no-BOM) ----------
$merged = "$ROOT\checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged"
$chainLog = "$LOGD\m5a-dpo-r9-gates-chain.log"
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# m5a-dpo-r9 门禁链日志（attempt-1，分离式 WMI 发射；编排器 PhaseA-G 自动）")
[void]$sb.AppendLine("# 训练: TRAIN-RC=0（rank64/alpha128/1200 步 = 47% 数据消费；日志 m5a-dpo-r9-train.log；三杠杆详见 reports/r9-build-brief.md v2）")
[void]$sb.AppendLine("# 合并: export CPU bf16，MERGE-CHECK=PASS（399 权重 0 缺失 0 悬多）")
[void]$sb.AppendLine("# 步序（同 r8 定案）：v023→gen→jb→ppl→toolout→longctx→verdict→dilution（Y 前置；topup_verdict 依赖 longctx 产物）")
[void]$sb.AppendLine("# 门禁评测对象 = LoRA 合并后完整模型 checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged，分片 sha256：")
Get-ChildItem $merged -Filter '*.safetensors' | Sort-Object Name | ForEach-Object {
  $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
  [void]$sb.AppendLine("#   $($_.Name): $h")
}
$ih = (Get-FileHash "$merged\model.safetensors.index.json" -Algorithm SHA256).Hash.ToLower()
[void]$sb.AppendLine("#   model.safetensors.index.json: $ih")
[System.IO.File]::WriteAllText($chainLog, $sb.ToString(), $U8)
HB 'PHASE-F chain log header written (merge sha registered)'

# ---------- Phase G: launch gates chain wrapper ----------
HB 'PHASE-G launching gates chain wrapper'
$chainProc = Start-Process powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\_tmp_r9_chain_detached.ps1" -WindowStyle Hidden -PassThru
$null = $chainProc.Handle
$spawned = $false
$deadline2 = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $deadline2) {
  if ((Test-Path "$LOGD\m5a-dpo-r9-gates-chain-heartbeat.log") -and ((Get-Content "$LOGD\m5a-dpo-r9-gates-chain-heartbeat.log" -Raw -Encoding UTF8) -match 'CHAIN-SPAWNED')) { $spawned = $true; break }
  Start-Sleep -Seconds 15
}
if (-not $spawned) { Die 'PhaseG: CHAIN-SPAWNED not confirmed within 3min' }
HB "ORCH-DONE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')（r9 门禁链已接管；读数/终裁 = r7-runner 在场职责）"
Remove-Item "$LOGD\m5a-dpo-r9-orch.lock" -Force -ErrorAction SilentlyContinue
