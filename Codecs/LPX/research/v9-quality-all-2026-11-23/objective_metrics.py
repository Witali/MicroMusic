"""Independent NumPy reference for the frozen V2 selection components.

Voice/noise equations follow this repository's existing Python research
objectives; unlike their integer-only API, this reference keeps antialiased
12/16->8 kHz analysis in double PCM16 units. It is evaluation, not encoding.
"""
import math
import numpy as np


def analysis8k(pcm, rate):
    pcm = np.asarray(pcm, dtype=np.float64)
    if rate == 8000:
        return pcm.copy()
    from pystoi.utils import resample_oct
    return resample_oct(pcm, 2, 3) if rate == 12000 else resample_oct(pcm, 1, 2)


def _period_error(frame, support, lag):
    whole = int(lag)
    fraction = lag - whole
    first = frame[:support]
    second = frame[whole:whole + support].copy()
    if fraction:
        second += fraction * (frame[whole + 1:whole + support + 1] - second)
    energy = np.dot(first, first) + np.dot(second, second)
    return float(np.dot(first - second, first - second) / energy) if energy else 1.


def _window(pcm):
    centered = pcm - pcm.mean()
    return centered, abs(np.fft.rfft(centered * np.hanning(len(pcm)), n=640)) ** 2


def _shape(power):
    grouped = power[1:].reshape(32, 10).sum(axis=1)
    return np.sqrt(grouped / grouped.sum()) if grouped.sum() else grouped


class QualityObjective:
    def __init__(self, reference, rate):
        from voice_character import PitchSettings, _period
        self.period = _period
        self.settings = PitchSettings()
        self.reference = analysis8k(reference, rate)
        self.rate = rate
        self.frames = []
        for start in range(0, len(self.reference), 160):
            raw = self.reference[start:start + 640]
            period, _, rms, _ = _period(raw, self.settings) if len(raw) == 640 else (math.nan, 0., 0., "partial")
            centered, power = _window(raw)
            self.frames.append((start, raw, centered, power, period, rms))

    def assess(self, decoded):
        candidate = analysis8k(decoded, self.rate)
        waveform = spectral = periodicity = noise_cost = period_error = shape_error = 0.
        voiced = within = collapsed = noise_frames = shape_frames = 0
        frequencies = np.arange(1, 321) * 12.5
        for start, original, x, px, period, source_rms in self.frames:
            raw = candidate[start:start + len(original)]
            y, py = _window(raw)
            difference = raw - original
            waveform += np.dot(difference, difference) / max(np.dot(original, original), len(original))
            spectral += np.sum((_shape(px) - _shape(py)) ** 2)
            if np.isfinite(period):
                voiced += 1
                support = len(x) - math.ceil(2 * period)
                periodicity += sum((_period_error(x, support, period * ratio) - _period_error(y, support, period * ratio)) ** 2
                                   for ratio in (.5, 1., 1.5, 2.)) / 4
                period_error += _period_error(y, len(y) - int(period) - 1, period)
            if len(raw) == 640:
                actual, _, rms, _ = self.period(raw, self.settings)
                within += int(np.isfinite(period) and np.isfinite(actual) and abs(1200 * math.log2(period / actual)) <= 100)
                collapsed += int(source_rms >= .5 and rms < .5)
                if source_rms >= .5:
                    shape_frames += 1
                    groups = np.minimum(23, np.arange(321) * 24 // 321)
                    a = np.bincount(groups, weights=px, minlength=24)
                    b = np.bincount(groups, weights=py, minlength=24)
                    a = a / a.sum() if a.sum() else a
                    b = b / b.sum() if b.sum() else b
                    shape_error += np.sqrt(np.mean((10 * np.log10(np.maximum(1e-8, a)) - 10 * np.log10(np.maximum(1e-8, b))) ** 2))
            if len(raw) < 4:
                continue
            noise_frames += 1
            total_x, total_y = px[1:].sum(), py[1:].sum()
            if total_x <= 0:
                noise_cost += min(1., float(np.dot(y, y) / len(raw)))
            elif total_y <= 0:
                noise_cost += 1.
            else:
                harmonics = int(math.floor(3800 / (8000 / period))) if np.isfinite(period) else 0
                labels = harmonics + np.arange(320)
                if harmonics:
                    base = 8000 / period
                    nearest = np.rint(frequencies / base).astype(np.int64)
                    use = (nearest >= 1) & (nearest <= harmonics) & (abs(frequencies - nearest * base) <= min(18.75, base / 4))
                    labels[use] = nearest[use] - 1
                a = np.bincount(labels, weights=px[1:], minlength=320 + harmonics) / total_x
                b = np.bincount(labels, weights=py[1:], minlength=320 + harmonics) / total_y
                hellinger = float(np.clip(np.sum((np.sqrt(a) - np.sqrt(b)) ** 2) / 2, 0, 1))
                noise_cost += (hellinger + abs(a[harmonics:].sum() - b[harmonics:].sum())) / 2 if harmonics else hellinger
        count = len(self.frames)
        return {"voice": float(.25 * waveform / count + spectral / count + 2 * periodicity / max(1, voiced)),
                "noise": float(np.clip(noise_cost / noise_frames, 0, 1)) if noise_frames else 0.,
                "diagnostic": {"within": within, "collapsed": collapsed, "source_period_frames": voiced,
                               "period": float(period_error / voiced) if voiced else None,
                               "shape": float(shape_error / shape_frames) if shape_frames else None,
                               "analysis_rate": 8000, "analysis_is_unrounded_double": True}}


def relative(value, baseline):
    if baseline == 0:
        return 0. if value == 0 else math.inf
    return value / baseline


def score(candidate, baseline):
    total = weight = 0.
    components = {}
    for path in ("pcm16", "pwm8"):
        a, b = candidate[path], baseline[path]
        parts = {"spectral": (2, a["v2_spectrum"]["balanced_error"], b["v2_spectrum"]["balanced_error"]),
                 "temporal": (2, a["v2_spectrum"]["balanced_temporal_error"], b["v2_spectrum"]["balanced_temporal_error"]),
                 "voice": (1, a["objective_voice"], b["objective_voice"]),
                 "noise": (1, a["objective_noise"], b["objective_noise"]),
                 "waveform": (1, a["error_energy"], b["error_energy"])}
        if b["stoi"] is not None:
            parts["intelligibility"] = (1, max(0., 1 - a["stoi"]) if a["stoi"] is not None else math.inf,
                                        max(0., 1 - b["stoi"]))
        for name in ("period", "shape"):
            floor = b["objective_diagnostic"][name]
            if floor is not None:
                value = a["objective_diagnostic"][name]
                parts[name] = (1, value if value is not None else math.inf, floor)
        components[path] = {}
        for name, (scale, value, floor) in parts.items():
            ratio = relative(value, floor)
            components[path][name] = ratio if math.isfinite(ratio) else None
            total += scale * ratio
            weight += scale
    result = total / weight
    return {"score": result if math.isfinite(result) else None, "status": "finite" if math.isfinite(result) else "zero_baseline_floor_violation",
            "relative_components": components, "weight": weight}
