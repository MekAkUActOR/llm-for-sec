# sec-jev J 门链（v023→gen→jb × r1/r2 双臂；会话内直跑，单前向每件分钟级）
# 仪器冻结纪律：score_heldout_v2 / jb 套件 sha 零改动；needle/dilution/longctx
# 对决策形态 not-form-applicable（登记于 secjev-j-readings.md）。
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = 'J:\Projects\llm_for_sec\.cache\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONUNBUFFERED = '1'
Set-Location J:\Projects\llm_for_sec
$PY = '.venv\Scripts\python.exe'
$LOG = 'reports\logs'
New-Item -ItemType Directory -Force -Path $LOG | Out-Null

function WaitIdle($tag) {
    & powershell -ExecutionPolicy Bypass -File scripts\stop_eval_procs.ps1 -Guard | Out-Null
    Write-Host "[$tag] GPU guard PASS"
}

foreach ($arm in @('r1', 'r2')) {
    $T = "secjev-0.6b-$arm"
    $MODEL = "checkpoints\secjev-0.6b-$arm"
    Write-Host "===== ARM $T ====="

    # ---- J1: v023 ORR ----
    WaitIdle "$T-v023"
    & $PY -X utf8 scripts\secjev\render_eval.py --model $MODEL `
        --heldout data\heldout\v0.2.3 --prompt-format chat `
        --out "reports\heldout-chat-v023-$T-mnt512.json" `
        --dump-responses "reports\resp-chat-v023-$T-mnt512.jsonl" `
        *> "$LOG\secjev-v023-$T.log"
    if ($LASTEXITCODE -ne 0) { throw "v023 eval fail $T" }
    & $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.2.3 `
        --responses "reports\resp-chat-v023-$T-mnt512.jsonl" `
        --out "reports\scored-chat-v023-$T-v2-mnt512.json" `
        *> "$LOG\secjev-v023-score-$T.log"
    if ($LASTEXITCODE -ne 0) { throw "v023 score fail $T" }
    Write-Host "STEP v023 $T DONE"

    # ---- J2: gen ASR ----
    WaitIdle "$T-gen"
    & $PY -X utf8 scripts\secjev\render_eval.py --model $MODEL `
        --heldout data\heldout\v0.3-gen --prompt-format chat `
        --out "reports\heldout-chat-gen-$T-mnt512.json" `
        --dump-responses "reports\resp-chat-gen-$T-mnt512.jsonl" `
        *> "$LOG\secjev-gen-$T.log"
    if ($LASTEXITCODE -ne 0) { throw "gen eval fail $T" }
    & $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.3-gen `
        --responses "reports\resp-chat-gen-$T-mnt512.jsonl" `
        --out "reports\scored-chat-gen-$T-v2-mnt512.json" `
        *> "$LOG\secjev-gen-score-$T.log"
    if ($LASTEXITCODE -ne 0) { throw "gen score fail $T" }
    Write-Host "STEP gen $T DONE"

    # ---- J3: jb tiered ----
    WaitIdle "$T-jb"
    & $PY -X utf8 scripts\secjev\probe_jailbreak_dec.py --model $MODEL `
        --name "$T-v0.7-full" --data data\heldout\v0.7-jailbreak\jailbreak.jsonl `
        --families all --exclude-holdout --tag "$T-v0.7-full" `
        *> "$LOG\secjev-jb-$T.log"
    if ($LASTEXITCODE -ne 0) { throw "jb fail $T" }
    Write-Host "STEP jb $T DONE"
}
Write-Host 'SECJEV-GATES-CHAIN=ALL-DONE'
