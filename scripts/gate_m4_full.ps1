# ═══ 全长跑跑完后，一次性补齐**完整门禁集**（第 24 轮备好）═══
#
# 用法（GPU 必须空闲；训练/评测不得并发）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate_m4_full.ps1
#
# ★ 为什么这样调
#   `eval_needlefix.ps1` 的**非** `-DecisiveOnly` 路径依次跑：
#     MUST-3/2 v0.3-gen(chat) → MUST-1 needle($NeedlePromptFormat) →
#     SHOULD v0.2.1(chat) → SHOULD v0.4-toolout(chat) → SHOULD v0.4 PPL
#   末尾 `Stop-IfFailed 'ALL'` ⇒ **任何一步失败即非零退出** ✓（不再无条件 exit 0 ✓）
#
# ★ 三个关键细节（都已按源码核实 ✓）
#   ① `-NeedlePromptFormat chat` 产出 `reports/longctx-$Tag-chat.json` ✓
#      —— 与 `raw` 口径的 `longctx-$Tag.json` **不同名** ⇒ **零覆盖** ✓
#      第 23 轮跑的是 raw ✓，而裁决的阻断项**明确要 chat** ✓ ⇒ 必须显式传 chat ✓
#   ② `-MaxNewTokens 512` ⇒ 产物名带 `-mnt512` 后缀 ✓ ⇒ 与 96 的历史读数**互不覆盖** ✓
#   ③ 脚本对**已存在**的产物会**跳过** ✓ ⇒ 用 `-Tag soup-a050` 复跑
#      **只会补出缺失的 needle@chat** ✓，既有的 scored/heldout 产物**不动** ✓
#
# ★ 顺序（决定性判据优先，docs/01 §11.6）
#   1) 全长跑产物：完整门禁集（含第一份 chat 口径 needle ✓）
#   2) 起点 soup-a050：只补 chat 口径 needle（裁决的对照组 ✓）
#   3) 官方裁决：topup_verdict.py
#
# ★ 守卫：脚本自己先查重 worker；有并发就退出，不静默继续 ✓
[CmdletBinding()]
param(
  [string]$FullTag = 'm4-capfix-full',
  [string]$FullModel = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m4-capfix-full',
  [string]$BaseTag = 'soup-a050',
  [string]$BaseModel = 'J:\Projects\llm_for_sec\checkpoints\soup-needlefix-a050',
  [int]$MaxNewTokens = 512,
  [switch]$SkipBaseline
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$guard = "$root\scripts\stop_eval_procs.ps1"

Write-Host "`n[gate-m4-full] 开始 $(Get-Date -Format 'HH:mm:ss')"
if (-not (Test-Path $FullModel)) { Write-Host "★缺模型目录：$FullModel"; exit 2 }

# ---- 守卫：不得有并发重 worker（规则 38：按重 worker 数判并发 ✓）
$g = & powershell -NoProfile -ExecutionPolicy Bypass -File $guard -Guard 2>&1
$gline = ($g | Select-String -Pattern 'GUARD=' | Select-Object -Last 1)
Write-Host "  $($gline.Line)"
if ($gline.Line -notmatch 'PASS') {
  Write-Host '★GUARD 非 PASS ⇒ 存在并发，拒绝继续（不静默继续 ✓）'
  exit 3
}

# ---- 1) 全长跑：完整门禁集
Write-Host "`n[gate-m4-full] ① 全长跑完整门禁集（$FullTag，chat 口径 needle ✓，$MaxNewTokens ✓）"
& powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_needlefix.ps1" `
    -Tag $FullTag -Model $FullModel `
    -NeedlePromptFormat chat -MaxNewTokens $MaxNewTokens 2>&1 |
  Tee-Object -FilePath "$root\reports\logs\gate-full-$FullTag.log"
$rc1 = $LASTEXITCODE
Write-Host "  ① rc=$rc1"

# ---- 2) 起点：只补 chat 口径 needle
if (-not $SkipBaseline) {
  Write-Host "`n[gate-m4-full] ② 起点补 chat needle（$BaseTag ✓，已存在产物自动跳过 ✓）"
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_needlefix.ps1" `
      -Tag $BaseTag -Model $BaseModel `
      -NeedlePromptFormat chat -MaxNewTokens $MaxNewTokens 2>&1 |
    Tee-Object -FilePath "$root\reports\logs\gate-base-$BaseTag.log"
  $rc2 = $LASTEXITCODE
  Write-Host "  ② rc=$rc2"
}

# ---- 3) 官方裁决
Write-Host "`n[gate-m4-full] ③ 官方裁决"
& "$root\.venv\Scripts\python.exe" "$root\scripts\topup_verdict.py" `
    --variant $FullTag --baseline $BaseTag `
    --family-base m15 --needle-format chat `
    --max-new-tokens $MaxNewTokens `
    --out "topup-verdict-$FullTag-mnt$MaxNewTokens.json" 2>&1 |
  Tee-Object -FilePath "$root\reports\logs\gate-verdict-$FullTag.log" |
  Select-Object -Last 45
$rc3 = $LASTEXITCODE
Write-Host "`n[gate-m4-full] 完成 $(Get-Date -Format 'HH:mm:ss')  ① rc=$rc1  ② rc=$rc2  ③ rc=$rc3"
Write-Host '★判读只有两个可能：'
Write-Host '  · 曲线末段 rewards/chosen 守住 +1 以上 ⇒ 过优化未重现 ⇒ capfix 全程成立 ✓'
Write-Host '  · 末段 chosen 掉回 ~0 且 rejected 独降 ⇒ 过优化重现 ⇒ capfix 不足，须改配比 ✓'
