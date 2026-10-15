# M5B-R5 gates chain RESUME (continuation agent; predecessor died 04:25 at step 7/8 mid-load).
# Scope: steps 7 (toolout) + readings extraction + step 8 (verdict) ONLY.
# Steps 1-6 already DONE by predecessor chain (reports\logs\m5g-chain-m5b-p2rl-grpo-v5.log:
# STEP1..STEP6 DONE, all rc=0); 11 artifacts on disk under ZERO-OVERWRITE protection.
# Discipline (copy of run_m5b_r5_gates.ps1): fail-closed (any rc!=0 aborts); Guard before
# each step; PREFLIGHT NOT-EXIST for every new target before running; final 15-artifact check.
# NOTE (r4 lesson kept): this file is ASCII-only on purpose (PS 5.1 misparses BOM-less UTF-8
# CJK comments); topup_verdict --out is resolved relative to reports\ -> pass bare filename.
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$PY = "$ROOT\.venv\Scripts\python.exe"
$T = 'm5b-p2rl-grpo-v5'
$MODEL = 'checkpoints\qwen3-06b-sec-p2rl-grpo-v5'
$LOG = "$ROOT\reports\logs"

function Fail([string]$msg) { Write-Host "GATES-FATAL: $msg"; exit 1 }

function WaitIdle([string]$step) {
  for ($i = 0; $i -lt 120; $i++) {
    $heavy = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
    if ($heavy.Count -eq 0) {
      & "$ROOT\scripts\stop_eval_procs.ps1" -Guard | Out-Host
      if ($LASTEXITCODE -eq 0) { Write-Host "GUARD=PASS heavy=0 before $step"; return }
      Fail "Guard FAIL before $step"
    }
    Write-Host "waiting GPU idle (heavy=$($heavy.Count)) before ${step}..."; Start-Sleep -Seconds 30
  }
  Fail "GPU never idle before $step (60min budget)"
}

# ---------- Step 0-resume: integrity of the 11 done artifacts (zero-overwrite) ----------
$existing = @(
  "reports\heldout-chat-v023-$T-mnt512.json", "reports\resp-chat-v023-$T-mnt512.jsonl", "reports\scored-chat-v023-$T-v2-mnt512.json",
  "reports\heldout-chat-gen-$T-mnt512.json", "reports\resp-chat-gen-$T-mnt512.jsonl", "reports\scored-chat-gen-$T-v2-mnt512.json",
  "reports\longctx-$T-chat.json", "reports\dilution-$T-v0.6.json",
  "reports\jb-resp-$T-v0.7-full.jsonl", "reports\jb-scored-$T-v0.7-full-v2.json",
  "reports\ppl-$T-v0.4.json"
)
foreach ($e in $existing) { if (-not (Test-Path "$ROOT\$e")) { Fail "existing artifact MISSING: $e" } }
Write-Host 'RESUME-INTEGRITY: 11 predecessor artifacts IN-PLACE (zero-overwrite) OK'

# ---------- PREFLIGHT: the 4 remaining targets must NOT exist ----------
$targets = @(
  "reports\heldout-to-$T-mnt512.json", "reports\resp-chat-to-$T-mnt512.jsonl", "reports\scored-chat-to-$T-v2-mnt512.json",
  "reports\topup-verdict-$T-v023-mnt512.json"
)
foreach ($tgt in $targets) { if (Test-Path "$ROOT\$tgt") { Fail "PREFLIGHT: target exists: $tgt" } }
Write-Host 'PREFLIGHT 4 remaining targets NOT-EXIST OK'
if (-not (Test-Path "$ROOT\$MODEL\model.safetensors")) { Fail "model not found: $MODEL\model.safetensors" }
Write-Host "model Test-Path OK: $MODEL (root endpoint model.safetensors)"
if ($T -cne 'm5b-p2rl-grpo-v5') { Fail "tag variable T clobbered: $T" }
Write-Host "tag intact: $T / model: $MODEL"
& $PY -X utf8 scripts\_tmp_m5b_r5_sha_check.py
if ($LASTEXITCODE -ne 0) { Fail 'instrument sha mismatch' }
Write-Host 'instrument sha re-verified OK (jb scorer / heldout scorer / jb suite / dilution pool / rlvr pool)'

