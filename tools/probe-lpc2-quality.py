#!/usr/bin/env python3
"""Compare exact LPC2 Improved and original LPX3 residual profiles at 7500 Hz.

No source normalization, DC removal, trimming, transposition or resampling.
All containers contain their own LPC2 base. Outputs are PC research results.
"""
import argparse
from copy import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np
from pystoi import stoi
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from lpc2_excitation import Lpc2Bridge,encode_excitation,decode_excitation,verify_javascript,default_node
from spectrogram_objective import SpectrogramObjective
from harmonic_tracks import HarmonicTrackObjective
from partial_bounds import check_partial_bounds
from hq4_speech_search import deterministic_estoi


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')


def raw_stats(audio):
    return dict(mean=float(np.mean(audio)),rms=float(np.sqrt(np.mean(audio**2))),
                peak=float(np.max(abs(audio))),samples_abs_ge_one=int(np.sum(abs(audio)>=1.)))


class Measurements:
    def __init__(self,reference,sr):
        self.reference,self.sr = reference,sr
        self.spectral = SpectrogramObjective(reference,sr)
        self.tracks = HarmonicTrackObjective(reference,sr)
        self.raw_tracks = copy(self.tracks)
        self.raw_tracks.matched = lambda value:sosfilt(self.raw_tracks.hp,np.asarray(value,dtype=float))

    def measure(self,audio):
        audio = np.asarray(audio,dtype=float)
        if audio.shape != self.reference.shape or not np.all(np.isfinite(audio)):
            raise ValueError('Candidate must preserve every reference sample and remain finite')
        matched = self.tracks.details(audio)
        raw = self.raw_tracks.details(audio)
        error = float(np.mean((self.reference-audio)**2))
        return dict(stoi=float(stoi(self.reference,audio,self.sr)),
            estoi=deterministic_estoi(self.reference,audio,self.sr),**self.spectral.evaluate(audio),
            raw_signal=raw_stats(audio),raw_mse=error,
            raw_snr_db=float(10*np.log10(max(float(np.mean(self.reference**2)),1e-30)/max(error,1e-30))),
            raw_output_rms_ratio=float(np.sqrt(np.mean(audio**2))/max(np.sqrt(np.mean(self.reference**2)),1e-30)),
            harmonic_metrics=matched['metrics'],raw_harmonic_metrics=raw['metrics'],
            strict_5db_raw=check_partial_bounds(raw,max_level_error_db=5.,duration_seconds=len(audio)/self.sr),
            strict_5db_level_matched=check_partial_bounds(matched,max_level_error_db=5.,duration_seconds=len(audio)/self.sr))


def read_before(path,samples,sr):
    if path.suffix.lower() == '.raw':
        pcm = np.frombuffer(path.read_bytes(),np.uint8)
        if len(pcm) == 3*samples and np.all(pcm[samples:] == 128):
            pcm = pcm[:samples]
        if len(pcm) != samples:
            raise ValueError('Before RAW must have exact phrase length, optionally followed by 2N midpoint silence')
        return (pcm.astype(float)-128)/128
    audio,rate = sf.read(path,dtype='float64')
    if rate != sr or audio.shape != (samples,):
        raise ValueError('Before WAV must have unchanged mono rate/count')
    return audio


