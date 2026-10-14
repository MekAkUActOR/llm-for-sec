"""T6 manifest 追加（M2.5 备料）——严格 append-only：以追加模式写入 3 行，
写入前后校验既有 51 行逐字节不变。"""
import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"

ENTRIES = [
    {
        "id": "t6_devign",
        "name": "t6_devign",
        "url": "https://codeload.github.com/epicosy/devign (tarball master da611bf3; original soarsmu/Devign & software-research/Devign 404 as of 2026-09-28)",
        "license": "MIT (epicosy/devign repository LICENSE verbatim, Copyright (c) 2020 Eduard - mirror of the Devign paper code+data release)",
        "tier": "public",
        "domain": "security",
        "lang": "en",
        "est_tokens": 18448064,
        "docs": 27318,
        "status": "ingested",
        "ingested_at": "2026-09-28",
        "files": ["data/corpora/clean/t6_devign.jsonl",
                  "data/corpora/raw/t6/devign"],
        "notes": "Devign (Zhou et al., NeurIPS 2019): FFmpeg 9,769 + qemu 17,549 function-level samples; target=1 vulnerable 12,460 / clean 14,858. T6 vuln-locate key sparse source for M2.5 task_single backfill (docs/research/m25-backfill-plan.md). github.com:443 dead on this network (git clone timeout); tarball via codeload.github.com. Provenance+sha256: data/corpora/raw/t6/provenance.json. Contamination: 8-gram matcher v3 vs FULL probes(v0.1/v0.1.1/v0.3/ais-500-draft)+heldout(v0.1/v0.2/v0.2.1) baseline - zero flagged (reports/t6-contamination-check.json). D3: MIT, attribution on model release.",
    },
    {
        "id": "t6_devign_lines",
        "name": "t6_devign_lines",
        "url": "https://hf-mirror.com/datasets/DetectVul/devign (train 21,854 + validation 2,732 + test 2,732)",
        "license": "MIT (upstream Devign dataset); derivative line annotation from DetectVul (Tran et al., FGCS 2024, doi:10.1016/j.future.2024.107504) - mirror card carries no explicit license, recorded as research derivative of MIT upstream, D3 re-eval before open weights",
        "tier": "public",
        "domain": "security",
        "lang": "en",
        "est_tokens": 6199675,
        "docs": 10039,
        "status": "ingested",
        "ingested_at": "2026-09-28",
        "files": ["data/corpora/clean/t6_devign_lines.jsonl",
                  "data/corpora/raw/t6/devign-lines"],
        "notes": "Line-annotated Devign derivative: target=1 functions with vul_lines line_no (verified 1-based onto raw func lines, 324/324 spot check); docs render function with '>> ' prefix marks on vulnerable lines - direct gold for T4/T6 vulnerability LOCALIZATION (m1 task_single T6 deficit 11.6K). Contamination: zero flagged vs full probes+heldout baseline. Provenance+sha256: data/corpora/raw/t6/provenance.json.",
    },
    {
        "id": "t6_cvefixes",
        "name": "t6_cvefixes",
        "url": "https://doi.org/10.5281/zenodo.13118970 (canonical CVEfixes v1.0.8, CC-BY-4.0); procured via https://hf-mirror.com/datasets/hitoshura25/cvefixes (commit-level parquet extract)",
        "license": "CC-BY-4.0 (CVEfixes v1.0.8, Zenodo DOI 10.5281/zenodo.13118970 - canonical data license governs; HF mirror card claims apache-2.0, discrepancy recorded; attribution required on model release)",
        "tier": "public",
        "domain": "security",
        "lang": "en",
        "est_tokens": 20720543,
        "docs": 11424,
        "status": "ingested",
        "ingested_at": "2026-09-28",
        "files": ["data/corpora/clean/t6_cvefixes.jsonl",
                  "data/corpora/raw/t6/cvefixes"],
        "notes": "CVEfixes v1.0.8 commit-level records (Bhandari et al., MSR 2021): 12,987 fix commits / 11,726 CVEs / 4,205 repos; doc = CVE meta + CWE id + commit message + fix diff. Dropped: 319 (cve,commit,files) dupes, 872 empty-diff, 204 diff>256KB (vendored churn), 168 contamination-flagged. Zenodo 12.1GB zip tested reachable (1.30 MB/s, ETA ~156min) but deferred - parquet extract sufficient; md5 of canonical zip recorded in provenance.json. Contamination lessons: round-1 2,248 flags = official MITRE CWE canonical names shared with GHSL sec-probes (fixed clean-side: cwe_id only, names recoverable from c0_cwe.jsonl); round-2 168 = CWE names inside NVD descriptions + PHP/Go import boilerplate shared with GHSL advisory code (excluded per 2026-09-26 boilerplate-collision precedent); final zero flagged. Top CWEs: CWE-79/125/787/20/89/22/119/476.",
    },
]


def main() -> int:
    before = MANIFEST.read_bytes()
    n_before = before.count(b"\n")
    prefix_sha = hashlib.sha256(before).hexdigest()
    print(f"before: {n_before} lines, sha256 {prefix_sha[:16]}")

    with open(MANIFEST, "a", encoding="utf-8", newline="\n") as f:
        for e in ENTRIES:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    after = MANIFEST.read_bytes()
    # 追加不变性断言：既有内容是 after 的逐字节前缀
    assert after.startswith(before), "APPEND-ONLY VIOLATED: prefix changed"
    n_after = after.count(b"\n")
    print(f"after:  {n_after} lines (+{n_after - n_before}), "
          f"prefix intact: {after[:len(before)] == before}")

    # 逐行 JSON 合法性 + 新条目字段断言
    names = []
    for line in after.decode("utf-8").splitlines():
        j = json.loads(line)
        names.append(j["name"])
    assert names[-3:] == ["t6_devign", "t6_devign_lines", "t6_cvefixes"]
    for e in ENTRIES:
        for k in ("id", "name", "url", "license", "tier", "domain", "lang",
                  "est_tokens", "docs", "status", "ingested_at", "files",
                  "notes"):
            assert e.get(k) not in (None, ""), f"{e['name']}: field {k}"
    print("manifest append OK; license/est_tokens/url/date all present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
