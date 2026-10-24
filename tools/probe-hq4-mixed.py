#!/usr/bin/env python3
"""Bounded PC experiment: add quantized frame-wise noise to original HQ4.

Frozen HQ4 remains an exact representable case. Only a candidate preserving
baseline STOI, eSTOI and both spectral ceilings can replace the exported elite.
No public firmware is changed and no assembler size or timing is verified.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import random
import sys
import time
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt
from pystoi import stoi

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from auto_encoder import SpectralObjective
from hq4_core import unpack_stream
from hq4_mixed import VERSION,decode,pack_mix
from model import decode as decode_baseline
from speech_spectrum import PersistentSpectrumObjective


def sha(data):return hashlib.sha256(data).hexdigest()


def extended_stoi(reference,audio,sr):
    state=np.random.get_state()
    try:
        np.random.seed(0)
        return float(stoi(reference,audio,sr,extended=True))
    finally:np.random.set_state(state)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clip',choices=('chego','otvechaesh','vinni'),default='vinni')
    p.add_argument('--input-stream',type=Path)
    p.add_argument('--reference',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'build/hq4-mixed/vinni')
    p.add_argument('--proposals',type=int,default=2000)
    p.add_argument('--seed',type=int,default=23102)
    a=p.parse_args()
    if a.proposals<0:p.error('--proposals must be nonnegative')
    source=a.input_stream or CODEC/'release'/a.clip/'speech.hq'
    original=a.reference or ROOT/'web-player/audio/originals'/(a.clip+'.wav')
    manifest=json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    clip=next(item for item in manifest['clips'] if item['id']==a.clip)
    if sha(original.read_bytes())!=clip['sha256']:
        p.error('Reference differs from the canonical recording')
    reference,sr=sf.read(original)
    frames,durations=unpack_stream(source.read_bytes())
    spectral=SpectralObjective(reference,sr)
    bands=PersistentSpectrumObjective(reference,sr)
    if int(durations.sum())!=len(reference):p.error('HQ4 stream must preserve every reference sample')
    zero=np.zeros(len(frames),np.uint8)
    np.testing.assert_array_equal(decode(frames,durations,zero),decode_baseline(frames,durations,0))

    def evaluate(codes):
        pcm=decode(frames,durations,codes)
        signed=pcm.astype(np.int16)-128
        peak=int(np.max(abs(signed)))
        steps=int(np.sum(abs(np.diff(signed))>=48))
        if peak>115 or steps:return None
        audio=signed.astype(np.float64)/128
        spectrum=spectral.spectrum(audio)
        spectrum['spectral_loss']=spectrum.pop('loss')
        detail=bands.evaluate(audio)
        loss=.7*spectrum['spectral_loss']+.2*detail['band_loss']+.1*detail['persistent_spectral_error']
        return dict(loss=loss,**spectrum,**detail,stoi=float(stoi(reference,audio,sr)),
                    estoi=extended_stoi(reference,audio,sr),peak_signed=peak,steps_ge_48=steps)

    # The hard baseline is always the current frozen release, even when a
    # previously accepted optimized stream is supplied as a starting point.
    frozen_f,frozen_d=unpack_stream((CODEC/'release'/a.clip/'speech.hq').read_bytes())
    if not np.array_equal(frames,frozen_f) or not np.array_equal(durations,frozen_d):
        frozen_pcm=decode_baseline(frozen_f,frozen_d,0)
        frozen_audio=(frozen_pcm.astype(np.float64)-128)/128
        fs=spectral.spectrum(frozen_audio);fd=bands.evaluate(frozen_audio)
        baseline=dict(spectral_loss=fs['loss'],log_spectral_error=fs['log_spectral_error'],
                      stoi=float(stoi(reference,frozen_audio,sr)),estoi=extended_stoi(reference,frozen_audio,sr))
    else:baseline=evaluate(zero)
    if baseline is None:raise ValueError('Frozen baseline exceeds peak/step constraints')

    def feasible(score):
        return (score is not None and all(math.isfinite(v) for v in score.values())
                and score['stoi']+1e-12>=baseline['stoi']
                and score['estoi']+1e-12>=baseline['estoi']
                and score['spectral_loss']<=baseline['spectral_loss']+1e-12
                and score['log_spectral_error']<=baseline['log_spectral_error']+1e-12)

    initial=evaluate(zero)
    if not feasible(initial):raise ValueError('Input stream does not satisfy frozen baseline guards')
    best=(zero.copy(),initial.copy())
    current=(zero.copy(),initial.copy())
    unconstrained=(zero.copy(),initial.copy())
    rng=random.Random(a.seed)
    options={}
    for i,frame in enumerate(frames):
        gain=int(frame[1])&15
        if frame[0] and gain:
            values={0:0}
            for code in (1,2,3):
                amount=gain>>(3-code)
                if amount and amount not in values:values[amount]=code
            options[i]=list(values.values())
    indices=list(options)
    singles=[(i,code) for i in indices for code in options[i] if code]
    # Every frame/level gets an independent zero-map test before joint search.
    rng.shuffle(singles)
    seen={pack_mix(zero)}
    history=[];evaluated=invalid=duplicates=0
    start=time.monotonic()
    for proposal in range(a.proposals):
        if proposal<len(singles):
            candidate=zero.copy();index,code=singles[proposal];candidate[index]=code
        elif indices:
            if proposal%300==0:current=(best[0].copy(),best[1].copy())
            candidate=(best if rng.random()<.65 else current)[0].copy()
            index=rng.choice(indices)
            for j in range(index,min(len(frames),index+rng.randint(1,4))):
                if j in options:candidate[j]=rng.choice(options[j])
        else:break
        packed=pack_mix(candidate)
        if packed in seen:
            duplicates+=1;continue
        seen.add(packed)
        score=evaluate(candidate);evaluated+=1
        if score is None:
            invalid+=1;continue
        if score['loss']<unconstrained[1]['loss']:
            unconstrained=(candidate.copy(),score.copy())
        if feasible(score) and score['loss']<best[1]['loss']-1e-10:
            best=(candidate.copy(),score.copy())
            history.append(dict(proposal=proposal+1,active_frames=int(np.count_nonzero(candidate)),**score))
        def energy(s):
            return (s['loss']+30*max(0.,baseline['stoi']-s['stoi'])
                    +15*max(0.,baseline['estoi']-s['estoi'])
                    +4*max(0.,s['spectral_loss']-baseline['spectral_loss']))
        delta=energy(score)-energy(current[1])
        temperature=.003*(.1**((proposal%300)/299))
        if delta<0 or rng.random()<math.exp(-min(700,max(0.,delta/temperature))):
            current=(candidate.copy(),score.copy())
        if (proposal+1)%500==0:
            print(json.dumps(dict(proposals=proposal+1,evaluated=evaluated,improvements=len(history),
                seconds=round(time.monotonic()-start,1),**best[1])),flush=True)

    a.output.mkdir(parents=True,exist_ok=True)
    selected_pcm=decode(frames,durations,best[0])
    original_pcm=decode(frames,durations,zero)
    selected_mix=pack_mix(best[0])
    (a.output/'mix.bin').write_bytes(selected_mix)
    (a.output/'expected.raw').write_bytes(selected_pcm.tobytes())
    (a.output/'speech.hq').write_bytes(source.read_bytes())
    audio=[reference,(original_pcm.astype(float)-128)/128,(selected_pcm.astype(float)-128)/128]
    audio=[sosfilt(spectral.hp,x) for x in audio]
    audio=[x*spectral.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in audio]
    scale=.85/max(float(np.max(abs(x))) for x in audio)
    for name,x in zip(('original','baseline','mixed'),audio):
        sf.write(a.output/(name+'.wav'),x*scale,sr,subtype='PCM_16')
    gap=np.zeros(round(.3*sr))
    sf.write(a.output/'comparison.wav',np.concatenate([part for i in (0,1,0,2) for part in (audio[i]*scale,gap)]),sr,subtype='PCM_16')
    paths=[Path(__file__)]+[CODEC/name for name in ('hq4_mixed.py','model.py','hq4_core.py','auto_encoder.py','speech_spectrum.py')]
    report=dict(schema=VERSION,clip=a.clip,sample_rate=sr,samples=len(reference),recording_trimmed=False,
        reference_sha256=clip['sha256'],input_stream_sha256=sha(source.read_bytes()),
        sources_sha256_normalized_lf={str(path.relative_to(ROOT)).replace('\\','/'):
            sha(path.read_text(encoding='utf-8').encode()) for path in paths},
        runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','numba','pystoi','soundfile')},
        config=dict(seed=a.seed,proposals=a.proposals,objective_weights=dict(spectral=.7,band=.2,persistent=.1),
                    ratios=['off','gain>>2','gain>>1','gain']),
        evaluated=evaluated,invalid_peak_or_steps=invalid,duplicate_maps=duplicates,
        exhaustive_single_maps=len(singles),history=history,baseline=baseline,initial=initial,final=best[1],
        selected_codes=best[0].tolist(),selected_active_frames=int(np.count_nonzero(best[0])),
        selected_mix_bytes=len(selected_mix),selected_mix_sha256=sha(selected_mix),
        selected_pcm_sha256=sha(selected_pcm.tobytes()),
        unconstrained_best=dict(metrics=unconstrained[1],codes=unconstrained[0].tolist(),
                                satisfies_baseline=feasible(unconstrained[1])),
        memory=dict(original_decoder_bytes=406,stream_bytes=len(source.read_bytes()),
            map_bytes=(len(frames)+3)//4,map_fits_64_byte_eeprom=(len(frames)+3)//4<=64,
            assembler_extra_code_estimate_bytes=[40,80],estimate_only=True,
            explanation='Rough engineering allowance for a2bit EEPROM-map reader, per-frame amplitude selection, voiced noise branch and reuse of the LFSR. No assembly, register allocation, code sharing or cycle audit has been performed. Extra code cannot be assumed to fit a currently full1024-byte image.'),
        limitations=['PC-only quantized decoder experiment; no AVR assembly or timing verification.',
            'Voiced mixing intentionally advances the shared existing LFSR; later unvoiced noise phase may change. All0 and zero-amplitude cases preserve baseline state exactly.',
            'Only mix codes are optimized; original pitch, coefficients, gain, frame boundaries and full sample count remain fixed.',
            'The lowest-loss unconstrained candidate is diagnostic only when any intelligibility or spectral guard fails.',
            'STOI/eSTOI and spectral metrics do not replace listening. No audible quality improvement is asserted.'],
        conclusion='Feasible mixed-excitation improvement found; remains a PC-only candidate.' if history else
                   'No mixed-excitation improvement satisfying all frozen HQ4 guards found in this bounded search; retain exact zero-map baseline.',
        elapsed_seconds=round(time.monotonic()-start,3),avr_assembled=False,hardware_tested=False)
    (a.output/'quality.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(conclusion=report['conclusion'],active_frames=report['selected_active_frames'],
        improvements=len(history),evaluated=evaluated,baseline=baseline,final=best[1])),flush=True)


if __name__=='__main__':main()
