"""PC research source with independently controlled, continuous-phase partials.

Only trajectories and one fitted initial phase per stable track are retained;
there is no stored waveform/residual. This is not an AVR implementation.
"""
import struct
import numpy as np
from scipy.signal import stft
from harmonic_tracks import HarmonicTrackObjective


def _basis(track, samples, sr, hop):
    positions = np.asarray(track['frames'], float)*hop
    start = max(0, int(positions[0]))
    stop = min(samples, int(positions[-1])+1)
    t = np.arange(start, stop, dtype=float)
    frequency = np.interp(t, positions, track['frequency_hz'])
    amplitude = interpolate_amplitude(t, positions, track['amplitude'])
    phase = np.zeros(len(t))
    if len(t) > 1:
        phase[1:] = np.cumsum(np.pi*(frequency[1:]+frequency[:-1])/sr)
    phase += track.get('initial_phase', 0.)
    return start, stop, amplitude*np.cos(phase), amplitude*np.sin(phase)


def interpolate_amplitude(t, positions, values):
    """Linear dB within voiced runs; explicit zeros keep silent gaps silent."""
    positions, values = np.asarray(positions), np.asarray(values)
    right = np.clip(np.searchsorted(positions, t, side='right'), 1, len(positions)-1)
    left = right-1
    if len(positions) == 1:
        return np.full(len(t), values[0])
    u = np.clip((t-positions[left])/np.maximum(positions[right]-positions[left], 1e-20), 0, 1)
    a, b = values[left], values[right]
    linear = a+(b-a)*u
    both = (a > 0) & (b > 0)
    linear[both] = np.exp(np.log(a[both])*(1-u[both])+np.log(b[both])*u[both])
    return linear


def adaptive_knots(track, frequency_tolerance_hz=3., level_tolerance_db=1.):
    """RDP in normalized time/frequency/level; retain material slope turns.

    Positive-run endpoints and zero transitions are mandatory. This prevents
    interpolation across silent gaps, including when looser bounds are chosen.
    """
    if frequency_tolerance_hz <= 0 or level_tolerance_db <= 0:
        raise ValueError('Interpolation bounds must be positive')
    t = np.asarray(track['frames'], float)
    f, a = np.asarray(track['frequency_hz']), np.asarray(track['amplitude'])
    keep = {0, len(t)-1}
    active = a > 0
    for i in np.flatnonzero(active[1:] != active[:-1]):
        keep.update((int(i), int(i)+1))
    def split(left, right):
        if right <= left+1:
            return
        u = (t[left+1:right]-t[left])/(t[right]-t[left])
        frequency_error = abs(f[left+1:right]-(f[left]+(f[right]-f[left])*u))/frequency_tolerance_hz
        predicted = interpolate_amplitude(t[left+1:right], t[[left, right]], a[[left, right]])
        real = a[left+1:right]
        level_error = np.zeros(len(real))
        positive = (real > 0) & (predicted > 0)
        level_error[positive] = abs(20*np.log10(predicted[positive]/real[positive]))/level_tolerance_db
        level_error[(real > 0) != (predicted > 0)] = np.inf
        errors = np.maximum(frequency_error, level_error)
        i = int(np.argmax(errors))
        if errors[i] > 1:
            index = left+1+i
            keep.add(index)
            split(left, index)
            split(index, right)
    mandatory = sorted(keep)
    for left, right in zip(mandatory[:-1], mandatory[1:]):
        split(left, right)
    indices = sorted(keep)
    return dict(track, frames=[track['frames'][i] for i in indices],
                frequency_hz=[track['frequency_hz'][i] for i in indices],
                amplitude=[track['amplitude'][i] for i in indices])


def simplify(model, frequency_tolerance_hz=3., level_tolerance_db=1.):
    return dict(model, tracks=[adaptive_knots(t, frequency_tolerance_hz, level_tolerance_db)
                              for t in model['tracks']])


def curve_errors(original, candidate):
    frequency = cents = level = 0.
    missing = 0
    for before, after in zip(original['tracks'], candidate['tracks']):
        frames = np.asarray(before['frames'])
        predicted_f = np.interp(frames, after['frames'], after['frequency_hz'])
        predicted_a = interpolate_amplitude(frames, after['frames'], after['amplitude'])
        a = np.asarray(before['amplitude'])
        active = a > 0
        if np.any(active):
            frequency = max(frequency, float(np.max(abs(predicted_f[active]-np.asarray(before['frequency_hz'])[active]))))
            cents = max(cents, float(np.max(abs(1200*np.log2(predicted_f[active]/np.asarray(before['frequency_hz'])[active])))))
        positive = active & (predicted_a > 0)
        missing += int(np.sum(active & ~positive))
        if np.any(positive):
            level = max(level, float(np.max(abs(20*np.log10(predicted_a[positive]/a[positive])))))
    return dict(maximum_frequency_error_hz=frequency, maximum_frequency_error_cents=cents, maximum_level_error_db=level,
                missing_positive_knots=missing)


