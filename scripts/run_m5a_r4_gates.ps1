# M5A-R4 门禁链（8 步，照抄 m5a-r3 流程/仪器/命名/判分口径；产物名 m5a-dpo-r4）
# 纪律：fail-closed（任一步 rc!=0 即中止）；每 GPU 步前 Guard + 重 worker=0 双确认；
# 启动前 PREFLIGHT 15 产物 NOT-EXIST + 冻结仪器 sha 复验。
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$PY = "$ROOT\.venv\Scripts\python.exe"
$T = 'm5a-dpo-r4'
$MODEL = 'checkpoints\qwen3-06b-sec-m5a-dpo-r4'
$LOG = "$ROOT\reports\logs"

function Fail([string]$msg) { Write-Host "GATES-FATAL: $msg"; exit 1 }

function WaitIdle([string]$step) {
  for ($i = 0; $i -lt 20; $i++) {
    $heavy = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
    if ($heavy.Count -eq 0) {
      & "$ROOT\scripts\stop_eval_procs.ps1" -Guard | Out-Host
      if ($LASTEXITCODE -eq 0) { Write-Host "GUARD=PASS heavy=0 before $step"; return }
      Fail "Guard FAIL before $step"
    }
    Write-Host "waiting GPU idle (heavy=$($heavy.Count)) before ${step}..."; Start-Sleep -Seconds 30
  }
  Fail "GPU never idle before $step"
}

# ---------- Step 0: PREFLIGHT + 仪器 sha 复验 ----------
$targets = @(
  "reports\heldout-chat-v023-$T-mnt512.json", "reports\resp-chat-v023-$T-mnt512.jsonl", "reports\scored-chat-v023-$T-v2-mnt512.json",
  "reports\heldout-chat-gen-$T-mnt512.json", "reports\resp-chat-gen-$T-mnt512.jsonl", "reports\scored-chat-gen-$T-v2-mnt512.json",
  "reports\longctx-$T-chat.json", "reports\dilution-$T-v0.6.json",
  "reports\jb-resp-$T-v0.7-full.jsonl", "reports\jb-scored-$T-v0.7-full-v2.json",
  "reports\ppl-$T-v0.4.json",
  "reports\heldout-to-$T-mnt512.json", "reports\resp-chat-to-$T-mnt512.jsonl", "reports\scored-chat-to-$T-v2-mnt512.json",
  "reports\topup-verdict-$T-v023-mnt512.json"
)
foreach ($t in $targets) { if (Test-Path "$ROOT\$t") { Fail "PREFLIGHT: target exists: $t" } }
Write-Host "PREFLIGHT 15 targets NOT-EXIST ✓"
& $PY -X utf8 scripts\_tmp_m5a_r4_sha_check.py
if ($LASTEXITCODE -ne 0) { Fail 'instrument sha mismatch' }
Write-Host 'instrument sha re-verified ✓ (jb scorer / heldout scorer / jb suite / dilution pool / r4 config)'

# ---------- Step 1: v0.2.3 全量 737 ----------
WaitIdle 'step1-v023'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.2.3 --out "reports\heldout-chat-v023-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-v023-$T-mnt512.jsonl" *> "$LOG\m5g-eval-v023-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step1 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.2.3 --responses "reports\resp-chat-v023-$T-mnt512.jsonl" --out "reports\scored-chat-v023-$T-v2-mnt512.json" *> "$LOG\m5g-score-v023-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step1 score rc=$LASTEXITCODE" }
Write-Host 'STEP1 v023 eval+score DONE'

# ---------- Step 2: v0.3-gen 258 ----------
WaitIdle 'step2-gen'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.3-gen --out "reports\heldout-chat-gen-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-gen-$T-mnt512.jsonl" *> "$LOG\m5g-eval-gen-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step2 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.3-gen --responses "reports\resp-chat-gen-$T-mnt512.jsonl" --out "reports\scored-chat-gen-$T-v2-mnt512.json" *> "$LOG\m5g-score-gen-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step2 score rc=$LASTEXITCODE" }
Write-Host 'STEP2 gen eval+score DONE'

# ---------- Step 3: needle chat ----------
WaitIdle 'step3-needle'
& $PY -X utf8 scripts\probe_longctx.py --model $MODEL --name "$T-chat" --lens 16384,32768 --n-docs 4 --seed 20260924 --max-new 32 --prompt-format chat --out "reports\longctx-$T-chat.json" *> "$LOG\m5g-needle-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step3 rc=$LASTEXITCODE" }
Write-Host 'STEP3 needle DONE'

# ---------- Step 4: 稀释 v0.6 全量 384 ----------
WaitIdle 'step4-dilution'
& $PY -X utf8 scripts\probe_dilution.py --model $MODEL --name "$T-v0.6" --lens 4096,16384,32768 --seed 20261007 --prompt-format chat --out "reports\dilution-$T-v0.6.json" *> "$LOG\m5g-dilution-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step4 rc=$LASTEXITCODE" }
Write-Host 'STEP4 dilution DONE'

# ---------- Step 5: 越狱 v0.7 全量 --exclude-holdout ----------
WaitIdle 'step5-jb'
& $PY -X utf8 scripts\probe_jailbreak.py --model $MODEL --name "$T-v0.7-full" --data data\heldout\v0.7-jailbreak\jailbreak.jsonl --families all --exclude-holdout --tag "$T-v0.7-full" *> "$LOG\m5g-jb-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step5 rc=$LASTEXITCODE" }
Write-Host 'STEP5 jb DONE'

# ---------- Step 6: PPL 双轨 v0.4 ----------
WaitIdle 'step6-ppl'
& $PY -X utf8 scripts\probe_ppl.py --model $MODEL --name "$T-v0.4" --probes data\probes\v0.4 --tokenizer ".cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd" --batch-size 1 --out "reports\ppl-$T-v0.4.json" *> "$LOG\m5g-ppl-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step6 rc=$LASTEXITCODE" }
Write-Host 'STEP6 ppl DONE'

# ---------- Step 7: v0.4-toolout 70 回归 ----------
WaitIdle 'step7-toolout'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.4-toolout --out "reports\heldout-to-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-to-$T-mnt512.jsonl" *> "$LOG\m5g-eval-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step7 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.4-toolout --responses "reports\resp-chat-to-$T-mnt512.jsonl" --out "reports\scored-chat-to-$T-v2-mnt512.json" *> "$LOG\m5g-score-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step7 score rc=$LASTEXITCODE" }
Write-Host 'STEP7 toolout DONE'

# ---------- Step 8: topup verdict（CPU）----------
& $PY -X utf8 scripts\topup_verdict.py --variant $T --baseline soup-a050 --orr-heldout v023 --orr-abs-max 0.01 --needle-format chat --max-new-tokens 512 --out "topup-verdict-$T-v023-mnt512.json" *> "$LOG\m5g-verdict-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step8 rc=$LASTEXITCODE" }
Write-Host 'STEP8 verdict DONE'

# ---------- 终检：15 产物在位 ----------
$missing = @($targets | Where-Object { -not (Test-Path "$ROOT\$_") })
if ($missing.Count -gt 0) { Fail "missing artifacts: $($missing -join ', ')" }
Write-Host 'GATES-CHAIN=OK (8 steps, 15 artifacts, all rc=0)'
exit 0
