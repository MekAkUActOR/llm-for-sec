import json, os, sys, re, collections
sys.stdout.reconfigure(encoding='utf-8')

def clip(s, n):
    s = str(s).replace('\r', '').replace('\n', '\\n')
    return s if len(s) <= n else s[:n] + '...<len=%d>' % len(str(s))

P_DEV = 'data/corpora/clean/t6_devign_lines.jsonl'
P_CVE = 'data/corpora/clean/t6_cvefixes.jsonl'
P_M1 = 'data/lf/sft_m1.jsonl'

print('## DEVIGN header census')
cnt = collections.Counter()
with open(P_DEV, encoding='utf-8') as f:
    for line in f:
        t = json.loads(line)['text']
        key = re.sub(r'\(project: [^;)]+; commit: [0-9a-f]+; split: \w+\)', '(META)', t[:100])
        cnt[key] += 1
for k, v in cnt.most_common(8):
    print(' %5d  %s' % (v, clip(k, 100)))

print()
print('## DEVIGN rec0 full + rec1 slices')
with open(P_DEV, encoding='utf-8') as f:
    t0 = json.loads(f.readline())['text']
    t1 = json.loads(f.readline())['text']
print('=== rec0 (len %d) FULL ===' % len(t0))
print(t0)
print('=== rec1 (len %d) head2000 ===' % len(t1))
print(t1[:2000])
print('=== rec1 tail 700 ===')
print(t1[-700:])

print()
print('## CVEFIXES rec0 slices')
with open(P_CVE, encoding='utf-8') as f:
    c0 = json.loads(f.readline())['text']
print('=== len %d head 2600 ===' % len(c0))
print(c0[:2600])
for marker in ('diff --git', '@@', 'Index:', '+++', 'Description:', 'Diff', 'patch'):
    print('marker %r first at %d' % (marker, c0.find(marker)))
print('=== tail 500 ===')
print(c0[-500:])

print()
print('## M1 task census + verdict shapes')
tasks = collections.Counter()
vshapes = collections.Counter()
vex = {}
n = 0
with open(P_M1, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            rec = json.loads(line)
        except Exception:
            continue
        tasks[str(rec.get('task'))] += 1
        msgs = {}
        for m in rec.get('messages', []):
            if isinstance(m, dict):
                msgs[m.get('role')] = m.get('content')
        a = msgs.get('assistant') or ''
        k = a.rfind('VERDICT')
        if k < 0:
            continue
        rest = a[k:].strip()
        try:
            j = rest.index(':')
            obj = json.loads(rest[j + 1:].strip())
            shape = (str(obj.get('action')), str(obj.get('verdict')), ','.join(sorted(obj.keys())))
        except Exception:
            shape = ('RAW', clip(rest, 50), '')
        vshapes[shape] += 1
        if shape not in vex:
            vex[shape] = (rec.get('task'), rec.get('lang'), clip(rest, 320))
print('records:', n)
print('top tasks:', tasks.most_common(25))
print()
for s, c in vshapes.most_common(15):
    print('x%-6d %s' % (c, s))
    print('   ex:', vex[s])

print()
print('## all systems delimited')
systems = {}
with open(P_M1, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        msgs = {}
        for m in rec.get('messages', []):
            if isinstance(m, dict):
                msgs[m.get('role')] = m.get('content')
        s = msgs.get('system')
        if s and s not in systems:
            systems[s] = (rec.get('task'), rec.get('lang'), rec.get('pack'))
        if len(systems) >= 6:
            break
for s, (task, lang, pack) in systems.items():
    print('===SYSTEM pack=%s lang=%s len=%d' % (pack, lang, len(s)))
    print(s)

print()
print('## fC sibling')
p = 'data/sft/m2.5-staging/fC_cvpku_release.jsonl'
recs = []
packcnt = collections.Counter()
langcnt = collections.Counter()
with open(p, encoding='utf-8') as f:
    for line in f:
        rec = json.loads(line)
        recs.append(rec)
        packcnt[rec.get('pack')] += 1
        langcnt[rec.get('lang')] += 1
print('n=%d packs=%s langs=%s' % (len(recs), dict(packcnt), dict(langcnt)))
print('id examples:', [r.get('id') for r in recs[:6]])

def show(r, ul=1500, al=1500):
    print('== id=%s task=%s pack=%s lang=%s' % (r.get('id'), r.get('task'), r.get('pack'), r.get('lang')))
    for m in r['messages']:
        c = m['content']
        print('--[%s] len=%d' % (m['role'], len(c)))
        print(c[:ul])
        if len(c) > ul:
            print('  ...TAIL...')
            print(c[-350:])

show(recs[0])
zr = next((r for r in recs if r.get('lang') == 'zh'), None)
if zr:
    show(zr, 900, 1100)
else:
    print('(no zh record found)')
