"""Select compact, measured FluidR3 instruments for the ATtiny13A EEPROM.

No SoundFont or audio renderer is needed when building a firmware. NumPy is
only imported by the optional measurement and bank-authoring operations.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / 'ATtiny13A/Music/instruments/bank.json'
ROLES = ('lead', 'keys', 'pluck')
MODELS = {'bowed', 'piano', 'pluck', 'sustain', 'off'}


def _validate_transient(name, profile):
    transient = profile.get('transient')
    if transient is None:
        return
    if profile['gmProgram'] != 0 or transient.get('kind') != 'piano-attack':
        raise ValueError(f'{name}: only the shared GM0 piano attack is supported')
    if transient.get('eepromOffsets') != {'low': 48, 'high': 56} or transient.get('minEnvelopeLevel') != 14:
        raise ValueError(f'{name}: expected attack banks 48/56 and threshold 14')
    if transient.get('maximumSwitchSampleDelta') != 1:
        raise ValueError(f'{name}: the shared piano supports a one-unit table switch')
    for register in ('low', 'high'):
        attack = transient['waves'][register]
        pack_wave(attack)
        sustain = profile['waves'][register]
        if sum(attack) or sum(sustain) or max(abs(a - b) for a, b in zip(attack, sustain)) > 1:
            raise ValueError(f'{name}: attack/sustain must be zero-DC with a maximum one-unit switch')


def load_bank(path=None):
    """Read and validate the declarative bank; no synthesis dependencies."""
    bank = json.loads(Path(path or BANK_PATH).read_text(encoding='utf-8'))
    if bank.get('schema') != 1 or not isinstance(bank.get('instruments'), dict):
        raise ValueError('Unsupported instrument bank schema')
    for name, profile in bank['instruments'].items():
        if not isinstance(name, str) or not name:
            raise ValueError('An instrument must have a nonempty ID')
        program = profile['gmProgram']
        if program is not None and (type(program) is not int or not 0 <= program <= 127):
            raise ValueError(f'{name}: GM programs are zero based, 0..127')
        for register in ('low', 'high'):
            wave = profile['waves'][register]
            if len(wave) != 16 or any(type(v) is not int or not -8 <= v <= 7 for v in wave):
                raise ValueError(f'{name}/{register}: expected 16 integer samples in -8..7')
        envelope = profile['envelope']
        if envelope['model'] not in MODELS or type(envelope['defaultLevel']) is not int or not 0 <= envelope['defaultLevel'] <= 15:
            raise ValueError(f'{name}: unsupported envelope or level')
        if name != 'off' and not profile.get('source', {}).get('measurement'):
            raise ValueError(f'{name}: measured source is required')
        _validate_transient(name, profile)
    if 'off' not in bank['instruments'] or any(bank['instruments']['off']['waves'][r] != [0] * 16 for r in ('low', 'high')):
        raise ValueError('The off profile must be silence')
    for name, kit in bank.get('percussion', {}).items():
        if name != 'natural-kit' or not kit.get('source', {}).get('measurement'):
            raise ValueError('Unsupported or unmeasured percussion kit')
        if [n['gmNote'] for n in kit['notes']] != [35, 38, 42]:
            raise ValueError('Natural kit must identify kick 35, snare 38 and closed hi-hat 42')
    return bank


def _assignment(value, bank):
    if isinstance(value, str):
        value = {'instrument': value}
    if not isinstance(value, dict) or set(value) - {'instrument', 'level'}:
        raise ValueError('An assignment is an ID or {instrument: ID, level: 0..15}')
    name = value.get('instrument')
    if not isinstance(name, str) or name not in bank['instruments']:
        raise ValueError(f'Unknown instrument: {name!r}')
    profile = bank['instruments'][name]
    level = value.get('level', profile['envelope']['defaultLevel'])
    if type(level) is not int or not 0 <= level <= 15:
        raise ValueError(f'{name}: level must be an integer in 0..15')
    if name == 'off' and level != 0:
        raise ValueError('The off profile has level zero')
    return name, level, profile


def describe_assignments(assignments, bank=None):
    """Resolve roles to profiles and explicit firmware envelope/level settings.

    Missing tonal roles are off. Percussion selects a separate noise generator
    and consumes no tonal EEPROM space; 'off' and 'natural-kit' are supported.
    Levels are metadata: the firmware must apply them in its envelope code.
    """
    bank = bank or load_bank()
    if not isinstance(assignments, dict) or set(assignments) - set(ROLES) - {'percussion'}:
        raise ValueError('Supported roles: lead, keys, pluck and percussion')
    if 'percussion' in assignments:
        kit_value = assignments['percussion']
        if isinstance(kit_value, str):
            kit_value = {'instrument': kit_value}
        if not isinstance(kit_value, dict) or set(kit_value) - {'instrument', 'level'}:
            raise ValueError('A percussion assignment is off or natural-kit')
        kit_name = kit_value.get('instrument')
        if not isinstance(kit_name, str) or kit_name not in ('off', 'natural-kit'):
            raise ValueError('A percussion assignment is off or natural-kit')
        kit_level = kit_value.get('level', 0 if kit_name == 'off' else 15)
        if type(kit_level) is not int or not 0 <= kit_level <= 15 or (kit_name == 'off' and kit_level != 0):
            raise ValueError('Percussion level must be 0..15; off must have level zero')
    result = {}
    for index, role in enumerate(ROLES):
        name, level, profile = _assignment(assignments.get(role, 'off'), bank)
        result[role] = dict(instrument=name, label=profile['label'], gmProgram=profile['gmProgram'],
                            eepromOffset=index * 16, level=level,
                            envelope=copy.deepcopy(profile['envelope']))
        if profile.get('transient') is not None:
            _validate_transient(name, profile)
            result[role]['transient'] = {key: copy.deepcopy(value) for key, value in profile['transient'].items() if key != 'waves'}
    if 'percussion' in assignments:
        if kit_name == 'off':
            result['percussion'] = dict(instrument='off', label='Выключены', level=0,
                                        enabled=False, notes=[])
        else:
            kit = bank['percussion'][kit_name]
            result['percussion'] = dict(instrument=kit_name, label=kit['label'],
                                        level=kit_level, enabled=kit_level > 0,
                                        notes=copy.deepcopy(kit['notes']),
                                        generator=kit['generator'], profiles=kit.get('profiles'), eepromBytes=0)
    return result


def pack_wave(wave):
    """Offset binary nibbles: first sample is the low nibble, silence is 8."""
    if len(wave) != 16 or any(type(v) is not int or not -8 <= v <= 7 for v in wave):
        raise ValueError('Expected 16 integer samples in -8..7')
    return bytes((wave[i] + 8) | ((wave[i + 1] + 8) << 4) for i in range(0, 16, 2))


def build_eeprom(assignments, bank=None):
    """Return all 64 physical EEPROM bytes for three assigned low/high pairs.

    If any selected role is GM0 piano, the final 16 bytes hold its common low/high
    attack pair. Without piano those bytes are silent. Levels remain firmware
    metadata. This function never changes any input or file on disk.
    """
    bank = bank or load_bank()
    roles = describe_assignments(assignments, bank)
    result = bytearray()
    attack_pair = None
    for role in ROLES:
        profile = bank['instruments'][roles[role]['instrument']]
        result.extend(pack_wave(profile['waves']['low']))
        result.extend(pack_wave(profile['waves']['high']))
        if profile.get('transient') is not None:
            _validate_transient(roles[role]['instrument'], profile)
            pair = pack_wave(profile['transient']['waves']['low']) + pack_wave(profile['transient']['waves']['high'])
            if attack_pair is not None and attack_pair != pair:
                raise ValueError('Selected piano parts require different shared attack tables')
            attack_pair = pair
    result.extend(attack_pair if attack_pair is not None else b'\x88' * 16)
    return bytes(result)


def verify_sources(bank=None):
    """Check retained measurement hashes and pinned SoundFont provenance."""
    bank = bank or load_bank()
    errors = []
    profiles = list(bank['instruments'].items()) + list(bank.get('percussion', {}).items())
    for name, profile in profiles:
        if name == 'off':
            continue
        source = profile['source']
        path = ROOT / source['measurement']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source['measurementSha256']:
            errors.append(f'{name}: missing or changed measurement {path}')
        if source['soundfontSha256'] != bank['soundfont']['sha256']:
            errors.append(f'{name}: inconsistent SoundFont provenance')
    if errors:
        raise ValueError('\n'.join(errors))
    return True


def fit_measurements(path, cutoff=3.2, peak=5, split_midi=63):
    """Fit measured harmonic envelopes to two quiet, zero-DC 16-point waves.

    Uses retained analyze-fluid-violin.py JSON. The seven representable
    harmonics get an explicit soft low-pass. A deterministic pairwise integer
    search improves normalized spectral error while preserving zero DC.
    This is bank authoring, not part of firmware assembly.
    """
    import numpy as np
    if not math.isfinite(cutoff) or cutoff <= 0 or type(peak) is not int or not 1 <= peak <= 7:
        raise ValueError('Expected positive harmonic cutoff and integer peak 1..7')
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    notes = data['notes']
    result = {}
    h = np.arange(1, 8)
    attenuation = 1 / np.sqrt(1 + (h / cutoff) ** 6)
    phase_grid = np.arange(16) * 2 * np.pi / 16
    # Evaluate all sum-preserving +/-1 sample changes in a single FFT batch.
    moves = np.array([np.eye(16, dtype=int)[i] - np.eye(16, dtype=int)[j]
                      for i in range(16) for j in range(16) if i != j])
    rng = np.random.default_rng(1331)
    for register in ('low', 'high'):
        chosen = [n for n in notes if (n['midi'] < split_midi) == (register == 'low')] or notes
        frames = [f for note in chosen for f in note['frames']]
        raw = np.median([np.array(f['amplitudes'][:7]) / np.linalg.norm(f['amplitudes'][:7]) for f in frames], axis=0)
        raw /= np.linalg.norm(raw)
        target = raw * attenuation
        target /= np.linalg.norm(target)
        phases = np.angle(np.mean(np.exp(1j * np.array([f['relativePhases'][:7] for f in frames])), axis=0))

        def losses(waves):
            z = np.fft.rfft(waves, axis=-1)
            amplitudes = abs(z[..., 1:8])
            normalized = amplitudes / np.maximum(1e-9, np.linalg.norm(amplitudes, axis=-1, keepdims=True))
            spectral = np.sum((normalized - target) ** 2, axis=-1)
            # Nyquist energy is not part of the seven-harmonic target.
            nyquist = abs(z[..., 8]) ** 2 / np.maximum(1e-9, np.sum(amplitudes ** 2, axis=-1))
            return spectral + .04 * nyquist

        best = None
        for attempt in range(24):
            angles = phases if attempt == 0 else rng.uniform(-np.pi, np.pi, 7)
            raw_wave = np.sum(target[:, None] * np.cos(h[:, None] * phase_grid + angles[:, None]), axis=0)
            wave = np.rint(raw_wave / max(abs(raw_wave)) * peak).astype(int)
            # Rounded waves can acquire DC; correct with the least time-domain error.
            while wave.sum():
                direction = -int(np.sign(wave.sum()))
                candidates = wave[None, :] + np.eye(16, dtype=int) * direction
                admissible = np.max(abs(candidates), axis=1) <= peak
                error = np.sum((candidates - raw_wave / max(abs(raw_wave)) * peak) ** 2, axis=1)
                error[~admissible] = np.inf
                wave = candidates[np.argmin(error)]
            value = float(losses(wave))
            for _ in range(24):
                candidates = wave[None, :] + moves
                admissible = (np.max(abs(candidates), axis=1) <= peak) & (np.max(abs(candidates), axis=1) >= peak - 1)
                scores = losses(candidates)
                scores[~admissible] = np.inf
                index = np.argmin(scores)
                if scores[index] >= value - 1e-12:
                    break
                wave, value = candidates[index], float(scores[index])
            if best is None or value < best[0]:
                best = value, wave
        wave = best[1]
        # Minimize an initial step at note-on without changing its spectrum.
        rotation = min(range(16), key=lambda i: (abs(wave[i]), abs(wave[i] - wave[(i - 1) % 16])))
        wave = np.roll(wave, -rotation)
        measured = abs(np.fft.rfft(wave)[1:8]); measured /= np.linalg.norm(measured)
        result[register] = dict(waveform=wave.tolist(), referenceNotes=[n['midi'] for n in chosen],
                                targetAmplitudes=raw.round(8).tolist(), softenedTargetAmplitudes=target.round(8).tolist(),
                                quantizedAmplitudes=measured.round(8).tolist(),
                                normalizedSpectralDistance=round(float(np.linalg.norm(measured - target)), 8))
    return dict(method='Median stereo-power partials; circular-mean phases; seven harmonics; '
                       f'H{cutoff:g} soft low-pass; deterministic integer spectral fit; zero-DC 16-point '
                       f'offset-binary four-bit samples, peak <= {peak}; quiet-start phase rotation', registers=result)


def measure_piano_transients(capture_folders):
    """Measure existing no-effects GM0 PCM captures, without redistributing PCM.

    Reproduce the input with render-fluid-violin.mjs --profile piano --program 0
    --notes 49,...,82 --gate 4 --tail 1.2 and the pinned SF2/renderer. Each folder
    contains its original capture.json and stereo 48 kHz signed-16-bit WAVs.
    """
    import numpy as np
    import wave
    rows, captures = [], []
    for folder in (Path(folder).resolve() for folder in capture_folders):
        capture = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
        if capture['program'] != 0 or capture['renderer']['effectsEnabled']:
            raise ValueError('Expected original GM0 piano with effects disabled')
        if capture['velocity'] != 100 or capture['gateSeconds'] != 4 or capture['tailSeconds'] != 1.2:
            raise ValueError('Expected velocity 100, four-second gate and 1.2-second tail')
        if capture['soundfont']['sha256'] != '74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0':
            raise ValueError('Unexpected SoundFont version')
        if capture['renderer']['sourceSha256'] != 'd7d74edf4056b1be835cfd717c8cfb579440ee5c741d087d684b84041d861035':
            raise ValueError('Unexpected renderer version')
        captures.append(capture)
        for note in capture['notes']:
            path = folder / note['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != note['sha256']:
                raise ValueError(f'PCM hash mismatch: {path}')
            with wave.open(str(path)) as stream:
                sample_rate = stream.getframerate()
                if sample_rate != 48000 or stream.getnchannels() != 2 or stream.getsampwidth() != 2:
                    raise ValueError('Expected stereo 48 kHz signed-16-bit PCM')
                signal = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').reshape(-1, 2) / 32768.
            nominal = 440 * 2 ** ((note['midi'] - 69) / 12)
            count = round(.08 * sample_rate)
            times = np.arange(count) / sample_rate
            segment = signal[round(.26 * sample_rate):round(.26 * sample_rate) + count]
            weighted = (segment - segment.mean(axis=0)) * np.hanning(count)[:, None]
            frequencies = nominal * np.linspace(.985, 1.015, 121)
            coefficients = np.exp(-2j * np.pi * frequencies[:, None] * times) @ weighted
            f0 = frequencies[np.argmax(np.sum(abs(coefficients) ** 2, axis=1))]
            frames = []
            for age in (.02, .04, .06, .09, .12, .2, .3, .5):
                window_seconds = .04 if age <= .09 else .08
                count = round(window_seconds * sample_rate)
                times = np.arange(count) / sample_rate
                start = round((age - window_seconds / 2) * sample_rate)
                segment = signal[start:start + count]
                hann = np.hanning(count)
                weighted = (segment - segment.mean(axis=0)) * hann[:, None]
                partials = np.exp(-2j * np.pi * np.arange(1, 8)[:, None] * f0 * times) @ weighted * 2 / hann.sum()
                amplitude = np.sqrt(np.mean(abs(partials) ** 2, axis=1))
                channel = int(np.argmax(abs(partials[0])))
                phase = np.angle(partials[:, channel]) - np.arange(1, 8) * np.angle(partials[0, channel])
                frames.append(dict(ageSeconds=age, windowSeconds=window_seconds, f0Hz=float(f0),
                    fundamentalPeakAmplitude=float(amplitude[0]), amplitudes=(amplitude / np.linalg.norm(amplitude)).round(8).tolist(),
                    ratiosToFundamental=(amplitude / max(amplitude[0], 1e-9)).round(8).tolist(), relativePhases=phase.round(8).tolist()))
            envelope_times = np.arange(.005, .605, .01)
            rms = np.array([np.sqrt(np.mean(signal[round((age - .005) * sample_rate):round((age + .005) * sample_rate)] ** 2)) for age in envelope_times])
            rms /= max(rms)
            rows.append(dict(midi=note['midi'], sourcePcmSha256=note['sha256'], sourceFile=path.relative_to(ROOT).as_posix(),
                             frames=frames, rms=rms.round(6).tolist()))
    if sorted(n['midi'] for n in rows) != list(range(49, 83)):
        raise ValueError('Expected each MIDI note 49..82 exactly once')
    return dict(schema=1, soundfont=captures[0]['soundfont'], renderer=captures[0]['renderer'],
                program=0, preset=captures[0]['preset'], velocity=100, sampleRate=48000, effectsEnabled=False,
                method='40-ms Hann centered at20/40/60/90ms,80-ms at120/200/300/500ms; seven stereo-power partials. F0 searched ±1.5% on80ms sustain. 10-ms RMS. No effects or per-note normalization before analysis.',
                envelopeTimesSeconds=envelope_times.round(4).tolist(), notes=rows)


def fit_piano_transients(path, attempts=400, maximum_switch_delta=1):
    """Jointly fit measured piano attack/sustain with matching fundamental.

    Optional offline authoring only. Seeded integer search keeps zero DC and
    bounds every possible instantaneous table switch to one four-bit unit.
    The legacy piano F0 magnitudes anchor loudness across this bank revision.
    """
    import numpy as np
    if type(attempts) is not int or attempts < 1 or maximum_switch_delta != 1:
        raise ValueError('Expected positive search count and one-unit maximum switch')
    path = Path(path).resolve()
    raw = path.read_bytes()
    data = json.loads(raw)
    if data['program'] != 0 or data['soundfont']['sha256'] != '74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0':
        raise ValueError('Expected measured original FluidR3 GM0 piano')
    legacy = dict(low=[0,2,4,5,3,0,0,0,1,1,1,-2,-4,-5,-4,-2],
                  high=[1,3,3,4,5,6,3,1,0,-1,-2,-3,-5,-6,-6,-3])
    h, angle = np.arange(1, 8), np.arange(16) * 2 * np.pi / 16
    moves = np.array([np.eye(16, dtype=int)[i] - np.eye(16, dtype=int)[j]
                      for i in range(16) for j in range(16) if i != j])
    rng = np.random.default_rng(83120)
    result = {}
    for register in ('low', 'high'):
        notes = [n for n in data['notes'] if (n['midi'] < 62) == (register == 'low')]
        attack = np.median([f['ratiosToFundamental'] for n in notes for f in n['frames'] if f['ageSeconds'] in (.02,.04,.06)], axis=0)
        sustain = np.median([f['ratiosToFundamental'] for n in notes for f in n['frames'] if f['ageSeconds'] in (.12,.2,.3,.5)], axis=0)
        attack *= 1 / np.sqrt(1 + (h / 5.) ** 6)
        sustain *= 1 / np.sqrt(1 + (h / 4.) ** 6)
        attack /= attack[0]
        sustain /= sustain[0]
        targets = np.array([attack / np.linalg.norm(attack), sustain / np.linalg.norm(sustain)])
        old = np.array(legacy[register])
        f0_target = abs(np.fft.rfft(old)[1])

        def loss(pairs):
            coefficients = np.fft.rfft(pairs, axis=-1)
            amplitudes = abs(coefficients[..., 1:8])
            normalized = amplitudes / np.linalg.norm(amplitudes, axis=-1, keepdims=True)
            spectrum = np.sum((normalized - targets) ** 2, axis=(-1, -2))
            coherence = 12 * abs(coefficients[..., 0, 1] - coefficients[..., 1, 1]) ** 2 / f0_target ** 2
            amplitude = 1.5 * np.sum((abs(coefficients[..., 1]) / f0_target - 1) ** 2, axis=-1)
            delta = .0005 * np.mean((pairs[..., 0, :] - pairs[..., 1, :]) ** 2, axis=-1)
            nyquist = .08 * np.sum(abs(coefficients[..., 8]) ** 2, axis=-1) / f0_target ** 2
            return spectrum + coherence + amplitude + delta + nyquist

        best = None
        for _ in range(attempts):
            phase = rng.uniform(-np.pi, np.pi, 7)
            phase[0] = 0
            target_waves = np.array([np.sum((ratios * f0_target / 8)[:, None] * np.cos(h[:, None] * angle + phase[:, None]), axis=0) for ratios in (attack, sustain)])
            pair = np.clip(np.rint(target_waves), -7, 7).astype(int)
            for voice in range(2):
                while pair[voice].sum():
                    direction = -int(np.sign(pair[voice].sum()))
                    candidates = pair[voice][None, :] + np.eye(16, dtype=int) * direction
                    errors = np.sum((candidates - target_waves[voice]) ** 2, axis=-1)
                    errors[np.max(abs(candidates), axis=1) > 7] = np.inf
                    pair[voice] = candidates[np.argmin(errors)]
            if np.max(abs(pair[0] - pair[1])) > maximum_switch_delta:
                continue
            value = float(loss(pair))
            for _ in range(32):
                candidates = np.repeat(pair[None, :, :], len(moves) * 3, axis=0)
                candidates[:len(moves), 0, :] += moves
                candidates[len(moves):2 * len(moves), 1, :] += moves
                candidates[2 * len(moves):, 0, :] += moves
                candidates[2 * len(moves):, 1, :] += moves
                valid = (np.max(abs(candidates), axis=(-1, -2)) <= 7) & (np.max(abs(candidates[:, 0, :] - candidates[:, 1, :]), axis=1) <= maximum_switch_delta)
                scores = loss(candidates)
                scores[~valid] = np.inf
                index = np.argmin(scores)
                if scores[index] >= value - 1e-12:
                    break
                pair, value = candidates[index], float(scores[index])
            if best is None or value < best[0]:
                best = value, pair.copy()
        if best is None:
            raise ValueError('No bounded attack/sustain pair found')
        pair = best[1]
        rotation = min(range(16), key=lambda i: (abs(pair[0, i]) + abs(pair[1, i]), abs(pair[0, i] - pair[0, (i - 1) % 16])))
        pair = np.roll(pair, -rotation, axis=1)
        coefficients = np.fft.rfft(pair)
        amplitudes = abs(coefficients[:, 1:8])
        normalized = amplitudes / np.linalg.norm(amplitudes, axis=1, keepdims=True)
        old_normalized = abs(np.fft.rfft(old)[1:8]) / np.linalg.norm(abs(np.fft.rfft(old)[1:8]))
        result[register] = dict(referenceMidi=[n['midi'] for n in notes], attackWave=pair[0].tolist(), sustainWave=pair[1].tolist(),
            attackTarget=targets[0].tolist(), sustainTarget=targets[1].tolist(),
            attackDistance=float(np.linalg.norm(normalized[0] - targets[0])), sustainDistance=float(np.linalg.norm(normalized[1] - targets[1])),
            fundamentalMagnitude=amplitudes[:, 0].tolist(), fundamentalLevelRatio=float(amplitudes[0, 0] / amplitudes[1, 0]),
            fundamentalPhaseDifferenceDegrees=float(np.angle(coefficients[0, 1] / coefficients[1, 1]) * 180 / np.pi),
            maximumWaveSwitchStep=int(max(abs(pair[0] - pair[1]))),
            oldSustainDistances=[float(np.linalg.norm(old_normalized - target)) for target in targets])
    comparison_times = [.1, .2, .3, .5]
    dynamics = {}
    for label, bottom, top, mask in (('low', 49, 61, 3), ('middle', 62, 74, 3), ('high', 75, 82, 0)):
        chosen = [n for n in data['notes'] if bottom <= n['midi'] <= top]
        measured = np.median([np.interp(comparison_times, data['envelopeTimesSeconds'], n['rms']) for n in chosen], axis=0)

        def synthesis_levels(base_mask):
            # The global envelope clock is independent of the score. Enumerate
            # all start phases, rather than promising one exact transition age.
            levels = []
            for phase in range(256):
                level, tick, samples = 15, phase, []
                for age in comparison_times:
                    while tick - phase < int(age * 37500 / 512):
                        tick += 1
                        effective = base_mask if level >= 10 else (base_mask << 1 | 1) if level >= 7 else (base_mask << 2 | 3)
                        if level and not tick & effective:
                            level -= 1
                    samples.append(level / 15)
                levels.append(samples)
            return np.median(levels, axis=0)

        dynamics[label] = dict(referenceMidi=[bottom, top], timesSeconds=comparison_times,
            measuredMedianNormalizedRms=measured.tolist(), selectedMask=mask,
            selectedEnvelopeMedian=synthesis_levels(mask).tolist(), oldMask3EnvelopeMedian=synthesis_levels(3).tolist())
    return dict(method=f'Joint zero-DC four-bit 16-point attack/sustain spectral magnitude fit; coherent fundamental; sample delta <= 1; attack H5/sustain H4 soft rolloff; seed 83120, {attempts} starts, 32 pairwise integer iterations.',
                measurement=path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                measurementSha256=hashlib.sha256(raw).hexdigest(), attackMinEnvelopeLevel=14,
                decayMaskByRegister=dict(thresholdMidi=75, thresholdDdsStep=2175, lowMask=3, highMask=0),
                envelopeComparison=dynamics,
                attackDurationRangeSeconds=dict(mask3=[512 / 37500 * 4, 512 / 37500 * 8], mask0=[512 / 37500, 512 / 37500 * 2]),
                limitations=['Two pitch-register waves and two temporal stages approximate 34 sampled notes.',
                    'Four-bit 16-point periodic tables preserve only seven harmonics; no hammer noise, inharmonic partials, stereo image or velocity layers.',
                    'Spectral fit uses magnitudes and a coherent attack/sustain fundamental, not the phase of every source partial.',
                    'The upper-note attack switches earlier because its decay clock is faster; no sample-by-sample crossfade.',
                    'Maximum one-unit table change bounds only the waveform-selection discontinuity; envelope quantization remains separate.'],
                registers=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ROLES:
        parser.add_argument('--' + role, default='off', help='Instrument ID (default: off)')
    parser.add_argument('--percussion', help='off or natural-kit; separate noise generator, no EEPROM')
    parser.add_argument('--output', type=Path, help='Write selected 64-byte EEPROM; no file is written by default')
    parser.add_argument('--describe', action='store_true', help='Print resolved build-time assignments')
    parser.add_argument('--verify-sources', action='store_true')
    parser.add_argument('--fit-measurement', type=Path, help='Print an optional NumPy spectral fit as JSON')
    parser.add_argument('--fit-piano-transients', type=Path, help='Print an optional jointly aligned piano attack/sustain fit')
    parser.add_argument('--measure-piano-captures', nargs='+', type=Path, help='Measure pinned GM0 stereo capture folders (NumPy authoring only)')
    args = parser.parse_args()
    if args.measure_piano_captures:
        print(json.dumps(measure_piano_transients(args.measure_piano_captures), indent=2))
        return
    if args.fit_piano_transients:
        print(json.dumps(fit_piano_transients(args.fit_piano_transients), indent=2))
        return
    if args.fit_measurement:
        print(json.dumps(fit_measurements(args.fit_measurement), indent=2))
        return
    bank = load_bank()
    if args.verify_sources:
        verify_sources(bank)
    assignments = {role: getattr(args, role) for role in ROLES}
    if args.percussion:
        assignments['percussion'] = args.percussion
    data = build_eeprom(assignments, bank)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
    if args.describe or not args.output:
        print(json.dumps(describe_assignments(assignments, bank), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
