"""Bounded host-only fitting of clip-specific LPX excitation periods.

This is an opt-in LPWB research encoder, not an active LPX firmware format.
Pitch/harmonic analysis proposes fields; every selected block is evaluated
through the unchanged integer LPC/postfilter arithmetic. No global optimum
or target-device timing is implied.
"""
from __future__ import annotations
import hashlib
import importlib.util
import time
from pathlib import Path
import numpy as np
from numba import njit
import period_excitation as codec
from q0_model import clamp, table

REPOSITORY = Path(__file__).resolve().parents[5]


def _period_analysis():
    path = REPOSITORY / "ATtiny13A/Sound/codec/period_wave.py"
    spec = importlib.util.spec_from_file_location("_lpx_period_analysis", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@njit(cache=True)
def _inverse_target(reference, co, params, steps, pre, bright):
    """Open-loop proposal only; the final candidate uses exact closed-loop PCM."""
    samples = len(reference)
    residual = np.zeros(samples, np.float64)
    prediction = np.zeros(samples, np.float64)
    last = 0.
    for j in range(samples):
        desired = max(-16384., min(16384., reference[j] / 2. + bright * last / 16384.))
        value = max(-32767., min(32767., desired - pre * last / 16384.))
        prediction[j] = value
        excitation = value
        for k in range(10):
            if j > k:
                excitation += co[j, k] * prediction[j-k-1] / 4096.
        step = steps[params[j // 160, 0] * 8]
        residual[j] = max(-32., min(31., excitation / step)) if step else 0.
        last = desired
    return residual


def analyze(reference, baseline):
    reference = np.asarray(reference)
    if (reference.ndim != 1 or reference.dtype.kind not in "iu" or
            not len(reference) or np.any(reference < -32768) or np.any(reference > 32767)):
        raise ValueError("Expected nonempty mono PCM16")
    model = codec.from_compact(baseline, np.zeros((1, 32), np.int8))
    if len(reference) != model["n"]:
        raise ValueError("Reference/sample count mismatch")
    co = codec.coefficients(model)
    padded = np.pad(reference.astype(np.int64), (0, len(co)-len(reference)))
    steps = table("scale_table.inc")
    params = np.asarray(model["params"], np.int64)
    target = _inverse_target(padded, co, params, steps, model["pre"], model["bright"])
    period = _period_analysis()
    blocks = len(params)
    speech = padded.astype(float) / 32768.
    pitch_input = np.pad(speech, (0, max(0, 512-len(speech))))
    centres, f0, confidence = period.track_pitch(
        pitch_input, sr=8000, hop=160, window=512, low=60., high=700.)
    centres, f0, confidence = centres[:blocks], f0[:blocks], confidence[:blocks]
    phase = period.continuous_phase(f0, centres, len(padded), sr=8000)
    phase = period.align_phase(target, phase, f0, centres, sr=8000)
    phase -= np.floor(phase[0])
    initial = int(np.rint(phase[0] * 65536)) & 65535
    phase += initial / 65536. - phase[0]
    codes, quantized_phase = period.quantize_phase(phase, len(padded), hop=160)
    shapes = period.fit_periods(target, quantized_phase, f0, centres, sr=8000, width=320)
    model["initial_phase"] = initial
    model["phase_codes"] = codes.astype(int).tolist()
    phases, noise = codec.oscillators(model)
    return dict(
        baseline_sha256=hashlib.sha256(baseline).hexdigest(),
        reference_sha256=hashlib.sha256(reference.astype("<i2").tobytes()).hexdigest(),
        model=model, co=co, reference=padded, target=target, shapes=shapes,
        voiced=f0 > 0, confidence=confidence, phases=phases, noise=noise,
        book_cache={}, steps=steps)


@njit(cache=True)
def _advance(start, size, mode, wave, previous_mode, previous_wave,
             book, params, pulses, extras, phases, noise, co, steps,
             pre, bright, hist, deemph, previous_clip, qring, target, valid_samples):
    h = hist.copy()
    ring = qring.copy()
    pcm = np.empty(size, np.int16)
    error = np.int64(0)
    for local in range(size):
        j = start + local
        if mode:
            value = codec.book_sample(book, wave[0], wave[1], wave[2], phases[j], noise[j])
            if previous_mode and local < 16:
                old = codec.book_sample(book, previous_wave[0], previous_wave[1],
                                        previous_wave[2], phases[j], noise[j])
                value = (old * (16-local) + value * local + 8) >> 4
        else:
            _, lag, gain = params[j // 160]
            value = min(31, max(-32, (gain * ring[(j-lag) & 255] + 8) >> 4))
            pos, amp = pulses[j // 20]
            ep, ea = extras[j // 40]
            if j % 20 == pos:
                value += amp
            if j % 40 == ep:
                value += ea
        q = min(31, max(-32, value))
        ring[j & 255] = q
        acc = np.int64(0)
        for k in range(10):
            acc += (co[j, k] * h[k]) >> 12
        pred = clamp(q * steps[params[j // 160, 0] * 8] - acc)
        for k in range(9, 0, -1):
            h[k] = h[k-1]
        h[0] = pred
        deemph = clamp(pred + ((pre * deemph) >> 14))
        clipped = clamp(deemph, -16384, 16384)
        post = clamp(clipped - ((bright * previous_clip) >> 14), -16384, 16384)
        previous_clip = clipped
        value = clamp(post * 2, -32768, 32767)
        pcm[local] = value
        delta = np.int64(value) - target[j]
        if j < valid_samples:
            error += delta * delta
    return error, h, deemph, previous_clip, ring, pcm


@njit(cache=True)
def _choose(reference, target_q, co, params, pulses, extras, book, phases,
            noise, steps, pre, bright, legacy_bits, rate_price, valid_samples):
    blocks = len(params)
    modes = np.zeros(blocks, np.int64)
    waves = np.zeros((blocks, 3), np.int64)
    output = np.empty(len(reference), np.int16)
    h = np.zeros(10, np.int64)
    ring = np.zeros(256, np.int64)
    dd = cc = 0
    evaluations = 0
    book_bits = 5 + int(np.log2(len(book))) + 5 + 4
    for block in range(blocks):
        start = block * 160
        previous_mode = modes[block-1] if block else 0
        previous_wave = waves[block-1] if block else np.zeros(3, np.int64)
        wave = np.zeros(3, np.int64)
        error, _, _, _, _, _ = _advance(
            start, 160, 0, wave, previous_mode, previous_wave, book,
            params, pulses, extras, phases, noise, co, steps, pre, bright,
            h, dd, cc, ring, reference, valid_samples)
        best_score = float(error) + rate_price * legacy_bits[block]
        best_bits = legacy_bits[block]
        best_mode = 0
        best_wave = wave.copy()
        evaluations += 1
        for index in range(len(book)):
            numerator = 0.
            denominator = 0.
            for j in range(start, min(start+160, valid_samples)):
                at = int(phases[j]) >> 11
                frac = (int(phases[j]) >> 7) & 15
                a, b = book[index, at], book[index, (at+1) & 31]
                basis = (a*16 + (b-a)*frac) / 128.
                numerator += target_q[j] * basis
                denominator += basis * basis
            centre = max(0, min(31, int(np.rint(numerator / max(denominator, 1e-12)))))
            seen = np.zeros(32, np.uint8)
            for offset in (-2, -1, 0, 1, 2):
                gain = max(0, min(31, centre+offset))
                if seen[gain]:
                    continue
                seen[gain] = 1
                remaining = 0.
                noise_power = 0.
                for j in range(start, min(start+160, valid_samples)):
                    v = codec.book_sample(book, index, gain, 0, phases[j], noise[j])
                    remaining += (target_q[j]-v) ** 2
                    noise_power += float(noise[j]) ** 2
                level = max(0, min(15, int(np.rint(np.sqrt(remaining / max(noise_power, 1e-12))*128))))
                levels = np.array([0, level // 2, level], np.int64)
                for ni in range(3):
                    if ni and levels[ni] in levels[:ni]:
                        continue
                    wave = np.array([index, gain, levels[ni]], np.int64)
                    error, _, _, _, _, _ = _advance(
                        start, 160, 1, wave, previous_mode, previous_wave, book,
                        params, pulses, extras, phases, noise, co, steps, pre, bright,
                        h, dd, cc, ring, reference, valid_samples)
                    score = float(error) + rate_price * book_bits
                    evaluations += 1
                    if score < best_score or (score == best_score and book_bits < best_bits):
                        best_score, best_bits = score, book_bits
                        best_mode, best_wave = 1, wave.copy()
        modes[block] = best_mode
        waves[block] = best_wave
        _, h, dd, cc, ring, pcm = _advance(
            start, 160, best_mode, best_wave, previous_mode, previous_wave, book,
            params, pulses, extras, phases, noise, co, steps, pre, bright,
            h, dd, cc, ring, reference, valid_samples)
        output[start:start+160] = pcm
    return modes, waves, output, evaluations


def fit(reference, baseline, words=8, rate_weight=0., seed=20261027, analysis=None):
    started = time.perf_counter()
    if words not in (0, 4, 8, 16) or not np.isfinite(rate_weight) or rate_weight < 0:
        raise ValueError("Expected words 0/4/8/16 and finite nonnegative rate weight")
    reference = np.asarray(reference)
    if (reference.ndim != 1 or reference.dtype.kind not in "iu" or
            not 1 <= len(reference) <= 64000 or
            np.any(reference < -32768) or np.any(reference > 32767)):
        raise ValueError("Expected 1..64000 mono PCM16 samples")
    data = analyze(reference, baseline) if analysis is None else analysis
    if (data["baseline_sha256"] != hashlib.sha256(baseline).hexdigest() or
            data["reference_sha256"] != hashlib.sha256(reference.astype("<i2").tobytes()).hexdigest()):
        raise ValueError("Analysis belongs to different input")
    cache_key = (int(words), int(seed))
    if cache_key not in data["book_cache"]:
        data["book_cache"][cache_key] = (
            np.zeros((1, 32), np.int64) if words == 0 else
            _period_analysis().train_book(data["shapes"], data["voiced"],
                seed=int(seed), starts=2, count=words).astype(np.int64))
    book = data["book_cache"][cache_key].copy()
    # Quantization must not add a DC term that the LPC/de-emphasis can amplify.
    for row in book:
        balance = int(row.sum())
        while balance:
            at = int(np.argmax(row)) if balance > 0 else int(np.argmin(row))
            row[at] += -1 if balance > 0 else 1
            balance += -1 if balance > 0 else 1
    model = codec.validate({**data["model"], "book":book.tolist()})
    params = np.asarray(model["params"], np.int64)
    pulses = np.asarray(model["pulses"], np.int64)
    extras = np.asarray(model["extras"], np.int64)
    legacy_bits = np.full(len(params), 15 + (40 if model["profile"] == 4 else 68), np.int64)
    if model["enhanced"]:
        for bi in range(len(params)):
            legacy_bits[bi] += 4 + 10 * sum(a != 0 for _, a in extras[bi*4:bi*4+4])
    rate_price = float(rate_weight) * float(np.mean(reference.astype(float)**2))
    modes, waves, expected, evaluations = _choose(
        data["reference"], data["target"], data["co"], params, pulses, extras,
        book, data["phases"], data["noise"], data["steps"], model["pre"], model["bright"],
        legacy_bits, rate_price, model["n"])
    # Remove unreferenced dictionary entries without changing the decoded signal.
    used = sorted({int(row[0]) for mode, row in zip(modes, waves)
                   if mode and row[1] and np.any(book[int(row[0])])})
    retained = 1 if not used else 1 << (len(used)-1).bit_length()
    compact_book = np.zeros((retained, 32), np.int64)
    mapping = {old:new for new, old in enumerate(used)}
    for old, new in mapping.items():
        compact_book[new] = book[old]
    for bi in range(len(modes)):
        if modes[bi]:
            waves[bi, 0] = mapping[int(waves[bi, 0])] if waves[bi, 1] and np.any(book[int(waves[bi, 0])]) else 0
    model.update(book=compact_book.tolist(), modes=modes.tolist(), wave_params=waves.tolist())
    blob = codec.pack(model)
    decoded = codec.decode_model(blob)
    if not np.array_equal(decoded, expected[:model["n"]]):
        raise AssertionError("Serialized receiver and encoder state disagree")
    actual = codec.unpack(blob)
    periodic = sum(bool(mode and gain and np.any(compact_book[index]))
                   for mode, (index, gain, _) in zip(modes, waves))
    noise_only = sum(bool(mode and not (gain and np.any(compact_book[index])) and level)
                     for mode, (index, gain, level) in zip(modes, waves))
    silent = sum(bool(mode and not (gain and np.any(compact_book[index])) and not level)
                 for mode, (index, gain, level) in zip(modes, waves))
    bitcount = codec.payload_bits(actual) if hasattr(codec, "payload_bits") else None
    report = dict(
        schema="lpx-period-fit-host-v1", requested_words=words, retained_words=retained,
        rate_weight=float(rate_weight), seed=int(seed), baseline_bytes=len(baseline),
        candidate_bytes=len(blob), dictionary_bytes=retained*16, header_bytes=codec.HEADER.size,
        payload_bytes=len(blob)-codec.HEADER.size-retained*16, payload_bits=bitcount,
        padding_bits=None if bitcount is None else (-bitcount)%8,
        mode_counts=dict(legacy=int(np.count_nonzero(modes == 0)), book=int(np.count_nonzero(modes)),
                         periodic_active=int(periodic), noise_only=int(noise_only), silent=int(silent)),
        objective_evaluations=int(evaluations), serialized_decode_exact=True,
        source_kind="zero-noise-ablation" if words == 0 else "clip-specific-inverse-filtered-periods",
        seconds=time.perf_counter()-started, hardware_timing_measured=False)
    return blob, report, data
