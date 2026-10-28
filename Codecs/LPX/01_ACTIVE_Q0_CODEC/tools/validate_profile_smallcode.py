"""Reuse the measured Flash recipe for selected legacy8/12/16 streams.

Speech parsers are explicitly disabled here. The existing Flash builder,
symbol retention, exact audio exclusion and full-PWM simulator are reused.
"""
import argparse,struct
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save
from benchmark_speech_flash import (ROOT,CANDIDATES,environment,runtime_fingerprint,
    simulate,compile_image,same_harness,load,sha,validation_provenance)
from lpx4 import decode,encode
from compact_format import pack
from q0_model import decode_pcm16
from standard_metrics import pwm_duties

RECIPE='unroll1-tune0-lto-call-relax'

def run(results,output,avr_bin,runner,lib,wsl,historical_runner=False):
    results,output=Path(results),Path(output);source=ROOT/'src'
    env=environment(source,avr_bin,legacy_only=True);runtime=runtime_fingerprint(runner,lib,wsl)
    spec=CANDIDATES[RECIPE];files=sorted(results.glob('case-*/complete.json'))
    if len(files)!=27:raise ValueError('All27 completed quality cases are required')
    target=output/'verification.json'
    validator=validation_provenance(runtime=runtime,sources=(Path(__file__),))
    previous=load(target) if target.exists() else None
    report=(previous if previous and previous['environment']==env and previous['runtime']==runtime
            and previous.get('validator_provenance')==validator else
            {'environment':env,'runtime':runtime,'recipe':RECIPE,'specification':spec,
             'cases':{},'images':{},'stress':{},'physical_hardware_measured':False})
    report['validator_provenance']=validator
    items={};reference=None
    with BatchSession('batch',v3_features=24) as decoder:
        for completed in files:
            c=load(completed);case=c['id'];points=[]
            for row in c['rates']:
                rate=row['ceiling_bps'];meta=row['selected'];path=results/case/str(rate)/'selected.l4hy';blob=path.read_bytes()
                pcm,sr=sf.read(path.with_suffix('.wav'),dtype='int16')
                if sr!=8000 or pcm.shape!=(32000,) or sha(blob)!=meta['stream_sha256'] or sha(pcm.astype('<i2').tobytes())!=meta['pcm16_sha256']:
                    raise ValueError('Saved selected stream/WAV changed')
                native=decoder.decode_one_s16(blob,32000)
                if native is None or not np.array_equal(native,pcm) or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('Merged native/model output changed')
                item={'id':case+'-'+str(rate),'case':case,'profile':rate,'blob':blob,'pwm':pwm_duties(pcm).tobytes(),
                    'samples':32000,'stream_sha256':sha(blob),'pcm_sha256':meta['pcm16_sha256']}
                if sha(item['pwm'])!=meta['pwm_sha256']:raise AssertionError('Saved selected PWM changed')
                if reference is None:
                    reference=compile_image(source,env,CANDIDATES['baseline'],item,output/'reference',avr_bin)
                key=item['stream_sha256'];items[item['id']]=item
                measured=simulate(source,env,spec,item,output/'images'/key,avr_bin,runner,lib,wsl,runtime,historical=historical_runner,validator_sources=(Path(__file__),))
                same_harness(measured,reference)
                if measured['underruns']:raise ValueError('Small-code selected stream underruns')
                report['images'][key]=measured;points.append({'ceiling_bps':rate,'stream_sha256':key,
                    'mean_decode_wall_cycles':measured['mean_decode_wall_cycles'],'underruns':measured['underruns']})
            report['cases'][case]={'quality_fingerprint':c['fingerprint'],'points':points};save(target,report)
            print(case,'small-code full PWM verified',len(report['cases']),'of27',flush=True)
        for rate in (8000,12000,16000):
            cases=[item for item in items.values() if item['profile']==rate]
            heaviest=max(cases,key=lambda item:report['images'][item['stream_sha256']]['mean_decode_wall_cycles'])
            frames,blocks,q=decode(heaviest['blob']);raw=bytearray(heaviest['blob'][:20]);raw[:6]=b'L3AV\x01\x03';struct.pack_into('<I',raw,8,len(q)*2)
            blob=encode({'raw':bytes(raw),'frames':frames*2,'blocks':blocks*2},fast=True)[0];other=pack(blob,24)[0]
            if len(other)<len(blob):blob=other
            pcm=decoder.decode_one_s16(blob,64000)
            if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('Continuous native/model output mismatch')
            item={'id':'repeat-'+str(rate),'case':heaviest['case'],'profile':rate,'blob':blob,'samples':64000,
                'pwm':pwm_duties(pcm).tobytes(),'stream_sha256':sha(blob),'pcm_sha256':sha(pcm.astype('<i2').tobytes())}
            path=output/'stress'/str(rate)/'repeat.l4hy';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
            record={'source_case':heaviest['case'],'source_stream_sha256':heaviest['stream_sha256'],
                'repeat_stream_sha256':sha(blob),'samples':64000,'continuous_state':True,'quality_reference':False,'images':{}}
            for name,assembly,irq in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
                measured=simulate(source,env,spec,item,path.parent/name,avr_bin,runner,lib,wsl,runtime,assembly,irq,historical_runner,validator_sources=(Path(__file__),))
                same_harness(measured,reference)
                if assembly and measured['underruns']:raise ValueError('Small-code continuous ASM underruns')
                record['images'][name]=measured
            report['stress'][str(rate)]=record;save(target,report)
            print(rate,'small-code continuous controls verified',flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('results',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--runner',type=Path,required=True);ap.add_argument('--lib',type=Path,required=True);ap.add_argument('--wsl',default='Ubuntu')
    ap.add_argument('--historical-runner',action='store_true',help='Explicitly label old capped duration evidence')
    a=ap.parse_args();run(a.results,a.output,a.avr_bin,a.runner,a.lib,a.wsl,a.historical_runner)
