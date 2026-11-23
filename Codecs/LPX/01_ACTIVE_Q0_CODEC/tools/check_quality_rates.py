#!/usr/bin/env python3
"""Dev-only actual-rate pystoi/FIR oracle and exact old-8-kHz comparison.

Build web-player/tests/helpers/lpx-quality-native.cpp with LPX_QUALITY_NATIVE,
LpxQuality.cpp, LpxStoi.cpp and LpxAdaptiveDsp.cpp, using function/data sections
and linker dead stripping. --native accepts the executable's native path, or
its Linux path on Windows (through WSL Ubuntu). --legacy optionally points to
the same harness linked against the frozen evaluator with LPX_QUALITY_LEGACY.
No input media or external network services are used.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import warnings

import numpy as np
from pystoi import stoi
from pystoi.utils import resample_oct


def cases():
    for rate in (8000, 12000, 16000):
        for name in ("voiced", "quiet", "silence", "transient", "clipped", "short"):
            count = {"voiced": rate * 2 + 17, "quiet": rate + 7,
                     "silence": rate // 10 + 1, "transient": rate + 53,
                     "clipped": rate // 2 + 1, "short": rate * 2 // 5 - 1}[name]
            x, y = np.empty(count, dtype="<i2"), np.empty(count, dtype="<i2")
            state, phase, previous = 0x12345678, 0, 0
            for i in range(count):
                state = (1664525 * state + 1013904223) & 0xFFFFFFFF
                noise = (state >> 24) - 128
                frequency = 120 + i // (rate // 5) % 5 * 20
                phase = (phase + frequency) % rate
                level = 6000 + i // (rate // 7) % 3 * 4000
                a = phase * level * 2 // rate - level
                b = math.trunc((3 * a + previous) / 4) + noise
                if name == "quiet":
                    a, b = (-1 if phase < rate / 2 else 1), (previous if i % 17 else 0)
                elif name == "silence":
                    a, b = 0, (100 if i % 71 == 0 else 0)
                elif name == "transient":
                    a = 20000 if i % 137 == 0 else -20000 if i % 137 == 1 else noise * 2
                    b = math.trunc((a + previous) / 2)
                elif name == "clipped":
                    a = (i % 64 - 32) * 1000
                    b = max(-32768, min(32767, a * 2))
                x[i], y[i], previous = a, b, a
            yield name, rate, x, y


def run(executable, rate, mode, x, y):
    command = (["wsl", "-d", "Ubuntu", "--", executable] if sys.platform == "win32"
               and executable.startswith("/") else [executable])
    done = subprocess.run(command + [str(rate), mode, str(len(x))], input=x.tobytes() + y.tobytes(),
                          capture_output=True, check=True)
    return np.frombuffer(done.stdout, dtype="<f8").copy(), done.stdout


def temporal_cases():
    rate, count, envelope = 16000, 8193, (0, 1, 4, 2, 0, 3, 4, 0)
    carrier = np.empty(count, dtype="<i2")
    state, previous, older = 0x2468ACE0, 0, 0
    for i in range(count):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        raw = (state >> 16) - 32768
        carrier[i] = math.trunc((raw - 2 * previous + older) / 8)
        older, previous = previous, raw
    source = np.array([math.trunc(int(carrier[i]) * envelope[i // 256 % 8] / 4)
                       for i in range(count)], dtype="<i2")
    for name in ("phase-noise", "delayed-envelope", "flat-envelope", "lost-high-band", "tail-noise", "silence", "silence-tail"):
        x, y = source.copy(), source.copy()
        if name == "phase-noise":
            y = -x
        elif name == "delayed-envelope":
            y = np.array([math.trunc(int(carrier[i]) * (0 if i < 256 else envelope[(i - 256) // 256 % 8]) / 4)
                          for i in range(count)], dtype="<i2")
        elif name == "flat-envelope":
            y = np.trunc(carrier.astype(float) / 2).astype("<i2")
        elif name == "lost-high-band":
            y = np.array([math.trunc(sum(int(source[i - k]) for k in range(min(8, i + 1))) / 8)
                          for i in range(count)], dtype="<i2")
        elif name == "tail-noise":
            x, y = np.zeros(count, dtype="<i2"), np.zeros(count, dtype="<i2")
            x[-35:] = carrier[-35:]
        elif name in ("silence", "silence-tail"):
            x, y = np.zeros(count, dtype="<i2"), np.zeros(count, dtype="<i2")
            if name == "silence-tail":
                y[-1] = 1
        yield name, rate, x, y


def pwm(pcm):
    return (np.clip(128 + ((((pcm.astype(np.int64) + 1) >> 1) * 130 + 8192) >> 14),
                    0, 255) - 128) * 256


def full_band(x, y, fixed, rate):
    """Independent NumPy FFT oracle for the prospectively fixed guard."""
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(512) / 511)
    weights = np.full(257, 2.0)
    weights[[0, -1]] = 1
    bands = rate // 2000
    labels = np.minimum(bands - 1, np.arange(257) * rate // (512 * 1000))
    source, output, error = np.zeros(8), np.zeros((2, 8)), np.zeros((2, 8))
    temporal, previous_residual = np.zeros((2, 8)), None
    frames = 0
    for start in range(-256, len(x), 256):
        amplitudes = []
        for pcm in (x, y, fixed):
            frame = np.zeros(512)
            begin, end = max(0, start), min(len(x), start + 512)
            frame[begin - start:end - start] = pcm[begin:end]
            amplitudes.append(np.abs(np.fft.rfft(frame * window)))
        for b in range(bands):
            mask = labels == b
            source[b] += np.sum(amplitudes[0][mask] ** 2 * weights[mask])
            for path in range(2):
                output[path, b] += np.sum(amplitudes[path + 1][mask] ** 2 * weights[mask])
                error[path, b] += np.sum((amplitudes[0][mask] - amplitudes[path + 1][mask]) ** 2 * weights[mask])
        residual = np.array([amplitudes[0] - amplitudes[path + 1] for path in range(2)])
        if previous_residual is not None:
            delta = residual - previous_residual
            for b in range(bands):
                mask = labels == b
                for path in range(2):
                    temporal[path, b] += np.sum(delta[path, mask] ** 2 * weights[mask])
        previous_residual = residual
        frames += 1
    scale = frames * 512 * np.sum(window * window)
    source, output, error, temporal = source / scale, output / scale, error / scale, temporal / scale
    total_source = np.sum(source)
    result = np.zeros(90)
    result[:2] = [1, bands]
    result[2:4] = np.sum(error, axis=1) / (total_source if total_source > 0 else 1)
    for b in range(bands):
        at = 4 + b * 8
        result[at:at + 2] = [source[b], total_source > 0 and source[b] > 1e-4 * total_source]
        for path in range(2):
            result[at + 2 + path * 3] = output[path, b]
            result[at + 3 + path * 3] = error[path, b] / (source[b] if source[b] > 0 else 1)
            result[at + 4 + path * 3] = min(1, math.sqrt(output[path, b] / source[b])) if source[b] > 0 else 0
            result[68 + path * 8 + b] = temporal[path, b] / (source[b] if source[b] > 0 else 1)
    for path in range(2):
        result[84 + path] = np.sum(temporal[path]) / (total_source if total_source > 0 else 1)
        floors = np.maximum(source[:bands], total_source * 1e-4) if total_source > 0 else np.ones(bands)
        result[86 + path] = np.mean(error[path, :bands] / floors)
        result[88 + path] = np.mean(temporal[path, :bands] / floors)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True)
    parser.add_argument("--legacy")
    parser.add_argument("--legacy-fullband", help="optional saved v1 binary for exact first-68-field comparison")
    parser.add_argument("--fixture", type=Path, help="write anonymous synthetic oracle fixture")
    args = parser.parse_args()
    rows = []
    for name, rate, x, y in cases():
        actual, raw = run(args.native, rate, "measure", x, y)
        legacy = None
        if rate == 8000 and args.legacy:
            old, old_raw = run(args.legacy, 0, "measure", x, y)
            default, default_raw = run(args.native, 0, "measure", x, y)
            if raw != old_raw or default_raw != old_raw:
                raise AssertionError(f"8 kHz changed: {name}")
            legacy = [float(v) if math.isfinite(v) else None for v in old]
        fixed = pwm(y)
        expected_stoi = []
        for path, pcm in enumerate((y, fixed)):
            expected_error = int(np.sum((x.astype(np.int64) - pcm.astype(np.int64)) ** 2))
            assert actual[path] == expected_error, (name, rate, "full-rate SSE")
            expected = None
            if np.any(x) and len(x) * 10000 > 4096 * rate:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    expected = float(stoi(x.astype(float) / 32768, pcm.astype(float) / 32768, rate))
                if any("Not enough STFT frames" in str(item.message) for item in caught):
                    expected = None
            if expected is not None:
                assert math.isfinite(actual[2 + path]) and abs(expected - actual[2 + path]) < 1e-10, (name, rate, expected, actual[2 + path])
            else:
                assert math.isnan(actual[2 + path]), (name, rate, "STOI availability")
            expected_stoi.append(expected)
        derived, _ = run(args.native, rate, "analysis", x, y)
        expected_analysis = x.astype(float) if rate == 8000 else resample_oct(x.astype(float), 2 if rate == 12000 else 1, 3 if rate == 12000 else 2)
        assert derived.shape == expected_analysis.shape
        assert np.max(np.abs(derived - expected_analysis)) < 2e-10, (name, rate, "double FIR")
        if name == "quiet" and rate != 8000:
            assert np.any((np.abs(derived) > 0) & (np.abs(derived) < .5)), "retain sub-LSB samples"
            assert actual[0] > 0 and actual[4] > 0, "retain quiet waveform loss"
        actual_band, band_raw = run(args.native, rate, "temporal", x, y)
        expected_band = full_band(x, y, fixed, rate)
        assert np.allclose(actual_band, expected_band, rtol=2e-10, atol=2e-10), (name, rate, "native full band")
        if args.legacy_fullband:
            _, old_band_raw = run(args.legacy_fullband, rate, "fullband", x, y)
            assert old_band_raw == band_raw[:68 * 8], (name, rate, "v1 full-band fields changed")
        indices = sorted(set([*range(min(12, len(derived))), *range(max(0, len(derived) - 12), len(derived)),
                              *np.linspace(0, len(derived) - 1, 24, dtype=int).tolist()]))
        rows.append({"name": name, "rate": rate, "count": len(x), "stoi": expected_stoi[0], "stoiPwm": expected_stoi[1],
                     "legacy8k": legacy, "analysisCount": len(derived),
                     "analysis": [[int(i), float(expected_analysis[i])] for i in indices],
                     "fullBand": expected_band[:68].tolist(), "fullBandTemporal": expected_band[68:].tolist()})
        print(f"{name}/{rate}: true-rate STOI, full-rate SSE, double FIR, native full band" + (", exact old 8 kHz" if legacy else ""))
    temporal_rows = []
    for name, rate, x, y in temporal_cases():
        actual, raw = run(args.native, rate, "temporal", x, y)
        expected = full_band(x, y, pwm(y), rate)
        assert np.allclose(actual, expected, rtol=2e-10, atol=2e-10), (name, "temporal FFT")
        if args.legacy_fullband:
            _, old_raw = run(args.legacy_fullband, rate, "fullband", x, y)
            assert raw[:68 * 8] == old_raw, (name, "v1 fields changed")
        temporal_rows.append({"name": name, "rate": rate, "count": len(x), "fullBand": expected.tolist()})
        print(f"{name}/{rate}: independent temporal, balanced and unchanged v1 full-band fields")
    if args.fixture:
        args.fixture.write_text(json.dumps({"schema": "lpx-quality-synthetic-reference-v1",
                                           "oracle": "pystoi 0.4.1; original evaluator f282950c at 8 kHz",
                                           "cases": rows, "temporalCases": temporal_rows}, indent=2) + "\n", newline="\n")


if __name__ == "__main__":
    main()
