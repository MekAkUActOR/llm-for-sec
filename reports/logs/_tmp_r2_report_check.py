# -*- coding: utf-8 -*-
import re
t = open(r'reports\p1.6-round2-build.md', encoding='utf-8').read()
checks = {
    '结尾标记 P16-R2-BUILD=DONE': t.rstrip().endswith('P16-R2-BUILD=DONE'),
    '门禁 12/12 PASS': 'P16-GATE=PASS' in t and '12/12' in t,
    '全 sha 表（>=10 个 64hex）': len(re.findall(r'[0-9a-f]{64}', t)) >= 10,
    '行数恒等式 5,216': '5,216 = 1,100+480+360+240+96+300+2,640' in t,
    '训练命令行': 'llamafactory-cli.exe' in t and 'm5a-dpo-r2.yaml' in t,
    '三注册名': all(s in t for s in ('sec_dpo_m5a_r2_base_m4capfix', 'sec_dpo_m5a_r2_p16_benign', 'sec_dpo_m5a_r2_p16_malicious')),
    'G1 时序约束登记': 'RESOLVED_BY_SEQUENCING' in t,
    'ASCII 纪律（dataset_info）': '纯 ASCII' in t,
    'HP 零改动证明': 'DIFF-HP-ZERO=PASS' in t,
    '自误记录': 'VERIFY-R2-INVARIANT=PASS' in t,
    '44.8:55.2': '44.8' in t and '55.2' in t,
}
for k, v in checks.items():
    print(('  [OK] ' if v else '  [FAIL] ') + k)
print('REPORT-CHECK=' + ('PASS' if all(checks.values()) else 'FAIL'))
print('chars:', len(t))
