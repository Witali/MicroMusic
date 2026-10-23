"""Fit a three-tone bell prefix and build its actual one-shot HQ4 voice image."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
TEMPLATE = CODEC/'bell-oneshot/hq4.S'
sys.path.insert(0, str(CODEC))
from bell_model import SINE, decode_bell, descriptor, fit
from hq4_core import pack_stream
from model import decode
from auto_encoder import SpectralObjective
from hq4_speech_search import deterministic_estoi

spec = importlib.util.spec_from_file_location('tiny_helpers', ROOT/'tools/build-tiny-speech.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def quality(reference, pcm, boundary):
    audio = (pcm.astype(float)-128)/128
    def metrics(a, b):
        return dict(stoi=float(stoi(a, b, 7500)), estoi=deterministic_estoi(a, b, 7500),
                    **SpectralObjective(a).spectrum(b))
    result = dict(full=metrics(reference, audio), voice=metrics(reference[boundary:], audio[boundary:]))
    x, y = reference[:boundary], audio[:boundary]
    scale = np.sqrt(np.mean(reference[boundary:]**2))/(np.sqrt(np.mean(audio[boundary:]**2))+1e-12)
    result['bell'] = dict(**SpectralObjective(x).spectrum(y),
        mse_at_voice_matched_level=float(np.mean((y*scale-x)**2)),
        reference_rms=float(np.sqrt(np.mean(x*x))), decoded_rms=float(np.sqrt(np.mean(y*y))),
        reference_bell_to_voice_rms=float(np.sqrt(np.mean(x*x)/np.mean(reference[boundary:]**2))),
        decoded_bell_to_voice_rms=float(np.sqrt(np.mean(y*y)/np.mean(audio[boundary:]**2))))
    result['peak_signed'] = int(np.max(abs(pcm.astype(np.int16)-128)))
    result['steps_ge_48'] = int(np.sum(abs(np.diff(pcm.astype(np.int16))) >= 48))
    return result


def build(reference_path, voice_model_path, baseline_path, output, avr_bin=None, node='node'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference, sr = sf.read(reference_path, dtype='float64')
    voice_model = json.loads(Path(voice_model_path).read_text(encoding='utf-8'))
    boundary = int(voice_model['voice_offset_samples'])
    frames = np.asarray(voice_model['frames'], np.uint8)
    durations = np.asarray(voice_model['durations'], np.uint16)
    voice = decode(frames, durations, 0)
    if sr != 7500 or reference.ndim != 1 or boundary+len(voice) != len(reference):
        raise ValueError('Reference and voice must preserve the exact complete phrase')
    voice_stream = pack_stream(frames, durations)
    if sha(voice_stream) != voice_model['stream_sha256']:
        raise ValueError('Voice serialization differs from retained input')
    model = fit(reference, voice, boundary)
    model['voice'] = voice_model
    model['reference_sha256'] = sha(Path(reference_path).read_bytes())
    model['samples'] = len(reference)
    (output/'model.json').write_text(json.dumps(model, indent=2)+'\n', encoding='utf-8', newline='\n')
    bell = decode_bell(model)
    phrase = np.r_[bell, voice]
    expected = np.r_[phrase, np.full(len(phrase)*2, 128, np.uint8)]
    eeprom = SINE.tobytes()
    for name in ('firmware.elf', 'firmware.bin', 'firmware.hex', 'verification.json', 'actual.raw'):
        (output/name).unlink(missing_ok=True)
    (output/'speech.hq').write_bytes(voice_stream)
    (output/'bell.bin').write_bytes(descriptor(model))
    (output/'eeprom.bin').write_bytes(eeprom)
    (output/'eeprom.hex').write_text(helpers.intel_hex(eeprom), encoding='ascii', newline='\n')
    (output/'expected.raw').write_bytes(expected.tobytes())
    (output/'config.inc').write_text(f".set BELL_BLOCKS,{boundary//64}\n.set MUTE_BLOCKS,{model['mute_samples']//64}\n.set DECAY_BLOCKS,{model['decay_blocks']}\n",
                                     encoding='ascii', newline='\n')
    shutil.copyfile(TEMPLATE, output/'firmware.S')
    suffix = '.exe' if os.name == 'nt' else ''
    def executable(name):
        return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name
    compiler = executable('avr-gcc')
    helpers.run([compiler, '-mmcu=attiny13', '-nostdlib', '-x', 'assembler', '-c',
                 'firmware.S', '-o', 'firmware.o'], output)
    symbols = helpers.parse_symbols(helpers.run([executable('avr-nm'), '-n', 'firmware.o'], output).stdout)
    flash_bytes = (symbols['voice_data']+len(voice_stream)+2) & ~1
    report = dict(schema='micromusic-bell-hq4-build-v1', experimental=True,
                  hardwareTested=False, status='oversized' if flash_bytes > 1024 else 'pending',
                  cpuHz=9600000, sampleHz=7500, playbackMode='once',
                  flashBytes=flash_bytes, flashLimitBytes=1024, codeBytes=symbols['code_end'],
                  dataBytes=flash_bytes-symbols['code_end'], bellDescriptorBytes=15,
                  streamBytes=len(voice_stream), eepromBytes=64, eepromUsedBytes=64,
                  phraseSamples=len(reference), bellPrefixSamples=boundary,
                  voiceSamples=len(voice), bellFrequenciesHz=model['frequencies_hz'],
                  referenceSha256=model['reference_sha256'], modelSha256=sha((output/'model.json').read_bytes()),
                  voiceStreamSha256=sha(voice_stream),
                  eepromSha256=sha(eeprom), phrasePcmSha256=sha(phrase.tobytes()),
                  symbols=symbols, compiler=helpers.run([compiler, '--version'], output).stdout.splitlines()[0])
    if flash_bytes <= 1024:
        helpers.run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
                     '-Wl,-Ttext=0', '-x', 'assembler', 'firmware.S', '-o', 'firmware.elf'], output)
        helpers.run([executable('avr-objcopy'), '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
        image = (output/'firmware.bin').read_bytes()
        if len(image) != flash_bytes:
            raise ValueError('Unexpected linked Flash size')
        (output/'firmware.hex').write_text(helpers.intel_hex(image), encoding='ascii', newline='\n')
        (output/'disassembly.txt').write_text(helpers.run([executable('avr-objdump'), '-d', 'firmware.elf'], output).stdout,
                                              encoding='utf-8', newline='\n')
        command = [node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin', output/'expected.raw',
                   output/'verification.json', '--eeprom', output/'eeprom.bin', '--phrase-samples', len(phrase),
                   '--loops', 3, '--playback', 'once', '--minimum-sp', symbols['STACK_FLOOR'],
                   '--wait-pc', symbols['wait_slot'], '--actual-raw', output/'actual.raw']
        checked = helpers.run(command, ROOT, check=False)
        verification = (json.loads((output/'verification.json').read_text(encoding='utf-8'))
                        if (output/'verification.json').exists() else None)
        report.update(status='verified' if verification and verification['pass'] else 'verification-failed',
                      imageSha256=sha(image), verification=verification)
        if verification is None:
            report['verificationError'] = (checked.stdout+checked.stderr).strip()
    scores = dict(hybrid=quality(reference, phrase, boundary))
    if baseline_path:
        baseline = json.loads(Path(baseline_path).read_text(encoding='utf-8'))
        baseline_pcm = decode(np.asarray(baseline['frames'], np.uint8), np.asarray(baseline['durations'], np.uint16), 0)
        if len(baseline_pcm) != len(reference):
            raise ValueError('Baseline duration differs from full reference')
        scores['baseline_hq4'] = quality(reference, baseline_pcm, boundary)
    (output/'quality.json').write_text(json.dumps(scores, indent=2)+'\n', encoding='utf-8', newline='\n')
    sf.write(output/'decoded.wav', (phrase.astype(float)-128)/128, 7500, subtype='PCM_16')
    hp = butter(2, 70, fs=7500, btype='highpass', output='sos')
    original = sosfilt(hp, reference)
    after = sosfilt(hp, (phrase.astype(float)-128)/128)
    after *= np.sqrt(np.mean(original**2))/(np.sqrt(np.mean(after**2))+1e-12)
    gain = min(1., .94/max(float(np.max(abs(original))), float(np.max(abs(after))), 1e-9))
    original *= gain
    after *= gain
    sf.write(output/'original-matched.wav', original, 7500, subtype='PCM_16')
    sf.write(output/'after-matched.wav', after, 7500, subtype='PCM_16')
    sf.write(output/'comparison.wav', np.r_[original, np.zeros(2250), after], 7500, subtype='PCM_16')
    inputs = [TEMPLATE, CODEC/'bell_model.py', Path(__file__), CODEC/'model.py', ROOT/'tools/verify-tiny-speech.mjs']
    report['normalizedSourceSha256'] = {p.relative_to(ROOT).as_posix():
        sha(p.read_text(encoding='utf-8').encode('utf-8')) for p in inputs}
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--voice-model', required=True, type=Path)
    parser.add_argument('--baseline-model', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    report = build(args.reference, args.voice_model, args.baseline_model, args.output, args.avr_bin, args.node)
    print(json.dumps({key: report[key] for key in ('status', 'flashBytes', 'codeBytes', 'streamBytes',
                                                  'phraseSamples', 'bellFrequenciesHz')}, indent=2))
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
