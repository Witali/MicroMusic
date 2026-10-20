"""Select compact, measured FluidR3 instruments for the ATtiny13A EEPROM.

No SoundFont or audio renderer is needed when building a firmware. NumPy is
only imported by fit_measurements(), the optional bank-authoring operation.
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
    if 'percussion' in assignments:
        if kit_name == 'off':
            result['percussion'] = dict(instrument='off', label='Выключены', level=0,
                                        enabled=False, notes=[])
        else:
            kit = bank['percussion'][kit_name]
            result['percussion'] = dict(instrument=kit_name, label=kit['label'],
                                        level=kit_level, enabled=kit_level > 0,
                                        notes=copy.deepcopy(kit['notes']),
                                        generator=kit['generator'], eepromBytes=0)
    return result


def pack_wave(wave):
    """Offset binary nibbles: first sample is the low nibble, silence is 8."""
    if len(wave) != 16 or any(type(v) is not int or not -8 <= v <= 7 for v in wave):
        raise ValueError('Expected 16 integer samples in -8..7')
    return bytes((wave[i] + 8) | ((wave[i + 1] + 8) << 4) for i in range(0, 16, 2))


def build_eeprom(assignments, bank=None):
    """Return all 64 physical EEPROM bytes for three assigned low/high pairs.

    The final 16 bytes are reserved and silent. This function never changes a
    firmware, an input profile, or a file on disk.
    """
    bank = bank or load_bank()
    roles = describe_assignments(assignments, bank)
    result = bytearray()
    for role in ROLES:
        profile = bank['instruments'][roles[role]['instrument']]
        result.extend(pack_wave(profile['waves']['low']))
        result.extend(pack_wave(profile['waves']['high']))
    result.extend(b'\x88' * 16)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ROLES:
        parser.add_argument('--' + role, default='off', help='Instrument ID (default: off)')
    parser.add_argument('--percussion', help='off or natural-kit; separate noise generator, no EEPROM')
    parser.add_argument('--output', type=Path, help='Write selected 64-byte EEPROM; no file is written by default')
    parser.add_argument('--describe', action='store_true', help='Print resolved build-time assignments')
    parser.add_argument('--verify-sources', action='store_true')
    parser.add_argument('--fit-measurement', type=Path, help='Print an optional NumPy spectral fit as JSON')
    args = parser.parse_args()
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
