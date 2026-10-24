"""Reference-derived time/frequency fitting, including unsupported narrow energy.

This is an offline engineering objective, not a perceptual quality standard.
No source frequencies are deleted or selected by hand. Both signals receive
the same highpass and only one global RMS match; timing is never warped.
"""
import numpy as np
from scipy.ndimage import maximum_filter1d
from scipy.signal import butter, sosfilt, stft


VERSION = 'spectrogram-match-v1'


def audio(value, samples=None):
    value = np.asarray(value, dtype=np.float64)
    if (value.ndim != 1 or len(value) < 3072 or not np.all(np.isfinite(value))
            or (samples is not None and len(value) != samples)):
        raise ValueError('Expected finite mono audio with unchanged duration, at least 3072 samples')
    return value


class SpectrogramObjective:
    """Joint fine-ridge and broad-envelope distance at two STFT resolutions.

    256/1024-sample Hann windows, hops 64/128. A one-bin frequency tolerance
    applies only to missing/excess magnitude energy; ordinary log-distance
    keeps the exact bins. Thirty-two overlapping mel triangles supply a
    broad-envelope comparison. Every time/frequency bin contributes.
    """
    def __init__(self, reference, sr=7500):
        self.reference = audio(reference)
        if sr != 7500:
            raise ValueError('Expected 7500 Hz')
        self.sr = sr
        self.hp = butter(2, 70, fs=sr, btype='highpass', output='sos')
        self.filtered = sosfilt(self.hp, self.reference)
        self.rms = float(np.sqrt(np.mean(self.filtered**2)))
        if self.rms < 1e-7:
            raise ValueError('Reference is silent')
        self.floor = self.rms*.005
        self.targets = []
        for size, hop in ((256, 64), (1024, 128)):
            f, t, mag = self.magnitude(self.filtered, size, hop)
            mel = 2595*np.log10(1+f/700)
            edges = np.linspace(mel[0], mel[-1], 34)
            weights = np.maximum(0, np.minimum(
                (mel[None, :]-edges[:-2, None])/(edges[1:-1]-edges[:-2])[:, None],
                (edges[2:, None]-mel[None, :])/(edges[2:]-edges[1:-1])[:, None]))
            weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-20)
            bands = np.sqrt(weights @ mag**2)
            self.targets.append(dict(size=size, hop=hop, frequencies=f, times=t,
                magnitude=mag, logged=np.log(np.maximum(mag, self.floor)),
                norm2=float(np.sum(mag**2)), expanded=maximum_filter1d(mag, 3, axis=0),
                weights=weights, bands=bands, band_norm=float(np.linalg.norm(bands))))

    def magnitude(self, x, size=1024, hop=128):
        f, t, z = stft(x, fs=self.sr, nperseg=size, noverlap=size-hop)
        return f, t, abs(z)

    def matched(self, candidate):
        x = sosfilt(self.hp, audio(candidate, len(self.reference)))
        return x*self.rms/(np.sqrt(np.mean(x*x))+1e-20)

    def evaluate(self, candidate):
        x = self.matched(candidate)
        log_error = band_error = excess = missing = 0.
        for target in self.targets:
            mag = self.magnitude(x, target['size'], target['hop'])[2]
            log_error += float(np.mean(abs(np.log(np.maximum(mag, self.floor))-target['logged'])))
            bands = np.sqrt(target['weights'] @ mag**2)
            band_error += float(np.linalg.norm(bands-target['bands'])/target['band_norm'])
            excess += float(np.sum(np.maximum(mag-target['expanded'], 0)**2)/target['norm2'])
            expanded = maximum_filter1d(mag, 3, axis=0)
            missing += float(np.sum(np.maximum(target['magnitude']-expanded, 0)**2)/target['norm2'])
        log_error /= 2
        band_error /= 2
        excess /= 2
        missing /= 2
        return dict(spectrogram_loss=.45*log_error+.25*band_error+.2*np.sqrt(excess)+.1*np.sqrt(missing),
                    fine_log_error=log_error, envelope_error=band_error,
                    unsupported_energy=excess, missing_energy=missing)
