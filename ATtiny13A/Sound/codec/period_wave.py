"""Offline research model: YIN-style F0 and continuous-phase period waveforms.

This is a floating-point experiment, not a cycle-accurate AVR implementation.
Pitch follows cumulative mean normalized differences (de Cheveigne/Kawahara,
JASA 2002); candidate selection and trajectory costs here are our own.
"""
import numpy as np
from scipy.signal import butter, sosfilt

SR = 7500
HOP = 64
PERIOD = 32


def track_pitch(audio, sr=SR, hop=HOP, window=256, low=65., high=850.):
    """Return frame-centred F0/periodicity estimates, with zero for unvoiced.

    Fixed-length difference comparisons avoid a preference for long lags.
    A shortest convincing trough preference discourages subharmonic errors;
    dynamic programming discourages octave jumps without suppressing glides.
    Real speech estimates are not independently measured F0 ground truth.
    """
    x = np.asarray(audio, dtype=float)
    if x.ndim != 1 or len(x) < window or not np.all(np.isfinite(x)):
        raise ValueError('Expected finite mono audio at least one window long')
    if not 0 < low < high < sr / 2 or not 0 < hop <= window:
        raise ValueError('Invalid pitch range or frame size')
    lo, hi = max(2, int(sr / high)), int(np.ceil(sr / low))
    if window <= 2 * hi:
        raise ValueError('Analysis window too short for minimum F0')
    centres = np.arange(0, len(x), hop) + hop / 2
    # High-frequency turbulence must not overwhelm the periodic low bands.
    # This is analysis only: synthesis and objective retain the full bandwidth.
    filtered = sosfilt(butter(2, 1300, fs=sr, output='sos'), x)
    padded = np.pad(filtered, (window, window))
    gate = max(np.sqrt(np.mean(x*x)) * .045, 1e-7)
    candidates, costs, qualities = [], [], []
    for centre in centres:
        start = int(centre) - window // 2 + window
        segment = padded[start:start + window]
        quality = 0.
        fs, emission = [0.], [.36]
        if np.sqrt(np.mean(segment**2)) > gate:
            width = window - hi - 1
            base = segment[:width]
            diff = np.array([np.sum((base-segment[k:k+width])**2) for k in range(hi+2)])
            cmnd = np.ones_like(diff)
            cmnd[1:] = diff[1:] * np.arange(1, hi+2) / np.maximum(np.cumsum(diff[1:]), 1e-20)
            troughs = [k for k in range(lo, hi+1) if cmnd[k] < cmnd[k-1] and cmnd[k] <= cmnd[k+1]]
            if troughs:
                best = min(troughs, key=lambda k: cmnd[k])
                quality = float(max(0., 1-cmnd[best]))
                convincing = next((k for k in troughs if cmnd[k] < .16), best)
                chosen = sorted(troughs, key=lambda k: cmnd[k] + .09*abs(np.log2(k/convincing)))[:6]
                for k in chosen:
                    if cmnd[k] > .55:
                        continue
                    curvature = cmnd[k-1] - 2*cmnd[k] + cmnd[k+1]
                    shift = np.clip(.5*(cmnd[k-1]-cmnd[k+1])/max(curvature, 1e-12), -.5, .5)
                    f = sr / (k+shift)
                    if low <= f <= high:
                        fs.append(float(f))
                        emission.append(float(cmnd[k] + .09*abs(np.log2(k/convincing))))
        candidates.append(np.array(fs))
        costs.append(np.array(emission))
        qualities.append(quality)
    path_cost, back = costs[0], []
    for i in range(1, len(candidates)):
        before, after = candidates[i-1], candidates[i]
        transition = np.full((len(before), len(after)), .12)
        transition[0, 0] = 0.
        if len(before) > 1 and len(after) > 1:
            transition[1:, 1:] = .55*np.minimum(abs(np.log2(before[1:, None]/after[None, 1:])), 2.)
        options = path_cost[:, None] + transition
        indices = np.argmin(options, axis=0)
        back.append(indices)
        path_cost = options[indices, np.arange(len(after))] + costs[i]
    selected = [int(np.argmin(path_cost))]
    for indices in reversed(back):
        selected.append(int(indices[selected[-1]]))
    selected.reverse()
    f0 = np.array([candidates[i][j] for i, j in enumerate(selected)])
    return centres, f0, np.array(qualities)


