# -*- coding: utf-8 -*-
"""P1 探测第六轮(收尾):Oracle 链接复查、RHSA 占比、MSRC 单文档大小、GHSL 新址、CSAF 单文件。"""
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")
UA = "llm-for-sec-research/0.1 (corpus feasibility probe)"


def fetch(url, timeout=25, max_bytes=1048576, via="urllib"):
    t0 = time.perf_counter()
    if via == "curl":
        try:
            p = subprocess.run(["curl.exe", "-sSL", "--noproxy", "*", "--max-time", str(timeout),
                                "-A", UA, "-w", "\n__M__%{http_code}|%{time_total}|%{size_download}", url],
                               capture_output=True, timeout=timeout + 10)
            m = re.search(rb"__M__(\d+)\|([\d.]+)\|(\d+)\s*$", p.stdout)
            return {"status": int(m.group(1)) if m and m.group(1).isdigit() else None,
                    "ms": int((time.perf_counter() - t0) * 1000), "data": p.stdout[:max_bytes],
                    "stderr": p.stderr.decode("utf-8", "replace")[:200]}
        except Exception as e:
            return {"status": None, "ms": int((time.perf_counter() - t0) * 1000), "data": b"", "error": str(e)}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            return {"status": r.status, "ms": int((time.perf_counter() - t0) * 1000),
                    "data": r.read(max_bytes), "final_url": r.url}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "ms": int((time.perf_counter() - t0) * 1000), "data": b"", "error": str(e.reason)}
    except Exception as e:
        return {"status": None, "ms": int((time.perf_counter() - t0) * 1000), "data": b"",
                "error": f"{type(e).__name__}: {e}"}


print("== A. Oracle 本地样本复查 ==", flush=True)
for f in [r"J:\Projects\llm_for_sec\docs\research\_oracle_alerts_index_sample.html",
          r"J:\Projects\llm_for_sec\docs\research\_oracle_archive_index.html"]:
    try:
        d = open(f, "rb").read().decode("utf-8", "replace")
    except FileNotFoundError:
        print(f, "missing", flush=True)
        continue
    links = sorted(set(re.findall(r'href="([^"]*\.html)"', d)))
    alertish = [l for l in links if re.search(r"(cpu|alert|bulletin)", l, re.I)]
    print(f.split("\\")[-1], len(d), "bytes;", len(links), "html links;", len(alertish), "alert-ish", flush=True)
    for l in alertish[:30]:
        print("   ", l, flush=True)

print("== B. Red Hat 2023 rhsa/rhba 占比 + CSAF 单文件大小 ==", flush=True)
r = fetch("https://security.access.redhat.com/data/csaf/v2/advisories/2023/", via="curl", max_bytes=4194304)
if r.get("status") == 200:
    names = re.findall(rb'href="((rh[a-z]+)-2023_[0-9]+\.json)"', r["data"])
    from collections import Counter
    c = Counter(p.decode() for _, p in names)
    print("2023 prefix counts:", dict(c), flush=True)
f1 = fetch("https://security.access.redhat.com/data/csaf/v2/advisories/2023/rhsa-2023_7886.json", via="curl", max_bytes=65536)
print("rhsa-2023_7886.json:", json.dumps({"status": f1.get("status"), "bytes": len(f1.get("data", b"")), "ms": f1.get("ms")}), flush=True)
if f1.get("status") == 200 and f1.get("data"):
    print("  head:", f1["data"][:220].decode("utf-8", "replace").replace("\n", " "), flush=True)

print("== C. MSRC 单文档大小(带响应头)==", flush=True)
for yid in ["2025-Jan", "2026-Sep", "2010-Jan"]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(["curl.exe", "-sSL", "--noproxy", "*", "--max-time", "60", "-A", UA,
                            "-r", "0-0", "-o", "NUL", "-D", "-", f"https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/{yid}"],
                           capture_output=True, text=True, timeout=70)
        cl = re.search(r"(?im)content-length:\s*(\d+)", p.stdout)
        cr = re.search(r"(?im)content-range:\s*\S+", p.stdout)
        print(json.dumps({"id": yid, "content_length": cl.group(1) if cl else None,
                          "content_range": cr.group(0) if cr else None,
                          "ms": int((time.perf_counter() - t0) * 1000)}), flush=True)
    except Exception as e:
        print("msrc size err", yid, e, flush=True)

print("== D. GHSL 新址 ==", flush=True)
for u in ["https://securitylab.github.com/", "https://securitylab.github.com/for-llms/",
          "https://securitylab.github.com/advisories/"]:
    r = fetch(u, via="urllib", max_bytes=131072)
    print(json.dumps({"url": u, "status": r.get("status"), "ms": r.get("ms"),
                      "bytes": len(r.get("data", b"")), "final": r.get("final_url"),
                      "err": r.get("error")}), flush=True)
    if r.get("status") == 200 and r.get("data"):
        d = r["data"].decode("utf-8", "replace")
        title = re.search(r"<title>([^<]+)</title>", d)
        print("   title:", title.group(1) if title else None, flush=True)
        for pat in ["llms.txt", "posts/", "research/"]:
            if pat in d:
                print("   contains:", pat, flush=True)
r = fetch("https://securitylab.github.com/llms.txt", max_bytes=262144)
print("llms.txt:", json.dumps({"status": r.get("status"), "bytes": len(r.get("data", b""))}), flush=True)
if r.get("status") == 200 and r.get("data"):
    print(r["data"][:800].decode("utf-8", "replace"), flush=True)
print("DONE6")
