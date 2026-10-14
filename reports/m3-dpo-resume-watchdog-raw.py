# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog: capture the RAW evidence trail.

Runs a fixed list of READ-ONLY commands, prints each command, its timestamp and its
captured output, and appends everything to reports/m3-dpo-resume-watchdog.raw.md.

No GPU jobs. No writes outside reports/m3-dpo-resume-watchdog*.
Re-runnable: each run appends a new timestamped block.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
OUTDIR = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
RAW = R / "m3-dpo-resume-watchdog.raw.md"
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PS = "powershell"

CMDS: list[tuple[str, str]] = [
    ("host time", "Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'"),
    ("GPU + the ONLY compute app (identification by command line, not exe name)",
     "nvidia-smi --query-gpu=memory.used,memory.total,power.draw,utilization.gpu --format=csv,noheader; "
     "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; "
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='llamafactory-cli.exe'\" | "
     "Select-Object ProcessId,Name,CreationDate,CommandLine | Format-List"),
    ("host memory / commit / the training processes",
     "Get-CimInstance Win32_OperatingSystem | Select-Object @{n='free_phys_MiB';e={[int]($_.FreePhysicalMemory/1024)}},"
     "@{n='commit_used_MiB';e={[int](($_.TotalVirtualMemorySize-$_.FreeVirtualMemory)/1024)}},"
     "@{n='commit_limit_MiB';e={[int]($_.TotalVirtualMemorySize/1024)}} | Format-List"),
    ("trainer_log.jsonl: size, mtime, first line, last line",
     "Get-Item 'checkpoints\\qwen3-06b-sec-m3-dpo\\trainer_log.jsonl' | Select-Object Length,LastWriteTime | Format-List; "
     "Get-Content 'checkpoints\\qwen3-06b-sec-m3-dpo\\trainer_log.jsonl' -TotalCount 1; "
     "Get-Content 'checkpoints\\qwen3-06b-sec-m3-dpo\\trainer_log.jsonl' -Tail 1"),
    ("checkpoint dirs (landing times are the file mtimes)",
     "Get-ChildItem 'checkpoints\\qwen3-06b-sec-m3-dpo' -Directory | Select-Object LastWriteTime,Name | Format-Table -AutoSize; "
     "Get-ChildItem 'checkpoints\\qwen3-06b-sec-m3-dpo' | Select-Object Name,Length | Format-Table -AutoSize"),
    ("the two resume lines (the primary in-band evidence of a resume)",
     "$logs='reports\\logs\\m3-dpo-resume-launch.log','reports\\logs\\m3-dpo-run.log'; "
     "foreach($l in $logs){ if(Test-Path $l){ Write-Host \"--- $l\"; "
     "Get-Content $l -Encoding Unicode | Select-String -Pattern 'Resuming training|Continuing training|global step' | "
     "Select-Object -First 6 | ForEach-Object { $_.Line } } }"),
    ("the exception/error regex sweep over both logs (expect 0)",
     "$logs='reports\\logs\\m3-dpo-resume-launch.log','reports\\logs\\m3-dpo-run.log'; "
     "foreach($p in 'Traceback','CUDA out of memory','RuntimeError','MemoryError','\\bnan\\b'){ "
     "$n=0; foreach($l in $logs){ if(Test-Path $l){ "
     "$n += (Get-Content $l -Encoding Unicode | Select-String -Pattern $p -AllMatches).Count } }; "
     "Write-Host ('{0,-22} {1}' -f $p,$n) }"),
    ("stdout DPO-metric channel: how many reward dict lines per log + their step range",
     "$logs='reports\\logs\\m3-dpo-launch.log','reports\\logs\\m3-dpo-run.log','reports\\logs\\m3-dpo-resume-launch.log'; "
     "foreach($l in $logs){ if(Test-Path $l){ $m = Get-Content $l -Encoding Unicode | Select-String -Pattern \"^\\{'loss':\"; "
     "$first=($m | Select-Object -First 1).Line; $last=($m | Select-Object -Last 1).Line; "
     "Write-Host ('{0}: n={1}' -f $l,$m.Count); Write-Host ('   first: ' + $first.Substring(0,[Math]::Min(160,$first.Length))); "
     "Write-Host ('   last : ' + $last.Substring(0,[Math]::Min(160,$last.Length))) } }"),
    ("trainer_state.json per checkpoint: global_step + how many rewards/* rows (cumulative)",
     "Get-ChildItem 'checkpoints\\qwen3-06b-sec-m3-dpo\\checkpoint-*' -Directory | ForEach-Object { "
     "$j=Get-Content (Join-Path $_.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; "
     "$rw=@($j.log_history | Where-Object { $_.'rewards/chosen' }); "
     "Write-Host ('{0}: global_step={1} n_log_history={2} rewards_rows={3} first={4} last={5}' -f "
     "$_.Name,$j.global_step,$j.log_history.Count,$rw.Count,$rw[0].step,$rw[-1].step) }"),
    ("last checkpoint's trainer_state.json max_steps + best_metric",
     "$d=(Get-ChildItem 'checkpoints\\qwen3-06b-sec-m3-dpo\\checkpoint-*' -Directory | Sort-Object {[int]($_.Name -replace '\\D','')} | Select-Object -Last 1); "
     "$j=Get-Content (Join-Path $d.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; "
     "Write-Host ('dir={0} global_step={1} max_steps={2} epoch={3} best_metric={4}' -f $d.Name,$j.global_step,$j.max_steps,$j.epoch,$j.best_metric)"),
    ("telemetry sampler: is it alive, and its head/tail",
     "Get-Content 'reports\\m3-dpo-resume-watchdog-telemetry.csv' -TotalCount 2; "
     "Get-Content 'reports\\m3-dpo-resume-watchdog-telemetry.csv' -Tail 2; "
     "(Get-Content 'reports\\m3-dpo-resume-watchdog-telemetry.csv').Count"),
    ("analysis artifacts present (size + mtime)",
     "Get-ChildItem 'reports\\m3-dpo-resume-watchdog-*' | Sort-Object Name | "
     "Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize"),
    ("protocol L: below-reference episodes + distance to the pre-registered early stop",
     f'& "{PY}" "reports\\m3-dpo-resume-watchdog-L-episodes.py"'),
    ("identity check M: loss >= log2*(1-acc)",
     f'& "{PY}" "reports\\m3-dpo-resume-watchdog-M-loss-consistency.py"'),
]


def run(ps: str) -> str:
    p = subprocess.run([PS, "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT), timeout=600)
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")
    return out.rstrip()


def main() -> int:
    blocks = [f"\n\n# RAW evidence block — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
    for title, cmd in CMDS:
        t0 = datetime.now()
        print(f"[raw] {title} ...", flush=True)
        try:
            out = run(cmd)
        except Exception as e:  # noqa: BLE001
            out = f"<<command failed: {e!r}>>"
        blocks.append(
            f"\n## {title}\n\n*command* ({t0.strftime('%H:%M:%S')}):\n```powershell\n{cmd}\n```\n\n"
            f"*output* ({datetime.now().strftime('%H:%M:%S')}):\n```\n{out}\n```\n")
    with RAW.open("a", encoding="utf-8") as f:
        f.write("".join(blocks))
    print("APPENDED", RAW, RAW.stat().st_size, "bytes total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