def render(model):
    out = np.zeros(model['samples'], float)
    for track in model['tracks']:
        start, stop, cosine, _ = _basis(track, len(out), model['sample_rate'], model['hop'])
        out[start:stop] += cosine
    return out


def analyze(reference, components=3, sr=7500):
    x = np.asarray(reference, float)
    control = HarmonicTrackObjective(x, sr, max_tracks=components)
    source = control.reference_tracks
    _, _, z = stft(x, fs=sr, nperseg=control.n_fft, noverlap=control.n_fft-control.hop)
    tracks = []
    for ident in np.unique(source['track_id']):
        if ident < 0:
            continue
        rows, cols = np.where(source['track_id'] == ident)
        first, last = max(0, int(rows[0])-1), min(len(source['times'])-1, int(rows[-1])+1)
        frames = np.arange(first, last+1)
        frequencies = np.interp(frames, rows, source['frequency_hz'][rows, cols])
        amplitudes = np.zeros(len(frames))
        amplitudes[rows-first] = source['amplitude'][rows, cols]
        # Center-correct the FFT bin phase. Neighbouring bins of one sinusoid
        # agree after this correction; the least-squares step fits final phase.
        peak_bin = int(np.clip(round(source['frequency_hz'][rows[0], cols[0]]/control.bin_hz), 1, z.shape[0]-2))
        measured_phase = float(np.angle(z[peak_bin, rows[0]])+np.pi*peak_bin)
        offset_seconds = float(source['times'][rows[0]]-source['times'][first])
        initial_phase = measured_phase-2*np.pi*frequencies[0]*offset_seconds
        tracks.append(dict(id=int(ident), frames=frames.tolist(), frequency_hz=frequencies.tolist(),
                           amplitude=amplitudes.tolist(), initial_phase=initial_phase))
    model = dict(schema='sin-partials-pc-v1', sample_rate=sr, samples=len(x), hop=control.hop,
                 components=components, tracks=tracks, phase_policy='Continuous integral of piecewise-linear frequency; one phase per track',
                 analysis='Original-derived strongest local peaks; stable IDs with births/deaths and zero-amplitude gaps')
    # A global linear fit simultaneously chooses one amplitude scale and phase
    # correction per track, while keeping all independently controlled curves.
    matrix = np.zeros((len(x), 2*len(tracks)))
    for j, track in enumerate(tracks):
        start, stop, cosine, sine = _basis(track, len(x), sr, control.hop)
        matrix[start:stop, 2*j] = cosine
        matrix[start:stop, 2*j+1] = sine
    if len(tracks):
        coefficients = np.linalg.lstsq(matrix, x, rcond=1e-5)[0]
        for j, track in enumerate(tracks):
            c, s = coefficients[2*j:2*j+2]
            gain = float(np.hypot(c, s))
            track['amplitude'] = (np.asarray(track['amplitude'])*gain).tolist()
            track['initial_phase'] -= float(np.arctan2(s, c))
    return model


def _put_uint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return out


def _get_uint(data, offset):
    value = shift = 0
    while True:
        if offset >= len(data) or shift > 35:
            raise ValueError('Truncated or excessive variable integer')
        b = data[offset]
        offset += 1
        value |= (b & 127) << shift
        if b < 128:
            return value, offset
        shift += 7


