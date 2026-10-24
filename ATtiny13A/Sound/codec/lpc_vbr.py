"""LPV1: adaptive closed-loop LPC residual, selected in raw output space.

The embedded LPC2 descriptor supplies every predictor coefficient. No original
PCM, normalization gain, brightness or output limiter is needed by the decoder.
Legacy emphasized-state guard events are counted separately from output range.
"""
from collections import Counter
import hashlib
import struct

import numpy as np
from numba import njit
from lpc2_excitation import legacy

HEADER = struct.Struct('<4sBBHIIHHI')
WIDTHS = (2, 3, 4, 6, 8)
SCALE_FACTORS = (.30, .45, .60, .75, .90, 1., 1.12, 1.30, 1.55, 1.85, 2.25, 2.90, 3.80)


class BitWriter:
    def __init__(self):
        self.data, self.acc, self.count, self.total = bytearray(), 0, 0, 0

    def write(self, value, width):
        if not 0 <= int(value) < 1 << width:
            raise ValueError('LPV1 field does not fit its declared width')
        self.acc |= int(value) << self.count
        self.count += width
        self.total += width
        while self.count >= 8:
            self.data.append(self.acc & 255)
            self.acc >>= 8
            self.count -= 8

    def finish(self):
        return bytes(self.data)+(bytes([self.acc]) if self.count else b'')


class BitReader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, width):
        if self.position+width > len(self.data)*8:
            raise ValueError('Truncated LPV1 block bitstream')
        value = 0
        for bit in range(width):
            value |= ((self.data[self.position >> 3] >> (self.position & 7)) & 1) << bit
            self.position += 1
        return value


def pack(base, sample_rate, samples, block_samples, blocks):
    if len(blocks) != (samples+block_samples-1)//block_samples:
        raise ValueError('LPV1 block count does not preserve full duration')
    writer = BitWriter()
    for index, (width, scale, codes) in enumerate(blocks):
        if width not in WIDTHS or len(codes) != min(block_samples, samples-index*block_samples):
            raise ValueError('Invalid LPV1 block width or sample count')
        writer.write(WIDTHS.index(width), 3)
        writer.write(scale, 8)
        for value in codes:
            writer.write(value, width)
    return HEADER.pack(b'LPV1', 1, 0, sample_rate, samples, len(base), block_samples, len(WIDTHS), len(blocks))+base+writer.finish()