def run_one(reference_path,output,*,recording_id='reference',node=None,bits=(2,3,4),before=()):
    started = time.perf_counter()
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or len(reference)<3072 or not np.all(np.isfinite(reference)):
        raise ValueError('Expected a complete mono 7500-Hz reference with >=3072 finite samples')
    output.mkdir(parents=True,exist_ok=True)
    node = node or default_node()
    bridge = Lpc2Bridge(output/'encode-cache',node=node)
    base,native = bridge.encode(reference,sr,output/'native')
    # Empty provider cache guarantees that the validation decoder derives
    # coefficients from the embedded parameters without reading the input PCM.
    independent = Lpc2Bridge(output/'parameter-only-decode',node=node)
    coefficients = independent(base)
    if coefficients[1] != sr or len(coefficients[2]) != len(reference):
        raise AssertionError('Base-only LPC2 decoder changed sample rate/count')
    metrics = Measurements(reference,sr)
    parametric = np.frombuffer((output/'native/decoded.f32').read_bytes(),dtype='<f4').copy()
    freshly_decoded = np.frombuffer((output/'parameter-only-decode'/sha(base)/'decoded.f32').read_bytes(),dtype='<f4')
    if not np.array_equal(parametric,freshly_decoded):
        raise AssertionError('Native LPC2 decode differs when only base bytes are supplied')
    (output/'base.lp2').write_bytes(base)
    sf.write(output/'lpc2-improved.wav',parametric,sr,subtype='FLOAT')
    report = dict(schema='lpc2-quality-probe-v1',recording_id=recording_id,sample_rate=sr,samples=len(reference),
        reference_sha256=sha(reference_path.read_bytes()),reference_raw_signal=raw_stats(reference),
        input_policy='Unchanged full-duration 7500-Hz source level/DC; no normalization, cropping or resampling',
        profile_policy='Exact LPC2 Improved default postfilter0.35; original LPX3v1 uses encoded excitation instead of chirp/mixed-noise/postfilter',
        brightness_policy='LPX3 reserved brightness field is zero; automatic brightness is disabled',
        size_policy='Actual complete data containers including embedded base/header/scales; decoder code/runtime memory excluded',
        avr_implemented=False,hardware_tested=False,profiles={},before={})
    report['profiles']['lpc2-improved'] = dict(container='base.lp2',audio='lpc2-improved.wav',
        container_bytes=len(base),container_sha256=sha(base),parameter_only_pcm_exact=True,
        **metrics.measure(parametric))
    listening = [('Original',reference)]
    for label,path in before:
        audio = read_before(path,len(reference),sr)
        filename = f'before-{len(report["before"])}.wav'
        sf.write(output/filename,audio,sr,subtype='FLOAT')
        report['before'][label] = dict(source_sha256=sha(path.read_bytes()),audio=filename,**metrics.measure(audio))
        listening.append((label,audio))
    listening.append(('LPC2 Improved',parametric.astype(float)))
    for width in bits:
        name = f'{"lpx3" if width<=4 else "lpx4"}-{width}bit'
        blob,audio,info = encode_excitation(reference,sr,base,width,bridge)
        container_path = output/(name+('.lpx3' if width<=4 else '.lpx4'))
        container_path.write_bytes(blob)
        decoded,decode_info = decode_excitation(blob,independent)
        if not np.array_equal(audio,decoded):
            raise AssertionError('LPX3 full-container parameter-only decode differs from encoder output')
        js = verify_javascript(container_path,output/(name+'-js.f32'),node=node)
        difference = float(np.max(abs(decoded.astype(float)-js.astype(float))))
        if js.shape != decoded.shape or difference > 1e-6:
            raise AssertionError('Independent original JavaScript LPX3 PCM differs')
        sf.write(output/(name+'.wav'),decoded,sr,subtype='FLOAT')
        report['profiles'][name] = dict(container=container_path.name,audio=name+'.wav',
            container_bytes=len(blob),container_sha256=sha(blob),pcm_f32_sha256=sha(decoded.astype('<f4').tobytes()),
            parameter_only_pcm_exact=True,independent_javascript_max_abs_error=difference,
            bits_per_second=len(blob)*8*sr/len(reference),container_info=decode_info,training=info['training'],
            **metrics.measure(decoded))
        listening.append((f'{"LPX3" if width<=4 else "LPX4"} {width} bit',decoded.astype(float)))
        print(json.dumps(dict(id=recording_id,profile=name,bytes=len(blob),stoi=report['profiles'][name]['stoi'],
                              estoi=report['profiles'][name]['estoi'],js_max_error=difference)),flush=True)
    processed = [(name,metrics.spectral.matched(audio)) for name,audio in listening]
    peak = max(float(np.max(abs(audio))) for name,audio in processed)
    scale = .85/max(peak,1e-20)
    sf.write(output/'comparison.wav',np.concatenate([np.r_[audio*scale,np.zeros(round(.3*sr))] for name,audio in processed]),
             sr,subtype='PCM_16')
    report['listening_order'] = [name for name,audio in processed]
    report['listening_processing'] = 'Diagnostic only: common70Hz highpass, globalRMSmatch and shared peak scaling; raw individual WAVs unchanged'
    sources = [Path(__file__),CODEC/'lpc2_excitation.py',ROOT/'tools/lpc2-reference-cli.mjs',
        ROOT/'ATmega328/Sound/reference/lpx3/hybrid_codec.py',ROOT/'ATmega328/Sound/reference/lpx3/lpx3_decoder.js',
        ROOT/'ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html',CODEC/'spectrogram_objective.py',
        CODEC/'harmonic_tracks.py',CODEC/'partial_bounds.py',CODEC/'hq4_speech_search.py']
    report['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources}
    report['runtime'] = {name:importlib.metadata.version(name) for name in ('numpy','scipy','numba','soundfile','pystoi')}
    report['elapsed_seconds'] = round(time.perf_counter()-started,6)
    save(output/'report.json',report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--reference',type=Path)
    source.add_argument('--manifest',type=Path)
    p.add_argument('--references-root',type=Path)
    p.add_argument('--ids',nargs='+')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recording-id',default='reference')
    p.add_argument('--node')
    p.add_argument('--bits',nargs='+',type=int,choices=(2,3,4,6,8),default=[2,3,4])
    p.add_argument('--before',action='append',default=[],help='Label=matching WAV or actual AVR RAW; single-reference mode')
    p.add_argument('--before-hq4-root',type=Path,help='Corpus baseline models root containing ID/expected.raw and model.json')
    p.add_argument('--retain',type=Path,help='Retain reports only; no original/derived audio or residual containers')
    a = p.parse_args()
    if a.reference:
        before = [(label,Path(path)) for label,path in (value.split('=',1) for value in a.before)]
        report = run_one(a.reference,a.output,recording_id=a.recording_id,node=a.node,bits=tuple(a.bits),before=before)
        if a.retain:
            save(a.retain/'report.json',report)
        return
    if not a.references_root or a.before:
        p.error('Corpus mode requires --references-root; use --before-hq4-root for matching baseline')
    manifest = json.loads(a.manifest.read_text(encoding='utf-8'))
    entries = [entry for entry in manifest['clips'] if entry['variant']=='center2048']
    if a.ids:
        requested=set(a.ids)
        entries=[entry for entry in entries if entry['id'] in requested or entry['source_clip_id'] in requested]
        found={value for entry in entries for value in (entry['id'],entry['source_clip_id'])}
        if requested-found:
            p.error('Unknown corpus IDs: '+','.join(sorted(requested-found)))
    summary = dict(schema='lpc2-quality-corpus-v1',manifest_sha256=sha(a.manifest.read_bytes()),clips=[])
    for entry in entries:
        ident = entry['id']
        try:
            path=(a.references_root/entry['reference']).resolve()
            if not path.is_relative_to(a.references_root.resolve()) or sha(path.read_bytes()) != entry['reference_sha256']:
                raise ValueError('Prepared corpus reference path/hash mismatch')
            before=[]
            if a.before_hq4_root:
                folder=a.before_hq4_root/ident
                model=json.loads((folder/'model.json').read_text(encoding='utf-8'))
                if model['reference_sha256'] != entry['reference_sha256']:
                    raise ValueError('HQ4 baseline belongs to another corpus reference')
                before=[('HQ4 automatic baseline',folder/'expected.raw')]
            report=run_one(path,a.output/ident,recording_id=ident,node=a.node,bits=tuple(a.bits),before=before)
            summary['clips'].append(dict(id=ident,status='complete',report=f'{ident}/report.json',
                metrics={name:{key:row[key] for key in ('container_bytes','stoi','estoi','spectrogram_loss','raw_mse')}
                         for name,row in report['profiles'].items()}))
            if a.retain:
                save(a.retain/ident/'report.json',report)
        except Exception as error:
            summary['clips'].append(dict(id=ident,status='failed',error_type=type(error).__name__,
                                          error_message='See generated local logs; this recording is not dropped'))
            print(json.dumps(dict(id=ident,status='failed',error=str(error))),flush=True)
        save(a.output/'corpus-report.json',summary)
        if a.retain:
            save(a.retain/'corpus-report.json',summary)


if __name__ == '__main__':
    main()