def continuous_phase(f0, centres, samples, sr=SR, initial=0.):
    """Integrated cycles at each sample; unvoiced gaps carry phase/frequency."""
    voiced = np.asarray(f0) > 0
    frequency = np.interp(np.arange(samples), np.asarray(centres)[voiced], np.asarray(f0)[voiced]) if np.any(voiced) else np.full(samples, 150.)
    return initial + np.r_[0., np.cumsum(frequency[:-1]/sr)]


def quantize_phase(phase, samples, hop=HOP):
    """8-bit frequency codes, 16-bit phase step=32*code, error feedback.

    Error diffusion holds endpoint phase within half a frequency quantum per
    frame. It uses only the encoder's target trajectory, never decoder audio.
    The fixed step maps codes 1..255 to 3.662..933.838 Hz at 7500 Hz.
    """
    codes, actual = [], np.empty(samples)
    position = float(phase[0])
    for start in range(0, samples, hop):
        size = min(hop, samples-start)
        # Extrapolate the last target interval rather than dropping a sample.
        end = phase[start+size] if start+size < samples else phase[-1]+(phase[-1]-phase[-2])
        code = int(np.clip(np.rint((end-position)*65536/(32*size)), 1, 255))
        actual[start:start+size] = position + np.arange(size)*code*32/65536
        position += size*code*32/65536
        codes.append(code)
    return np.array(codes, dtype=np.uint8), actual


