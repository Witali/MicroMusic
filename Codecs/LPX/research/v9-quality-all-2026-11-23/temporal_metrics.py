"""Independent source-frozen native STFT/time/noisy-component diagnostics.

No phase identity is required by the magnitude/time metrics. Complex residual
is reported separately as a waveform diagnostic, never a denoising target.
Private framewise values can fingerprint audio; export only cohort aggregates.
"""
from __future__ import annotations

import math
import numpy as np

FFT_SAMPLES = 512
HOP_SAMPLES = 256


def _frames(pcm):
    padded = np.pad(np.asarray(pcm, dtype=np.float64), (HOP_SAMPLES, FFT_SAMPLES))
    return np.stack([padded[start + HOP_SAMPLES:start + HOP_SAMPLES + FFT_SAMPLES]
                     for start in range(-HOP_SAMPLES, len(pcm), HOP_SAMPLES)])


def _source_mask(frames, source_spectra, rate, window, norm, weight):
    source_power = ((abs(source_spectra) ** 2) * weight).sum(axis=1) / norm
    active = source_power >= .5 ** 2
    centered = frames - frames.mean(axis=1, keepdims=True)
    classification_power = abs(np.fft.rfft(centered * window, axis=1)) ** 2
    use = np.fft.rfftfreq(FFT_SAMPLES, 1 / rate) >= 100
    selected = classification_power[:, use]
    arithmetic = selected.mean(axis=1)
    geometric = np.exp(np.log(np.maximum(selected, 1e-30)).mean(axis=1))
    flatness = np.divide(geometric, arithmetic, out=np.zeros_like(geometric), where=arithmetic > 0)
    lags = np.arange(math.ceil(rate / 800), min(FFT_SAMPLES - 1, math.floor(rate / 50)) + 1)
    peak = np.zeros(len(frames))
    for i, frame in enumerate(centered):
        correlation = np.correlate(frame, frame, mode="full")[FFT_SAMPLES - 1 + lags]
        cumulative = np.concatenate(([0.], np.cumsum(frame ** 2)))
        denominator = np.sqrt(np.maximum(0., cumulative[FFT_SAMPLES - lags] * (cumulative[-1] - cumulative[lags])))
        normalized = np.divide(correlation, denominator, out=np.zeros_like(correlation), where=denominator > 0)
        peak[i] = np.clip(normalized.max(initial=0.), 0., 1.)
    noisy = active & ((flatness >= .2) | (peak < .6))
    return active, noisy, flatness, peak


def _summary(source_power, output_power, waveform, magnitude, change, source_change, noisy):
    source_envelope = np.sqrt(source_power)
    output_envelope = np.sqrt(output_power)
    envelope_error = output_envelope - source_envelope
    source_onset = np.maximum(0., np.diff(source_envelope))
    output_onset = np.maximum(0., np.diff(output_envelope))
    onset_error = output_onset - source_onset
    transitions = noisy[:-1] | noisy[1:]
    result = {"frames": len(source_power), "transitions": len(change),
              "source_power_sum": float(source_power.sum()), "output_power_sum": float(output_power.sum()),
              "waveform_residual_power_sum": float(waveform.sum()),
              "magnitude_residual_power_sum": float(magnitude.sum()),
              "magnitude_change_residual_power_sum": float(change.sum()),
              "source_magnitude_change_power_sum": float(source_change.sum()),
              "envelope_error_squared_sum": float(np.dot(envelope_error, envelope_error)),
              "envelope_absolute_error_sum": float(abs(envelope_error).sum()),
              "onset_error_squared_sum": float(np.dot(onset_error, onset_error)),
              "onset_absolute_error_sum": float(abs(onset_error).sum())}
    result["noisy_unvoiced"] = {"frames": int(noisy.sum()), "transitions": int(transitions.sum()),
              "source_power_sum": float(source_power[noisy].sum()), "output_power_sum": float(output_power[noisy].sum()),
              "waveform_residual_power_sum": float(waveform[noisy].sum()),
              "magnitude_residual_power_sum": float(magnitude[noisy].sum()),
              "magnitude_change_residual_power_sum": float(change[transitions].sum()),
              "source_magnitude_change_power_sum": float(source_change[transitions].sum()),
              "envelope_error_squared_sum": float(np.dot(envelope_error[noisy], envelope_error[noisy])),
              "envelope_absolute_error_sum": float(abs(envelope_error[noisy]).sum()),
              "onset_error_squared_sum": float(np.dot(onset_error[transitions], onset_error[transitions])),
              "onset_absolute_error_sum": float(abs(onset_error[transitions]).sum())}
    return result


