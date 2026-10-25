#!/usr/bin/env python3
"""WAV -> automatic LSF analysis -> closed-loop Q0 quantization -> L4HY v2.

Only WAV input is needed. Every candidate is scored by the frozen C++ PCM16
decoder and checked against an independent host arithmetic model. Long input
is split into independently decodable, <=65535-byte streams without changing
the MCU format. The JSON playlist describes reset boundaries, not seamless
firmware streaming. No AVR cycle/underrun claim is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import soundfile as sf
from numba import njit
from scipy.signal import stft
from batch_decoder import BatchSession
from lpx4 import encode, decode
from q0_model import coefficient_trace, table, clamp, decode_pcm16, filter_stability
from wav_lpc import analyze, load_wav, pack_frames
from tune_pcm16 import metrics
from output_paths import protect_outputs


@njit(cache=True)
def quantize_trial(target, co, history, previous, previous_clip, pre, bright, step, bits):
    hist = history.copy()
    codes = np.empty(len(target), np.int64)
    loss = 0.
    lo, hi = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if bits else (0, 0)
    for j in range(len(target)):
        acc = 0
        for k in range(10):
            acc += (co[j, k] * hist[k]) >> 12
        preterm = (pre * previous) >> 14
        postterm = (bright * previous_clip) >> 14
        needed = target[j] / 2 + postterm - preterm + acc
        center = int(np.floor(needed / step + .5)) if bits else 0
        best = float('inf')
        selected = selected_pred = selected_deemph = selected_clip = 0
        for q in range(max(lo, min(hi, center - 1)), min(hi, max(lo, center + 1)) + 1):
            pred = clamp(q * step - acc)
            deemph = clamp(pred + preterm)
            clipped = clamp(deemph, -16384, 16384)
            out = clamp(clamp(clipped - postterm, -16384, 16384) * 2, -32768, 32767)
            error = float(out - target[j]) ** 2
            if error < best:
                best, selected = error, q
                selected_pred, selected_deemph, selected_clip = pred, deemph, clipped
        codes[j] = selected
        loss += best
        for k in range(9, 0, -1):
            hist[k] = hist[k - 1]
        hist[0] = selected_pred
        previous, previous_clip = selected_deemph, selected_clip
    return codes, loss, hist, previous, previous_clip


@njit(cache=True)
def quantize(pcm, co, steps, pre, bright, lam, fixed_bits):
    hist = np.zeros(10, np.int64)
    previous = previous_clip = 0
    all_q = np.empty(len(pcm), np.int64)
    scales = np.empty((len(pcm) + 79) // 80, np.int64)
    modes = np.empty(len(scales), np.int64)
    # Source residual is only a scale-search seed; scoring uses synthesized PCM16.
    xq = pcm.astype(np.float64) / 2
    xp = xq.copy()
    for j in range(len(xq) - 1, 0, -1):
        xp[j] -= (pre * int(np.rint(xq[j - 1]))) >> 14
    for bi in range(len(scales)):
        start, end = bi * 80, min(len(pcm), (bi + 1) * 80)
        energy = 0.
        residual_power = 0.
        for j in range(start, end):
            v = xp[j]
            for k in range(10):
                if j > k:
                    v += (co[j, k] * int(np.rint(xp[j - k - 1]))) >> 12
            residual_power += v * v
            energy += float(pcm[j]) ** 2
        rms = max(1., np.sqrt(residual_power / (end - start)))
        energy = max((.025 * 32768) ** 2, energy / (end - start))
        best = float('inf')
        best_scale = best_bits = 0
        for bits in range(2, 7):
            if fixed_bits and bits != fixed_bits:
                continue
            nominal = rms / ((1 << (bits - 1)) - .5)
            for multiplier in (.3, .5, .75, 1., 1.3, 1.85, 2.9, 5., 7.):
                scale = min(255, max(0, int(np.rint(128 + 16 * np.log2(max(1., nominal * multiplier) / 16.384)))))
                q, loss, hh, dd, cc = quantize_trial(pcm[start:end], co[start:end], hist,
                                                    previous, previous_clip, pre, bright,
                                                    steps[scale], bits)
                objective = loss / (end - start) / energy + lam * (bits - 2)
                if objective < best:
                    best, best_scale, best_bits = objective, scale, bits
        q, loss, hist, previous, previous_clip = quantize_trial(pcm[start:end], co[start:end], hist,
                                                              previous, previous_clip, pre, bright,
                                                              steps[best_scale], best_bits)
        all_q[start:end] = q
        scales[bi], modes[bi] = best_scale, best_bits
    return all_q, scales, modes


def quality(ref, pcm, kind='speech'):
    met = metrics(ref, pcm, with_stoi=(kind == 'speech' and len(ref) >= 4000 and np.any(ref)))
    x, y = ref.astype(np.float64) / 32768, pcm.astype(np.float64) / 32768
    nperseg = min(256, len(x))
    _, _, a = stft(x, 8000, nperseg=nperseg)
    _, _, b = stft(y, 8000, nperseg=nperseg)
    floor = 1 / 32768
    spectral = 20 * np.log10(np.maximum(abs(a), floor)) - 20 * np.log10(np.maximum(abs(b), floor))
    return {'ser_db': met['pcm16_snr_db'] if np.any(ref) else None,
            'rmse': met['pcm16_rmse'], 'stoi': met.get('stoi_pcm16'),
            'spectral_rmse_db': float(np.sqrt(np.mean(spectral ** 2))),
            'reference_rms': float(np.sqrt(np.mean(x * x))),
            'decoded_rms': float(np.sqrt(np.mean(y * y))),
            'clip_count': met['clip_count'], 'pcm16_sha256': met['pcm16_sha256']}


def compact_zero_blocks(blob,decoder):
    """Lossless post-pack: a zero excitation block needs no source bit width."""
    frames,blocks,q=decode(blob);changed=0
    for block in blocks:
        if block['bits'] and not any(block['q']):block['bits']=0;changed+=1
    if not changed:return blob,0
    raw=bytearray(blob[:20]);raw[:5]=b'L3AV\x01'
    packed=encode({'raw':bytes(raw),'sampleCount':len(q),'frames':frames,'blocks':blocks},fast=True)[0]
    if len(packed)>len(blob):raise AssertionError('Zero-block repack grew the stream')
    first=decoder.decode_one_s16(blob,len(q));second=decoder.decode_one_s16(packed,len(q))
    if first is None or second is None or not np.array_equal(first,second):
        raise AssertionError('Zero-block repack changed native PCM')
    return packed,changed


def encode_segment(pcm, decoder, max_bytes=65535, lambdas=(0., .0002, .001, .005, .02),
                   pre=13926, bright=0, kind='speech', fixed_bits=0,
                   analysis_profiles=('legacy', 'regularized', 'flat'), stoi_drop=0.,canonical_zero=True):
    import struct
    if not 1 <= len(pcm) <= 64000 or not 32 <= max_bytes <= 65535:
        raise ValueError('Expected 1..64000 samples and a 32..65535-byte segment budget')
    if kind not in ('speech', 'music') or fixed_bits not in (0, 2, 3, 4, 5, 6):
        raise ValueError('Invalid content kind or bit width')
    if not 0 <= pre <= 16384 or not 0 <= bright <= 11469:
        raise ValueError('Q14 header out of range')
    if not lambdas or any(not np.isfinite(v) or v < 0 for v in lambdas):
        raise ValueError('Provide finite nonnegative lambda values')
    if not analysis_profiles or any(p not in ('legacy', 'regularized', 'flat') for p in analysis_profiles):
        raise ValueError('Unknown or empty analysis profile set')
    if not 0 <= stoi_drop <= .01:
        raise ValueError('Invalid STOI tolerance')
    candidates, reports, analyses, seen = [], [], [], set()
    steps = table('scale_table.inc')
    for profile in analysis_profiles:
        local_pre = 0 if profile == 'flat' else pre
        if profile == 'flat':
            vectors = [[round(1023 * i / 11) for i in range(1, 11)]] * ((len(pcm) + 159) // 160)
            analysis = {'window_samples': 0, 'lsf_fallback_frames': 0}
        else:
            vectors, analysis = analyze(pcm, pre=local_pre, bandwidth=.90 if profile == 'regularized' else 1.)
        frames = pack_frames(vectors)
        co = coefficient_trace(frames, len(pcm))
        # Test the *quantized/interpolated* coefficients used by Q0, not only
        # the stable floating-point analysis filter. No changes to firmware.
        analysis.update(profile=profile, preQ14=local_pre,
                        **filter_stability(co))
        analyses.append(analysis)
        if analysis['unstable_subframes']:
            analysis['rejected'] = 'Unstable quantized/interpolated LPC filter'
            continue
        for lam in lambdas:
            q, scales, modes = quantize(pcm.astype(np.int64), co, steps, local_pre, bright, lam, fixed_bits)
            blocks = [{'bits': int(b), 'scale': int(s), 'q': q[i * 80:(i + 1) * 80].tolist()}
                      for i, (s, b) in enumerate(zip(scales, modes))]
            doc = {'raw': struct.pack('<4sBBHIHHHH', b'L3AV', 1, 3, 8000, len(pcm), local_pre, bright, 160, 80),
                   'frames': frames, 'blocks': blocks}
            blob, stats, chunks, packed_q = encode(doc, fast=True)
            if packed_q != q.tolist():
                raise AssertionError('Lossless excitation packing changed quantizer codes')
            digest = hashlib.sha256(blob).hexdigest()
            r = {'profile': profile, 'preQ14': local_pre, 'lambda': float(lam), 'bytes': len(blob), 'sha256': digest,
                 'mode_counts': {str(i): int(np.count_nonzero(modes == i)) for i in range(2, 7)},
                 'within_budget': len(blob) <= max_bytes}
            reports.append(r)
            if len(blob) > max_bytes or digest in seen:
                continue
            seen.add(digest)
            native = decoder.decode_one_s16(blob, len(pcm))
            if native is None:
                raise RuntimeError('Unmodified Q0 decoder rejected generated stream')
            if not np.array_equal(native, decode_pcm16(blob)):
                raise AssertionError('Host Q0 model disagrees with C++ PCM16')
            decode(blob)
            difference = pcm.astype(np.float64) - native
            sse = float(np.dot(difference, difference))
            r['quality'] = quality(pcm, native, kind)
            candidates.append((sse, len(blob), digest, blob, native, r))
    if not candidates:
        raise ValueError('No candidate fits the byte budget; shorten segments or increase --max-bytes')
    legacy = [c for c in candidates if c[5]['profile'] == 'legacy']
    baseline = min(legacy, key=lambda x: x[:3]) if legacy else None
    if baseline and baseline[5]['quality']['stoi'] is not None:
        floor = baseline[5]['quality']['stoi'] - stoi_drop
        candidates = [c for c in candidates if c[5]['quality']['stoi'] >= floor - 1e-12]
    winner = min(candidates, key=lambda x: x[:3])
    blob=winner[3];selected=winner[5]
    if canonical_zero and not fixed_bits:
        blob,count=compact_zero_blocks(blob,decoder)
        selected={**selected,'pre_repack_bytes':winner[1],'zero_blocks_repacked':count,
                  'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}
        packed_blocks=decode(blob)[1]
        selected['mode_counts']={str(i):sum(b['bits']==i for b in packed_blocks) for i in (0,2,3,4,5,6)}
    return blob, winner[4], {'analysis': analyses, 'selected': selected, 'candidates': reports,
                                'legacy_quality_floor': baseline[5]['quality'] if baseline else None}


def segment_ranges(pcm,limit,search=0):
    """Optional frame-aligned quiet cuts; complete coverage, no inserted samples."""
    if search<0 or search%160 or search>limit-160:raise ValueError('Invalid boundary search span')
    start=0;ranges=[]
    while start<len(pcm):
        end=min(start+limit,len(pcm))
        if search and end<len(pcm):
            def score(cut):
                neighborhood=pcm[max(0,cut-40):min(len(pcm),cut+40)].astype(np.float64)
                return float(np.mean(neighborhood**2)),-cut
            end=min(range(end-search,end+1,160),key=score)
        ranges.append((start,end));start=end
    return ranges


def run(source, output, max_bytes=65535, segment_samples=64000, kind='speech', lambdas=None,boundary_search=0):
    source, output = Path(source), Path(output)
    protect_outputs([source], [output/'decoded.wav', output/'manifest.json'])
    if not 160 <= segment_samples <= 64000 or segment_samples % 160:
        raise ValueError('segment_samples must be a multiple of 160 in 160..64000')
    if not 32 <= max_bytes <= 65535:
        raise ValueError('max_bytes must be in 32..65535')
    pcm, input_info = load_wav(source)
    ranges=segment_ranges(pcm,segment_samples,boundary_search)
    start = time.perf_counter()
    encoded, reconstructions, entries = [], [], []
    with BatchSession('batch') as decoder:
        for offset,end in ranges:
            part = pcm[offset:end]
            blob, decoded, report = encode_segment(part, decoder, max_bytes=max_bytes,
                kind=kind, **({'lambdas': lambdas} if lambdas is not None else {}))
            name = 'audio.l4hy' if len(pcm) <= segment_samples else f'audio-{len(entries) + 1:04d}.l4hy'
            encoded.append((name, blob));reconstructions.append(decoded)
            entries.append({'file': name, 'offset_samples': offset, 'samples': len(part),
                            'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(), **report})
    decoded = np.concatenate(reconstructions)
    report = {'source_file': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'input': input_info, 'sample_rate': 8000, 'samples': len(pcm),
              'duration_seconds': len(pcm) / 8000, 'kind': kind, 'max_segment_bytes': max_bytes,
              'codec_bytes': sum(len(b) for _, b in encoded),
              'codec_bitrate_bps': sum(len(b) for _, b in encoded) * 8 * 8000 / len(pcm),
              'quality': quality(pcm, decoded, kind), 'segments': entries,
              'segment_boundary': 'Each file resets the unchanged decoder; concatenated PCM is a host preview.',
              'boundary_search_samples':boundary_search,
              'elapsed_seconds': time.perf_counter() - start,
              'decoder_sha256': hashlib.sha256((Path(__file__).resolve().parents[1] / 'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
              'avr_real_time_verified': False}
    # No partial outputs on encoding/budget/decoder failure.
    protect_outputs([source], [output/name for name, _ in encoded] + [output/'decoded.wav', output/'manifest.json'])
    output.mkdir(parents=True, exist_ok=True)
    for name, blob in encoded:
        (output / name).write_bytes(blob)
    sf.write(str(output / 'decoded.wav'), decoded, 8000, subtype='PCM_16')
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('output_directory', type=Path)
    ap.add_argument('--max-bytes', type=int, default=65535, help='Strict byte cap per L4HY file, including its header')
    ap.add_argument('--segment-samples', type=int, default=64000)
    ap.add_argument('--boundary-search',type=int,default=0,help='Search this many samples before each limit for a quiet 160-aligned boundary')
    ap.add_argument('--kind', choices=('speech', 'music'), default='speech')
    ap.add_argument('--lambdas', default='0,.0002,.001,.005,.02')
    a = ap.parse_args()
    report = run(a.input, a.output_directory, a.max_bytes, a.segment_samples, a.kind,
                 tuple(float(v) for v in a.lambdas.split(',')),a.boundary_search)
    print(json.dumps({k: report[k] for k in ('samples', 'codec_bytes', 'codec_bitrate_bps', 'quality')}, indent=2))


if __name__ == '__main__':
    main()
