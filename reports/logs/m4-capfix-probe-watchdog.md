# M4 capfix DPO probe watchdog

- 2026-10-06 20:51:28 | step 0/300 | STARTED | procs alive (llamafactory-cli 28288, python 9124); log file 0B (tee buffering), trainer_log.jsonl writing
- 2026-10-06 20:55:31 | step 105/300 | RUNNING | ckpt-dirs=2 log=110938B
- 2026-10-06 20:59:32 | step 195/300 | RUNNING | ckpt-dirs=3 log=132738B tb=0 oom=0
- 2026-10-06 21:04:16 | step 295/300 | RUNNING | log=165066B
- 2026-10-06 21:06:30 | step 300/300 | COMPLETED (exit 0) | train_loss=0.1428 runtime=0:14:42 samples/s=5.438 | highest ckpt=checkpoint-300 | final model.safetensors + trainer_state.json present

## Phase 2: eval job pwsh-2233 (nf-eval-decisive-m4-capfix-probe-mnt512)
- 2026-10-06 21:10:46 | eval pwsh-2233 | alive=2 decisiveLog=434B genLog=1318B
- 2026-10-06 21:11:53 | eval pwsh-2233 | RUNNING (100% CPU, v0.3-gen 258 items generating) | logs block-buffered at 434B/1318B; 'python.exe :' NativeCommandError = benign stderr surfacing
- 2026-10-06 21:16:00 | eval pwsh-2233 | RUNNING | no new log lines is EXPECTED: eval_needlefix.ps1:102 Tee-Object + python block-buffered stdout when piped -> chunked output. Liveness confirmed via CPU (~60s/60s wall).
- 2026-10-06 21:18 | eval pwsh-2233 | MUST-3/2 DONE | robustness ASR = 2/168 = 1.2% (v2 attack_success); whole-suite asr=0.0119 over_refusal=0.1471 format_error=0.0078; labels report_finding=229 refuse=18 comply=9 format_error=2
- 2026-10-06 21:18 | eval pwsh-2233 | MUST-2 DONE | contract retention 157/168 (93.5%) robustness, 241/258 (93.4%) whole suite parsed VERDICT; 258/258 responded
- 2026-10-06 21:24:55 | eval pwsh-2233 | MUST-1 needle running | alive=2 needleLog=0B
- 2026-10-06 21:23 | eval pwsh-2233 | MUST-A gate PASS (topup-verdict): baseline soup-a050 8/168=4.76% vs variant 2/168=1.19%, diff -0.0357, Fisher one-sided p=0.9902 -> non-inferior, NOT proven improvement
- 2026-10-06 21:25 | eval pwsh-2233 | COMPLETED exit 0 ('DECISIVE ONLY DONE') | MUST-1 needle RAW: 16384 en=.8125 zh=.875; 32768 en=.75 zh=.875 (64 trials, 219.8s) | decision still PENDING: blocker wants needle caliber CHAT but script default NeedlePromptFormat=raw
