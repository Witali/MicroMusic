"""Qualify and build a separate compact Q3/T1 voice plus EEPROM bell profile.

The candidate must preserve both intelligibility floors and all structural
spectrogram components of the supplied T1 bell model's voice before AVR tools
are called. The unchanged bell frequencies, phases, event timing and EEPROM
table are retained; three integer bell amplitudes are fitted automatically.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
TEMPLATE = CODEC/'q3-bell-oneshot/hq4.S'
sys.path.insert(0, str(CODEC))
from bell_model import decode_bell, validate as validate_bell
from hq4_core import pack_stream
from hq4_q3 import render
from hq4_speech_search import deterministic_estoi, validate as validate_stream
from model import decode as legacy_decode
from spectrogram_objective import SpectrogramObjective


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


natural = load_module('q3_bell_level_helper', ROOT/'tools/build-natural-bell-hq4.py')
tilt = load_module('q3_bell_t1_helper', ROOT/'tools/probe-hq4-natural-timbre.py').tilt


def arrays(model):
    f, d = np.asarray(model['frames']), np.asarray(model['durations'])
    samples = model.get('samples')
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 3072:
        raise ValueError('Voice model must contain an integer full sample count')
    validate_stream(f, d, samples)
    return f.astype(np.uint8), d.astype(np.uint16)


def candidate_voice(model):
    if (model.get('schema') != 'hq4-q3-v1' or model.get('coefficient_scale') != 8
            or model.get('coefficient_range') != [-7, 7]
            or model.get('tilt_shift') != 1 or model.get('sample_rate') != 7500):
        raise ValueError('Candidate must be explicitly encoded as HQ4-Q3-T1; Q4 data is incompatible')
    frames, durations = arrays(model)
    if np.any((frames[:, 2:] & 15) == 0) or np.any((frames[:, 2:] >> 4) == 0):
        raise ValueError('Q3 coefficient -8 is excluded from the stable reflection range')
    if len(pack_stream(frames, durations)) > 432:
        raise ValueError('576-byte core, 15-byte bell descriptor and end marker leave 432 voice bytes')
    pcm, wraps = render(frames, durations, 1)
    if np.any(wraps):
        raise ValueError('Candidate has intermediate signed-byte arithmetic wraps')
    signed = pcm.astype(np.int16)-128
    if np.max(abs(signed)) > 115 or np.any(abs(np.diff(signed)) >= 48):
        raise ValueError('Candidate exceeds PWM headroom or discontinuity guards')
    return frames, durations, pcm, wraps


def control_voice(model):
    if (model.get('schema') != 'hq4-natural-timbre-v1' or model.get('tilt_shift') != 1
            or model.get('sample_rate') != 7500):
        raise ValueError('The bell model must retain its explicit original Q4-T1 control voice')
    frames, durations = arrays(model)
    pcm, wraps = tilt(legacy_decode(frames, durations, 0), 1)
    if wraps:
        raise ValueError('The control T1 output contains wraps')
    return pcm


def quality_gate(reference, before_pcm, after_pcm):
    objective = SpectrogramObjective(reference)
    def score(pcm):
        if len(pcm) != len(reference):
            raise ValueError('Candidate and control must preserve the complete voice duration')
        audio = (pcm.astype(float)-128)/128
        return dict(**objective.evaluate(audio), stoi=float(stoi(reference, audio, 7500)),
                    estoi=deterministic_estoi(reference, audio, 7500))
    before, after = score(before_pcm), score(after_pcm)
    floors = ('stoi', 'estoi')
    ceilings = ('fine_log_error', 'envelope_error', 'unsupported_energy', 'missing_energy')
    failed = ([key for key in floors if after[key] < before[key]-1e-12]+
              [key for key in ceilings if after[key] > before[key]+1e-12])
    if after['spectrogram_loss'] >= before['spectrogram_loss']-1e-12:
        failed.append('spectrogram_loss')
    return dict(before=before, after=after, passed=not failed, failed_guards=failed)


def build(reference_path, bell_path, voice_path, output, avr_bin=None, node='node'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference, sr = sf.read(reference_path, dtype='float64')
    source_bell = json.loads(Path(bell_path).read_text(encoding='utf-8'))
    model = json.loads(Path(voice_path).read_text(encoding='utf-8'))
    validate_bell(source_bell)
    if source_bell.get('schema') != 'micromusic-bell-hq4-t1-v1':
        raise ValueError('Bell input must retain the explicitly identified Q4-T1 comparison model')
    frames, durations, voice_pcm, wraps = candidate_voice(model)
    before_voice = control_voice(source_bell['voice'])
    boundary = int(source_bell['prefix_samples'])
    if (sr != 7500 or reference.ndim != 1 or not np.all(np.isfinite(reference))
            or len(reference) != boundary+len(voice_pcm)):
        raise ValueError('Full reference must preserve the complete bell and voice at 7500 Hz')
    gate = quality_gate(reference[boundary:], before_voice, voice_pcm)
    provenance = dict(sourceBellModelSha256=sha(Path(bell_path).read_bytes()),
                      sourceVoiceModelSha256=sha(Path(voice_path).read_bytes()),
                      referenceSha256=sha(Path(reference_path).read_bytes()))
    gate.update(schema='micromusic-q3-bell-voice-gate-v1', **provenance,
                intermediate_wraps=wraps.tolist(), hardware_tested=False,
                human_listening_verified=False)
    (output/'voice-gate.json').write_text(json.dumps(gate, indent=2)+'\n', encoding='utf-8', newline='\n')
    if not gate['passed']:
        # A rejected rerun cannot leave a stale, apparently current HEX image.
        for name in ('firmware.elf', 'firmware.bin', 'firmware.hex', 'verification.json', 'actual.raw'):
            (output/name).unlink(missing_ok=True)
        return dict(status='rejected-quality-guards', gate=gate, avrAssembled=False)
    selected_bell = natural.balance_bell(source_bell, reference, voice_pcm)
    prepared = copy.deepcopy(model)
    prepared.update(voice_offset_samples=boundary, stream_sha256=sha(pack_stream(frames, durations)))
    (output/'voice-input.json').write_text(json.dumps(prepared, indent=2)+'\n', encoding='utf-8', newline='\n')
    builder = load_module('q3_bell_private_builder', ROOT/'tools/encode-bell-hq4.py')
    builder.TEMPLATE = TEMPLATE
    builder.decode = lambda f, d, _: render(f, d, 1)[0]
    builder.fit = lambda reference, voice_pcm, boundary: copy.deepcopy(selected_bell)
    report = builder.build(reference_path, output/'voice-input.json', None, output, avr_bin, node)
    after_pcm = np.r_[decode_bell(selected_bell), voice_pcm]
    before_pcm = np.r_[decode_bell(source_bell), before_voice]
    scores = dict(control_t1_hybrid=builder.quality(reference, before_pcm, boundary),
                  q3_t1_hybrid=builder.quality(reference, after_pcm, boundary), voice_gate=gate,
                  bell_level_policy='source-relative-voice-rms', intermediate_wraps=wraps.tolist())
    (output/'quality.json').write_text(json.dumps(scores, indent=2)+'\n', encoding='utf-8', newline='\n')
    hp = butter(2, 70, fs=sr, btype='highpass', output='sos')
    tracks = [sosfilt(hp, x) for x in (reference, (before_pcm.astype(float)-128)/128,
                                     (after_pcm.astype(float)-128)/128)]
    rms = float(np.sqrt(np.mean(tracks[0]**2)))
    tracks = [x*rms/(np.sqrt(np.mean(x*x))+1e-12) for x in tracks]
    gain = min(1., .94/max(float(np.max(abs(x))) for x in tracks))
    for name, track in zip(('original-matched', 'before-matched', 'after-matched'), tracks):
        sf.write(output/(name+'.wav'), track*gain, sr, subtype='PCM_16')
    sf.write(output/'comparison.wav', np.r_[tracks[0]*gain, np.zeros(2250), tracks[1]*gain,
                                           np.zeros(2250), tracks[2]*gain], sr, subtype='PCM_16')
    assembled_model = json.loads((output/'model.json').read_text(encoding='utf-8'))
    assembled_model.update(schema='micromusic-bell-hq4-q3-t1-v1', coefficient_scale=8,
                           coefficient_range=[-7, 7], tilt_shift=1,
                           bell_level_policy='source-relative-voice-rms')
    (output/'model.json').write_text(json.dumps(assembled_model, indent=2)+'\n', encoding='utf-8', newline='\n')
    report.update(schema='micromusic-bell-hq4-q3-t1-build-v1', coefficientScale=8,
                  tiltShift=1, modelSha256=sha((output/'model.json').read_bytes()),
                  voiceGatePassed=True, bellMultiplierScale=16, voiceMultiplierScale=8,
                  bellLevelPolicy='source-relative-voice-rms', **provenance)
    for path in (Path(__file__), CODEC/'hq4_q3.py', CODEC/'spectrogram_objective.py',
                 ROOT/'tools/build-natural-bell-hq4.py', ROOT/'tools/probe-hq4-natural-timbre.py'):
        report['normalizedSourceSha256'][path.relative_to(ROOT).as_posix()] = sha(path.read_text(encoding='utf-8').encode())
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'bell-model', 'voice-model', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--node', default='node')
    a = p.parse_args()
    report = build(a.reference, a.bell_model, a.voice_model, a.output, a.avr_bin, a.node)
    print(json.dumps({key:report[key] for key in ('status', 'flashBytes', 'codeBytes', 'streamBytes', 'phraseSamples') if key in report}, indent=2))
    return 0 if report['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
