# M5A-R9-TMPL 门禁链（3 步，模板错配隔离实验；reports/r9-tmpl-brief.md 预注册冻结）
# 评测对象 = checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged-notmpl（权重与 r9-merged 逐字节同；
#   仅 chat_template.jinja 无条件空 think 预填；sha b4d28698abae8273...c1323333 已登记）。
# 步序（Lead 2026-10-20 11:3x 指令，时间盒 ~3h）：jb（Y3'/Y4' 主源）→ toolout（Y4' 第二源）→ gen（Y2'）。
#   v023 跳过（Y1' 记录项性质，737 条太长）；ppl/needle/verdict/dilution 不在本臂范围。
# 纪律：fail-closed；每 GPU 步前 WaitIdle+Guard 双确认；PREFLIGHT 8 产物 NOT-EXIST + 仪器 sha 复验
#   （五件冻结 + r9 config sha 不变——notmpl = 评测侧工件，非训练配置变更）。
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$env:PYTHONUNBUFFERED = '1'
$PY = "$ROOT\.venv\Scripts\python.exe"
$T = 'm5a-dpo-r9-notmpl'
$MODEL = 'checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged-notmpl'
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
  "reports\jb-resp-$T-v0.7-full.jsonl", "reports\jb-scored-$T-v0.7-full-v2.json",
  "reports\heldout-to-$T-mnt512.json", "reports\resp-chat-to-$T-mnt512.jsonl", "reports\scored-chat-to-$T-v2-mnt512.json",
  "reports\heldout-chat-gen-$T-mnt512.json", "reports\resp-chat-gen-$T-mnt512.jsonl", "reports\scored-chat-gen-$T-v2-mnt512.json"
)
foreach ($tgt in $targets) { if (Test-Path "$ROOT\$tgt") { Fail "PREFLIGHT: target exists: $tgt" } }
Write-Host 'PREFLIGHT 8 targets NOT-EXIST OK (jb 2 + toolout 3 + gen 3; jb/toolout/gen 族)'
if ($T -cne 'm5a-dpo-r9-notmpl') { Fail "tag variable T clobbered: $T" }
Write-Host "tag intact: $T / model: $MODEL"
$tmplSha = (Get-FileHash "$ROOT\$MODEL\chat_template.jinja" -Algorithm SHA256).Hash.ToLower()
if ($tmplSha -ne 'b4d28698abae82732da6a74bb08a623934fa81b775aea50908246e9fc1323333') { Fail "notmpl chat_template.jinja sha mismatch: $tmplSha" }
Write-Host 'notmpl chat_template.jinja sha verified OK'
& $PY -X utf8 scripts\_tmp_m5a_r9_sha_check.py
if ($LASTEXITCODE -ne 0) { Fail 'instrument sha mismatch' }
Write-Host 'instrument sha re-verified OK (jb scorer / heldout scorer / jb suite / dilution pool / r9 config)'

# ---------- Step 1: 越狱 v0.7 全量 --exclude-holdout（Y3'/Y4' 主源）----------
WaitIdle 'step1-jb'
& $PY -X utf8 scripts\probe_jailbreak.py --model $MODEL --name "$T-v0.7-full" --data data\heldout\v0.7-jailbreak\jailbreak.jsonl --families all --exclude-holdout --tag "$T-v0.7-full" *> "$LOG\m5g-jb-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step1 rc=$LASTEXITCODE" }
Write-Host 'STEP1 jb DONE'

# ---------- Step 2: v0.4-toolout 70 回归（Y4' 第二源）----------
WaitIdle 'step2-toolout'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.4-toolout --out "reports\heldout-to-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-to-$T-mnt512.jsonl" *> "$LOG\m5g-eval-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step2 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.4-toolout --responses "reports\resp-chat-to-$T-mnt512.jsonl" --out "reports\scored-chat-to-$T-v2-mnt512.json" *> "$LOG\m5g-score-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step2 score rc=$LASTEXITCODE" }
Write-Host 'STEP2 toolout DONE'

# ---------- Step 3: v0.3-gen 258（Y2' 源）----------
WaitIdle 'step3-gen'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.3-gen --out "reports\heldout-chat-gen-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-gen-$T-mnt512.jsonl" *> "$LOG\m5g-eval-gen-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step3 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.3-gen --responses "reports\resp-chat-gen-$T-mnt512.jsonl" --out "reports\scored-chat-gen-$T-v2-mnt512.json" *> "$LOG\m5g-score-gen-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step3 score rc=$LASTEXITCODE" }
Write-Host 'STEP3 gen DONE'

# ---------- 终检：8 产物在位 ----------
$missing = @($targets | Where-Object { -not (Test-Path "$ROOT\$_") })
if ($missing.Count -gt 0) { Fail "missing artifacts: $($missing -join ', ')" }
Write-Host 'GATES-CHAIN=OK (3 steps, 8 artifacts, all rc=0)'
exit 0
