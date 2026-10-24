"""Encoder-only persistent spectral detail; never a speech/noise classifier.

The reference supplies soft time/frequency weights. No frequency is removed
from the source, and no extra oscillator or MCU data format is implied. A
narrow peak may be a voice harmonic, ringing, music, or another sound. Broad
formant envelopes require a separate interpretation from narrow ridges.
"""
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, find_peaks, sosfilt, stft


VERSION = 'persistent-spectrum-v1'


def _audio(value, samples=None):
    x = np.asarray(value, dtype=np.float64)
    if x.ndim != 1 or len(x) < 512 or not np.all(np.isfinite(x)):
        raise ValueError('Expected at least 512 finite mono samples')
    if samples is not None and len(x) != samples:
        raise ValueError('Candidate must preserve the exact reference duration')
    return x


class PersistentSpectrumObjective:
    """Cached soft emphasis on contiguous spectral ridges in the reference.

    512-sample Hann analysis, hop 64, identical 70 Hz highpass and global RMS
    matching for both signals. Local maxima must exceed their 9-bin median by
    6 dB, exceed 6% of the frame maximum, and continue in consecutive frames
    for at least 80 ms. Neighbouring frames may move by two FFT bins. This is
    a resolution-limited acoustic heuristic, not independent F0 ground truth.

    evaluate(candidate) needs no pitch analysis and is suitable for an encoder
    search. Its persistent_spectral_error is a full-band log magnitude error
    with weights 1..3; thus short consonants and nonpersistent energy still
    contribute. The unweighted metric is retained for comparison. Use STOI/
    eSTOI constraints independently; no spectral score guarantees listening
    quality. Candidate PCM must be signed floating-point, not uint8 PWM.

    band_loss combines two complementary diagnostics in equal proportions:
    band_envelope_loss follows time-varying activity after per-band RMS
    normalization; band_shape_loss follows the relative spectral envelope
    after per-frame L2 normalization. Both use all one-third-octave bands
    above 80 Hz. Reference-derived activity weights stay positive, so no
    transient or quiet band is discarded. This is an engineering objective,
    not a standardized perceptual metric.
    """
    def __init__(self, reference, sr=7500, *, min_run_ms=80., strength=2.):
        self.reference = _audio(reference)
        if sr != 7500 or not 0 < min_run_ms <= 10000 or not 0 <= strength <= 4:
            raise ValueError('Expected 7500 Hz and valid persistence/weight settings')
        self.sr, self.size, self.hop = sr, 512, 64
        self.min_run_ms, self.strength = float(min_run_ms), float(strength)
        self.hp = butter(2, 70, fs=sr, btype='highpass', output='sos')
        filtered = sosfilt(self.hp, self.reference)
        self.rms = float(np.sqrt(np.mean(filtered * filtered)))
        if self.rms < 1e-7:
            raise ValueError('Reference is silent')
        self.frequencies, self.times, self.target = self._magnitude(filtered)
        # A reference-relative floor makes the score independent of recording
        # gain, while keeping a finite penalty for missing narrow components.
        self.floor = self.rms * .005
        self.logged = np.log(np.maximum(self.target, self.floor))
        self.ridges, ridge_mask = self._ridges()
        self.weights = 1. + self.strength * ridge_mask
        self.weight_sum = float(self.weights.sum())
        self.bands = self._bands()
        self.target_envelopes = self._envelopes(self.target)
        self.band_rms = np.sqrt(np.mean(self.target_envelopes**2, axis=1))
        self.band_weights = np.where(self.band_rms >= self.band_rms.max()*.02,1.,.25)
        frame_level = np.sqrt(np.sum(self.target_envelopes**2,axis=0))
        self.frame_weights = .25+.75*np.minimum(1.,frame_level/(np.sqrt(np.mean(frame_level**2))+1e-20))
        self.band_frame_weights = self.band_weights[:,None]*self.frame_weights[None,:]
        self.band_frame_sum = float(self.band_frame_weights.sum())

    def _magnitude(self, x):
        f, t, z = stft(x, fs=self.sr, nperseg=self.size,
                       noverlap=self.size-self.hop, boundary='zeros', padded=True)
        return f, t, abs(z)

    def _ridges(self):
        mag = self.target
        background = median_filter(mag, size=(9, 1), mode='nearest')
        minimum_frames = max(2, int(np.ceil(self.min_run_ms*self.sr/1000/self.hop)))
        active, complete = [], []
        for frame in range(mag.shape[1]):
            column = mag[:, frame]
            peaks, _ = find_peaks(column)
            peaks = [int(k) for k in peaks
                     if self.frequencies[k] >= 80
                     and column[k] > max(self.floor*2, column.max()*.06)
                     and column[k] > background[k, frame]*2]
            # Greedy closest-frequency continuation, with no missing frames.
            pairs = sorted((abs(track[-1][1]-k), i, k)
                           for i, track in enumerate(active) for k in peaks
                           if abs(track[-1][1]-k) <= 2)
            used_tracks, used_peaks = set(), set()
            continued = []
            for distance, index, peak in pairs:
                if index in used_tracks or peak in used_peaks:
                    continue
                track = active[index]
                track.append((frame, peak))
                continued.append(track)
                used_tracks.add(index); used_peaks.add(peak)
            complete.extend(track for i, track in enumerate(active) if i not in used_tracks)
            continued.extend([(frame, peak)] for peak in peaks if peak not in used_peaks)
            active = continued
        complete.extend(active)
        mask = np.zeros_like(mag)
        ridges = []
        total_energy = max(float(np.sum(mag*mag)), 1e-30)
        for track in complete:
            if len(track) < minimum_frames:
                continue
            fs, bins = np.asarray(track, dtype=int).T
            frequencies = []
            energy = 0.
            for frame, k in track:
                logs = np.log(np.maximum(mag[k-1:k+2, frame], 1e-30))
                denominator = logs[0]-2*logs[1]+logs[2]
                shift = np.clip(.5*(logs[0]-logs[2])/denominator, -.5, .5) if denominator < -1e-12 else 0.
                frequencies.append((k+shift)*self.sr/self.size)
                for offset in range(-2, 3):
                    if 0 <= k+offset < len(self.frequencies):
                        mask[k+offset, frame] = max(mask[k+offset, frame], np.exp(-offset*offset/2))
                energy += float(np.sum(mag[max(0,k-1):k+2, frame]**2))
            start = float(self.times[fs[0]])
            end = min(len(self.reference)/self.sr,float(self.times[fs[-1]]+self.hop/self.sr))
            ridges.append(dict(start_seconds=start, end_seconds=end,
                               duration_ms=(end-start)*1000,
                               median_hz=float(np.median(frequencies)),
                               minimum_hz=float(min(frequencies)), maximum_hz=float(max(frequencies)),
                               relative_energy=energy/total_energy,
                               frames=fs.tolist(), frequency_hz=frequencies))
        ridges.sort(key=lambda item:item['relative_energy'], reverse=True)
        return ridges, mask

    def _bands(self):
        # One-third-octave edges, clipped at the retained 7.5 kHz bandwidth.
        edges = [80.]
        while edges[-1] < self.sr/2:
            edges.append(min(self.sr/2, edges[-1]*2**(1/3)))
        result = []
        for i, (low, high) in enumerate(zip(edges, edges[1:])):
            selected = (self.frequencies >= low)&((self.frequencies <= high) if i == len(edges)-2 else (self.frequencies < high))
            if np.any(selected):
                result.append((low, high, selected))
        return result

    def _candidate(self, candidate):
        x = sosfilt(self.hp, _audio(candidate, len(self.reference)))
        rms = float(np.sqrt(np.mean(x*x)))
        x = x * (self.rms/rms) if rms > 1e-12 else np.zeros_like(x)
        return self._magnitude(x)[2]

    def _envelopes(self, magnitude):
        return np.asarray([np.sqrt(np.sum(magnitude[selected]**2,axis=0))
                           for low, high, selected in self.bands])

    def _band_score(self, mag):
        actual = self._envelopes(mag)
        # Temporal envelopes have unit RMS within each band. This removes
        # static band gains; the separate shape term must therefore accompany
        # it, otherwise a quiet or missing formant could escape that term.
        actual_rms = np.sqrt(np.mean(actual**2,axis=1))
        target_normalized = self.target_envelopes/np.maximum(self.band_rms[:,None],self.floor)
        actual_normalized = actual/np.maximum(actual_rms[:,None],self.floor)
        envelope_error = abs(actual_normalized-target_normalized)
        # Per-frame unit-L2 band vectors describe the spectral envelope.
        target_shape = self.target_envelopes/np.maximum(np.linalg.norm(self.target_envelopes,axis=0),self.floor)
        actual_shape = actual/np.maximum(np.linalg.norm(actual,axis=0),self.floor)
        shape_error = abs(np.log(np.maximum(actual_shape,.01))-np.log(np.maximum(target_shape,.01)))
        envelope = float(np.sum(envelope_error*self.band_frame_weights)/self.band_frame_sum)
        shape = float(np.sum(shape_error*self.band_frame_weights)/self.band_frame_sum)
        return dict(band_envelope_loss=envelope, band_shape_loss=shape,
                    band_loss=.5*(envelope+shape))

    def evaluate(self, candidate):
        mag = self._candidate(candidate)
        error = abs(np.log(np.maximum(mag, self.floor))-self.logged)
        return dict(persistent_spectral_error=float(np.sum(error*self.weights)/self.weight_sum),
                    unweighted_spectral_error=float(np.mean(error)), **self._band_score(mag))

    def compare_bands(self, candidate):
        """Rank magnitude deficits/excesses; these are not waveform residuals."""
        mag = self._candidate(candidate)
        total_energy = max(float(np.sum(self.target**2)), 1e-30)
        result = []
        for low, high, selected in self.bands:
            target, actual = self.target[selected], mag[selected]
            missing = np.maximum(target-actual, 0)
            excess = np.maximum(actual-target, 0)
            result.append(dict(low_hz=low, high_hz=high,
                reference_energy_fraction=float(np.sum(target**2)/total_energy),
                missing_magnitude_energy_fraction=float(np.sum(missing**2)/total_energy),
                excess_magnitude_energy_fraction=float(np.sum(excess**2)/total_energy),
                log_error=float(np.mean(abs(np.log(np.maximum(target,self.floor))-
                                           np.log(np.maximum(actual,self.floor)))))))
        return sorted(result,key=lambda item:item['missing_magnitude_energy_fraction']+item['excess_magnitude_energy_fraction'],reverse=True)

    def diagnostics(self, f0=None, periodicity=None, centres=None, limit=40):
        """Optional F0 proximity is a hint, never a semantic noise label."""
        output = []
        for ridge in self.ridges[:limit]:
            item = {k:v for k,v in ridge.items() if k not in ('frames','frequency_hz')}
            if f0 is not None:
                if periodicity is None or centres is None or not len(f0)==len(periodicity)==len(centres):
                    raise ValueError('Supply matching pitch, confidence and centre arrays')
                seconds = self.times[ridge['frames']]
                pitch = np.interp(seconds, np.asarray(centres)/self.sr, f0)
                confidence = np.interp(seconds, np.asarray(centres)/self.sr, periodicity)
                frequency = np.asarray(ridge['frequency_hz'])
                harmonic = np.maximum(1, np.rint(frequency/np.maximum(pitch,1e-12)))
                close = (pitch>0)&(confidence>=.7)&(abs(frequency-harmonic*pitch)<np.maximum(self.sr/self.size, frequency*.025))
                item['near_estimated_voice_harmonic_fraction'] = float(np.mean(close))
                item['interpretation'] = 'harmonic_context_candidate' if np.mean(close)>=.65 else 'unclassified_narrow_component'
            output.append(item)
        return dict(schema=VERSION, sample_rate=self.sr, analysis_window=self.size, hop=self.hop,
                    frequency_bin_hz=self.sr/self.size, min_run_ms=self.min_run_ms,
                    weight_range=[1.,1.+self.strength], persistent_ridges=len(self.ridges), ridges=output,
                    interpretation='Narrow spectral persistence is not proof of a voice harmonic, a formant or unwanted noise. Do not notch or add these components without exact-decoder search and intelligibility checks.')
