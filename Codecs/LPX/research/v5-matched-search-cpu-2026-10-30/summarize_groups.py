"""Descriptive grouping of the already exported anonymous paired results."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path


def summarize(pairs):
    groups = defaultdict(list)
    for row in pairs:
        key = ('speech' if row['speech'] else 'nonspeech',row['profile'],
            row['tier_label'],row['cpu']['matched_total_cpu'])
        groups[key].append(row)
    output = []
    for (domain,profile,tier,matched),rows in sorted(groups.items()):
        outcomes = {str(cap):dict(Counter(next(d['outcome'] for d in row['decisions'] if d['percent']==cap)
            for row in rows)) for cap in (100,95,90)}
        output.append(dict(domain=domain,profile=profile,tier_label=tier,matched_total_helper_cpu=matched,
            pairs=len(rows),outcomes=outcomes,
            summed_comparator_cpu=dict(single_path=sum(row['cpu']['single_path_total_helper_cpu'] for row in rows),
                trajectory=sum(row['cpu']['trajectory_total_helper_cpu'] for row in rows)),
            cumulative_tier_includes_prior2=tier=='cumulative-2+8'))
    if sum(row['pairs'] for row in output)!=124 or sum(row['pairs'] for row in output if row['matched_total_helper_cpu'])!=64:
        raise ValueError('The fixed full paired population or matched subset differs')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Use a fresh output; existing evidence is immutable')
    value=summarize(json.loads(args.pairs.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(groups=len(value),pairs=124,matched_pairs=64)),flush=True)


if __name__=='__main__':
    main()
