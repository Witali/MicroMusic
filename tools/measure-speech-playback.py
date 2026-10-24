"""Measure unchanged speech playback against its original, with optional AVR provenance.

This reuses the existing spectral, partial and intelligibility measurements.
Raw levels remain unadjusted; only the explicitly named spectral/track metrics
use the established 70 Hz highpass and one global RMS match. No time alignment
or frequency warping is applied, and no parameter search is performed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('playback_measurements', ROOT/'tools/probe-lpc2-quality.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def named(values):
    result = {}
    for value in values:
        label, separator, path = value.partition('=')
        if not separator or not label or not path or label in result:
            raise ValueError('Expected unique nonempty Label=path arguments')
        result[label] = Path(path)
    return result


def label_path(path):
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else 'external/'+path.name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--candidate',required=True,action='append',help='Label=unchanged.wav or Label=AVR.raw')
    p.add_argument('--build',action='append',default=[],help='SameLabel=verified-build.json')
    p.add_argument('--output',required=True,type=Path)
    a = p.parse_args()
    candidates, builds = named(a.candidate), named(a.build)
    if set(builds)-set(candidates):
        p.error('Build labels must identify candidates')
    reference,sr = sf.read(a.reference,dtype='float64')
    measure = metrics.Measurements(reference,sr)
    report = dict(schema='speech-playback-measurements-v1',reference=label_path(a.reference),
        reference_sha256=sha(a.reference.read_bytes()),samples=len(reference),sample_rate=sr,
        duration_seconds=len(reference)/sr,reference_raw_signal=metrics.raw_stats(reference),
        processing=dict(raw='Every unchanged sample, no DC/gain adjustment',
            spectral='Identical 70Hz highpass, global RMS match; no time/frequency warping',
            partials='Up to ten strongest peaks over time; raw-level HP-only and RMS-matched results both retained',
            intelligibility='STOI and deterministic eSTOI on original raw signals',
            strict_bounds='Every selected reference peak must be present and within5dB; matched-only averages cannot establish this'),
        candidates={})
    for label,path in candidates.items():
        audio = metrics.read_before(path,len(reference),sr)
        row = dict(source=label_path(path),source_sha256=sha(path.read_bytes()))
        if label in builds:
            build_path = builds[label]
            build = json.loads(build_path.read_text(encoding='utf-8'))
            pcm = np.rint(audio*128+128)
            if (not np.array_equal((pcm-128)/128,audio) or np.any((pcm<0)|(pcm>255))):
                raise ValueError('AVR provenance requires exact raw PWM samples, without level adjustment')
            phrase_hash = sha(pcm.astype(np.uint8).tobytes())
            complete = np.r_[pcm.astype(np.uint8),np.full(2*len(pcm),128,np.uint8)]
            complete_hash = sha(complete.tobytes())
            verification = build.get('verification',{})
            # Flash-only fixtures still load an erased 64-byte EEPROM image
            # in the emulator; that scaffolding is not firmware EEPROM use.
            eeprom_hash = (build.get('eepromSha256') if build['eepromUsedBytes']
                else build.get('verificationEepromSha256'))
            if (build['status']!='verified' or build['phraseSamples']!=len(reference)
                    or build['sampleHz']!=sr or build['phrasePcmSha256']!=phrase_hash
                    or build['expectedPcmSha256']!=complete_hash
                    or not verification.get('pass') or verification.get('mismatches')!=0
                    or len(verification.get('engines',[]))!=3
                    or verification.get('expectedPcmSha256')!=complete_hash
                    or verification.get('actualPcmSha256')!=complete_hash
                    or verification.get('flashBytes')!=build['flashBytes']
                    or not eeprom_hash or verification.get('eepromSha256')!=eeprom_hash):
                raise ValueError('Candidate differs from the verified complete AVR recording')
            row['firmware'] = dict(build=label_path(build_path),build_sha256=sha(build_path.read_bytes()),
                flash_bytes=build['flashBytes'],eeprom_bytes=build['eepromUsedBytes'],
                verification_eeprom_image_bytes=verification['eepromBytes'],
                phrase_pcm_sha256=phrase_hash,retained_three_engine_pcm_matches=True,
                pwm_endpoint_samples=int(np.sum((pcm==0)|(pcm==255))),
                unique_pwm_values=int(len(np.unique(pcm))),
                maximum_sram_span_bytes=verification['maximumSramSpanBytes'],
                minimum_slack_cycles=verification['foregroundTiming']['minimumSlackCycles'])
        row.update(measure.measure(audio))
        report['candidates'][label] = row
    sources = [Path(__file__),ROOT/'tools/probe-lpc2-quality.py']
    sources += [ROOT/'ATtiny13A/Sound/codec'/name for name in (
        'harmonic_tracks.py','partial_bounds.py','spectrogram_objective.py','hq4_speech_search.py')]
    report['sources_sha256_normalized_lf'] = {
        label_path(path):sha(path.read_bytes().replace(b'\r\n',b'\n')) for path in sources}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({label:{key:row[key] for key in ('stoi','estoi','spectrogram_loss','raw_mse','raw_snr_db')}
        for label,row in report['candidates'].items()}))


if __name__=='__main__':
    main()
