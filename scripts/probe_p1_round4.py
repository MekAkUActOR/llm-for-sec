# -*- coding: utf-8 -*-
"""P1 探测第四轮:规模计数(目录/索引页)、Oracle+Cisco 条款全文(curl.exe)、GHSL 文章目录、MSRC CVRF 大小(HEAD)。"""
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
OUT = r"J:\Projects\llm_for_sec\docs\research"


def fetch(url, timeout=20, max_bytes=524288, via="urllib"):
    t0 = time.perf_counter()
    if via == "curl":
        try:
            p = subprocess.run(
                ["curl.exe", "-sS", "--noproxy", "*", "--max-time", str(timeout), "-A", UA,
                 "-w", "\n__CURLMETA__%{http_code}|%{time_total}|%{size_download}", url],
                capture_output=True, timeout=timeout + 5)
            body = p.stdout
            m = re.search(rb"__CURLMETA__(\d+)\|([\d.]+)\|(\d+)\s*$", body)
            meta = (m.group(1).decode(), m.group(2).decode(), m.group(3).decode()) if m else ("?", "?", "?")
            return {"url": url, "via": "curl", "status": int(meta[0]) if meta[0].isdigit() else None,
                    "ms": int((time.perf_counter() - t0) * 1000), "data": body[: max_bytes],
                    "stderr": p.stderr.decode("utf-8", "replace")[:150] if p.stderr else ""}
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


