# M5A-R8 门禁链（8 步，照抄 m5a-r7 流程/仪器/命名/判分口径；产物名 m5a-dpo-r8）
# 纪律：fail-closed（任一步 rc!=0 即中止）；每 GPU 步前 Guard + 重 worker=0 双确认；
# 启动前 PREFLIGHT 15 产物 NOT-EXIST + 冻结仪器 sha 复验。
# ═══ R8 对 r7 模板的全部偏离登记（append-only 勘误；其余逐字替换）═══
#   1. $MODEL：'checkpoints\qwen3-8b-sec-m5a-dpo-r7-merged' →
#      'checkpoints\qwen3-8b-sec-m5a-dpo-r8-merged'（r8 LoRA 经 llamafactory-cli export
#      合并的完整模型目录；configs/m5a-dpo-r8-export.yaml）。
#      **本链运行前提 = r8 训练 + 合并已完成**。
#   2. Step 4 PPL --tokenizer：r7 指向 8B-Base HF 快照
#      (models--Qwen--Qwen3-8B-Base\snapshots\49e3418f…)。r8 底座 = ModelScope 对齐
#      快照 (.cache\modelscope-dl\models\Qwen--Qwen3-8B\snapshots\master)，Qwen3 家族
#      分词器同构同 vocab，改指 r8 底座快照并在此登记。
#   3. 头两行注释轮次标识 M5A-R7→M5A-R8；sha check 件名 r7→r8（其 config 行 =
#      r8 件新 sha 7d4786f43ddd043e…5149a1c2，四件冻结仪器 sha 与 r6/r7 逐字节相同）。
#   4.（继承 r7 attempt-2 落地）$env:PYTHONUNBUFFERED='1'——python 子进程 stdout 逐条
#      实时落盘（r7 attempt-1 死因诊断发现 8KB 块缓冲致日志零增长、活性无法判定；
#      零计算行为影响，同一批 print 同一判分路径仅落盘时机）。
#   5. ★步序重排（Lead 指令 2026-10-16 08:37 消息 7ec8df07；append-only 勘误
#      r8-build-brief §二）：r7 序 v023→gen→needle→dilution→jb→ppl→toolout→verdict
#      改为 v023→gen→jb→ppl→toolout→longctx→verdict→dilution。
#      动机 = X 判据相关步前置（X1/X2 源 v023/gen、X3/X4 源 jb），X 读数可在链启动
#      ~2.5-3h 提取，dilution（r7 实测 1.5-3.5h 波动项）后置不阻塞终裁。
#      **判读门限不变；15 产物清单不变（仅落盘顺序）**。
#      ⚠ 对指令原文的一处机械偏离（登记）：指令原文序为 …verdict→longctx→dilution，
#      但 topup_verdict.py needle()（L220-226）直读 longctx-<tag>-chat.json——
#      verdict 先于 longctx 运行 = 读不存在文件 = fail-closed 误触发。故 longctx
#      前置于 verdict（longctx 本身非 X 判据步，仅 ~12 分钟，不损 X 前置意图）。
#   其余（PREFLIGHT 15 目标 / WaitIdle+Guard 双确认 / 各步命令与参数 / 15 产物
#   终检 / $t 循环变量防覆写修复）与 r7 逐字相同。
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$env:PYTHONUNBUFFERED = '1'  # attempt-2: live per-item progress in m5g logs (header note 4)
$PY = "$ROOT\.venv\Scripts\python.exe"
$T = 'm5a-dpo-r8'
$MODEL = 'checkpoints\qwen3-8b-sec-m5a-dpo-r8-merged'
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
# ★ PowerShell 变量不区分大小写：循环变量不得用 $t（会覆写标签 $T）——r7 attempt-1 事故修复
if ($T -cne 'm5a-dpo-r8') { Fail "tag variable T clobbered: $T" }
Write-Host "tag intact: $T / model: $MODEL"
& $PY -X utf8 scripts\_tmp_m5a_r8_sha_check.py
if ($LASTEXITCODE -ne 0) { Fail 'instrument sha mismatch' }
Write-Host 'instrument sha re-verified ✓ (jb scorer / heldout scorer / jb suite / dilution pool / r8 config)'

# ---------- Step 1: v0.2.3 全量 737（X1 源）----------
WaitIdle 'step1-v023'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.2.3 --out "reports\heldout-chat-v023-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-v023-$T-mnt512.jsonl" *> "$LOG\m5g-eval-v023-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step1 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.2.3 --responses "reports\resp-chat-v023-$T-mnt512.jsonl" --out "reports\scored-chat-v023-$T-v2-mnt512.json" *> "$LOG\m5g-score-v023-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step1 score rc=$LASTEXITCODE" }
Write-Host 'STEP1 v023 eval+score DONE'

