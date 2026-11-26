"""Read-only full matrix, field-mask, native-output and admission verification."""
import argparse
import hashlib
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--packages',type=Path);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--public',type=Path,required=True);parser.add_argument('--validation',type=Path,required=True)


def validate(args):
    import run_study as r
    r.setup(args.packages);j,np,sparse,old=r.j,r.np,r.sparse,r.j.old
    from refine_sparse80_pulses import _floors,band_error_floors
    out=r.prev.private_output(args.output);freeze=r.frozen(out);public=r.prev.read(args.public)
    if (public['completed_cases']!=27 or [c['ordinal'] for c in public['cases']]!=[c['ordinal'] for c in freeze['cases']]
            or sum(c['split']=='heldout_speech' for c in public['cases'])!=10):
        raise ValueError('Complete original membership changed')
    def safe(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('symbols','parameters','sha256','target_sha256','baseline_sha256','previous_receipt','previous_pointer'):
                    raise ValueError('Private binding field in public case')
                safe(item)
        elif isinstance(value,list):
            for item in value:safe(item)
        elif isinstance(value,str):
            if ':\\' in value or '/mnt/' in value or len(value)==64 and all(c in '0123456789abcdef' for c in value):
                raise ValueError('Private path/hash in public case')
    safe(public['cases'])
    counts=dict(cases=0,leaf_masks=0,native_model_variant_replays=0,final_floor_checks=0,
                raw_and_queue_identity_checks=0,coordinate_tables=0)
    wall=time.perf_counter()
    with r.NativeReceiver('common') as common,r.NativeReceiver('v5-only') as only:
        receiver=old.bridge_receiver(common,only)
        for case,public_row in zip(freeze['cases'],public['cases']):
            folder=out/('case-%03d'%case['ordinal']);pointer=r.prev.read(folder/'result-pointer-private.json')
            receipt=r.prev.read(r.prev.checked(folder,pointer['receipt_file'],pointer['receipt_sha256']))
            if (receipt['status']!='PASS' or receipt['source_freeze_sha256']!=r.prev.digest(r.prev.encoded(freeze))
                    or pointer['selected_file']!='final-joint.lpx'
                    or pointer['selected_sha256']!=receipt['variants']['joint']['final']['sha256']):
                raise ValueError('Authoritative joint result pointer changed')
            if r.public_case(receipt)!=public_row:raise ValueError('Anonymous row is not the exact numeric whitelist')
            for name,expected in receipt['artifacts'].items():r.prev.checked(folder,name,expected)
            blob=(folder/'baseline.lpx').read_bytes();layout=old.parse_layout(blob);offsets=j.metadata_offsets(blob)
            fields=sparse.unpack(blob);by_frame={x['frame']:x for x in receipt['regions']}
            target=np.frombuffer((folder/'target.pcm16').read_bytes(),dtype='<i2').copy()
            base_pcm,base_pwm=old._oracle(receiver,blob,sparse.decode_model(blob))
            counts['native_model_variant_replays']+=1
            if ((folder/'baseline.pcm16').read_bytes()!=base_pcm.astype('<i2').tobytes()
                    or (folder/'baseline.pwm8').read_bytes()!=base_pwm.tobytes()):
                raise ValueError('Protected baseline waveform files are not native/model output')
            point_tables={frame:{} for frame in by_frame};candidate_rows={}
            for leaf in receipt['leaves']:
                candidate=(folder/leaf['file']).read_bytes();decoded=sparse.unpack(candidate);frame=leaf['frame']
                if r.prev.digest(candidate)!=leaf['sha256']:raise ValueError('Leaf file digest differs from its declared identity')
                expected_pulses=list(fields[3]);path=tuple(leaf['symbols'])
                if len(path)!=4:raise ValueError('Leaf does not declare exactly four pulse symbols')
                pi=0
                for part,symbol in enumerate(path):
                    pool=by_frame[frame]['pools'][part]['symbols']
                    if type(symbol) is not int or symbol not in pool:raise ValueError('Leaf pulse lies outside its common frozen pool')
                    pi=pi*len(pool)+pool.index(symbol)
                    expected_pulses[frame*4+part]=old.symbol_fields(symbol)
                if (leaf['metadata_index'] not in (0,1) or leaf['ordinal']!=leaf['metadata_index']*81+pi
                        or decoded[3]!=expected_pulses):
                    raise ValueError('Leaf ordinal or actual pulse fields differ from their labels')
                expected=list(fields[2]);expected[frame]=tuple(leaf['parameters'])
                if (len(candidate)!=len(blob) or decoded[:2]!=fields[:2] or decoded[2]!=expected
                        or decoded[4:]!=fields[4:] or decoded[2][frame][1]!=fields[2][frame][1]):
                    raise ValueError('Leaf changed immutable fields or complete B0')
                allowed=set(range(offsets[frame],offsets[frame]+5))
                allowed.update(range(offsets[frame]+12,offsets[frame]+15))
                for packet in range(frame*4,frame*4+4):
                    allowed.update(range(layout.pulse_offsets[packet],layout.pulse_offsets[packet]+7))
                for at,(a,b) in enumerate(zip(blob,candidate)):
                    for bit in range(8):
                        if (a^b)&(1<<bit) and at*8+bit not in allowed:
                            raise ValueError('Leaf changed original non-editable bits')
                meta=tuple(leaf['parameters'])
                if meta!=tuple(by_frame[frame]['metadata'][leaf['metadata_index']]):raise ValueError('Leaf outside frozen metadata states')
                p=j.Point(frame,leaf['metadata_index'],meta,tuple(leaf['symbols']),leaf['ordinal'],candidate,
                          np.empty(0,np.int16),np.empty(0,np.uint8),leaf['pcm_sse'])
                point_tables[frame][p.ordinal]=p;candidate_rows[r.prev.digest(candidate)]=p
                counts['leaf_masks']+=1
            queried={arm:{} for arm in j.ARMS}
            for frame,table in point_tables.items():
                region=by_frame[frame]
                pools=tuple(j.Pool(p['packet'],tuple(p['symbols']),tuple(p['winners']),tuple(p['losses'])) for p in region['pools'])
                inc=tuple(layout.symbols[frame*4:frame*4+4]);points=list(table.values())
                queries,endpoints,attempts=j.controls(points,pools,inc)
                for arm in ('coordinate_mp','coordinate_pm'):
                    if ([p.ordinal for p in queries[arm]]!=region['queried'][arm]
                            or endpoints[arm].ordinal!=region['endpoints'][arm]
                            or attempts[arm]!=region['query_attempts'][arm]):
                        raise ValueError('Full-objective coordinate table changed')
                    counts['coordinate_tables']+=1
                queries['joint']=points
                for arm in j.ARMS:
                    for p in queries[arm]:
                        if p.blob!=blob:queried[arm].setdefault(p.blob,p)
            key=lambda p:(p.pcm_sse,p.frame,p.metadata_index,p.ordinal)
            for arm in j.ARMS:
                queue=sorted(queried[arm].values(),key=key)[:12]
                if ([r.prev.digest(p.blob) for p in queue]!=[x['sha256'] for x in receipt['admission']['candidates'][arm]]
                        or receipt['variants'][arm]['raw']['sha256']!=r.prev.digest(queue[0].blob)):
                    raise ValueError('An arm received another arm candidate or lost its raw identity')
                counts['raw_and_queue_identity_checks']+=1
            counter=receipt['counters']
            unique={case['baseline_sha256']}|{x['sha256'] for rows in receipt['admission']['candidates'].values() for x in rows}
            if (counter['leaves']!=324 or counter['model_checks']!=325 or counter['native_oracle_calls']!=323
                    or counter['pulse_screens']!=2048 or counter['branch_prefix_samples']!=960
                    or counter['coordinate_mp_queries']!=498 or counter['coordinate_pm_queries']!=498
                    or counter['metric_proposal_attempts']!=36 or counter['unique_metric_evaluations']!=len(unique)):
                raise ValueError('Registered work/queue/cache accounting changed')
            replayed={blob:(base_pcm,base_pwm)}
            for arm,variants in receipt['variants'].items():
                for kind,row in variants.items():
                    stem=kind+'-'+arm;candidate=(folder/(stem+'.lpx')).read_bytes()
                    if r.prev.digest(candidate)!=row['sha256'] or len(candidate)!=len(blob):raise ValueError('Variant digest or B0 changed')
                    if candidate not in replayed:
                        modeled=sparse.decode_model(candidate);replayed[candidate]=old._oracle(receiver,candidate,modeled)
                        counts['native_model_variant_replays']+=1
                    pcm,pwm=replayed[candidate]
                    if ((folder/(stem+'.pcm16')).read_bytes()!=pcm.astype('<i2').tobytes()
                            or (folder/(stem+'.pwm8')).read_bytes()!=pwm.tobytes()):raise ValueError('Variant waveform is not native/model output')
                    actual_pwm=(pwm.astype(np.int32)-128)*256
                    if (row['metrics']['metrics']['pcm16']['error_energy']!=old._sse(target,pcm)
                            or row['metrics']['metrics']['pwm8']['error_energy']!=old._sse(target,actual_pwm)
                            or row['pcm_changed_samples']!=int(np.count_nonzero(pcm!=base_pcm))
                            or row['pwm_changed_samples']!=int(np.count_nonzero(pwm!=base_pwm))
                            or row['changed']!=(candidate!=blob)):
                        raise ValueError('Variant waveform errors or changed-sample labels differ from actual output')
                    if kind!='final':continue
                    before=receipt['baseline']['metrics'];after=row['metrics']
                    if not _floors(after,before) or not band_error_floors(row['bands']['pwm8'],receipt['baseline']['bands']['pwm8']):
                        raise ValueError('Final arm violates latest B0 quality/frequency/tail floors')
                    if row['changed']:
                        entry=next(x for x in receipt['admission']['candidates'][arm] if x['sha256']==row['sha256'])
                        if (after!=entry['metrics'] or not all(entry['floors'].values()) or after['score']>=before['score']-1e-12
                                or after['pwm_joint_score']>=before['pwm_joint_score']-1e-12):raise ValueError('Changed final not admitted in its own arm')
                    elif candidate!=blob:raise ValueError('Rollback is not exact latest baseline')
                    counts['final_floor_checks']+=1
            counts['cases']+=1
    if r.export(out,None)!=public:raise ValueError('Anonymous sums/STOI/denominators differ from private immutable receipts')
    report=dict(schema='lpx-sparse2-joint-validation-v1',status='PASS',counters=counts,
        wall_seconds=time.perf_counter()-wall,latest_admitted_baseline_exact=True,targets_unchanged=True,
        coordinate_queries_same_full_objective=True,equal_metric_queue_caps=True,
        native_model_pcm_pwm_and_eof_exact=True,all_original_nonedit_bits_exact=True,
        all_arms_latest_quality_and_frequency_tail_floors=True,anonymous_numeric_export_exact=True,
        validator_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Read-only artifact validation; no search rerun/listening/AVR claim')
    destination=args.validation.resolve();destination.relative_to(HERE.resolve());r.prev.write(destination,report)
    print(r.prev.encoded(dict(status='PASS',**counts)).decode().strip(),flush=True)


if __name__=='__main__':
    args=parser.parse_args()
    try:validate(args)
    except Exception as error:
        (args.output/'validation-error-private.log').write_text(traceback.format_exc(),encoding='utf-8')
        print('{"status":"INFRASTRUCTURE_STOP","exception":"'+type(error).__name__+'"}',flush=True);sys.exit(2)