def temporal_metrics(reference, decoded, rate, *, framewise=True):
    reference, decoded = np.asarray(reference), np.asarray(decoded)
    if (reference.ndim != 1 or reference.shape != decoded.shape or not len(reference)
            or rate not in (8000, 12000, 16000)):
        raise ValueError("Complete equal-length mono arrays at an actual supported rate required")
    window = np.hanning(FFT_SAMPLES)
    norm = FFT_SAMPLES * np.dot(window, window)
    weight = np.full(FFT_SAMPLES // 2 + 1, 2.)
    weight[0] = weight[-1] = 1.
    source_frames = _frames(reference)
    a = np.fft.rfft(source_frames * window, axis=1)
    b = np.fft.rfft(_frames(decoded) * window, axis=1)
    active, noisy, flatness, periodicity = _source_mask(source_frames, a, rate, window, norm, weight)
    band_count = rate // 2000
    band = np.minimum(np.arange(FFT_SAMPLES // 2 + 1) * rate // (FFT_SAMPLES * 1000), band_count - 1)
    powers = (abs(a) ** 2, abs(b) ** 2, abs(a - b) ** 2, (abs(a) - abs(b)) ** 2)
    change_bins = (np.diff(abs(a), axis=0) - np.diff(abs(b), axis=0)) ** 2
    source_change_bins = np.diff(abs(a), axis=0) ** 2
    band_arrays = []
    for i in range(band_count):
        mask = band == i
        values = [(power[:, mask] * weight[mask]).sum(axis=1) / norm for power in powers]
        change = (change_bins[:, mask] * weight[mask]).sum(axis=1) / norm
        source_change = (source_change_bins[:, mask] * weight[mask]).sum(axis=1) / norm
        band_arrays.append((*values, change, source_change))
    results = []
    for i, (source, output, waveform, magnitude, change, source_change) in enumerate(band_arrays):
        result = {"low_hz": i * 1000, "high_hz": (i + 1) * 1000,
                  **_summary(source, output, waveform, magnitude, change, source_change, noisy)}
        if framewise:
            result["framewise_private"] = {"source_power": source.tolist(), "output_power": output.tolist(),
                  "waveform_residual_power": waveform.tolist(), "magnitude_residual_power": magnitude.tolist(),
                  "magnitude_change_residual_power": change.tolist(),
                  "source_magnitude_change_power": source_change.tolist(),
                  "envelope_error": (np.sqrt(output) - np.sqrt(source)).tolist(),
                  "onset_error": (np.maximum(0., np.diff(np.sqrt(output))) - np.maximum(0., np.diff(np.sqrt(source)))).tolist()}
        results.append(result)
    high = {}
    for cutoff in (3000, 4000, 6000):
        chosen = [values for i, values in enumerate(band_arrays) if i * 1000 >= cutoff]
        high[str(cutoff)] = _summary(*(np.sum([row[i] for row in chosen], axis=0) for i in range(6)), noisy) if chosen else None
    answer = {"schema": 1, "sample_rate": rate, "fft_samples": FFT_SAMPLES, "hop_samples": HOP_SAMPLES,
              "frames": len(source_frames), "source_active_frames": int(active.sum()), "source_noisy_unvoiced_frames": int(noisy.sum()),
              "source_rule": {"active_rms_pcm16": .5, "flatness_min_hz": 100, "flatness_at_least": .2,
                              "periodicity_min_hz": 50, "periodicity_max_hz": 800, "peak_correlation_below": .6},
              "bands": results, "high_bands_from_hz": high}
    if framewise:
        answer["source_framewise_private"] = {"active": active.tolist(), "noisy_unvoiced": noisy.tolist(),
                                               "flatness": flatness.tolist(), "peak_periodicity": periodicity.tolist()}
    return answer
