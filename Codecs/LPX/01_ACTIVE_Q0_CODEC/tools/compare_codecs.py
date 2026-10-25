#!/usr/bin/env python3
"""Compare native LPX3 v7 / LPX4 Q0 with Opus and AAC-LC at actual byte caps.

Input is the reproducible benchmark report plus its external/ignored media
directory. Encoded containers, including all headers, must fit the LPX4 file
size. Actual shortfall is reported; approximate matches are not called exact.
FFmpeg applies container pre-skip/edit lists; only trailing padding is removed.
No fitted delay, gain or normalization is used for quality metrics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import numpy as np
from batch_decoder import BatchSession
from lpx4 import encode
from q0_model import coefficient_trace, table, synthesize
from rice_v7 import encode_v7
from wav_lpc import analyze, pack_frames
from wav_to_lpx4 import quantize, quality
from tune_pcm16 import read_wav16

ROOT = Path(__file__).resolve().parents[1]
LAMBDAS = (0., .0002, .001, .005, .02, .1, .5, 10.)


def external(reference, folder, codec, cap, ref, kind):
    path = folder / ('comparison.opus' if codec == 'libopus' else 'comparison.m4a')
    lo, hi, best, trials = 500, 96000, None, []
    for _ in range(17):
        if lo > hi:
            break
        bitrate = (lo + hi) // 2
        options = ['-application', 'audio'] if codec == 'libopus' else ['-profile:a', 'aac_low']
        process = subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(reference),
            '-c:a', codec, '-b:a', str(bitrate), '-ac', '1', '-ar', '8000', *options, str(path)],
            capture_output=True)
        if process.returncode:
            trials.append({'bitrate': bitrate, 'error': process.stderr.decode(errors='replace')[-500:]})
            lo = bitrate + 1
            continue
        blob = path.read_bytes()
        trials.append({'bitrate': bitrate, 'bytes': len(blob)})
        if len(blob) <= cap:
            if best is None or len(blob) > len(best[1]):
                best = bitrate, blob
            lo = bitrate + 1
        else:
            hi = bitrate - 1
    if best is None:
        return {'status': 'No valid container fits the byte cap', 'trials': trials}
    bitrate, blob = best
    path.write_bytes(blob)
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
        '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1'], check=True, capture_output=True)
    pcm = np.frombuffer(decoded.stdout, dtype='<i2')
    if len(pcm) < len(ref):
        raise ValueError('External decoder returned fewer samples than reference')
    return {'codec': codec, 'requested_bitrate': bitrate, 'bytes': len(blob), 'byte_cap': cap,
            'shortfall_bytes': cap - len(blob), 'shortfall_fraction': (cap - len(blob)) / cap,
            'sha256': hashlib.sha256(blob).hexdigest(), 'terminal_padding_samples_trimmed': len(pcm) - len(ref),
            'decoder_warnings': decoded.stderr.decode(errors='replace'),
            'quality': quality(ref, pcm[:len(ref)], kind), 'trials': trials}


def lpx3(folder, case, ref, cap, driver, decoder):
    best = None
    records = []
    stable = {a['profile'] for a in case['generation']['analysis'] if not a.get('rejected')}
    for profile in ('legacy', 'regularized', 'flat'):
        if profile not in stable:
            continue
        pre = 0 if profile == 'flat' else 13926
        vectors = ([[round(1023 * i / 11) for i in range(1, 11)]] * ((len(ref) + 159) // 160)
                   if profile == 'flat' else analyze(ref, pre=pre, bandwidth=.9 if profile == 'regularized' else 1.)[0])
        frames = pack_frames(vectors)
        co, steps = coefficient_trace(frames, len(ref)), table('scale_table.inc')
        for lam in LAMBDAS:
            q, scales, modes = quantize(ref.astype(np.int64), co, steps, pre, 0, lam, 0)
            doc = {'raw': struct.pack('<4sBBHIHHHH', b'L3AV', 1, 3, 8000, len(ref), pre, 0, 160, 80),
                   'sampleCount': len(ref), 'frames': frames, 'blocks': [{'bits': int(b), 'scale': int(s), 'q': q[i * 80:(i + 1) * 80].tolist()}
                   for i, (s, b) in enumerate(zip(scales, modes))]}
            blob = encode_v7(doc)[0]
            record = {'profile': profile, 'lambda': lam, 'bytes': len(blob)}
            records.append(record)
            if len(blob) > cap:
                continue
            stream, output = folder / 'candidate.l3av', folder / 'candidate.pcm16le'
            stream.write_bytes(blob)
            subprocess.run([str(driver), str(stream), str(output)], check=True, capture_output=True)
            pcm = np.frombuffer(output.read_bytes(), dtype='<i2').copy()
            model = synthesize(q, scales, co, steps, pre, 0)
            if not np.array_equal(pcm, model):
                raise AssertionError('Original LPX3 native/model PCM16 mismatch')
            diff = ref.astype(np.float64) - pcm
            error = float(np.dot(diff, diff))
            record['quality'] = quality(ref, pcm, case['kind'])
            if best is None or (error, len(blob)) < best[:2]:
                best = error, len(blob), blob, pcm, record, doc
    if best is None:
        return {'status': 'No LPX3 candidate fits byte cap', 'candidates': records}
    blob, pcm, record, doc = best[2:]
    # Native Q0 LPX4 must produce identical pre-PWM samples for the same data.
    parity = encode(doc, fast=True)[0]
    if not np.array_equal(pcm, decoder.decode_one_s16(parity, len(ref))):
        raise AssertionError('LPX3/LPX4 PCM16 parity failed for identical source fields')
    (folder / 'comparison.l3av').write_bytes(blob)
    return {'codec': 'LPX3 Rice v7 Q0', 'bytes': len(blob), 'byte_cap': cap,
            'shortfall_bytes': cap - len(blob), 'shortfall_fraction': (cap - len(blob)) / cap,
            'sha256': hashlib.sha256(blob).hexdigest(), 'quality': record['quality'],
            'same_data_lpx4_pcm16_exact': True, 'selected': record, 'candidates': records}


def run(benchmark, media, report):
    media, report = Path(media).resolve(), Path(report)
    inputs = json.loads(Path(benchmark).read_text(encoding='utf-8'))
    driver = media / ('decode-lpx3-s16.exe' if os.name == 'nt' else 'decode-lpx3-s16')
    subprocess.run(['g++', '-O3', '-std=c++11', str(ROOT.parent / 'validation/decode_lpx3_s16.cpp'),
                    '-o', str(driver)], check=True, capture_output=True)
    result = {'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
              'protocol': 'Actual full container bytes <= LPX4 size; reported shortfall; no fitted gain/delay; trailing decoder padding removed.',
              'lpx3_source_sha256': hashlib.sha256((ROOT / 'src/Lpx3AvrCore.cpp').read_bytes()).hexdigest(),
              'cases': []}
    with BatchSession('batch') as decoder:
        for case in inputs['cases']:
            folder = media / case['id']
            reference = folder / 'reference.wav'
            ref = read_wav16(reference)
            if hashlib.sha256(ref.astype('<i2').tobytes()).hexdigest() != case['reference_pcm_sha256']:
                raise ValueError('Reference PCM checksum mismatch')
            blob = (folder / 'optimized.l4hy').read_bytes()
            cap = len(blob)
            pcm = decoder.decode_one_s16(blob, len(ref))
            item = {'id': case['id'], 'kind': case['kind'], 'samples': len(ref), 'byte_cap': cap,
                    'LPX4': {'bytes': cap, 'quality': quality(ref, pcm, case['kind'])}}
            item['LPX3'] = lpx3(folder, case, ref, cap, driver, decoder)
            for name, codec in (('Opus', 'libopus'), ('AAC_LC', 'aac')):
                item[name] = external(reference, folder, codec, cap, ref, case['kind'])
            result['cases'].append(item)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(case['id'], {c: (item[c].get('bytes'), item[c].get('quality', {}).get('ser_db'))
                              for c in ('LPX4', 'LPX3', 'Opus', 'AAC_LC')}, flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('benchmark', type=Path);ap.add_argument('media_directory', type=Path);ap.add_argument('report', type=Path)
    a = ap.parse_args()
    run(a.benchmark, a.media_directory, a.report)
