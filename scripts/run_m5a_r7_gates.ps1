# M5A-R7 门禁链（8 步，照抄 m5a-r6 流程/仪器/命名/判分口径；产物名 m5a-dpo-r7）
# 纪律：fail-closed（任一步 rc!=0 即中止）；每 GPU 步前 Guard + 重 worker=0 双确认；
# 启动前 PREFLIGHT 15 产物 NOT-EXIST + 冻结仪器 sha 复验。
# ═══ R7 对 r6 模板的全部偏离登记（append-only 勘误；其余逐字替换）═══
#   1. $MODEL：r6 值 'checkpoints\qwen3-06b-sec-m5a-dpo-r6'。逐字替换 'm5a-dpo-r6'→
#      'm5a-dpo-r7' 会得到 'checkpoints\qwen3-06b-sec-m5a-dpo-r7'——两处错：(a) 06b
#      名不实（本轮底座 8B）；(b) r7 训练走 finetuning_type: lora，output 根 = adapter
#      而非完整模型，冻结仪器（AutoModelForCausalLM 直载、无 peft）无法加载。
#      ⇒ $MODEL = 'checkpoints\qwen3-8b-sec-m5a-dpo-r7-merged'（LoRA 经
#      llamafactory-cli export 合并的完整模型目录；configs/m5a-dpo-r7-export.yaml，
#      日志 reports\logs\m5a-dpo-r7-export.log）。**本链运行前提 = 合并已完成**。
#   2. Step 6 PPL --tokenizer：r6 指向 0.6B base 快照
#      (models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb…)。8B 与 0.6B 同为 Qwen3
#      家族（分词器/vocab 同构），按任务书指示改为 8B 快照
#      (models--Qwen--Qwen3-8B-Base\snapshots\49e3418f…) 并在此登记。
#   3. 头两行注释的轮次标识 M5A-R6→M5A-R7；sha check 件名 r6→r7（其 config 行 =
#      r7 LoRA 适配件新 sha 2845b6b3…c5b3e61d，四件冻结仪器 sha 与 r6 逐字节相同）。
#   4.（attempt-2 追加，2026-10-16 03:2x，Lead 批准 R1 重发的可观测性增强）
#      新增 $env:PYTHONUNBUFFERED='1'——仅关掉 python 子进程 stdout 的 8KB 块缓冲
#      （attempt-1 死因诊断发现：逐条 print 全程憋在缓冲里，60+ 分钟日志零增长，
#      活性无法判定）。零计算行为影响（同一批 print，同一判分路径，仅落盘时机）。
#      仪器 sha 五件不动。
#   其余（PREFLIGHT 15 目标 / WaitIdle+Guard 双确认 / 8 步顺序与参数 / 15 产物
#   终检）与 r6 逐字相同。
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$env:PYTHONUNBUFFERED = '1'  # attempt-2: live per-item progress in m5g logs (header note 4)
$PY = "$ROOT\.venv\Scripts\python.exe"
$T = 'm5a-dpo-r7'
$MODEL = 'checkpoints\qwen3-8b-sec-m5a-dpo-r7-merged'
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
foreach ($tgt in $targets) { if (Test-Path "$ROOT\$tgt") { Fail "PREFLIGHT: target exists: $tgt" } }
Write-Host "PREFLIGHT 15 targets NOT-EXIST ✓"
# ★ PowerShell 变量不区分大小写：循环变量不得用 $t（会覆写标签 $T）——attempt-1 事故修复
if ($T -cne 'm5a-dpo-r7') { Fail "tag variable T clobbered: $T" }
Write-Host "tag intact: $T / model: $MODEL"
& $PY -X utf8 scripts\_tmp_m5a_r7_sha_check.py
if ($LASTEXITCODE -ne 0) { Fail 'instrument sha mismatch' }
Write-Host 'instrument sha re-verified ✓ (jb scorer / heldout scorer / jb suite / dilution pool / r7 config)'

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
& $PY -X utf8 scripts\probe_ppl.py --model $MODEL --name "$T-v0.4" --probes data\probes\v0.4 --tokenizer ".cache\huggingface\hub\models--Qwen--Qwen3-8B-Base\snapshots\49e3418fbbbca6ecbdf9608b4d22e5a407081db4" --batch-size 1 --out "reports\ppl-$T-v0.4.json" *> "$LOG\m5g-ppl-$T.log"
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
