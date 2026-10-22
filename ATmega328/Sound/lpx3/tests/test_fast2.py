#!/usr/bin/env python3
"""Compare identical compressed L3AV data decoded via old LPC and Fast2 LPC.
This is a PC functional test. Do not mislabel results as measured AVR cycles.
"""
from pathlib import Path
import json, subprocess, hashlib, wave, sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
PRIV=ROOT.parent/'private_inputs'
REPORT=ROOT/'reports'/'fast2_validation.json'

def build():
    (ROOT/'profiling').mkdir(exist_ok=True)
    for suffix,defines in [('base',[]),('fast2',['-DLPX3_FAST_LPC_INTERP','-DLPX3_LPC_SEGMENTS=2']),('fast4',['-DLPX3_FAST_LPC_INTERP','-DLPX3_LPC_SEGMENTS=4'])]:
        cmd=['g++','-std=c++11','-O2','-Wall','-Wextra','-Werror',*defines,str(ROOT/'src/Lpx3AvrCore.cpp'),str(ROOT/'tests/decode_host.cpp'),'-o',str(ROOT/'profiling'/f'decode_{suffix}_host')]
        subprocess.run(cmd,check=True)

def pcm(decoder: str,compressed:Path) -> bytes:
    out=ROOT/'profiling'/(compressed.stem+'_'+decoder+'.pcm8')
    p=subprocess.run([str(ROOT/'profiling'/f'decode_{decoder}_host'),str(compressed),str(out)],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError((p.returncode,p.stderr,compressed,decoder))
    return out.read_bytes()

def main():
    build()
    from pystoi import stoi
    rows=[]
    tests=[('synthetic',ROOT/'examples/LPX3_PROGMEM/synthetic_voice.l3av')]
    for voice in ['vinni','xtuj-ntt','ne-otv']:
        for bits in [2,3,4]:
            for qbits in [8,10]:
                stream=ROOT/'build'/f'{voice}_{bits}bit_lsf{qbits}.l3av'
                if stream.exists():tests.append((voice,stream))
    assert len(tests) in (1,19), (len(tests),'Expected synthetic alone, or synthetic + 18 optional private streams')
    for voice,stream in tests:
        src=stream.read_bytes()
        assert src[:4]==b'L3AV'
        output_count=int.from_bytes(src[8:12],'little')
        base=pcm('base',stream)
        assert len(base)==output_count,(voice,stream,'base',len(base),output_count)
        for suffix in ['fast2','fast4']:
            fast=pcm(suffix,stream)
            assert len(fast)==len(base)
            a=np.frombuffer(base,dtype=np.uint8).astype(np.int16)
            b=np.frombuffer(fast,dtype=np.uint8).astype(np.int16)
            d=a-b
            rows.append({'voice':voice,'stream':stream.name,'mode':suffix,'bytes':len(src),
                         'samples':len(base),'max_abs_PCM8_diff':int(np.abs(d).max()),
                         'rms_PCM8_difference':float(np.sqrt(np.mean(np.square(d.astype(np.float64))))),
                         'equal_samples':int(np.count_nonzero(d==0)),
                         'pcm_sha256':hashlib.sha256(fast).hexdigest()})
    quality=[]
    for voice in ['vinni','xtuj-ntt','ne-otv']:
        wav=PRIV/voice/'original.wav'
        if not wav.exists():continue
        with wave.open(str(wav)) as wf:
            assert wf.getframerate()==8000 and wf.getnchannels()==1
            ref=np.frombuffer(wf.readframes(wf.getnframes()),dtype='<i2').astype(float)/32768
        old=np.fromfile(PRIV/voice/'pcm_f32.bin',dtype='<f4').astype(float)
        assert len(ref)==len(old)
        stream=ROOT.parent/'release_private'/voice/f'{voice}_L3AV_optimized.l3av'
        q={'voice':voice,'stream_bytes':stream.stat().st_size,'samples':len(ref),'lpx3_reference_STOI':float(stoi(ref,old,8000))}
        baseline=np.frombuffer(pcm('base',stream),dtype=np.uint8).astype(float)
        assert len(baseline)==len(ref)
        q['base_STOI']=float(stoi(ref,(baseline-128)/127,8000))
        for suffix in ['fast2','fast4']:
            o=np.frombuffer(pcm(suffix,stream),dtype=np.uint8).astype(float)
            assert len(o)==len(ref)
            q[f'{suffix}_STOI']=float(stoi(ref,(o-128)/127,8000))
            q[f'{suffix}_STOI_delta_against_base']=q[f'{suffix}_STOI']-q['base_STOI']
        quality.append(q)
    report={'test_environment':'desktop C++ compiler; NOT AVR clock/cycle trace',
            'fast2_note':'Original .l3av files are byte-identical; only playback coefficients differ',
            'streams_tested':len(tests),'pair_tests':len(rows),
            'modes_tested':['baseline','fast2','fast4'],
            'quality':quality,'pair_stats':rows}
    REPORT.parent.mkdir(exist_ok=True,parents=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('PASS streams',len(tests),'comparisons',len(rows),'quality cases',len(quality))
    for q in quality:print(q['voice'],'base',round(q['base_STOI'],6),'fast2',round(q['fast2_STOI'],6),'fast4',round(q['fast4_STOI'],6))
if __name__=='__main__': main()
