#!/usr/bin/env python3
"""Find persistent reference frequencies and magnitude deficits against HQ4.

The output guides an offline encoder objective. It does not authorize filtering
the source or adding sinusoidal oscillators to the decoder. All source samples
are retained and each original recording is checked against its saved hash.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from hq4_core import unpack_stream
from model import decode
from speech_pitch import track_speech_pitch
from speech_spectrum import PersistentSpectrumObjective, VERSION


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references',type=Path,default=ROOT/'web-player/audio/originals',
                   help='Directory containing canonical <clip>.wav originals')
    p.add_argument('--clip',choices=('chego','otvechaesh','vinni'))
    p.add_argument('--candidate-wav',type=Path,help='Alternative decoded WAV; requires --clip')
    p.add_argument('--output',type=Path,default=ROOT/'build/speech-spectrum/analysis.json')
    a = p.parse_args()
    if a.candidate_wav and not a.clip:
        p.error('--candidate-wav requires --clip')
    manifest = json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    results = []
    for clip in manifest['clips']:
        name = clip['id']
        if a.clip and name != a.clip:
            continue
        source = a.references/(name+'.wav')
        if digest(source) != clip['sha256']:
            raise ValueError(f'{name}: canonical source hash mismatch')
        reference,sr = sf.read(source)
        objective = PersistentSpectrumObjective(reference,sr)
        centres,f0,periodicity,pitch = track_speech_pitch(reference,sr)
        if a.candidate_wav:
            candidate,candidate_sr = sf.read(a.candidate_wav)
            if candidate_sr != sr:
                raise ValueError('Candidate sample rate differs from the original')
            candidate_source = dict(kind='external-decoded-wav',sha256=digest(a.candidate_wav))
        else:
            stream_path = CODEC/'release'/name/'speech.hq'
            payload = stream_path.read_bytes()
            frames,durations = unpack_stream(payload)
            pcm = decode(frames,durations,0)
            candidate = (pcm.astype(np.float64)-128)/128
            candidate_source = dict(kind='frozen-hq4-exact-numerical-decode',
                source_path=str(stream_path.relative_to(ROOT)).replace('\\','/'),
                sha256=digest(stream_path),stream_bytes=len(payload),
                pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
                avr_verification='See retained frozen HQ4 and one-shot verification reports; this diagnostic itself does not run an AVR emulator.')
        diagnostics = objective.diagnostics(f0,periodicity,centres)
        result = dict(id=name,source_sha256=clip['sha256'],samples=len(reference),
            duration_seconds=len(reference)/sr,recording_trimmed=False,
            candidate=candidate_source,persistent_voice_prior_hz=pitch['prior_hz'],
            objective=objective.evaluate(candidate),frequency_analysis=diagnostics,
            error_bands=objective.compare_bands(candidate))
        results.append(result)
        print(json.dumps(dict(id=name,ridges=len(objective.ridges),
            objective=result['objective'],strongest_ridges_hz=[round(item['median_hz'],1) for item in diagnostics['ridges'][:8]],
            largest_error_bands_hz=[[round(item['low_hz']),round(item['high_hz'])] for item in result['error_bands'][:4]])),flush=True)
    sources = [Path(__file__)]+[CODEC/name for name in ('speech_spectrum.py','speech_pitch.py','period_wave.py','hq4_core.py','model.py')]
    report = dict(schema=VERSION,runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','numba','soundfile')},
        sources_sha256_normalized_lf={str(path.relative_to(ROOT)).replace('\\','/'):
            hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources},
        objective_definition=dict(band_envelope_loss='Weighted mean absolute difference between temporal one-third-octave magnitude envelopes, independently normalized to unit RMS within each band.',
            band_shape_loss='Weighted mean absolute natural-log difference of unit-L2 spectral-band vectors in each frame; relative magnitude floor .01.',
            band_loss='0.5*(band_envelope_loss+band_shape_loss)',
            persistent_spectral_error='Full-bin log magnitude error, reference-derived ridge weights 1..3, absolute magnitude floor .005*highpassed_reference_RMS.',
            reference_weights='Frame weight .25+.75*min(1,frame_RMS/overall_frame_RMS); band weight1 above2% of highest band RMS, otherwise .25.',
            common_preprocessing='Identical70Hz second-order Butterworth highpass and global RMS matching; no time alignment, frequency warping, trimming or phase fitting.'),
        limitations=['Magnitude deficits/excesses are not a waveform residual: phase is discarded.',
            'The 512-sample Hann window is68.3ms long with14.65Hz FFT-bin spacing; true frequency resolution is poorer than the bin spacing. Short attacks are smeared and ridge timing is uncertain by approximately half a window.',
            'A persistent narrow component cannot be semantically classified as speech, a formant, a knock or noise by this analysis alone.',
            'STOI/eSTOI constraints and listening are required; these metrics are encoder search aids, not perceptual quality guarantees.',
            'No additional MCU Flash, EEPROM data, FFT, notch filter or oscillator has been introduced.'],
        clips=results)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
