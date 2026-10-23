"""Exact three-tone EEPROM oscillator prelude followed by an unchanged HQ4 voice.

The prelude boundary comes from the supplied voice model. Tonal frequencies,
phases, amplitude and common staircase decay are estimated from source PCM.
The remaining recording, including any ringing overlapping speech, stays HQ4.
"""
import itertools
import math

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import find_peaks, stft

SAMPLE_RATE = 7500
SINE = np.rint(31*np.sin(np.arange(64)*2*np.pi/64)).astype(np.int8)


def validate(model):
    for key in ('prefix_samples', 'mute_samples', 'decay_blocks'):
        if not math.isfinite(model[key]) or int(model[key]) != model[key]:
            raise ValueError('Bell timing parameters must be finite integers')
    n, mute, decay = (int(model[k]) for k in ('prefix_samples', 'mute_samples', 'decay_blocks'))
    partials = model['partials']
    if (not 64 <= n <= 255*64 or n % 64 or not 0 <= mute < n or mute % 64
            or not 1 <= decay <= 255 or len(partials) != 3):
        raise ValueError('Invalid bell prefix length, onset or decay')
    if any(not math.isfinite(p[key]) or int(p[key]) != p[key]
           for p in partials for key in ('phase', 'step', 'amplitude')):
        raise ValueError('Bell partial parameters must be finite integers')
    if any(not 0 <= int(p['phase']) <= 65535 or not 1 <= int(p['step']) <= 32767
           or not 1 <= int(p['amplitude']) <= 7 for p in partials):
        raise ValueError('Invalid bell phase, frequency or signed-Q4 amplitude')
    if sum(int(p['amplitude']) for p in partials) > 15:
        raise ValueError('Bell amplitude sum must prevent signed-byte wraparound')


def descriptor(model):
    validate(model)
    result = bytearray()
    for field in ('phase', 'step'):
        for partial in model['partials']:
            result.extend(int(partial[field]).to_bytes(2, 'little'))
    result.extend(int(partial['amplitude']) for partial in model['partials'])
    return bytes(result)


def decode_bell(model):
    validate(model)
    n, mute, decay = (int(model[k]) for k in ('prefix_samples', 'mute_samples', 'decay_blocks'))
    count = n-mute
    samples = np.arange(1, count+1, dtype=np.int64)
    output = np.zeros(n, np.int16)
    signal = np.zeros(count, np.int16)
    for partial in model['partials']:
        phase = (int(partial['phase'])+samples*int(partial['step'])) & 65535
        wave = SINE[phase >> 10].astype(np.int16)
        signal += (wave*int(partial['amplitude'])) >> 4
    # Sum is provably within int8 because the total amplitude is at most 15.
    shift = np.arange(count)//(64*decay)
    output[mute:] = (signal+1) >> shift
    return (output+128).astype(np.uint8)


