"""Selection policies, complete-case rollback and resumable corpus evidence."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import benchmark_shared_corpus as benchmark
import optimize_shared_corpus as driver
from speech_compact import repack, unpack, pack, decode_model
from standard_metrics import pwm_duties
from test_speech_v4 import fixture


def metrics(pcm_sse=10.,pwm_sse=20.,pcm_stoi=.8,pwm_stoi=.7):
    return {'pcm16':{'error_energy':pcm_sse,'reference_energy':100.,'ser_db':10.,'stoi':pcm_stoi},
            'pwm8':{'error_energy':pwm_sse,'reference_energy':100.,'ser_db':7.,'stoi':pwm_stoi},
            'activity_preserved':True,'pwm_activity_preserved':True,'rms_gain_db':0.}


class SharedSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.inputs=self.root/'inputs';self.sources=self.root/'baseline';self.out=self.root/'selected'
        self.inputs.mkdir();self.cases=[];self.base_env=benchmark.environment()

    def run_driver(self,**kwargs):
        with redirect_stdout(io.StringIO()):
            return driver.run(self.inputs,self.sources,self.out,**kwargs)

    def make_case(self,*,kind='music',condition='natural',zero=False,parts=(321,),profile=4,status='complete'):
        key=f'case-{len(self.cases)+1:016x}'
        blobs=[repack(fixture(profile,n))[0] for n in parts]
        pieces=[decode_model(blob) for blob in blobs]
        complete=np.concatenate(pieces)
        reference=np.zeros(len(complete),np.int16) if zero else complete.copy()
        path=self.inputs/'references'/key;path.mkdir(parents=True)
        sf.write(path/'reference.wav',reference,8000,subtype='PCM_16')
        case={'id':key,'cohort':'regression','kind':kind,'language':'ru' if kind=='speech' else 'und',
            'condition':condition,'split':'evaluation','samples':len(reference),
            'reference':f'references/{key}/reference.wav',
            'reference_pcm16_sha256':benchmark.sha(reference.astype('<i2').tobytes()),'segments':[]}
        source=self.sources/key/str(profile);source.mkdir(parents=True)
        records=[];start=0
        for index,(n,blob,pcm) in enumerate(zip(parts,blobs,pieces)):
            ref=reference[start:start+n];name=f'segment-{index:03d}'
            sf.write(path/(name+'.wav'),ref,8000,subtype='PCM_16')
            geometry={'index':index,'start':start,'samples':n,
                'reference':f'references/{key}/{name}.wav','pcm16_sha256':benchmark.sha(ref.astype('<i2').tobytes())}
            case['segments'].append(geometry)
            (source/(name+'.l4hy')).write_bytes(blob)
            sf.write(source/(name+'.wav'),pcm,8000,subtype='PCM_16')
            cap=20+((n+319)//320)*(20 if profile==4 else 30)
            self.assertLessEqual(len(blob),cap)
            records.append({'index':index,'start':start,'samples':n,'stream':name+'.l4hy','decoded':name+'.wav',
                'reference_pcm16_sha256':geometry['pcm16_sha256'],'stream_sha256':benchmark.sha(blob),
                'pcm16_sha256':benchmark.sha(pcm.astype('<i2').tobytes()),'pwm_sha256':benchmark.sha(pwm_duties(pcm).tobytes()),
                'cap_bytes':cap,'file_bytes':len(blob),'header_bytes':22,'payload_bytes':len(blob)-22,
                'quality':benchmark.quality(ref,pcm,kind=='speech'),'encode_seconds':0.,'refine_seconds':0.,'enhance_seconds':0.})
            start+=n
        sf.write(source/'complete.wav',complete,8000,subtype='PCM_16')
        row={'id':key,'profile':profile,'environment':self.base_env,
            'fingerprint':benchmark.sha(benchmark.canonical([self.base_env,case,profile])),
            'reference_pcm16_sha256':case['reference_pcm16_sha256'],'status':status,'segments':records,
            'quality':benchmark.quality(reference,complete,kind=='speech'),
            'file_bytes':sum(len(b) for b in blobs),'payload_bytes':sum(len(b)-22 for b in blobs),
            'file_bps':sum(len(b) for b in blobs)*64000/len(reference),
            'payload_bps':sum(len(b)-22 for b in blobs)*64000/len(reference),
            'pcm16_sha256':benchmark.sha(complete.astype('<i2').tobytes()),'seconds':0.}
        if status!='complete':
            row={k:row[k] for k in ('id','profile','environment','fingerprint','reference_pcm16_sha256','status','seconds')}
            row.update(segments=[],error={'type':'ValueError','message':'Exact compact baseline does not fit file cap'})
        benchmark.save(source/'report.json',driver._signed(row))
        self.cases.append(case)
        benchmark.save(self.inputs/'manifest.json',{'schema':'lpx-shared-corpus-v1','cases':self.cases})
        return case,source,blobs

    def selected(self,case,profile=4):
        return benchmark.load(self.out/case['id']/str(profile)/'report.json')

    def test_necessary_policy_uses_frozen_triggers_without_changing_floors(self):
        case={'kind':'speech','condition':'natural'};good=metrics()
        self.assertFalse(driver.choose_work(case,good,'necessary')['run'])
        self.assertTrue(driver.choose_work(case,good,'all-speech')['run'])
        changes=[('condition',None),('activity_preserved',False),('pwm_activity_preserved',False),
                 ('error_energy',101.),('ser_db',2.99),('stoi',.59),('rms_gain_db',-3.01)]
        for field,value in changes:
            q=deepcopy(good);c=dict(case)
            if field=='condition':c[field]='Noisy quiet input'
            elif field in ('error_energy','ser_db','stoi'):q['pcm16'][field]=value
            else:q[field]=value
            with self.subTest(field=field):self.assertTrue(driver.choose_work(c,q,'necessary')['run'])
        self.assertFalse(driver.whole_case_guard(good,metrics(pwm_stoi=.69))['passed'])

    def test_nonspeech_only_exact_silence_gets_lower_scale_repair(self):
        case={'kind':'music','condition':'synthetic'}
        self.assertFalse(driver.choose_work(case,metrics(pcm_sse=200.),'all-speech')['run'])
        work=driver.choose_work(case,metrics(),'necessary',exact_zero=True)
        self.assertTrue(work['run']);self.assertEqual(work['proposals'],['lower_scales'])
        self.assertFalse(driver.choose_work(case,metrics(pcm_sse=0.),'necessary',exact_zero=True)['run'])

    def test_joined_floors_handle_unavailable_stoi_and_new_activity_failures(self):
        before=metrics()
        for candidate in (metrics(pcm_sse=11.),metrics(pwm_sse=21.),metrics(pcm_stoi=None),metrics(pwm_stoi=.69)):
            self.assertFalse(driver.whole_case_guard(before,candidate)['passed'])
        missing=metrics(pcm_stoi=None,pwm_stoi=None)
        self.assertTrue(driver.whole_case_guard(missing,missing)['passed'])
        for key in ('activity_preserved','pwm_activity_preserved'):
            candidate=deepcopy(before);candidate[key]=False
            self.assertFalse(driver.whole_case_guard(before,candidate)['passed'])
            old=deepcopy(before);old[key]=False
            self.assertTrue(driver.whole_case_guard(old,candidate)['passed'])

    def test_missing_and_partial_reports_are_pending_and_can_resume(self):
        case,source,_=self.make_case();valid=(source/'report.json').read_bytes()
        (source/'report.json').write_bytes(b'{')
        first=self.run_driver()
        self.assertEqual(first['baseline_pending'],1);self.assertEqual(first['baseline_missing'],1)
        self.assertEqual(first['accounted'],0)
        (source/'report.json').write_bytes(valid)
        with patch.object(driver.optimizer,'optimize',side_effect=AssertionError('Non-speech search')):
            second=self.run_driver()
        self.assertEqual(second['complete'],1);self.assertEqual(second['baseline_missing'],1)
        self.assertTrue(self.selected(case)['retained_baseline'])

    def test_no_fit_is_accounted_without_selected_audio_and_reuses_cache(self):
        case,_,_=self.make_case(status='no_fit')
        first=self.run_driver(profiles=(4,))
        row=self.selected(case)
        self.assertEqual(first['baseline_no_fit'],1);self.assertEqual(row['status'],'no_fit')
        self.assertEqual(row['cohort'],case['cohort']);self.assertEqual(row['samples'],case['samples'])
        self.assertEqual(row['segments'],[])
        self.assertFalse((self.out/case['id']/'4/complete.wav').exists())
        self.assertEqual(self.run_driver(profiles=(4,))['reused'],1)

    def test_music_retains_exact_streams_and_revalidates_cached_references(self):
        case,_,blobs=self.make_case(parts=(321,321))
        with patch.object(driver.optimizer,'optimize',side_effect=AssertionError('Non-speech search')):
            self.run_driver(profiles=(4,));self.run_driver(profiles=(4,))
        row=self.selected(case)
        self.assertEqual(row['policy_decision']['reason'],'outside_speech_scope')
        for part,blob in zip(row['segments'],blobs):
            self.assertEqual((self.out/case['id']/'4'/part['stream']).read_bytes(),blob)
        path=self.inputs/case['reference'];pcm,_=sf.read(path,dtype='int16');pcm[0]^=1
        sf.write(path,pcm,8000,subtype='PCM_16')
        with self.assertRaisesRegex(ValueError,'Prepared PCM reference changed'):
            self.run_driver(profiles=(4,))

    def test_exact_silence_repair_runs_only_lower_scales_and_preserves_cap(self):
        case,_,_=self.make_case(zero=True)
        with patch.object(driver.optimizer,'optimize',wraps=driver.optimizer.optimize) as search:
            result=self.run_driver(profiles=(4,))
        self.assertEqual(search.call_args.kwargs['proposals'],('lower_scales',))
        self.assertEqual(search.call_args.kwargs['refinement_passes'],2)
        self.assertEqual(search.call_args.kwargs['refinement_horizon'],320)
        row=self.selected(case)
        self.assertEqual(result['changed'],1)
        self.assertEqual(row['quality']['pcm16']['error_energy'],0)
        self.assertEqual(row['quality']['pwm8']['error_energy'],0)
        self.assertEqual(row['baseline_quality_status']['status'],'no_fit')
        self.assertEqual(row['selected_quality_status']['status'],'passes_waveform_activity_checks')
        self.assertLessEqual(row['segments'][0]['file_bytes'],row['segments'][0]['cap_bytes'])

    def test_full_case_rejection_restores_all_segments_and_keeps_rejected_evidence(self):
        case,_,blobs=self.make_case(zero=True,parts=(321,321))
        def worse(ref,blob,*args,**kwargs):
            n,p,spectra,params,pulses,pre,bright,extras=unpack(blob)
            candidate,_=pack(n,p,spectra,[(31,lag,gain) for scale,lag,gain in params],pulses,pre,bright,extras)
            pcm=decode_model(candidate)
            return candidate,pcm,{'accepted':True,'seconds':0.,'status':'accepted'}
        with patch.object(driver.optimizer,'optimize',side_effect=worse):self.run_driver(profiles=(4,))
        row=self.selected(case)
        self.assertTrue(row['whole_case_rollback']);self.assertTrue(row['retained_baseline'])
        self.assertFalse(row['whole_case_guard']['passed']);self.assertIsNotNone(row['rejected'])
        for record,blob in zip(row['segments'],blobs):
            self.assertEqual((self.out/case['id']/'4'/record['stream']).read_bytes(),blob)
        self.assertEqual(self.run_driver(profiles=(4,))['reused'],1)
        rejected=self.out/case['id']/'4/rejected'/row['rejected']['segments'][0]['stream']
        rejected.write_bytes(rejected.read_bytes()+b'\0')
        with self.assertRaisesRegex(ValueError,'Cached stream/PCM/model/PWM'):
            self.run_driver(profiles=(4,))

    def test_modified_metadata_or_changed_baseline_bytes_cannot_reuse_cache(self):
        case,source,_=self.make_case()
        self.run_driver(profiles=(4,))
        cached=self.out/case['id']/'4/report.json';valid=cached.read_bytes();row=json.loads(valid)
        row['quality']['pcm16']['error_energy']+=1;benchmark.save(cached,row)
        with self.assertRaisesRegex(ValueError,'Stale or modified result metadata'):
            self.run_driver(profiles=(4,))
        cached.write_bytes(valid)
        report=source/'report.json';report.write_bytes(report.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'Stale or modified result metadata'):
            self.run_driver(profiles=(4,))

    def test_shards_partition_jobs_and_outputs_cannot_overlap_baseline(self):
        self.make_case();self.make_case()
        left=self.run_driver(shard=0,shards=2);right=self.run_driver(shard=1,shards=2)
        self.assertEqual(left['expected_jobs'],2);self.assertEqual(left['complete'],2)
        self.assertEqual(right['expected_jobs'],2);self.assertEqual(right['baseline_missing'],2)
        with self.assertRaisesRegex(ValueError,'must not overlap'):
            driver.run(self.inputs,self.sources,self.sources,profiles=(4,))


if __name__=='__main__':unittest.main()
