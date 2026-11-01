"""Strict read-only admission of persisted bounded proofs; no image jobs.

The original worker completed all16 images, then its historical proof helper
compared JSON lists with in-memory tuple ranges. Keep that failed journal and
every pinned source/handoff byte unchanged. Load persisted JSON, reopen every
proof and create a separately labelled continuation gate pointing to the same
original image paths. This is not a successful original worker attempt.
"""
import argparse
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_player as run

THIS=Path(__file__).resolve()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('handoff','source-campaign','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('handoff','source_campaign','output'):setattr(args,name,getattr(args,name).resolve())
    run.require(not args.output.exists(),'Use a fresh derived admission/continuation folder')
    began=time.perf_counter();source_raw=THIS.read_bytes()
    h,raw,cases,chains=run.context(args)
    original=args.source_campaign/'workers/bounded'
    paths={name:original/name for name in ('results-private.json','attempt-private.json','failure-private.json')}
    pins={str(path):run.sha(path.read_bytes()) for path in paths.values()}
    stored=run.load(paths['results-private.json']);attempt=run.load(paths['attempt-private.json'])
    failure=run.load(paths['failure-private.json'])
    run.require(stored['handoff_sha256']==attempt['handoff_sha256']==run.sha(raw)
        and stored['status']=='running' and attempt['status']=='failed' and failure['exception_type']=='AssertionError'
        and "cost == verified['cost'] == row['verification']['cost']" in failure['traceback'],
        'Original end-stage serialization failure differs; do not generalize this recovery')
    expected=[row for row in cases['rows'] if chains[row['chain_id']]['kind']=='short']
    indexed={row['id']:row for row in stored['rows']}
    run.require(len(indexed)==len(stored['rows'])==len(attempt['events'])==len(expected)==16
        and all(event['status']=='passed' for event in attempt['events']),'All16 actual bounded images must already have passed')
    events=[]
    for row in expected:
        record=indexed[row['id']]
        run.require(all(record[name]==value for name,value in row.items()) and record['passed'],
                    'A persisted bounded image differs from the exact original plan')
        run.reopen_record(h,chains[row['chain_id']],row,record)
        events.append(dict(id=row['id'],status='passed',operation='strict-read-only-artifact-reopen',new_image=False))
    run.guard(h,raw,args,True)
    run.require(THIS.read_bytes()==source_raw and all(run.sha(Path(name).read_bytes())==digest for name,digest in pins.items()),
                'An admission source or original receipt changed')
    mapping=dict(role='derived-read-only-admission',source_file=str(THIS),source_sha256=run.sha(source_raw),
        original_receipts_sha256=pins,original_worker_status='failed-after-all-images-passed',
        original_images_preserved=True,new_builds=0,new_simulations=0,source_handoff_preserved=True,
        normalized_only_by_json_loading=True,wall_seconds=time.perf_counter()-began)
    folder=args.output/'workers/bounded'
    run.save(folder/'attempt-private.json',dict(schema='lpx-derived-bounded-admission-attempt-v1',status='complete',
        handoff_sha256=run.sha(raw),events=events,admission=mapping))
    run.save(folder/'artifact-check-private.json',dict(status='passed',handoff_sha256=run.sha(raw),rows=16,
        both_backends_and_storage_recipes_reopened=True,new_builds_or_simulations=0,admission=mapping))
    run.save(folder/'results-private.json',dict(schema='lpx-derived-bounded-admission-results-v1',status='complete',
        handoff_sha256=run.sha(raw),rows=stored['rows'],admission=mapping,
        summary=dict(status='complete',rows=16,passed=16,new_builds=0,new_simulations=0)))
    print('{"status":"derived read-only bounded admission passed","rows":16,"new_images":0,"new_simulations":0}',flush=True)


if __name__=='__main__':main()
