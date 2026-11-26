"""Synthetic, actual-recurrence tests before any new speech search."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import unittest

parser=argparse.ArgumentParser();parser.add_argument('--packages',type=Path)
options,remaining=parser.parse_known_args()
if options.packages:sys.path.insert(0,str(options.packages.resolve()))
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import joint as j
import numpy as np
import speech_sparse80 as sparse
from native_receiver import NativeReceiver,REPO
from lpx4 import BitWriter
from refine_sparse80_pulses import _floors,band_error_floors
OUTPUT=REPO/'build/compact-quality/sparse2-joint-tests'


def witness():
    rng=np.random.default_rng(0);n=641;frames=(n+319)//320;frame=1
    spectra=[[3+5*k+f%2 for k in range(10)] for f in range(frames)]
    parameters=[(15,18,14)]*frames
    symbols=[int(rng.integers(128)) for _ in range(frames*4)]
    blob=sparse.pack(n,spectra,parameters,[j.old.symbol_fields(x) for x in symbols],15564,4096)
    context=j.Context(blob);base=context.base.pcm.astype(np.int64)
    original=tuple(symbols[4:8]);changed=list(original);changed[2]=10
    meta=(14,18,14)
    vectors=np.asarray([context.render(frame,meta,tuple(changed)).astype(np.int64)-base,
        context.render(frame,meta).astype(np.int64)-base,
        context.render(frame,(15,18,14),tuple(changed)).astype(np.int64)-base])
    # Q16 coefficients of an adversarial Voronoi construction. This is a
    # fixed integer fixture, not a fitted speech target or runtime LP solver.
    target=base+((vectors.T@np.asarray([567897,-543045,-351939],np.int64)+32768)//65536)
    if np.any(target<-32768) or np.any(target>32767):raise AssertionError('Synthetic target out of range')
    return blob,target.astype(np.int16)


def nonminimal(blob):
    n,spectra,parameters,pulses,pre,bright=sparse.unpack(blob);writer=BitWriter()
    for f,vec in enumerate(spectra):
        writer.put(1,1);writer.put(0,1)
        for gap in [vec[0]]+[b-a-1 for a,b in zip(vec,vec[1:])]:
            writer.put(0,8);writer.put(gap,6)
        scale,lag,gain=parameters[f]
        writer.put(scale,5);writer.put(lag-18,7);writer.put(gain//2,3)
        for position,amp in pulses[f*4:f*4+4]:
            writer.put(sparse.POSITIONS.index(position),6);writer.put(int(amp>0),1)
    writer.aligned();payload=writer.get()
    return blob[:20]+struct.pack('<H',len(payload))+payload


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True,exist_ok=True);cls.wall=time.perf_counter()
        cls.sources={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                     for name in ('joint.py','test_joint.py','PROTOCOL.md')}
        cls.receivers=[NativeReceiver('common'),NativeReceiver('v5-only')]
        cls.receiver=staticmethod(j.old.bridge_receiver(*cls.receivers));cls.report={}

    @classmethod
    def tearDownClass(cls):
        for r in cls.receivers:
            r.close()
            if r.process.returncode:raise AssertionError('Native receiver shutdown failed')
        if cls.sources!={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in cls.sources}:
            raise AssertionError('Synthetic sources changed during validation')
        cls.report.update(schema='lpx-sparse2-joint-synthetic-v1',status='UNVERIFIED',source_hashes=cls.sources,
            seconds=time.perf_counter()-cls.wall,python=sys.version.split()[0],numpy=np.__version__,
            requests_per_receiver={r.kind:r.calls for r in cls.receivers},
            scope='Adversarial synthetic mechanism only; no speech/listening/AVR claim')
        (OUTPUT/'tests.json').write_text(json.dumps(cls.report,indent=2)+'\n')

    def test_real_coordinate_rescue_and_all_native_points(self):
        blob,target=witness();result=j.search(target,blob,self.receiver)
        region=next(r for r in result.regions if r.frame==1)
        self.assertEqual(region.metadata,((15,18,14),(14,18,14)))
        self.assertEqual([p.symbols for p in region.pools],[(39,38,40),(5,4,3),(9,10,8),(2,3,4)])
        self.assertEqual(result.baseline.pcm_sse,7612088)
        inc=(39,5,9,2)
        for arm in ('coordinate_mp','coordinate_pm'):
            p=region.endpoints[arm]
            self.assertEqual((p.metadata_index,p.symbols,p.pcm_sse),(0,inc,7612088))
            self.assertEqual(min(p.pcm_sse for p in region.queried[arm]),7612088)
            self.assertEqual(region.query_attempts[arm],249)
        winner=region.endpoints['joint']
        self.assertEqual((winner.metadata_index,winner.symbols,winner.pcm_sse),(1,(39,5,10,2),6720780))
        self.assertEqual(min(p.pcm_sse for p in region.points if p.metadata_index==0),7612088)
        self.assertEqual(result.counters['leaves'],324)
        self.assertEqual(result.counters['native_oracle_calls'],323)
        self.assertEqual(result.counters['model_checks'],325)
        self.assertEqual(result.counters['pulse_screens'],2048)
        self.assertEqual(result.counters['branch_prefix_samples'],960)
        self.assertTrue(all(len(q)==12 for q in result.queues.values()))
        self.assertEqual(result.counters['coordinate_mp_queries'],498)
        self.assertEqual(result.counters['coordinate_pm_queries'],498)
        # Every point already passed independent complete model and BOTH native
        # reference paths. Verify raw remains generated even when it loses.
        self.assertTrue(all(result.raw[a].blob!=blob for a in j.ARMS))
        self.report['witness']=dict(frame=1,baseline_sse=7612088,joint_sse=6720780,
            coordinate_mp_sse=7612088,coordinate_pm_sse=7612088,
            metadata=region.metadata,pools=[p.symbols for p in region.pools],
            original_pulses=inc,joint_pulses=winner.symbols,
            target_recipe='Fixed Q16 integer recombination of actual synthetic decoder traces',
            counters=result.counters,all_native_model_pcm_pwm_exact=True)
        self.__class__.result=result;self.__class__.target=target

    def test_metadata_patch_gain_codes_nonminimal_and_tail(self):
        n=641;spectra=[[3+5*k for k in range(10)]]*3
        parameters=[(0,145,0),(31,18,14),(15,63,6)]
        pulses=[(sparse.POSITIONS[(i*13)%64],-8 if i%2 else 7) for i in range(12)]
        blob=nonminimal(sparse.pack(n,spectra,parameters,pulses,8192,4096));context=j.Context(blob)
        self.assertTrue(np.any((context.base.pcm==-32768)|(context.base.pcm==32767)))
        cases=0
        for frame,meta in ((0,(1,145,2)),(0,(0,145,0)),(1,(30,18,12)),(1,(31,18,14))):
            path=tuple(context.base.layout.symbols[frame*4:frame*4+4])
            patched=context.patch(frame,meta,path);fields=sparse.unpack(patched)
            self.assertEqual(len(patched),len(blob));self.assertEqual(fields[2][frame],meta)
            self.assertEqual(fields[1],spectra);self.assertEqual(fields[3],pulses)
            allowed=set(range(context.offsets[frame],context.offsets[frame]+5))
            allowed.update(range(context.offsets[frame]+12,context.offsets[frame]+15))
            for at,(a,b) in enumerate(zip(blob,patched)):
                for bit in range(8):
                    if (a^b)&(1<<bit):self.assertIn(at*8+bit,allowed)
            j.old._oracle(self.receiver,patched,context.render(frame,meta,path));cases+=1
        # Explicit gain2-to-0 at a nonzero high scale, preserving every lag bit.
        original=tuple(context.base.layout.symbols[4:8])
        gain2=context.patch(1,(31,18,2),original);gain2_context=j.Context(gain2)
        gain0=gain2_context.patch(1,(31,18,0),original)
        self.assertEqual(sparse.unpack(gain2)[2][1],(31,18,2))
        self.assertEqual(sparse.unpack(gain0)[2][1],(31,18,0))
        j.old._oracle(self.receiver,gain2,sparse.decode_model(gain2))
        j.old._oracle(self.receiver,gain0,sparse.decode_model(gain0));cases+=2
        for at,(a,b) in enumerate(zip(gain2,gain0)):
            for bit in range(8):
                if (a^b)&(1<<bit):self.assertIn(at*8+bit,range(context.offsets[1]+12,context.offsets[1]+15))
        with self.assertRaises(ValueError):context.patch(0,(1,145,3),(0,0,0,0))
        with self.assertRaises(ValueError):context.patch(0,(1,144,2),(0,0,0,0))
        with self.assertRaises(ValueError):context.patch(2,(1,63,2),(0,0,0,0))
        for frame,symbols in ((-1,(0,0,0,0)),(0,(0,0,0,0,0)),(0,(0.,0,0,0)),
                              (True,(0,0,0,0)),(0,(True,0,0,0)),(0,(128,0,0,0))):
            with self.assertRaises(ValueError):context.patch(frame,(1,145,2),symbols)
        self.report['patches']=dict(cases=cases,all_nonedit_bits_exact=True,
            nonminimal_rice=True,partial_frame_protected=True,gain_code_mapping_exact=True,
            gain2_to_0_exact=True,actual_saturated_recurrence=True,malformed_patch_contract_rejected=True)

    def test_state_conditional_pools_equal_independent_full_model(self):
        blob,target=witness();context=j.Context(blob);frame=1
        metas=((15,18,14),(15,18,12));pools=j.freeze_pools(context,target,frame,metas)
        checks=0
        original=tuple(context.base.layout.symbols[4:8])
        for m,meta in enumerate(metas):
            for part in (1,2,3):
                for symbol in (0,63,127):
                    path=list(original);path[part]=symbol
                    encoded=context.patch(frame,meta,tuple(path));pcm=sparse.decode_model(encoded)
                    at=(frame*4+part)*80;stop=min(at+400,len(target))
                    self.assertEqual(pools[part].losses[m][symbol],j.old._sse(target[at:stop],pcm[at:stop]))
                    checks+=1
        self.report['conditional_snapshots']=dict(independent_screen_checks=checks,
            carried_ring_lpc_dd_cc_under_each_metadata=True,common_pools_for_all_arms=True)

    def test_whole_admission_same_caps_and_protected_floors(self):
        # unittest sorts names: construct a small result if this method is run
        # alone; the normal suite reuses the already verified witness grid.
        if not hasattr(self.__class__,'result'):
            blob,target=witness();result=j.search(target,blob,self.receiver)
        else:result,target=self.__class__.result,self.__class__.target
        selected,journal=j.admit(target,result,speech=False)
        self.assertEqual(journal['metric_proposal_attempts'],36)
        self.assertLessEqual(journal['unique_metric_evaluations'],37)
        for arm in j.ARMS:
            self.assertEqual(len(journal['candidates'][arm]),12)
            final=selected[arm]
            self.assertEqual(len(final.blob),len(result.baseline.blob))
            metrics=journal['baseline'] if final.blob==result.baseline.blob else next(
                r['metrics'] for r in journal['candidates'][arm]
                if r['sha256']==hashlib.sha256(final.blob).hexdigest())
            self.assertTrue(_floors(metrics,journal['baseline']))
        self.report['admission']=dict(equal_proposal_cap_per_arm=12,attempts=36,
            unique_metric_evaluations=journal['unique_metric_evaluations'],same_baseline_floors=True)


if __name__=='__main__':
    program=unittest.main(argv=[sys.argv[0],*remaining],verbosity=2,exit=False)
    path=OUTPUT/'tests.json'
    if path.exists():
        report=json.loads(path.read_text());report['status']='PASS' if program.result.wasSuccessful() else 'FAIL'
        path.write_text(json.dumps(report,indent=2)+'\n')
    sys.exit(0 if program.result.wasSuccessful() else 1)