# ---------- Step 2: v0.3-gen 258（X2 源）----------
WaitIdle 'step2-gen'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.3-gen --out "reports\heldout-chat-gen-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-gen-$T-mnt512.jsonl" *> "$LOG\m5g-eval-gen-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step2 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.3-gen --responses "reports\resp-chat-gen-$T-mnt512.jsonl" --out "reports\scored-chat-gen-$T-v2-mnt512.json" *> "$LOG\m5g-score-gen-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step2 score rc=$LASTEXITCODE" }
Write-Host 'STEP2 gen eval+score DONE'

# ---------- Step 3: 越狱 v0.7 全量 --exclude-holdout（X3/X4 源）----------
WaitIdle 'step3-jb'
& $PY -X utf8 scripts\probe_jailbreak.py --model $MODEL --name "$T-v0.7-full" --data data\heldout\v0.7-jailbreak\jailbreak.jsonl --families all --exclude-holdout --tag "$T-v0.7-full" *> "$LOG\m5g-jb-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step3 rc=$LASTEXITCODE" }
Write-Host 'STEP3 jb DONE'

# ---------- Step 4: PPL 双轨 v0.4 ----------
WaitIdle 'step4-ppl'
& $PY -X utf8 scripts\probe_ppl.py --model $MODEL --name "$T-v0.4" --probes data\probes\v0.4 --tokenizer ".cache\modelscope-dl\models\Qwen--Qwen3-8B\snapshots\master" --batch-size 1 --out "reports\ppl-$T-v0.4.json" *> "$LOG\m5g-ppl-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step4 rc=$LASTEXITCODE" }
Write-Host 'STEP4 ppl DONE'

# ---------- Step 5: v0.4-toolout 70 回归 ----------
WaitIdle 'step5-toolout'
& $PY -X utf8 scripts\baseline_eval.py --model $MODEL --heldout data\heldout\v0.4-toolout --out "reports\heldout-to-$T-mnt512.json" --max-new-tokens 512 --prompt-format chat --dump-responses "reports\resp-chat-to-$T-mnt512.jsonl" *> "$LOG\m5g-eval-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step5 eval rc=$LASTEXITCODE" }
& $PY -X utf8 scripts\score_heldout_v2.py --heldout data\heldout\v0.4-toolout --responses "reports\resp-chat-to-$T-mnt512.jsonl" --out "reports\scored-chat-to-$T-v2-mnt512.json" *> "$LOG\m5g-score-to-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step5 score rc=$LASTEXITCODE" }
Write-Host 'STEP5 toolout DONE'

# ---------- Step 6: needle chat（verdict 的机械前置，见头注 5）----------
WaitIdle 'step6-needle'
& $PY -X utf8 scripts\probe_longctx.py --model $MODEL --name "$T-chat" --lens 16384,32768 --n-docs 4 --seed 20260924 --max-new 32 --prompt-format chat --out "reports\longctx-$T-chat.json" *> "$LOG\m5g-needle-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step6 rc=$LASTEXITCODE" }
Write-Host 'STEP6 needle DONE'

# ---------- Step 7: topup verdict（CPU；读 v023 评分件 + longctx 产物）----------
& $PY -X utf8 scripts\topup_verdict.py --variant $T --baseline soup-a050 --orr-heldout v023 --orr-abs-max 0.01 --needle-format chat --max-new-tokens 512 --out "topup-verdict-$T-v023-mnt512.json" *> "$LOG\m5g-verdict-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step7 rc=$LASTEXITCODE" }
Write-Host 'STEP7 verdict DONE'

# ---------- Step 8: 稀释 v0.6 全量 384（后置；仅五合取记录补全）----------
WaitIdle 'step8-dilution'
& $PY -X utf8 scripts\probe_dilution.py --model $MODEL --name "$T-v0.6" --lens 4096,16384,32768 --seed 20261007 --prompt-format chat --out "reports\dilution-$T-v0.6.json" *> "$LOG\m5g-dilution-$T.log"
if ($LASTEXITCODE -ne 0) { Fail "step8 rc=$LASTEXITCODE" }
Write-Host 'STEP8 dilution DONE'

# ---------- 终检：15 产物在位 ----------
$missing = @($targets | Where-Object { -not (Test-Path "$ROOT\$_") })
if ($missing.Count -gt 0) { Fail "missing artifacts: $($missing -join ', ')" }
Write-Host 'GATES-CHAIN=OK (8 steps, 15 artifacts, all rc=0)'
exit 0