# ---------- Step 7: v0.4-toolout 70 regression (rerun of dead step; eval-to log overwritten) ----------
WaitIdle 'step7-toolout'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.4-toolout --out "reports\heldout-to-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-to-$T-mnt512.jsonl" *> "$LOG\m5g-eval-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step7 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.4-toolout --responses "reports\resp-chat-to-$T-mnt512.jsonl" --out "reports\scored-chat-to-$T-v2-mnt512.json" *> "$LOG\m5g-score-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step7 score rc=$LASTEXITCODE" }
Write-Host 'STEP7 toolout DONE'

# ---------- Step 7b: readings extraction (all 15 artifacts minus verdict; verdict read after step 8) ----------
$readlogs = @('m5g-readings-m5b-r5-partial.log', 'm5g-readings-m5b-r5-full.log', 'm5g-readings-m5b-r5-toolout.log', 'm5g-readings-m5b-r5-reploop.log')
foreach ($rl in $readlogs) { if (Test-Path "$LOG\$rl") { Fail "PREFLIGHT: readings log exists: $rl" } }
& "$ROOT\scripts\stop_eval_procs.ps1" -Guard | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'Guard FAIL before readings' }
Write-Host 'GUARD=PASS before readings'
& $PY -X utf8 scripts\_tmp_m5_readings.py --tag $T --v023 "reports\scored-chat-v023-$T-v2-mnt512.json" --v023-resp "reports\resp-chat-v023-$T-mnt512.jsonl" --dilution "reports\dilution-$T-v0.6.json" --needle "reports\longctx-$T-chat.json" *> "$LOG\m5g-readings-m5b-r5-partial.log"
if ($LASTEXITCODE -ne 0) { Fail "readings partial rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\_tmp_m5_readings.py --tag $T --v023 "reports\scored-chat-v023-$T-v2-mnt512.json" --v023-resp "reports\resp-chat-v023-$T-mnt512.jsonl" --dilution "reports\dilution-$T-v0.6.json" --needle "reports\longctx-$T-chat.json" --jb-scored "reports\jb-scored-$T-v0.7-full-v2.json" --jb-resp "reports\jb-resp-$T-v0.7-full.jsonl" *> "$LOG\m5g-readings-m5b-r5-full.log"
if ($LASTEXITCODE -ne 0) { Fail "readings full rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\_tmp_m5r2_toolout.py $T m5b-p2rl-grpo-v4 soup-a050 *> "$LOG\m5g-readings-m5b-r5-toolout.log"
if ($LASTEXITCODE -ne 0) { Fail "readings toolout rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\_tmp_m5r5_reploop.py $T m5b-p2rl-grpo-v4 *> "$LOG\m5g-readings-m5b-r5-reploop.log"
if ($LASTEXITCODE -ne 0) { Fail "readings reploop rc=$LASTEXITCODE" }
Write-Host 'READINGS extraction DONE (partial/full/toolout/reploop)'

# ---------- Step 8: topup verdict (CPU; --out bare name = resolved under reports\, r4 lesson) ----------
& "$ROOT\scripts\stop_eval_procs.ps1" -Guard | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'Guard FAIL before verdict' }
Write-Host 'GUARD=PASS before verdict'
& $PY -X utf8 scripts\topup_verdict.py --variant $T --baseline soup-a050 --orr-heldout v023 --orr-abs-max 0.01 --needle-format chat --max-new-tokens 512 --out "topup-verdict-$T-v023-mnt512.json" *> "$LOG\m5g-verdict-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step8 rc=$LASTEXITCODE" }
Write-Host 'STEP8 verdict DONE'

# ---------- Final check: all 15 artifacts in place ----------
$missing = @($targets | Where-Object { -not (Test-Path "$ROOT\$_") })
if ($missing.Count -gt 0) { Fail "missing artifacts: $($missing -join ', ')" }
Write-Host 'GATES-RESUME=OK (steps 7+8 + readings; 4 new artifacts; all rc=0; 15/15 artifacts on disk)'
exit 0