def fit_periods(audio, phase, f0, centres, sr=SR, width=192):
    """Local weighted harmonic fits mapped to 32 samples per cycle.

    Harmonics stop below Nyquist. Fundamental phase alignment is applied before
    this function by the caller; all fitted coefficients remain encoder data.
    """
    x = np.asarray(audio)
    shapes = np.zeros((len(centres), PERIOD))
    for i, centre in enumerate(centres):
        if f0[i] <= 0:
            continue
        left, right = max(0, int(centre)-width//2), min(len(x), int(centre)+width//2)
        indices = np.arange(left, right)
        weight = np.maximum(0., 1-abs(indices-centre)/(width/2))
        harmonics = np.arange(1, min(15, int(sr*.46/f0[i]))+1)
        angle = 2*np.pi*phase[indices, None]*harmonics
        basis = np.concatenate((np.cos(angle), np.sin(angle)), axis=1)
        coeff = np.linalg.lstsq(basis*weight[:, None], x[indices]*weight, rcond=1e-5)[0]
        angle = 2*np.pi*np.arange(PERIOD)[:, None]/PERIOD*harmonics
        shapes[i] = np.concatenate((np.cos(angle), np.sin(angle)), axis=1) @ coeff
    return shapes


def align_phase(audio, initial_phase, f0, centres, sr=SR):
    """Remove slowly changing fundamental phase from characteristic waves.

    Only confident voiced runs are unwrapped. The phase correction itself is
    converted to transmitted frequency codes; it is not a decoder side input.
    """
    offsets = np.zeros(len(centres))
    valid = np.zeros(len(centres), dtype=bool)
    for i, centre in enumerate(centres):
        if f0[i] <= 0:
            continue
        width = max(64, int(3*sr/f0[i]))
        indices = np.arange(max(0, int(centre)-width), min(len(audio), int(centre)+width))
        weight = np.maximum(0., 1-abs(indices-centre)/width)
        c = np.sum(audio[indices]*weight*np.exp(-2j*np.pi*initial_phase[indices]))
        if abs(c) > 1e-8:
            offsets[i] = np.angle(c)/(2*np.pi)
            valid[i] = True
    if not np.any(valid):
        return initial_phase.copy()
    # An unvoiced gap has no audible phase constraint. Choose the nearest branch
    # at re-entry, then interpolate the corrections through the silent gap.
    corrections = np.unwrap(offsets[valid]*2*np.pi)/(2*np.pi)
    return initial_phase + np.interp(np.arange(len(audio)), centres[valid], corrections)


def render_periods(shapes, phase, centres, voiced=None):
    """Linear time/phase interpolation; no oscillator reset at frame boundaries."""
    samples = len(phase)
    frame = np.interp(np.arange(samples), centres, np.arange(len(centres)))
    left = np.floor(frame).astype(int)
    right = np.minimum(left+1, len(shapes)-1)
    blend = frame-left
    lookup = np.remainder(phase, 1)*PERIOD
    a = np.floor(lookup).astype(int) % PERIOD
    b, fraction = (a+1) % PERIOD, lookup-np.floor(lookup)
    first = shapes[left, a]*(1-fraction) + shapes[left, b]*fraction
    second = shapes[right, a]*(1-fraction) + shapes[right, b]*fraction
    out = first*(1-blend)+second*blend
    if voiced is not None:
        out *= np.interp(np.arange(samples), centres, voiced)
    return out


def train_book(shapes, voiced, seed=23065, starts=8, count=16):
    """Deterministic clip-specific, normalized-period k-means; signed 4-bit book."""
    peaks = np.max(abs(shapes), axis=1)
    usable = voiced & (peaks > 1e-7)
    if not np.any(usable):
        return np.zeros((count, PERIOD), dtype=np.int8)
    vectors = shapes[usable]/peaks[usable, None]
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(starts):
        book = vectors[rng.choice(len(vectors), count, replace=len(vectors)<count)].copy()
        for iteration in range(60):
            distances = np.sum((vectors[:, None, :]-book[None, :, :])**2, axis=2)
            labels = np.argmin(distances, axis=1)
            updated = book.copy()
            for k in range(count):
                if np.any(labels == k):
                    updated[k] = vectors[labels == k].mean(axis=0)
            if np.max(abs(updated-book)) < 1e-7:
                break
            book = updated
        quantized = np.rint(book*7).clip(-7, 7).astype(np.int8)
        loss = float(np.min(np.sum((vectors[:, None, :]-quantized[None, :, :]/7)**2, axis=2), axis=1).sum())
        if best is None or loss < best[0]:
            best = loss, quantized
    return best[1]


GAIN_LEVELS = np.array([0., .03125, .0625, .125, .25, .5, .75, 1.])


def noise_colors(samples):
    """Fixed-seed unit-RMS noise colors, independent of source or frame fields."""
    state, noise = 23065, np.empty(samples)
    for i in range(samples):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        state &= 0xffffffff
        noise[i] = (state/2147483648-1)*np.sqrt(3)
    colors = []
    for k in range(16):
        cutoff = 200+400*(k % 8)
        color = sosfilt(butter(1, cutoff, fs=SR, btype='lowpass' if k<8 else 'highpass', output='sos'), noise)
        colors.append(color/(np.sqrt(np.mean(color*color))+1e-12))
    return np.asarray(colors)


def decode_model(model):
    """Decode solely retained parameters; does not accept reference audio/F0."""
    if model['schema'] != 'period-wave-v2' or model['sample_rate'] != SR or model['hop'] != HOP:
        raise ValueError('Unsupported period-wave model')
    samples = int(model['samples'])
    frames = np.asarray(model['frames'], dtype=int)
    book = np.asarray(model['codebook'], dtype=float)/7
    if frames.shape != ((samples+HOP-1)//HOP, 4) or book.shape != (16, PERIOD):
        raise ValueError('Invalid model dimensions')
    if np.any((frames < 0) | (frames > [255, 15, 7, 1])) or np.any(abs(book) > 1):
        raise ValueError('Invalid quantized parameters')
    centres = np.arange(len(frames))*HOP + HOP/2
    steps = np.repeat(frames[:, 0], HOP)[:samples]*32/65536
    phase = model['initial_phase_u16']/65536 + np.r_[0., np.cumsum(steps[:-1])]
    gains = GAIN_LEVELS[frames[:, 2]] * model['scale_u16']/65535
    shapes = book[frames[:, 1]]*gains[:, None]*frames[:, 3, None]
    periodic = render_periods(shapes, phase, centres)
    # Deterministic xorshift32 white noise, then 16 simple spectral colors.
    # Noise selection reuses the template index in unvoiced frames.
    colors = noise_colors(samples)
    frame = np.interp(np.arange(samples), centres, np.arange(len(frames)))
    left = np.floor(frame).astype(int)
    right = np.minimum(left+1, len(frames)-1)
    blend = frame-left
    def noise_at(indices):
        return colors[frames[indices, 1], np.arange(samples)]*gains[indices]*(1-frames[indices, 3])
    return periodic + noise_at(left)*(1-blend) + noise_at(right)*blend


def encode_model(audio, seed=23065, starts=8):
    """Learn pitch, phase-aligned book, gain and noise color from a single clip."""
    centres, f0, quality = track_pitch(audio)
    phase = align_phase(audio, continuous_phase(f0, centres, len(audio)), f0, centres)
    phase -= np.floor(phase[0])
    initial = int(np.rint(phase[0]*65536)) % 65536
    phase += initial/65536-phase[0]
    codes, quantized_phase = quantize_phase(phase, len(audio))
    shapes = fit_periods(audio, quantized_phase, f0, centres)
    book = train_book(shapes, f0 > 0, seed, starts)
    peaks = np.max(abs(shapes), axis=1)
    rms = np.array([np.sqrt(np.mean(audio[max(0, int(c)-HOP//2):min(len(audio), int(c)+HOP//2)]**2)) for c in centres])
    scale = float(min(1., max(np.max(peaks), np.max(rms), 1e-6)))
    scale_u16 = max(1, int(np.rint(scale*65535)))
    scale = scale_u16/65535
    vectors = book[:, None, :]/7*GAIN_LEVELS[None, :, None]*scale
    distance = np.sum((shapes[:, None, None, :]-vectors[None, :, :, :])**2, axis=3)
    assignment = np.argmin(distance.reshape(len(shapes), -1), axis=1)
    ids, gains = assignment//8, assignment % 8
    for i, centre in enumerate(centres):
        if f0[i] > 0:
            continue
        gains[i] = np.argmin(abs(GAIN_LEVELS*scale-rms[i]))
        indices = np.arange(max(0, int(centre)-64), min(len(audio), int(centre)+64))
        spectrum = abs(np.fft.rfft(audio[indices]*np.hanning(len(indices))))**2
        frequencies = np.fft.rfftfreq(len(indices), 1/SR)
        centroid = np.sum(frequencies*spectrum)/(np.sum(spectrum)+1e-20)
        # An explicitly limited two-family noise-color initializer.
        ids[i] = np.argmin(abs(np.r_[np.arange(8)*160+300, np.arange(8)*150+1900]-centroid))
    frames = np.column_stack((codes, ids, gains, f0>0)).astype(int)
    model = dict(schema='period-wave-v2', sample_rate=SR, samples=len(audio), hop=HOP,
                 initial_phase_u16=initial, scale_u16=scale_u16,
                 codebook=book.astype(int).tolist(), frames=frames.tolist())
    analysis = dict(centres=centres, f0=f0, periodicity=quality, phase=quantized_phase,
                    shapes=shapes, continuous_unquantized=render_periods(shapes, quantized_phase, centres),
                    phase_target=phase)
    return model, analysis


def packed_bytes(model):
    """Actual compact research payload: 10-byte header, 256-byte book, 2B/frame.

    Header: samples u16, initial phase u16, scale u16, PW version 2 (4 bytes).
    Fixed sample rate/hop/book/noise seed/gain levels are decoder conventions.
    Decoder code and constants are deliberately NOT included in this count.
    """
    import struct
    if not 0 < model['samples'] <= 65535:
        raise ValueError('Compact model supports 1..65535 samples')
    # Validate all numerical conventions through the same decoder contract.
    decode_model(model)
    book = np.asarray(model['codebook'], dtype=int).ravel()
    nibbles = book & 15
    output = bytearray(struct.pack('<4sHHH', b'PW\x02\x00', model['samples'], model['initial_phase_u16'], model['scale_u16']))
    output.extend((nibbles[::2] | nibbles[1::2] << 4).astype(np.uint8).tobytes())
    for pitch, index, gain, voiced in model['frames']:
        output.extend((pitch, index | gain << 4 | voiced << 7))
    return bytes(output)


def unpack_bytes(payload):
    import struct
    if len(payload) < 266:
        raise ValueError('Truncated period-wave payload')
    magic, samples, initial, scale = struct.unpack('<4sHHH', payload[:10])
    count = (samples+HOP-1)//HOP
    if magic != b'PW\x02\x00' or len(payload) != 266+2*count:
        raise ValueError('Invalid period-wave payload')
    packed = np.frombuffer(payload[10:266], dtype=np.uint8).astype(int)
    book = np.column_stack((packed & 15, packed >> 4)).ravel()
    book[book >= 8] -= 16
    frames = [[payload[i], payload[i+1] & 15, (payload[i+1] >> 4) & 7, payload[i+1] >> 7] for i in range(266, len(payload), 2)]
    return dict(schema='period-wave-v2', sample_rate=SR, samples=samples, hop=HOP,
                initial_phase_u16=initial, scale_u16=scale,
                codebook=book.reshape(16, PERIOD).tolist(), frames=frames)


class FrameSynthesis:
    """Cached linear contributions for fixed-pitch frame-parameter search.

    The final decoder remains decode_model. This cache only speeds up encoder
    proposals; matching it against the independent decoder is a test contract.
    """
    def __init__(self, model):
        samples = model['samples']
        frames = np.array(model['frames'], dtype=int)
        centres = np.arange(len(frames))*HOP+HOP/2
        phase = model['initial_phase_u16']/65536 + np.r_[0., np.cumsum(np.repeat(frames[:, 0], HOP)[:samples-1]*32/65536)]
        lookup = np.remainder(phase, 1)*PERIOD
        a = np.floor(lookup).astype(int) % PERIOD
        b, mix = (a+1) % PERIOD, lookup-np.floor(lookup)
        book = np.array(model['codebook'])/7
        periodic = book[:, a]*(1-mix)+book[:, b]*mix
        noise = noise_colors(samples)
        self.bases, self.slices = [], []
        position = np.interp(np.arange(samples), centres, np.arange(len(frames)))
        for i in range(len(frames)):
            weight = np.maximum(0, 1-abs(position-i))
            support = np.flatnonzero(weight > 0)
            region = slice(int(support[0]), int(support[-1])+1)
            self.slices.append(region)
            self.bases.append(np.stack((noise[:, region], periodic[:, region]))*weight[region]*model['scale_u16']/65535)
        self.samples = samples

    def contribution(self, i, frame):
        _, index, gain, voiced = frame
        return self.bases[i][voiced, index]*GAIN_LEVELS[gain]

    def render(self, frames):
        out = np.zeros(self.samples)
        for i, frame in enumerate(frames):
            out[self.slices[i]] += self.contribution(i, frame)
        return out


def refine_frames(model, objective, proposals=5000, seed=23066):
    """Greedy analysis-by-synthesis, balancing spectra and STOI explicitly.

    Does not promise a global optimum or a STOI floor. Pitch/book stay fixed;
    gain, template/color and voiced/noise mode are chosen through actual audio.
    """
    from copy import deepcopy
    from pystoi import stoi
    rng = np.random.default_rng(seed)
    result = deepcopy(model)
    frames = np.array(model['frames'], dtype=int)
    cache = FrameSynthesis(model)
    audio = cache.render(frames)
    def score(x):
        return objective.spectrum(x)['loss'] + 2*(1-float(stoi(objective.reference, x, SR)))
    initial = energy = score(audio)
    improvements = 0
    for step in range(proposals):
        i = int(rng.integers(len(frames)))
        proposed = frames[i].copy()
        kind = int(rng.integers(4))
        if kind in (0, 3):
            proposed[2] = int(rng.integers(8))
        if kind in (1, 3):
            proposed[1] = int(rng.integers(16))
        if kind == 2:
            proposed[3] ^= 1
        if np.array_equal(proposed, frames[i]):
            continue
        candidate = audio.copy()
        candidate[cache.slices[i]] += cache.contribution(i, proposed)-cache.contribution(i, frames[i])
        value = score(candidate)
        if value < energy:
            frames[i], audio, energy = proposed, candidate, value
            improvements += 1
    result['frames'] = frames.tolist()
    exact = decode_model(result)
    if not np.allclose(audio, exact, atol=1e-11, rtol=0):
        raise AssertionError('Search cache differs from independent decoder')
    return result, dict(proposals=proposals, improvements=improvements, seed=seed,
                        objective='spectral_loss + 2 * (1 - STOI)', initial_energy=initial, final_energy=energy)
