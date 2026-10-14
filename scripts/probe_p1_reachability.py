# -*- coding: utf-8 -*-
"""P1 描述层安全数据源——本机可达性小样本测试(HEAD/单次 GET,仅读前 ~64KB,不批量下载)。
不使用任何代理设置;自定义 User-Agent;并发探测,每目标 15s 超时。"""
import json
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

UA = "llm-for-sec-research/0.1 (corpus feasibility probe; contact: local-researcher)"

TARGETS = [
    ("MSRC", "cvrf v2 root (no key)", "https://api.msrc.microsoft.com/cvrf/v2.0/"),
    ("MSRC", "cvrf v3 root (no key)", "https://api.msrc.microsoft.com/cvrf/v3.0/"),
    ("MSRC", "update-guide portal HTML", "https://msrc.microsoft.com/update-guide"),
    ("MSRC", "portal internal api (unofficial)", "https://portal.msrc.microsoft.com/api/security-guidance/en-US"),
    ("Cisco PSIRT", "openVuln v2 all (no token)", "https://apix.cisco.com/security/advisories/v2/all"),
    ("Cisco PSIRT", "publicationListing HTML", "https://tools.cisco.com/security/center/publicationListing.x"),
    ("Cisco PSIRT", "cisco.com security page", "https://www.cisco.com/c/en/us/products/security.html"),
    ("Oracle CPU", "security-alerts index", "https://www.oracle.com/security-alerts/"),
    ("Oracle CPU", "one CPU advisory HTML", "https://www.oracle.com/security-alerts/cpuapr2025.html"),
    ("Oracle CPU", "legal terms", "https://www.oracle.com/legal/terms.html"),
    ("Project Zero", "blogspot home", "https://googleprojectzero.blogspot.com/"),
    ("Project Zero", "googlesource 0day-in-the-wild", "https://project-zero.googlesource.com/0day-in-the-wild/+/master/"),
    ("Project Zero", "issues tracker", "https://project-zero.issues.chromium.org/"),
    ("CTFtime", "api v1 events", "https://ctftime.org/api/v1/events/?limit=1"),
    ("CTFtime", "site home", "https://ctftime.org/"),
    ("SANS ISC", "api infocon json", "https://isc.sans.edu/api/infocon?json"),
    ("SANS ISC", "rss feed", "https://isc.sans.edu/rssfeed.xml"),
    ("SANS ISC", "diary archive", "https://isc.sans.edu/diaryarchive.html"),
    ("Debian DSA", "dsa index page", "https://www.debian.org/security/dsa/"),
    ("Debian DSA", "single dsa page", "https://www.debian.org/security/2026/dsa-5817"),
    ("Red Hat", "csaf v2 index", "https://security.access.redhat.com/data/csaf/v2/advisories.json"),
    ("Red Hat", "rhsa rss", "https://security.access.redhat.com/data/meta/v1/rhsa.rss"),
    ("GH Security Lab", "repo page", "https://github.com/github/securitylab"),
    ("GH Security Lab", "api.github repo meta", "https://api.github.com/repos/github/securitylab"),
    ("GH Security Lab", "raw LICENSE", "https://raw.githubusercontent.com/github/securitylab/main/LICENSE"),
]


def probe(t):
    name, label, url = t
    rec = {"src": name, "label": label, "url": url}
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=15) as r:
            data = r.read(65536)
            rec.update(
                status=r.status,
                ms=int((time.perf_counter() - t0) * 1000),
                ctype=r.headers.get("Content-Type", ""),
                bytes=len(data),
                final_url=r.url,
                head_sample=data[:200].decode("utf-8", "replace").replace("\n", " ") if data else "",
            )
    except urllib.error.HTTPError as e:
        try:
            body = e.read(300).decode("utf-8", "replace").replace("\n", " ")
        except Exception:
            body = ""
        rec.update(status=e.code, ms=int((time.perf_counter() - t0) * 1000),
                   error=f"HTTPError {e.reason}", body_head=body)
    except Exception as e:
        rec.update(status=None, ms=int((time.perf_counter() - t0) * 1000),
                   error=f"{type(e).__name__}: {e}")
    return rec


results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(probe, t): t for t in TARGETS}
    for f in as_completed(futs):
        r = f.result()
        results.append(r)
        print(json.dumps(r, ensure_ascii=True), flush=True)

order = {t[2]: i for i, t in enumerate(TARGETS)}
results.sort(key=lambda r: order[r["url"]])
with open(r"J:\Projects\llm_for_sec\docs\research\_p1_probe_results.json", "w", encoding="utf-8") as fh:
    json.dump(results, fh, ensure_ascii=False, indent=1)
print("DONE", len(results))