def fit(reference, voice_pcm, boundary):
    x = np.asarray(reference, dtype=float)
    if len(x) != boundary+len(voice_pcm) or boundary % 64:
        raise ValueError('Voice boundary must preserve the whole input')
    prelude = x[:boundary]
    rms = np.sqrt(np.mean(prelude.reshape(-1, 64)**2, axis=1))
    noise = float(np.median(rms[:max(4, len(rms)//10)]))
    threshold = max(noise*6, float(np.max(rms))*.075)
    above = np.flatnonzero(rms > threshold)
    if not len(above):
        raise ValueError('No significant tonal event before the voice boundary')
    mute = int(above[0])*64
    voice = (np.asarray(voice_pcm, dtype=float)-128)/128
    source_voice = x[boundary:]
    # Preserve the original bell/voice level relationship, even when the small
    # integer decoder emits a quieter voice. Never normalize the bell alone.
    scale = float(np.sqrt(np.mean(voice**2))/(np.sqrt(np.mean(source_voice**2))+1e-12))
    target = prelude*scale
    active = prelude[mute:]
    t = np.arange(len(active))/SAMPLE_RATE
    fft_n = 1 << (max(32768, len(active))-1).bit_length()
    power = abs(np.fft.rfft(active*np.hanning(len(active)), fft_n))
    peaks, _ = find_peaks(power, distance=max(1, int(30*fft_n/SAMPLE_RATE)))
    peaks = peaks[(peaks*SAMPLE_RATE/fft_n > 100) & (peaks*SAMPLE_RATE/fft_n < 3400)]
    ranked = sorted(peaks, key=lambda i: power[i], reverse=True)[:10]
    if len(ranked) < 3:
        raise ValueError('Not enough independent tonal peaks')
    candidates = []
    for peak in ranked:
        center = peak*SAMPLE_RATE/fft_n

        def residual(freq):
            wave = np.column_stack((np.sin(2*np.pi*freq*t), np.cos(2*np.pi*freq*t)))
            coefficient = np.linalg.lstsq(wave, active, rcond=None)[0]
            return float(np.sum((active-wave@coefficient)**2))

        refined = minimize_scalar(residual, bounds=(center-2, center+2), method='bounded')
        candidates.append(int(round(refined.x*65536/SAMPLE_RATE)))
    targets = [(size, abs(stft(target, nperseg=size, noverlap=size//2)[2])) for size in (128, 256, 512)]
    def error_for(decoded):
        result = 0.
        for size, spectrum in targets:
            actual = abs(stft(decoded, nperseg=size, noverlap=size//2)[2])
            result += float(np.linalg.norm(actual-spectrum)/(np.linalg.norm(spectrum)+1e-12))
        return result/3 + .05*float(np.mean((decoded-target)**2))/(np.mean(target**2)+1e-12)

    best = None
    for steps in itertools.combinations(candidates[:7], 3):
        for decay in (20, 24, 28, 32, 36, 40, 48, 64):
            envelope = 2.**-(np.arange(len(active))//(decay*64))
            columns = []
            for step in steps:
                phase = 2*np.pi*step/65536*np.arange(len(active))
                columns.extend((np.sin(phase)*envelope, np.cos(phase)*envelope))
            matrix = np.column_stack(columns)
            # The recording has measurable pitch drift. Estimate attack phase
            # locally and rank stationary approximations by short-window spectra,
            # otherwise full-waveform cancellation falsely favors silence.
            attack = min(1024, len(active))
            coefficients = np.linalg.lstsq(matrix[:attack], target[mute:mute+attack], rcond=None)[0]
            partials = []
            for i, step in enumerate(steps):
                a, b = coefficients[i*2:i*2+2]
                amplitude = min(7, max(1, int(round(math.hypot(a, b)*128*16/31))))
                phase = int(round(math.atan2(b, a)*65536/(2*np.pi)-step+512)) & 65535
                partials.append(dict(step=int(step), phase=phase, amplitude=amplitude))
            while sum(p['amplitude'] for p in partials) > 15:
                largest = max(partials, key=lambda p: p['amplitude'])
                largest['amplitude'] -= 1
            model = dict(prefix_samples=boundary, mute_samples=mute, decay_blocks=decay, partials=partials)
            decoded = (decode_bell(model).astype(float)-128)/128
            error = error_for(decoded)
            if best is None or error < best[0]:
                best = error, model
    error, model = best
    # Refine only explicitly serialized integer parameters against actual LUT
    # quantization; no ideal floating oscillator is used for final selection.
    for _ in range(3):
        changed = False
        for index in range(3):
            for field, offsets in (('step', (-1, 1)), ('phase', (-512, -256, 256, 512)),
                                   ('amplitude', (-1, 1))):
                for offset in offsets:
                    trial = dict(model, partials=[p.copy() for p in model['partials']])
                    trial['partials'][index][field] += offset
                    if field == 'phase':
                        trial['partials'][index][field] &= 65535
                    try:
                        decoded = (decode_bell(trial).astype(float)-128)/128
                    except ValueError:
                        continue
                    candidate = error_for(decoded)
                    if candidate < error:
                        error, model, changed = candidate, trial, True
        if not changed:
            break
    model.update(schema='micromusic-bell-prelude-v1', sample_rate=SAMPLE_RATE,
                 voice_level_scale=scale, source_onset_threshold=threshold,
                 source_noise_rms=noise, spectral_fit_objective=error,
                 level_matched_mse=float(np.mean(((decode_bell(model).astype(float)-128)/128-target)**2)),
                 frequencies_hz=[p['step']*SAMPLE_RATE/65536 for p in model['partials']])
    return model
