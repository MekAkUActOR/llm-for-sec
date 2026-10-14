# -*- coding: utf-8 -*-
"""P1 探测第五轮:精确计数与剩余条款/结构核验。"""
import base64
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")
UA = "llm-for-sec-research/0.1 (corpus feasibility probe; contact: local-researcher)"
TMP = r"J:\Projects\llm_for_sec\docs\research"


def fetch(url, timeout=25, max_bytes=8388608, via="urllib", extra=None):
    t0 = time.perf_counter()
    if via == "curl":
        cmd = ["curl.exe", "-sSL", "--noproxy", "*", "--max-time", str(timeout), "-A", UA,
               "-w", "\n__CURLMETA__%{http_code}|%{time_total}|%{size_download}"]
        if extra:
            cmd = cmd[:1] + extra + cmd[1:]
        cmd.append(url)
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
            body = p.stdout
            m = re.search(rb"__CURLMETA__(\d+)\|([\d.]+)\|(\d+)\s*$", body)
            return {"url": url, "via": "curl", "status": int(m.group(1)) if m and m.group(1).isdigit() else None,
                    "ms": int((time.perf_counter() - t0) * 1000), "data": body[: max_bytes],
                    "stderr": p.stderr.decode("utf-8", "replace")[:200] if p.stderr else ""}
        except Exception as e:
            return {"url": url, "via": "curl", "status": None, "ms": int((time.perf_counter() - t0) * 1000),
                    "data": b"", "error": str(e)}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            return {"url": url, "via": "urllib", "status": r.status, "ms": int((time.perf_counter() - t0) * 1000),
                    "data": r.read(max_bytes), "final_url": r.url}
    except urllib.error.HTTPError as e:
        return {"url": url, "via": "urllib", "status": e.code, "ms": int((time.perf_counter() - t0) * 1000),
                "data": b"", "error": str(e.reason)}
    except Exception as e:
        return {"url": url, "via": "urllib", "status": None, "ms": int((time.perf_counter() - t0) * 1000),
                "data": b"", "error": f"{type(e).__name__}: {e}"}


print("== A. MSRC CVRF 文档实际大小(curl Range 0-0 读 Content-Range)==", flush=True)
for yid in ["1999-Sep", "2005-Jan", "2010-Jan", "2015-Jan", "2020-Jan", "2025-Jan", "2026-Sep"]:
    r = fetch(f"https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/{yid}", via="curl", max_bytes=4096,
              extra=["-r", "0-0"])
    hdr = r.get("data", b"")
    m = re.search(rb"(?i)content-range:\s*bytes\s+\S+/(\d+)", hdr)
    print(json.dumps({"id": yid, "status": r.get("status"),
                      "total_bytes": int(m.group(1)) if m else None}), flush=True)

print("== B. MSRC swagger.json(api.github.com,base64 解码)==", flush=True)
r = fetch("https://api.github.com/repos/microsoft/MSRC-Microsoft-Security-Updates-API/contents/docs/swagger.json")
if r.get("status") == 200:
    j = json.loads(r["data"])
    txt = base64.b64decode(j["content"]).decode("utf-8", "replace")
    print("swagger size:", len(txt), flush=True)
    info = re.search(r'"info"\s*:\s*\{.*?\}', txt, re.S)
    if info:
        print("swagger info:", info.group(0)[:600], flush=True)
    print("termsOfService present:", "termsOfService" in txt, flush=True)

print("== C. 0days-in-the-wild LICENSE ==", flush=True)
r = fetch("https://api.github.com/repos/googleprojectzero/0days-in-the-wild/contents/LICENSE")
if r.get("status") == 200:
    j = json.loads(r["data"])
    lic = base64.b64decode(j["content"]).decode("utf-8", "replace")
    print("0day LICENSE head:", json.dumps(lic[:500]), flush=True)
else:
    print("0day LICENSE status:", r.get("status"), r.get("error"), flush=True)

print("== D. GHSL 站点源定位 ==", flush=True)
r = fetch("https://api.github.com/repos/github/securitylab/branches")
if r.get("status") == 200:
    print("securitylab branches:", json.dumps([b["name"] for b in json.loads(r["data"])]), flush=True)
site = fetch("https://securitylab.github.io/", max_bytes=131072)
print("securitylab.github.io status:", site.get("status"), "bytes:", len(site.get("data", b"")), flush=True)
if site.get("status") == 200:
    gen = re.search(rb'href="(https://github\.com/[^"]+)"', site["data"])
    print("site github link:", gen.group(1).decode() if gen else None, flush=True)

print("== E. Red Hat CSAF 2023 完整计数(curl 落盘再数)==", flush=True)
r = fetch("https://security.access.redhat.com/data/csaf/v2/advisories/2023/", via="curl", max_bytes=16777216)
if r.get("status") == 200:
    n = len(set(re.findall(rb'href="([^"]+\.json)"', r["data"])))
    print("RH CSAF 2023 json files:", n, "listing bytes:", len(r["data"]), flush=True)
    # 文件名年份样本
    names = sorted(set(re.findall(rb'href="([^"]+\.json)"', r["data"])))
    print("first/last:", names[0].decode(), names[-1].decode(), flush=True)

print("== F. Oracle 历史通告计数(alertsarchive)==", flush=True)
r = fetch("https://www.oracle.com/security-alerts/alertsarchive.html", via="curl", max_bytes=2097152)
if r.get("status") == 200:
    links = sorted(set(re.findall(rb'href="(/security-alerts/[a-z0-9\-]+\.html)"', r["data"])))
    cpu = [l for l in links if "cpu" in l.decode()]
    print("oracle archive links:", len(links), "cpu pages:", len(cpu), flush=True)
    print("sample cpu links:", [l.decode() for l in cpu[:5]], [l.decode() for l in cpu[-3:]], flush=True)
    with open(TMP + r"\_oracle_archive_index.html", "wb") as f:
        f.write(r["data"][:524288])
else:
    print("oracle archive status:", r.get("status"), r.get("error"), flush=True)

print("== G. CTFtime writeup ID 上界 ==", flush=True)
for wid in ["33500", "32800", "32500"]:
    r = fetch(f"https://ctftime.org/writeup/{wid}", max_bytes=1024)
    print(json.dumps({"id": wid, "status": r.get("status")}), flush=True)

print("== H. SANS ISC 低 ID 检查(估计总量)==", flush=True)
for did in ["100", "5000", "15000", "25000"]:
    r = fetch(f"https://isc.sans.edu/diary/{did}", max_bytes=2048)
    print(json.dumps({"id": did, "status": r.get("status")}), flush=True)

print("DONE5")