def head_curl(url, timeout=15):
    t0 = time.perf_counter()
    try:
        p = subprocess.run(["curl.exe", "-sSI", "--noproxy", "*", "--max-time", str(timeout), "-A", UA, url],
                           capture_output=True, text=True, timeout=timeout + 5)
        cl = re.search(r"(?i)content-length:\s*(\d+)", p.stdout)
        ct = re.search(r"(?i)content-type:\s*([^\r\n]+)", p.stdout)
        return {"url": url, "HEAD": "ok" if p.returncode == 0 and "200" in p.stdout.split("\n", 1)[0] else p.stdout[:80],
                "content_length": int(cl.group(1)) if cl else None,
                "ctype": ct.group(1).strip() if ct else None,
                "ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"url": url, "HEAD": f"err {e}"}


def txt_of(html):
    t = re.sub(rb"(?is)<script.*?</script>|<style.*?</style>", b" ", html)
    t = re.sub(rb"<[^>]+>", b" ", t)
    return b" ".join(t.split())


print("== A. MSRC CVRF 文档大小(HEAD)==", flush=True)
for yid in ["1999-Sep", "2005-Jan", "2010-Jan", "2015-Jan", "2020-Jan", "2025-Jan", "2026-Sep"]:
    print(json.dumps(head_curl(f"https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/{yid}")), flush=True)

print("== B. Oracle 索引与单篇 CPU(curl)==", flush=True)
ora = fetch("https://www.oracle.com/security-alerts/", via="curl", max_bytes=262144)
print(json.dumps({"status": ora["status"], "ms": ora["ms"], "bytes": len(ora.get("data", b""))}), flush=True)
if ora.get("data"):
    links = sorted(set(re.findall(rb'href="(/security-alerts/[a-z0-9\-]+\.html)"', ora["data"])))
    print("oracle alert links:", len(links), [l.decode() for l in links[:8]], flush=True)
    with open(OUT + r"\_oracle_alerts_index_sample.html", "wb") as f:
        f.write(ora["data"][:262144])
    if links:
        adv = fetch("https://www.oracle.com" + links[-1].decode(), via="curl", max_bytes=524288)
        print("oracle CPU page:", json.dumps({"url": adv["url"], "status": adv["status"], "ms": adv["ms"],
                                              "bytes": len(adv.get("data", b""))}), flush=True)
        if adv.get("data"):
            t = txt_of(adv["data"])
            with open(OUT + r"\_oracle_cpu_sample.txt", "wb") as f:
                f.write(t)
            print("oracle CPU text sample:", json.dumps(t[:300].decode("utf-8", "replace")), flush=True)

print("== C. Cisco 站点条款(curl)==", flush=True)
cis = fetch("https://www.cisco.com/c/en/us/about/legal/terms-conditions.html", via="curl", max_bytes=262144)
print(json.dumps({"status": cis["status"], "ms": cis["ms"], "bytes": len(cis.get("data", b"")),
                  "stderr": cis.get("stderr", ""), "error": cis.get("error")}), flush=True)
if cis.get("data"):
    with open(OUT + r"\_cisco_terms_sample.html", "wb") as f:
        f.write(cis["data"])
    t = txt_of(cis["data"])
    print("cisco terms text sample:", json.dumps(t[:400].decode("utf-8", "replace")), flush=True)

print("== D. GHSL 文章目录定位(api.github.com)==", flush=True)
for path in ["docs", "SecurityExploits"]:
    r = fetch(f"https://api.github.com/repos/github/securitylab/contents/{path}?ref=main")
    if r.get("status") == 200:
        arr = json.loads(r["data"])
        names = [a["name"] for a in arr]
        print(f"GHSL {path}: {len(names)} entries", json.dumps(names[:12]), flush=True)
    else:
        print(f"GHSL {path}: status {r.get('status')} {r.get('error','')}", flush=True)

print("== E. MSRC API swagger(docs 目录)==", flush=True)
r = fetch("https://api.github.com/repos/microsoft/MSRC-Microsoft-Security-Updates-API/contents/docs")
if r.get("status") == 200:
    for a in json.loads(r["data"]):
        print("msrc docs file:", a["name"], flush=True)
        if a["name"].endswith((".json", ".yaml")):
            r2 = fetch(a["download_url"]) if a.get("download_url", "").startswith("http") and "githubusercontent" not in a["download_url"] else None
            if r2 and r2.get("status") == 200:
                head = r2["data"][:800].decode("utf-8", "replace")
                print("swagger head:", json.dumps(head), flush=True)

print("== F. Red Hat CSAF 年度计数 ==", flush=True)
for year in ["2023", "2024", "2025"]:
    r = fetch(f"https://security.access.redhat.com/data/csaf/v2/advisories/{year}/", max_bytes=2097152)
    n = len(re.findall(rb'href="[^"]+\.json"', r.get("data", b""))) if r.get("status") == 200 else None
    print(json.dumps({"year": year, "status": r.get("status"), "json_files": n, "bytes": len(r.get("data", b""))}), flush=True)

print("== G. CTFtime 探查 ==", flush=True)
for wid in ["35000", "32000", "30000", "27000"]:
    r = fetch(f"https://ctftime.org/writeup/{wid}", max_bytes=2048)
    print(json.dumps({"id": wid, "status": r.get("status")}), flush=True)
ab = fetch("https://ctftime.org/about/", max_bytes=65536)
if ab.get("status") == 200:
    t = txt_of(ab["data"])
    print("ctftime about text:", json.dumps(t[:600].decode("utf-8", "replace")), flush=True)
api = fetch("https://ctftime.org/api/", max_bytes=65536)
if api.get("status") == 200:
    t = txt_of(api["data"])
    print("ctftime api text:", json.dumps(t[:900].decode("utf-8", "replace")), flush=True)

print("== H. Debian 年度 DSA 计数 ==", flush=True)
for year in ["2024", "2023", "2020", "2015"]:
    r = fetch(f"https://lists.debian.org/debian-security-announce/{year}/", max_bytes=131072)
    n = len(set(re.findall(rb"msg\d+\.html", r.get("data", b"")))) if r.get("status") == 200 else None
    print(json.dumps({"year": year, "status": r.get("status"), "msgs": n}), flush=True)

print("== I. SANS ISC diary 计数(archive 页解析)==", flush=True)
da = fetch("https://isc.sans.edu/diaryarchive.html", max_bytes=1048576)
if da.get("status") == 200:
    ids = set(re.findall(rb"/diary/(\d+)", da["data"]))
    print("diary ids on archive page:", len(ids), "max:", max(int(i) for i in ids) if ids else None, flush=True)
    t = txt_of(da["data"])
    m = re.search(rb"(?i)(showing|archive).{0,200}", t)
    print("archive snippet:", json.dumps(m.group(0)[:200].decode("utf-8", "replace") if m else ""), flush=True)

print("== J. P0 0days-in-the-wild 镜像结构 ==", flush=True)
r = fetch("https://api.github.com/repos/googleprojectzero/0days-in-the-wild/contents/")
if r.get("status") == 200:
    print("0day repo:", json.dumps([a["name"] for a in json.loads(r["data"])]), flush=True)
else:
    print("0day repo status:", r.get("status"), r.get("error", ""), flush=True)
print("DONE4")
