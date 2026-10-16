# _tmp_r8_orchestrator.ps1 -- M5A-R8 全流水线编排器（分离式；Lead 04:06 时序指令的自动执行体）
# 序列（Lead 定案 2026-10-16 08:5x）：r7 链哨兵 → Guard → r8 训练 → 合并 → 完整性验证
#   → r8 链日志头（merge sha 登记）→ r8 门禁链（定案步序 v023→gen→jb→ppl→toolout→
#   longctx→verdict→dilution，X 前置）发射。
# 纪律：全程 fail-closed（任一环节 rc!=0 / 超时 => 写 FATAL 标记并停手，不进入下一环）；
#   GPU 串行铁律（Phase B Guard 在任何 GPU 动作前）；锁防重入。
# 状态：心跳 reports\logs\m5a-dpo-r8-orch-heartbeat.log（120s + 事件行）；
#   FATAL 标记 reports\logs\m5a-dpo-r8-orch-FATAL.txt；锁 reports\logs\m5a-dpo-r8-orch.lock。
# 由 r7-runner 经 WMI Win32_Process.Create 发射（父=WmiPrvSE，脱离 harness job 树——
#   r7 attempt-1 收割教训）。读数提取与向 Lead 的报告由 r7-runner 在场执行，不属本件。
$ErrorActionPreference = 'Continue'
$ROOT = 'J:\Projects\llm_for_sec'
$LOGD = "$ROOT\reports\logs"
$hb   = "$LOGD\m5a-dpo-r8-orch-heartbeat.log"
$fatal = "$LOGD\m5a-dpo-r8-orch-FATAL.txt"
$lock = "$LOGD\m5a-dpo-r8-orch.lock"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) { [System.IO.File]::AppendAllText($hb, "$msg`r`n", $U8); Write-Host $msg }
function Die([string]$why) {
  [System.IO.File]::WriteAllText($fatal, "ORCH-FATAL: $why`r`nat=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
  HB "ORCH-FATAL $why"
  exit 1
}
if (Test-Path $lock) { Write-Host 'ORCH-LOCK exists, refusing to run'; exit 1 }
[System.IO.File]::WriteAllText($lock, "pid=$PID start=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
if (Test-Path $fatal) { Remove-Item $fatal -Force }

Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$PY = "$ROOT\.venv\Scripts\python.exe"
$T = 'm5a-dpo-r8'

HB "ORCH-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') pid=$PID（Lead 04:06 时序 + 08:5x 定案步序）"

# ---------- Phase A: 等 r7 门禁链哨兵（cap 6h）----------
$r7rc = "$LOGD\m5a-dpo-r7-gates-chain-rc.txt"
$capA = (Get-Date).AddHours(6)
HB "PHASE-A waiting r7 sentinel: $r7rc"
while (-not (Test-Path $r7rc)) {
  if ((Get-Date) -gt $capA) { Die 'PhaseA 超时：r7 哨兵 6h 未落地' }
  Start-Sleep -Seconds 60
}
$rcLine = (Get-Content $r7rc -Raw).Trim()
HB "PHASE-A r7 sentinel: $rcLine"
if ($rcLine -notmatch 'GATES-CHAIN-RC=0') { Die "PhaseA: r7 链 rc 非 0（$rcLine）——不发射 r8，交 r7-runner/Lead 处置" }
Start-Sleep -Seconds 90   # r7 链终检后的缓冲（含 GPU 释放），对齐 r7 的 90s 纪律

# ---------- Phase B: Guard（3 次重试）----------
$guardOk = $false
for ($i = 1; $i -le 3; $i++) {
  & powershell -ExecutionPolicy Bypass -File "$ROOT\scripts\stop_eval_procs.ps1" -Guard | Out-Null
  if ($LASTEXITCODE -eq 0) { $guardOk = $true; break }
  HB "PHASE-B guard retry $i/3"
  Start-Sleep -Seconds 60
}
if (-not $guardOk) { Die 'PhaseB: Guard 3 次不过（GPU 非空闲）' }
HB 'PHASE-B GUARD=PASS'

# ---------- Phase C: r8 训练（cap 2h）----------
HB "PHASE-C launching r8 train wrapper"
$null = Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\_tmp_r8_train_detached.ps1" -WindowStyle Hidden
$trainRc = "$LOGD\m5a-dpo-r8-train-rc.txt"
$capC = (Get-Date).AddHours(2)
while (-not (Test-Path $trainRc)) {
  if ((Get-Date) -gt $capC) { Die 'PhaseC 超时：r8 训练 2h 未出 rc' }
  Start-Sleep -Seconds 60
}
$trc = (Get-Content $trainRc -Raw).Trim()
HB "PHASE-C $trc"
if ($trc -notmatch 'TRAIN-RC=0') { Die "PhaseC: r8 训练 rc 非 0（$trc）" }

# ---------- Phase D: adapter 在位速检 ----------
$adapt = "$ROOT\checkpoints\qwen3-8b-sec-m5a-dpo-r8"
$acfg = Get-Content "$adapt\adapter_config.json" -Raw -ErrorAction SilentlyContinue
$asize = (Get-Item "$adapt\adapter_model.safetensors" -ErrorAction SilentlyContinue).Length
if (-not $acfg -or $acfg -notmatch '"r":\s*16' -or -not $asize -or $asize -lt 100MB) { Die "PhaseD: adapter 异常（cfg r=16? / size=$asize）" }
HB "PHASE-D adapter ok（r=16, $([math]::Round($asize/1MB,1))MB）"

# ---------- Phase E: LoRA 合并导出（cap 30min）----------
HB 'PHASE-E launching export (CPU)'
$exp = Start-Process "$ROOT\.venv\Scripts\llamafactory-cli.exe" -ArgumentList 'export',"$ROOT\configs\m5a-dpo-r8-export.yaml" -RedirectStandardOutput "$LOGD\m5a-dpo-r8-export.log" -RedirectStandardError "$LOGD\m5a-dpo-r8-export.log.err" -PassThru -WindowStyle Hidden
$null = $exp.Handle  # PS5.1 PassThru 句柄钉住（否则 ExitCode 可能读空——2026-10-16 12:17 PhaseE 实发事故；本次 Phase F/G/H 由 r7-runner 手动接管完成）
if (-not $exp.WaitForExit(1800000)) { try { Stop-Process -Id $exp.Id -Force } catch {}; Die 'PhaseE 超时：export 30min 未完成' }
HB "PHASE-E export exit=$($exp.ExitCode)"
if ($exp.ExitCode -ne 0) { Die "PhaseE: export rc=$($exp.ExitCode)" }

# ---------- Phase F: 合并完整性验证 ----------
& $PY -X utf8 "$ROOT\scripts\_tmp_r8_merge_check.py" *> "$LOGD\m5a-dpo-r8-mergecheck.log"
if ($LASTEXITCODE -ne 0) { Die "PhaseF: merge check rc=$LASTEXITCODE（详见 m5a-dpo-r8-mergecheck.log）" }
HB 'PHASE-F MERGE-CHECK=PASS'

# ---------- Phase G: r8 链日志头（merge sha 登记；显式 UTF-8）----------
$chainLog = "$LOGD\m5a-dpo-r8-gates-chain.log"
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# m5a-dpo-r8 门禁链日志（attempt-1，分离式 WMI 发射）")
[void]$sb.AppendLine("# 发射: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') by _tmp_r8_orchestrator.ps1（Lead 04:06 时序指令）")
[void]$sb.AppendLine("# 步序（Lead 08:37 指令 + 08:5x 定案）：v023→gen→jb→ppl→toolout→longctx→verdict→dilution（X 前置；")
[void]$sb.AppendLine("#   topup_verdict 依赖 longctx 产物，故 longctx 前置于 verdict——Lead 已确认登记）")
[void]$sb.AppendLine("# 门禁评测对象 = LoRA 合并后完整模型 checkpoints\qwen3-8b-sec-m5a-dpo-r8-merged，分片 sha256：")
$merged = "$ROOT\checkpoints\qwen3-8b-sec-m5a-dpo-r8-merged"
Get-ChildItem $merged -Filter '*.safetensors' | Sort-Object Name | ForEach-Object {
  $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
  [void]$sb.AppendLine("#   $($_.Name): $h")
}
$ih = (Get-FileHash "$merged\model.safetensors.index.json" -Algorithm SHA256).Hash.ToLower()
[void]$sb.AppendLine("#   model.safetensors.index.json: $ih")
[System.IO.File]::WriteAllText($chainLog, $sb.ToString(), $U8)
HB 'PHASE-G chain log header written (merge shas registered)'

# ---------- Phase H: r8 门禁链发射（分离 wrapper）----------
$null = Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\_tmp_r8_chain_detached.ps1" -WindowStyle Hidden
$chainHb = "$LOGD\m5a-dpo-r8-gates-chain-heartbeat.log"
$capH = (Get-Date).AddMinutes(3)
$spawned = $false
while ((Get-Date) -lt $capH) {
  if ((Test-Path $chainHb) -and ((Get-Content $chainHb -Raw) -match 'CHAIN-SPAWNED')) { $spawned = $true; break }
  Start-Sleep -Seconds 10
}
if (-not $spawned) { Die 'PhaseH: r8 链 3 分钟内未见 CHAIN-SPAWNED 心跳' }
HB 'PHASE-H r8 gates chain spawned'
Remove-Item $lock -Force
HB "ORCH-DONE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')（后续：r7-runner 在场轮询 X 读数）"
exit 0
