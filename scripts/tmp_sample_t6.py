import json, os, sys, re, hashlib, collections
sys.stdout.reconfigure(encoding='utf-8')

def clip(s, n):
    s = str(s).replace('\r', '').replace('\n', '\\n')
    return s if len(s) <= n else s[:n] + '...<len=%d>' % len(str(s))

def load(p):
    out = []
    with open(p, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception as e:
                    out.append({'__parse_error__': str(e)})
    return out

P_DEV = 'data/corpora/clean/t6_devign_lines.jsonl'
P_CVE = 'data/corpora/clean/t6_cvefixes.jsonl'
P_M1 = 'data/lf/sft_m1.jsonl'

print('# sizes')
for p in (P_DEV, P_CVE, P_M1):
    print(' ', p, os.path.getsize(p) if os.path.exists(p) else 'MISSING')

# ---------- DEVIGN ----------
dev = load(P_DEV)
errs = sum(1 for r in dev if '__parse_error__' in r)
ku = sorted(set().union(*[set(r) for r in dev]) - {'__parse_error__'})
print()
print('# DEVIGN n=%d parse_errors=%d' % (len(dev), errs))
print('keys:', ku)
for i, r in enumerate(dev[:3]):
    print('-- rec%d' % i)
    for k, v in r.items():
        print('   %s = %s' % (k, clip(v, 150)))

codek = max(ku, key=lambda k: len(str(dev[0].get(k, '') or '')))
tgt = next((k for k in ('target', 'label', 'vul', 'is_vul', 'vulnerable', 'is_vulnerable') if k in ku), None)
vlk = next((k for k in ku if 'line' in k.lower()), None)
print('guess code=%r target=%r vul_lines=%r' % (codek, tgt, vlk))
try:
    n1 = sum(1 for r in dev if r.get(tgt) == 1)
    pool = [r for r in dev if r.get(tgt) == 1 and 100 < len(str(r.get(codek) or '')) < 8000]
    nv = sum(1 for r in pool if r.get(vlk))
    print('target1=%d lenfilter=%d withvul=%d' % (n1, len(pool), nv))
    hs = collections.Counter(hashlib.md5(str(r[codek]).encode('utf-8')).hexdigest() for r in pool if r.get(vlk))
    print('unique_code=%d dup_extra=%d' % (len(hs), sum(hs.values()) - len(hs)))
    bad = 0
    for r in pool:
        v = r.get(vlk)
        if not isinstance(v, list) or not v:
            continue
        ncl = str(r[codek]).count('\n') + 1
        if any((not isinstance(x, int)) or x < 1 or x > ncl for x in v):
            bad += 1
    print('vul_lines_out_of_range=%d' % bad)
    r0 = next((r for r in pool if r.get(vlk)), None)
    if r0:
        lines = str(r0[codek]).split('\n')
        v0 = min(x for x in r0[vlk] if isinstance(x, int))
        print('example vul_lines=%s nlines=%d codelen=%d' % (r0[vlk], len(lines), len(str(r0[codek]))))
        for j in range(max(0, v0 - 2), min(len(lines), v0 + 1)):
            print('  %4d| %s' % (j + 1, clip(lines[j], 90)))
except Exception as e:
    print('devign stats error:', repr(e))

# ---------- CVEFIXES ----------
cve = load(P_CVE)
errs2 = sum(1 for r in cve if '__parse_error__' in r)
ku2 = sorted(set().union(*[set(r) for r in cve]) - {'__parse_error__'})
print()
print('# CVEFIXES n=%d parse_errors=%d' % (len(cve), errs2))
print('keys:', ku2)
for i, r in enumerate(cve[:3]):
    print('-- rec%d' % i)
    for k, v in r.items():
        print('   %s = %s' % (k, clip(v, 220)))
dk = next((k for k in ku2 if 'diff' in k.lower()), None)
print('diff_key=%r' % dk)
if dk:
    print('with_diff=%d' % sum(1 for r in cve if r.get(dk)))
    r1 = next((r for r in cve if r.get(dk)), None)
    if r1:
        print('diff_head:', clip(r1[dk], 500))
    dl = sorted(len(str(r[dk])) for r in cve if r.get(dk))
    if dl:
        print('diff len p10/p50/p90/max: %d/%d/%d/%d' % (dl[len(dl) // 10], dl[len(dl) // 2], dl[9 * len(dl) // 10], dl[-1]))
        print('diff 200..6000 chars: %d' % sum(1 for x in dl if 200 <= x <= 6000))

# ---------- SFT_M1 ----------
print()
print('# SFT_M1')

def extract(rec):
    if isinstance(rec.get('messages'), list):
        d = {}
        for m in rec['messages']:
            if isinstance(m, dict):
                d[m.get('role')] = m.get('content')
        return d
    return rec

shown = 0
tot = 0
vcount = 0
acount = 0
systems = {}
tagcnt = collections.Counter()
rawprinted = False
try:
    fobj = open(P_M1, encoding='utf-8')
except Exception as e:
    fobj = None
    print('open m1 failed:', e)
if fobj:
    with fobj:
        for i, line in enumerate(fobj):
            line = line.strip()
            if not line:
                continue
            tot += 1
            try:
                rec = json.loads(line)
            except Exception:
                continue
            d = extract(rec)
            s = d.get('system')
            if s:
                h = hashlib.md5(str(s).encode('utf-8')).hexdigest()
                if h not in systems:
                    systems[h] = [str(s), 0]
                systems[h][1] += 1
            a = d.get('assistant')
            if a:
                acount += 1
                if 'VERDICT' in str(a)[-160:]:
                    vcount += 1
            u = d.get('user') or ''
            if u:
                m = re.search(r'```([A-Za-z0-9+#_.-]*)', u)
                if m:
                    tagcnt[m.group(1)] += 1
            if shown < 4 and '```' in u:
                shown += 1
                print('-- line%d keys=%s' % (i, list(rec.keys())))
                if not rawprinted:
                    rawprinted = True
                    print('   RAWHEAD = %s' % clip(line, 180))
                for role in ('system', 'user', 'assistant'):
                    v = d.get(role)
                    if v is None:
                        continue
                    if role == 'system':
                        print('   system = %s' % clip(v, 1300))
                    elif role == 'user':
                        print('   userHEAD = %s' % clip(v, 320))
                        print('   userTAIL = %s' % clip(v[-200:], 200))
                    else:
                        print('   asstHEAD = %s' % clip(v, 130))
                        print('   asstTAIL = %s' % clip(v[-200:], 200))
    print('scanned=%d shown=%d assistants=%d verdict_end=%d' % (tot, shown, acount, vcount))
    print('fence tags:', tagcnt.most_common(10))
    print('distinct_systems=%d' % len(systems))
    for h, (txt, c) in sorted(systems.items(), key=lambda kv: -kv[1][1])[:5]:
        print('== system x%d len=%d ==' % (c, len(txt)))
        print(txt[:1300])

# ---------- staging ----------
print()
print('# staging')
sd = 'data/sft/m2.5-staging'
if os.path.isdir(sd):
    for fn in sorted(os.listdir(sd)):
        p2 = os.path.join(sd, fn)
        if os.path.isfile(p2):
            extra = ''
            try:
                with open(p2, encoding='utf-8') as f2:
                    first = json.loads(f2.readline())
                extra = ' keys=%s' % list(first.keys())
            except Exception:
                extra = ' (unreadable)'
            print(' ', fn, os.path.getsize(p2), extra)
else:
    print(' missing - generator will create')
