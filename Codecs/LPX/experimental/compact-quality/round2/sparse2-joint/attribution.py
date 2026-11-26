"""Posthoc field/coordinate attribution from immutable receipts; no search."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--packages',type=Path);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--public',type=Path,required=True)


def main(args):
    import run_study as r
    r.setup(args.packages);out=r.prev.private_output(args.output);freeze=r.frozen(out)
    counts=Counter({key:0 for key in ('cases','joint_unchanged','joint_admitted_changes','scale_changed',
        'gain_changed','pulses_changed','metadata_and_pulses_changed','pulses_only','metadata_only')})
    rows=[];shared={arm:Counter({key:0 for key in ('queried','in_metric_queue',
        'selected_at_some_step','returned_as_final')}) for arm in ('coordinate_mp','coordinate_pm')}
    for case in freeze['cases']:
        folder=out/('case-%03d'%case['ordinal']);p=r.prev.read(folder/'result-pointer-private.json')
        receipt=r.prev.read(r.prev.checked(folder,p['receipt_file'],p['receipt_sha256']))
        final=receipt['variants']['joint']['final'];counts['cases']+=1
        if not final['changed']:
            counts['joint_unchanged']+=1;continue
        counts['joint_admitted_changes']+=1
        baseline=r.sparse.unpack((folder/'baseline.lpx').read_bytes())
        current=r.sparse.unpack(r.prev.checked(folder,'final-joint.lpx',final['sha256']).read_bytes())
        if current[:2]!=baseline[:2] or current[4:]!=baseline[4:]:raise ValueError('Joint final changed immutable decoder fields')
        scale=sum(a[0]!=b[0] for a,b in zip(current[2],baseline[2]))
        gain=sum(a[2]!=b[2] for a,b in zip(current[2],baseline[2]))
        if any(a[1]!=b[1] for a,b in zip(current[2],baseline[2])):raise ValueError('Joint final changed lag')
        pulses=sum(a!=b for a,b in zip(current[3],baseline[3]))
        metadata=bool(scale or gain)
        for key,value in (('scale_changed',bool(scale)),('gain_changed',bool(gain)),('pulses_changed',bool(pulses)),
                          ('metadata_and_pulses_changed',metadata and bool(pulses)),
                          ('pulses_only',not metadata and bool(pulses)),('metadata_only',metadata and not pulses)):
            counts[key]+=int(value)
        if not metadata and not pulses:raise ValueError('Admitted joint bytes have no allowed field change')
        point_hash={(leaf['frame'],leaf['ordinal']):leaf['sha256'] for leaf in receipt['leaves']}
        arms={}
        for arm in shared:
            queried={point_hash[region['frame'],ordinal] for region in receipt['regions'] for ordinal in region['queried'][arm]}
            entries=[entry for entry in receipt['admission']['candidates'][arm] if entry['sha256']==final['sha256']]
            values=dict(queried=final['sha256'] in queried,in_metric_queue=bool(entries),
                selected_at_some_step=any(e['selected_at_step'] for e in entries),
                returned_as_final=receipt['variants'][arm]['final']['sha256']==final['sha256'])
            for key,value in values.items():shared[arm][key]+=int(value)
            arms[arm]=values
        rows.append(dict(ordinal=case['ordinal'],group=case['group'],split=case['split'],
            scale_fields_changed=scale,gain_fields_changed=gain,pulse_packets_changed=pulses,
            metadata_and_pulses_changed=metadata and bool(pulses),pulses_only=not metadata and bool(pulses),
            metadata_only=metadata and not pulses,coordinate_sharing=arms))
    if counts['cases']!=27:raise ValueError('Attribution requires all original cases')
    report=dict(schema='lpx-sparse2-joint-posthoc-attribution-v1',status='PASS',counts=dict(counts),
        coordinate_sharing_counts={arm:dict(value) for arm,value in shared.items()},admitted_cases=rows,
        posthoc_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Anonymous field-change/query attribution only; metadata-and-pulse edits do not alone prove causal or audible benefit')
    destination=args.public.resolve();destination.relative_to(HERE.resolve());r.prev.write(destination,report)
    print(r.prev.encoded(dict(status='PASS',counts=dict(counts))).decode().strip(),flush=True)


if __name__=='__main__':main(parser.parse_args())
