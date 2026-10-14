# -*- coding: utf-8 -*-
"""M3 DPO watchdog: carrier-batch breakdown of data/lf/dpo_m3_final.jsonl.
Independently checks prereg hard assertions A4 (carrier >=15%), A5 (five carrier
types each >=600), A8 (benign negatives >=20%). Read-only."""
import json
import os
from collections import Counter

ROOT = r"J:\Projects\llm_for_sec"
DS = os.path.join(ROOT, "data", "lf", "dpo_m3_final.jsonl")
OUT = os.path.join(ROOT, "reports", "m3-dpo-watchdog-carrier-breakdown.json")

CARRIER_CLASSES = {"carrier_inject_obedient", "carrier_inject_hollow", "carrier_clean_overrefusal"}
BENIGN_CLASSES = {"carrier_clean_overrefusal"}


def main():
    total = 0
    carrier = 0
    contract = 0
    pack_all = Counter()
    src_task_all = Counter()
    carrier_pack = Counter()
    carrier_src = Counter()
    carrier_type = Counter()
    carrier_type_x_class = Counter()
    contract_carrier_type = Counter()
    carrier_class = Counter()
    carrier_packclass = Counter()
    carrier_lang = Counter()
    contract_pack = Counter()
    contract_lang = Counter()
    variant = Counter()
    benign = 0
    carrier_convs_len = Counter()
    contract_convs_len = Counter()

    with open(DS, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            r = json.loads(line)
            dc = r.get("dpo_class")
            pk = str(r.get("pack"))
            st = str(r.get("src_task"))
            lg = str(r.get("lang"))
            nconv = len(r.get("conversations", []) or [])
            pack_all[pk] += 1
            if r.get("variant") is not None:
                variant[str(r.get("variant"))] += 1
            parts = st.split(":")
            ctype = parts[1] if len(parts) >= 3 else ("NO_SRC_TASK" if st == "None" else st)
            if dc in CARRIER_CLASSES:
                carrier += 1
                carrier_type[ctype] += 1
                carrier_type_x_class[ctype + "|" + str(dc)] += 1
                carrier_pack[pk] += 1
                carrier_src[st] += 1
                carrier_class[dc] += 1
                carrier_packclass[pk + "|" + str(dc)] += 1
                carrier_lang[lg] += 1
                carrier_convs_len[nconv] += 1
                if dc in BENIGN_CLASSES:
                    benign += 1
            else:
                contract += 1
                contract_carrier_type[ctype] += 1
                contract_pack[pk] += 1
                contract_lang[lg] += 1
                contract_convs_len[nconv] += 1
            src_task_all[st] += 1

    res = {
        "total_lines": total,
        "carrier_rows": carrier,
        "contract_rows": contract,
        "carrier_share": round(carrier / total, 6),
        "contract_share": round(contract / total, 6),
        "A4_carrier_ge_15pct": carrier / total >= 0.15,
        "benign_negative_rows": benign,
        "benign_negative_share_of_carrier": round(benign / carrier, 6) if carrier else None,
        "A8_benign_ge_20pct": (benign / carrier >= 0.20) if carrier else None,
        "carrier_pack_distribution": dict(carrier_pack.most_common()),
        "carrier_src_task_distribution": dict(carrier_src.most_common(30)),
        "carrier_dpo_class_distribution": dict(carrier_class.most_common()),
        "carrier_type_distribution": dict(carrier_type.most_common()),
        "A5_five_types_each_ge_600": {
            k: v for k, v in carrier_type.items() if v < 600
        },
        "carrier_type_x_class": dict(carrier_type_x_class.most_common(40)),
        "contract_carrier_type_distribution": dict(contract_carrier_type.most_common(20)),
        "carrier_pack_x_class": dict(carrier_packclass.most_common(40)),
        "carrier_lang": dict(carrier_lang.most_common()),
        "contract_pack_distribution": dict(contract_pack.most_common(20)),
        "contract_lang": dict(contract_lang.most_common()),
        "variant_distribution": dict(variant.most_common(20)),
        "carrier_conversations_len": dict(carrier_convs_len.most_common()),
        "contract_conversations_len": dict(contract_convs_len.most_common()),
        "all_pack_distribution_top": dict(pack_all.most_common(20)),
        "all_src_task_distribution_top": dict(src_task_all.most_common(30)),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