def unpack(data):
    if len(data) < HEADER.size:
        raise ValueError('Short LPV1 header')
    magic, version, flags, sr, samples, base_bytes, block_samples, profiles, count = HEADER.unpack_from(data)
    if (magic != b'LPV1' or version != 1 or flags or profiles != len(WIDTHS)
            or not 4000 <= sr <= 65535 or not 1 <= samples <= sr*3600
            or not 20 <= block_samples <= 2048 or base_bytes < 36
            or count != (samples+block_samples-1)//block_samples or HEADER.size+base_bytes > len(data)):
        raise ValueError('Invalid LPV1 header')
    base = data[HEADER.size:HEADER.size+base_bytes]
    if (base[:4] != b'LPC2' or struct.unpack_from('<H', base, 6)[0] != sr
            or struct.unpack_from('<I', base, 16)[0] != samples):
        raise ValueError('Embedded LPC2 rate/count disagrees with LPV1')
    payload = data[HEADER.size+base_bytes:]
    reader, blocks = BitReader(payload), []
    code_bits = 0
    for index in range(count):
        profile = reader.read(3)
        if profile >= len(WIDTHS):
            raise ValueError('Unknown LPV1 block width index')
        width, scale = WIDTHS[profile], reader.read(8)
        size = min(block_samples, samples-index*block_samples)
        codes = np.array([reader.read(width) for _ in range(size)], np.uint8)
        blocks.append((width, scale, codes))
        code_bits += size*width
    if len(payload) != (reader.position+7)//8:
        raise ValueError('Noncanonical trailing LPV1 bytes')
    if reader.position % 8 and payload[-1] >> (reader.position % 8):
        raise ValueError('Nonzero LPV1 final padding bits')
    info = dict(format='LPV1', version=1, sample_rate=sr, samples=samples, block_samples=block_samples,
        blocks=count, header_bytes=HEADER.size, base_bytes=base_bytes, block_header_bits=count*11,
        excitation_bits=code_bits, payload_bytes=len(payload), padding_bits=(-reader.position) % 8,
        total_bytes=len(data), base_sha256=hashlib.sha256(base).hexdigest(),
        container_sha256=hashlib.sha256(data).hexdigest(),
        width_block_counts={str(k):v for k,v in sorted(Counter(b[0] for b in blocks).items())},
        decoder_implemented_for_avr=False, hardware_tested=False)
    return base, blocks, info


@njit(cache=True)
def output_block(emphasized, pre, previous):
    output = np.empty(len(emphasized), np.float64)
    for index in range(len(output)):
        value = emphasized[index]+pre*previous
        if not np.isfinite(value) or abs(value) > 1e6:
            raise ValueError('LPV1 unbounded-output finite/range guard failed')
        output[index] = value
        previous = value
    return output, previous


@njit(cache=True)
def emphasized_guard_hits(codes, scale, initial_history, coefficients, width):
    """Independently count pre-clamp events in the unchanged legacy kernel."""
    history = initial_history.copy()
    hits = 0
    for index in range(len(codes)):
        prediction = 0.
        for k in range(10):
            prediction += coefficients[index, k]*history[k]
        raw = (int(codes[index])-(1 << (width-1)))*scale-prediction
        hits += int(raw > 2 or raw < -2)
        value = min(2., max(-2., raw))
        for k in range(9, 0, -1):
            history[k] = history[k-1]
        history[0] = value
    return hits


@njit(cache=True)
def encode_output_block(original, coefficients, initial_history, pre, initial_previous, scale, width):
    """Causal closed-loop target in the FINAL output domain, every sample.

    Predictor/sign/code bounds match the original residual quantizer. The
    desired emphasized value uses the actual decoded previous output rather
    than the original previous input; quantization error is not recursively
    carried through de-emphasis as an uncorrected target offset.
    """
    history, previous = initial_history.copy(), initial_previous
    codes = np.empty(len(original), np.uint8)
    half = 1 << (width-1)
    for index in range(len(original)):
        prediction = 0.
        for k in range(10):
            prediction += coefficients[index, k]*history[k]
        desired = original[index]-pre*previous
        quantized = int(np.floor((desired+prediction)/scale+.5))
        quantized = min(half-1, max(-half, quantized))
        emphasized = min(2., max(-2., quantized*scale-prediction))
        previous = emphasized+pre*previous
        for k in range(9, 0, -1):
            history[k] = history[k-1]
        history[0] = emphasized
        codes[index] = quantized+half
    return codes


def descriptor(base, provider, samples, sr):
    pre, rate, coefficients = provider(base)
    coefficients = np.asarray(coefficients, dtype=np.float64)
    if rate != sr or coefficients.shape != (samples, 10) or not np.isfinite(pre) or not 0 <= pre < 1 or not np.all(np.isfinite(coefficients)):
        raise ValueError('Base-only coefficient provider disagrees with LPV1 descriptor')
    return float(pre), coefficients


def decode(data, coefficient_provider):
    base, blocks, info = unpack(data)
    pre, coefficients = descriptor(base, coefficient_provider, info['samples'], info['sample_rate'])
    history, previous, start, hits = np.zeros(10, np.float64), 0., 0, 0
    output = np.empty(info['samples'], np.float64)
    for width, code, codes in blocks:
        stop = start+len(codes)
        co, scale = coefficients[start:stop], legacy.byte_to_scale(code)
        hits += int(emphasized_guard_hits(codes, scale, history, co, width))
        emphasized = legacy.decode_qs(codes, scale, history, co, width)
        output[start:stop], previous = output_block(emphasized, pre, previous)
        start = stop
    info.update(emphasized_guard_hits=hits, output_clipping=False, gain_normalization=False,
        output_samples_outside_unit_interval=int(np.count_nonzero(abs(output) > 1)),
        output_peak=float(abs(output).max()))
    return output, info


def encode(reference, sample_rate, base, coefficient_provider, *, target_snr_db=24., block_samples=75,
           floor_relative_db=-60.):
    reference = np.asarray(reference, dtype=np.float64)
    if (reference.ndim != 1 or not len(reference) or not np.all(np.isfinite(reference))
            or not np.isfinite(target_snr_db) or not np.isfinite(floor_relative_db)
            or not 20 <= block_samples <= 2048 or floor_relative_db > 0):
        raise ValueError('Invalid LPV1 reference or raw-error target')
    pre, coefficients = descriptor(base, coefficient_provider, len(reference), sample_rate)
    target = reference.copy()
    target[1:] -= pre*reference[:-1]
    residual = target.copy()
    for k in range(10):
        residual[k+1:] += coefficients[k+1:, k]*target[:-k-1]
    global_power = float(np.mean(reference**2))
    floor_power = max(1e-20, global_power*10**(floor_relative_db/10))
    history, previous = np.zeros(10, np.float64), 0.
    blocks, records, outputs = [], [], []
    candidate_count = 0
    for start in range(0, len(reference), block_samples):
        stop = min(start+block_samples, len(reference))
        original, co = reference[start:stop], coefficients[start:stop]
        reference_power = float(np.mean(original**2))
        threshold = max(reference_power, floor_power)*10**(-target_snr_db/10)
        residual_rms = max(.00005, float(np.sqrt(np.mean(residual[start:stop]**2))))
        accepted, fallback = None, None
        for width in WIDTHS:
            nominal = residual_rms/max(1., (1 << (width-1))-.5)
            best = None
            for code in sorted({legacy.scale_to_byte(nominal*factor) for factor in SCALE_FACTORS}):
                scale = legacy.byte_to_scale(code)
                codes = encode_output_block(original, co, history, pre, previous, scale, width)
                trial_history = history.copy()
                trial_emphasized = legacy.decode_qs(codes, scale, trial_history, co, width)
                audio, next_previous = output_block(trial_emphasized, pre, previous)
                loss = float(np.mean((audio-original)**2))
                hits = int(emphasized_guard_hits(codes, scale, history, co, width))
                candidate_count += 1
                candidate = (loss, width, code, codes, trial_history, next_previous, audio, hits)
                if best is None or (bool(hits), loss, code) < (bool(best[7]), best[0], best[2]):
                    best = candidate
            if fallback is None or (bool(best[7]), best[0], width) < (bool(fallback[7]), fallback[0], fallback[1]):
                fallback = best
            if best[0] <= threshold and not best[7]:
                accepted = best
                break
        loss, width, code, codes, history, previous, audio, hits = accepted or fallback
        blocks.append((width, code, codes))
        outputs.append(audio)
        records.append(dict(start_sample=start, samples=stop-start, width=width, scale_code=code,
            reference_rms=float(np.sqrt(reference_power)), raw_output_mse=loss,
            maximum_permitted_mse=threshold, target_met=bool(loss <= threshold and not hits),
            raw_block_snr_db=float(10*np.log10(max(reference_power, 1e-30)/max(loss, 1e-30))),
            floor_applied=reference_power < floor_power, emphasized_guard_hits=hits))
    data = pack(base, sample_rate, len(reference), block_samples, blocks)
    decoded, info = decode(data, coefficient_provider)
    training_output = np.concatenate(outputs)
    if not np.array_equal(decoded, training_output):
        raise AssertionError('Parameter-only LPV1 decode differs from carried-state encoding trials')
    error = float(np.mean((decoded-reference)**2))
    info.update(target_snr_db=float(target_snr_db), target_statistic='Per-block raw output MSE / original block power, with explicit global floor',
        global_floor_relative_db=float(floor_relative_db), global_floor_rms=float(np.sqrt(floor_power)),
        target_failed_blocks=sum(not r['target_met'] for r in records),
        floor_applied_blocks=sum(r['floor_applied'] for r in records), candidate_trials=candidate_count,
        raw_output_snr_db=float(10*np.log10(max(global_power, 1e-30)/max(error, 1e-30))),
        raw_output_mse=error, parameter_only_decode_exact=True,
        quantizer_policy='Every sample targets final raw output using actual carried de-emphasis state; original predictor and signed-code bounds',
        policy='Greedy minimum-width feasible block; lowest-error safe fallback reports failure. No guarantee of globally optimal rate or monotonic rate across independently encoded targets.',
        block_decisions=records)
    return data, decoded, info