def encode(model, *, stride=1, frequency_step=1., amplitude_bits=8):
    if stride < 1 or frequency_step <= 0 or amplitude_bits not in (4, 8):
        raise ValueError('Invalid trajectory quantization')
    maximum = max((max(track['amplitude']) for track in model['tracks']), default=1.)
    maximum = max(maximum, 1e-10)
    levels = (1 << amplitude_bits)-1
    # The amplitude/frequency scales are rounded into the actual serialized
    # float32 header before quantizing, so numerical reconstruction is explicit.
    maximum = struct.unpack('<f', struct.pack('<f', maximum))[0]
    frequency_step = struct.unpack('<f', struct.pack('<f', frequency_step))[0]
    out = bytearray(struct.pack('<4sHIHBBHff', b'SP01', model['sample_rate'], model['samples'],
                                model['hop'], model['components'], amplitude_bits,
                                len(model['tracks']), frequency_step, maximum))
    for track in model['tracks']:
        indices = sorted(set(range(0, len(track['frames']), stride)) | {len(track['frames'])-1})
        out += _put_uint(len(indices))
        out.append(int(round((track['initial_phase'] % (2*np.pi))*256/(2*np.pi))) & 255)
        previous_frame = previous_frequency = 0
        amplitudes = []
        for i in indices:
            frame = int(track['frames'][i])
            freq = max(0, int(round(track['frequency_hz'][i]/frequency_step)))
            out += _put_uint(frame-previous_frame)
            delta = freq-previous_frequency
            out += _put_uint(2*delta if delta >= 0 else -2*delta-1)
            amplitudes.append(max(0, min(levels, int(round(track['amplitude'][i]/maximum*levels)))))
            previous_frame, previous_frequency = frame, freq
        if amplitude_bits == 8:
            out += bytes(amplitudes)
        else:
            out += bytes(amplitudes[i] | ((amplitudes[i+1] if i+1 < len(amplitudes) else 0) << 4)
                         for i in range(0, len(amplitudes), 2))
    return bytes(out)


