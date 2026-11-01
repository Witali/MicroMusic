"""Count and match every saved cap decision; no codec imports or execution."""
from __future__ import annotations

import argparse
from pathlib import Path

from anchor_runtime import HERE,Inputs,save,sha


def validate_cap_rows(rows):
    if len(rows)!=48 or sorted(r['id'] for r in rows)!=list(range(48)):
        raise ValueError('The exact forty-eight distinct arm records are required')
    count=0
    for row in rows:
        if [d['percent'] for d in row['decisions']]!=[100,95,90]:
            raise ValueError('Every actual arm must contain exactly ordered 100/95/90 decisions')
        for decision in row['decisions']:
            cap=row['baseline_bytes']*decision['percent']//100
            if decision['cap']!=cap or row['whole_caps'][str(decision['percent'])]!=cap:
                raise ValueError('An actual complete-B derived cap differs')
            count+=1
    if count!=144:raise ValueError('The actual decision count differs from 144')
    return count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.export=args.export.resolve();args.output=args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh ignored private build output')
    args.output.mkdir(parents=True);inputs=Inputs()
    binding=inputs.json(args.export/'binding-private.json');summary=inputs.json(args.export/'summary.json')
    public=inputs.json(args.export/'rows.json')
    if binding['status']!='PASS' or summary['status']!='PASS':raise ValueError('A terminal successful export is required')
    actual=[]
    for path in binding['shard_paths']:
        path=(Path(path)/'results-private.json').resolve()
        actual.extend(inputs.json(path,binding['input_files_sha256'][str(path)]))
    count=validate_cap_rows(actual)
    if validate_cap_rows(public)!=count:raise ValueError('Public and private actual cap counts differ')
    by_id={r['id']:r for r in public}
    for row in actual:
        for private,projected in zip(row['decisions'],by_id[row['id']]['decisions']):
            for key in private:
                if private[key]!=projected[key]:raise ValueError('A projected cap decision differs from its actual saved record')
    inputs.verify()
    receipt=dict(status='PASS',arm_records=48,actual_cap_decisions=count,ordered_percentages=[100,95,90],
        every_actual_row_has_exact_ordered_caps=True,public_matches_actual_saved_decisions=True,
        new_search_metric_decode_native_build_calls=0,
        tie_definition='Absolute joint score difference <=1e-12 with equal actual bytes is a tolerance rank tie, not PCM or stream identity')
    save(args.output/'postcheck.json',receipt)
    save(args.output/'binding-private.json',dict(status='PASS',input_files_sha256=inputs.pins,
        postcheck_source_sha256=sha(Path(__file__).read_bytes())))
    print(__import__('json').dumps(receipt),flush=True)


if __name__=='__main__':main()