def decode(data):
    header = struct.Struct('<4sHIHBBHff')
    if len(data) < header.size:
        raise ValueError('Truncated partial source header')
    magic, sr, samples, hop, components, bits, count, freqstep, maximum = header.unpack_from(data)
    if magic != b'SP01' or bits not in (4, 8) or not 1 <= components <= 10 or freqstep <= 0:
        raise ValueError('Unsupported partial source header')
    offset = header.size
    tracks = []
    for ident in range(count):
        n, offset = _get_uint(data, offset)
        if n < 1 or offset >= len(data):
            raise ValueError('Invalid partial trajectory')
        phase = data[offset]*2*np.pi/256
        offset += 1
        frames, frequencies = [], []
        frame = freq = 0
        for _ in range(n):
            delta, offset = _get_uint(data, offset)
            frame += delta
            zigzag, offset = _get_uint(data, offset)
            freq += zigzag//2 if zigzag % 2 == 0 else -(zigzag//2)-1
            frames.append(frame)
            frequencies.append(freq*freqstep)
        byte_count = n if bits == 8 else (n+1)//2
        if offset+byte_count > len(data):
            raise ValueError('Truncated partial amplitudes')
        packed = data[offset:offset+byte_count]
        amps = list(packed) if bits == 8 else [((packed[i//2] >> (4*(i % 2))) & 15) for i in range(n)]
        offset += byte_count
        tracks.append(dict(id=ident, frames=frames, frequency_hz=frequencies,
                           amplitude=[a*maximum/((1 << bits)-1) for a in amps], initial_phase=phase))
    if offset != len(data):
        raise ValueError('Trailing partial source bytes')
    return dict(schema='sin-partials-pc-v1', sample_rate=sr, samples=samples, hop=hop,
                components=components, tracks=tracks)


def fit_phase_only(reference, model, passes=3):
    """Refit one initial phase per track after quantizing frequency curves.

    Frequency, amplitudes and knot positions stay frozen. No phase reset occurs
    at an interior knot, and no source residual is retained in the model.
    """
    tracks = [dict(t) for t in model['tracks']]
    result = dict(model, tracks=tracks)
    output = render(result)
    for _ in range(passes):
        for track in tracks:
            start, stop, old, _ = _basis(track, len(output), model['sample_rate'], model['hop'])
            residual = reference[start:stop]-output[start:stop]+old
            basis = dict(track, initial_phase=0.)
            _, _, cosine, sine = _basis(basis, len(output), model['sample_rate'], model['hop'])
            phase = -float(np.arctan2(np.dot(residual, sine), np.dot(residual, cosine)))
            updated = cosine*np.cos(phase)-sine*np.sin(phase)
            if np.sum((residual-updated)**2) < np.sum((residual-old)**2):
                track['initial_phase'] = phase
                output[start:stop] += updated-old
    return result


def encode_log(model, bins_per_octave=32, level_step_db=1.):
    """Actual byte/nibble-delta log-frequency and dB-level source serialization."""
    fmin = model['sample_rate']/128
    maxindex = int(np.ceil(bins_per_octave*np.log2((model['sample_rate']/2)/fmin)))
    if not 1 <= bins_per_octave <= 42 or maxindex > 254 or not 0 < level_step_db <= 63.75:
        raise ValueError('Log-frequency indices must fit one byte')
    level_quarters = max(1, int(round(level_step_db*4)))
    level_step_db = level_quarters/4
    maximum = max(max(t['amplitude']) for t in model['tracks']) if model['tracks'] else 1.
    maximum = max(1e-10, struct.unpack('<f', struct.pack('<f', maximum))[0])
    out = bytearray(struct.pack('<4sHIHBBBHff', b'SP02', model['sample_rate'], model['samples'],
                                model['hop'], model['components'], bins_per_octave, level_quarters,
                                len(model['tracks']), fmin, maximum))
    for track in model['tracks']:
        out += _put_uint(len(track['frames']))
        out.append(int(round((track['initial_phase'] % (2*np.pi))*256/(2*np.pi))) & 255)
        previous_frame = previous_index = previous_level = 0
        for i, (frame, frequency, amplitude) in enumerate(zip(track['frames'], track['frequency_hz'], track['amplitude'])):
            index = max(0, min(maxindex, int(round(bins_per_octave*np.log2(max(frequency, fmin)/fmin)))))
            level = 255 if amplitude <= 0 else max(0, min(254, int(round(-20*np.log10(amplitude/maximum)/level_step_db))))
            out += _put_uint(int(frame)-previous_frame)
            if i == 0:
                out += bytes((index, level))
            else:
                di, dl = index-previous_index, level-previous_level
                ni, nl = (di+7 if -7 <= di <= 7 else 15), (dl+7 if -7 <= dl <= 7 else 15)
                out.append(ni | (nl << 4))
                if ni == 15:
                    out.append(index)
                if nl == 15:
                    out.append(level)
            previous_frame, previous_index, previous_level = int(frame), index, level
    return bytes(out)


def decode_log(data):
    header = struct.Struct('<4sHIHBBBHff')
    if len(data) < header.size:
        raise ValueError('Truncated logarithmic source header')
    magic, sr, samples, hop, components, bins, quarters, count, fmin, maximum = header.unpack_from(data)
    if magic != b'SP02' or not 1 <= bins <= 42 or not quarters:
        raise ValueError('Invalid logarithmic source header')
    tracks = []
    offset = header.size
    for ident in range(count):
        n, offset = _get_uint(data, offset)
        if not n or offset >= len(data):
            raise ValueError('Invalid logarithmic trajectory')
        phase = data[offset]*2*np.pi/256
        offset += 1
        frames, frequencies, amplitudes = [], [], []
        frame = index = level = 0
        for i in range(n):
            gap, offset = _get_uint(data, offset)
            frame += gap
            if i == 0:
                if offset+2 > len(data):
                    raise ValueError('Truncated logarithmic first knot')
                index, level = data[offset:offset+2]
                offset += 2
            else:
                if offset >= len(data):
                    raise ValueError('Truncated logarithmic delta knot')
                packed = data[offset]
                offset += 1
                ni, nl = packed & 15, packed >> 4
                if ni == 15:
                    if offset >= len(data): raise ValueError('Truncated frequency escape')
                    index = data[offset]; offset += 1
                else:
                    index += ni-7
                if nl == 15:
                    if offset >= len(data): raise ValueError('Truncated level escape')
                    level = data[offset]; offset += 1
                else:
                    level += nl-7
            frames.append(frame)
            frequencies.append(fmin*2**(index/bins))
            amplitudes.append(0. if level == 255 else maximum*10**(-level*quarters/80))
        tracks.append(dict(id=ident, frames=frames, frequency_hz=frequencies,
                           amplitude=amplitudes, initial_phase=phase))
    if offset != len(data):
        raise ValueError('Trailing logarithmic source bytes')
    return dict(schema='sin-partials-pc-v1', sample_rate=sr, samples=samples,
                hop=hop, components=components, tracks=tracks)


def log_layout(model, payload_bytes):
    tracks = len(model['tracks'])
    knots = sum(len(t['frames']) for t in model['tracks'])
    counts = sum(len(_put_uint(len(t['frames']))) for t in model['tracks'])
    times = 0
    for track in model['tracks']:
        previous = 0
        for frame in track['frames']:
            times += len(_put_uint(frame-previous))
            previous = frame
    result = dict(header_bytes=struct.calcsize('<4sHIHBBBHff'), phase_bytes=tracks,
                  knot_count_varint_bytes=counts, time_delta_varint_bytes=times,
                  first_frequency_index_bytes=tracks, first_level_index_bytes=tracks,
                  packed_frequency_level_delta_bytes=knots-tracks, explicit_track_id_bytes=0)
    result['absolute_escape_bytes'] = payload_bytes-sum(result.values())
    result['total_bytes'] = payload_bytes
    return result
