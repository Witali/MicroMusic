"""Compact measured percussion profiles, separate from the tonal EEPROM bank.

Selection and integer hit rendering require only Python's standard library.
The optional spectrum measurement imports NumPy. These profiles never edit an
AVR source file, existing instrument bank, or firmware when they are loaded.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / 'ATtiny13A/Music/instruments/percussion-profiles.json'


def _integer(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{label} must be an integer in {lo}..{hi}')
    return value


def load_bank(path=None):
    bank = json.loads(Path(path or BANK_PATH).read_text(encoding='utf-8'))
    return _validate_bank(bank)


def _validate_bank(bank):
    if bank.get('schema') != 1 or not isinstance(bank.get('profiles'), dict):
        raise ValueError('Unsupported percussion bank')
    if bank['timing'] != dict(cpuHz=9600000, synthesisHz=18750, pwmHz=37500, envelopeTickCycles=131072):
        raise ValueError('Profiles target the existing 9.6MHz interpolated-PWM engine')
    for name, profile in bank['profiles'].items():
        _integer(profile['gmNote'], 0, 127, name + ' GM note')
        if profile['gmBank'] != 128:
            raise ValueError('Expected the FluidR3 Standard percussion bank128')
        if profile['generator']['kind'] not in ('triangle', 'noise', 'noise+triangle'):
            raise ValueError('Unsupported compact drum generator')
        _integer(profile['gainShift'], 0, 3, 'gain shift')
        generator = profile['generator']
        if generator['kind'] != 'triangle':
            if generator['noiseMode'] not in ('centered', 'difference'):
                raise ValueError('Unsupported noise shaping')
            _integer(generator['noiseShift'], 0, 4, 'noise shift')
        if generator['kind'] != 'noise':
            _integer(generator['phaseStep'], 1, 255, 'phase step')
            _integer(generator['phaseStart'], 0, 255, 'phase start')
            _integer(generator['phaseOffset'], -255, 255, 'phase offset')
            _integer(generator['triangleShift'], 0, 4, 'triangle shift')
            _integer(generator['triangleBias'], 0, 127, 'triangle bias')
        envelope = profile['envelope']
        if envelope['decayShifts'] != [0, 1, 1, 2] or envelope['ticksPerStep'] != 2:
            raise ValueError('Expected the existing four-stage, shift-only drum decay')
        if envelope['firstStageTicks'] != [1, 2] or envelope['attackRampSamples'] != 0:
            raise ValueError('Expected documented global-clock decay and immediate legacy attack')
    if bank['noise'] != dict(bits=16, feedbackXor=45, nonzeroSeed=167, period=65535):
        raise ValueError('The existing long-period hi-hat LFSR must remain unchanged')
    for kit in bank['kits'].values():
        if set(kit) != {'kick', 'snare', 'hat'} or any(profile not in bank['profiles'] for profile in kit.values()):
            raise ValueError('A kit selects exactly three known profiles')
        if [bank['profiles'][kit[role]]['gmNote'] for role in ('kick', 'snare', 'hat')] != [35, 38, 42]:
            raise ValueError('The measured kit uses GM35/38/42')
    return bank


def verify_source(bank=None):
    bank = bank or load_bank()
    source = bank['source']
    data = (ROOT / source['measurement']).read_bytes()
    if hashlib.sha256(data).hexdigest() != source['measurementSha256']:
        raise ValueError('Retained FluidR3 percussion measurements changed')
    return True


def select_hit(name, attenuation_shift=0, bank=None):
    bank = bank or load_bank()
    if not isinstance(name, str) or name not in bank['profiles']:
        raise ValueError(f'Unknown percussion profile: {name!r}')
    _integer(attenuation_shift, 0, 3, 'attenuation shift')
    result = copy.deepcopy(bank['profiles'][name])
    result['id'] = name
    result['gainShift'] = min(3, result['gainShift'] + attenuation_shift)
    result['timing'] = copy.deepcopy(bank['timing'])
    result['noise'] = copy.deepcopy(bank['noise'])
    result['signedDutyRange'] = duty_range(result)
    return result


def select_kit(name='natural-kit', attenuation_shift=0, bank=None):
    bank = bank or load_bank()
    if not isinstance(name, str) or name not in bank['kits']:
        raise ValueError(f'Unknown percussion kit: {name!r}')
    return {role: select_hit(profile, attenuation_shift, bank) for role, profile in bank['kits'][name].items()}


def select_gm_note(note, kit='natural-kit', attenuation_shift=0, bank=None):
    _integer(note, 0, 127, 'GM note')
    for hit in select_kit(kit, attenuation_shift, bank).values():
        if hit['gmNote'] == note:
            return hit
    raise ValueError(f'GM{note} has no measured profile in this kit; no implicit drum substitution')


def lfsr_step(state):
    carry = state >> 15
    state = (state << 1) & 65535
    return state ^ (45 if carry else 0)


def triangle(phase, bias=61, shift=2):
    phase &= 255
    folded = 255 - phase if phase & 128 else phase
    return (folded - bias) >> shift


def noise_sample(state, mode, shift):
    low = state & 255
    first = (low >> 1) & 63
    return (first - (low & 63) if mode == 'difference' else first - 32) >> shift


def duty_range(hit):
    """Conservative exact bounds, including independent noise/tone phases."""
    generator = hit['generator']
    noise = [0] if generator['kind'] == 'triangle' else [noise_sample(i, generator['noiseMode'], generator['noiseShift']) for i in range(256)]
    tone = [0] if generator['kind'] == 'noise' else [triangle(i, generator['triangleBias'], generator['triangleShift']) for i in range(256)]
    return [(min(noise) + min(tone)) >> hit['gainShift'], (max(noise) + max(tone)) >> hit['gainShift']]


def _compile_settings(hits):
    kick, snare, hat = (hits[role]['generator'] for role in ('kick', 'snare', 'hat'))
    if kick['kind'] != 'triangle' or kick['phaseStep'] != 1 or kick['phaseStart'] != 168 or kick['phaseOffset'] != 0:
        raise ValueError('The compact kick requires existing R14, seed167, step1')
    if hat != dict(kind='noise', noiseMode='difference', noiseShift=2):
        raise ValueError('The working Lumiere hi-hat must remain unchanged')
    if snare['kind'] not in ('noise', 'noise+triangle') or snare['noiseMode'] != 'centered' or snare['noiseShift'] not in (1, 2):
        raise ValueError('The compact snare supports centered noise with one/two ASR')
    if snare['kind'] == 'noise+triangle' and (snare['phaseSource'] != 'existing PWM counter R15' or snare['phaseStep'] != 2 or snare['phaseStart'] != 1):
        raise ValueError('The snare body uses the existing R15 PWM phase, step2')
    if len({hit['gainShift'] for hit in hits.values()}) != 1:
        raise ValueError('Per-drum attenuation would need a different AVR branch layout')
    for hit in hits.values():
        if max(abs(v) for v in duty_range(hit)) > 32:
            raise ValueError('Drum level exceeds the safe signed mix budget')
    return kick, snare, next(iter(hits.values()))['gainShift']


def _render_region(hits):
    kick, snare, gain_shift = _compile_settings(hits)
    lines = ['render_drum:', '  /* Compact measured kit; parameters from percussion-bank.py. */',
        '  cpi r21, 4', '  brcc write_pwm', '  cpi r29, 2', '  brcs .L280', '  rjmp .L298',
        '.L280:', '  ldi r17, 1', '  add r14, r17', '.L28a:', '  mov r17, r14',
        '  sbrc r17, 7', '  com r17', f'  subi r17, {kick["triangleBias"]}']
    lines += ['  asr r17'] * kick['triangleShift']
    lines += ['  rjmp .L2ae', '.L298:', '  lds r27, 96', '  lsl r14', '  adc r27, r27',
        '  brcc .L2a0', '  ldi r17, 45', '  eor r14, r17', '.L2a0:', '  sts 96, r27',
        '  mov r17, r14', '  lsr r17', '  andi r17, 63', '  mov r27, r14', '  andi r27, 63',
        '  sbrc r29, 1', '  sub r17, r27', '  sbrs r29, 1', '  subi r17, 32',
        '  asr r17', '  sbrc r29, 1', '  asr r17']
    if snare['kind'] == 'noise+triangle' or snare['noiseShift'] == 2:
        lines += ['  sbrc r29, 1', '  rjmp .L2ae']
        lines += ['  asr r17'] * (snare['noiseShift'] - 1)
        if snare['kind'] == 'noise+triangle':
            lines += ['  mov r27, r15']
            if snare['phaseOffset']:
                lines += [f'  subi r27, {(-snare["phaseOffset"]) & 255}']
            lines += ['  sbrc r27, 7', '  com r27', f'  subi r27, {snare["triangleBias"]}']
            lines += ['  asr r27'] * snare['triangleShift']
            lines += ['  add r17, r27']
    lines += ['.L2ae:', '  sbrc r21, 0', '  asr r17', '  sbrc r21, 1', '  asr r17']
    lines += ['  asr r17'] * gain_shift
    lines += ['  add r26, r17']
    return '\n'.join(lines) + '\n'


def _instructions(source):
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return '\n'.join(line.strip() for line in source.splitlines() if line.strip())


def _baseline_hits(body_noise_shift=None):
    # Frozen templates accepted as compiler input, independent of edited bank
    # parameters. This prevents quietly overwriting an unfamiliar AVR routine.
    kick = dict(kind='triangle', phaseSource='per-hit R14', phaseStep=1, phaseStart=168,
                phaseOffset=0, triangleBias=61, triangleShift=2)
    snare = dict(kind='noise', noiseMode='centered', noiseShift=1)
    if body_noise_shift is not None:
        snare = dict(kind='noise+triangle', noiseMode='centered', noiseShift=body_noise_shift,
                     phaseSource='existing PWM counter R15', phaseStep=2, phaseStart=1,
                     phaseOffset=-64, triangleBias=61, triangleShift=2)
    return {'kick': dict(generator=kick, gainShift=0), 'snare': dict(generator=snare, gainShift=0),
            'hat': dict(generator=dict(kind='noise', noiseMode='difference', noiseShift=2), gainShift=0)}


def compile_source(source, kit='natural-kit', *, bank=None, attenuation_shift=0):
    """Return assembly with one validated drum region selected at build time.

    Supported input is the project's known legacy/full-body/soft-body routine,
    after build-instrument-engine.specialize() with percussion enabled. The
    existing seed167/LFSR0x002D and hi-hat arithmetic are fixed. Biases, shifts
    and body phase offset are compiled to immediates; no EEPROM/state is added.
    Unknown source layouts or unrepresentable profile changes fail closed.
    """
    if not isinstance(source, str) or source.count('render_drum:\n') != 1 or source.count('write_pwm:\n') != 1:
        raise ValueError('Expected one known render_drum -> write_pwm assembly region')
    bank = _validate_bank(bank) if bank is not None else load_bank()
    verify_source(bank)
    hits = select_kit(kit, attenuation_shift, bank)
    selected = _render_region(hits)
    start, end = source.index('render_drum:\n'), source.index('write_pwm:\n')
    if end <= start:
        raise ValueError('Invalid drum region marker order')
    known = {_instructions(_render_region(_baseline_hits(mode))) for mode in (None, 1, 2)}
    known.add(_instructions(selected))
    if _instructions(source[start:end]) not in known:
        raise ValueError('Unrecognized AVR drum routine; do not silently replace it')
    if 'drum_trigger:' in source:
        trigger = source.split('drum_trigger:', 1)[1].split('.L0ba:', 1)[0]
        if 'ldi r16, 167\n  mov r14, r16' not in trigger:
            raise ValueError('The selected kit requires the existing nonzero drum seed167')
    return source[:start] + selected + source[end:]


def render_hit(hit, first_stage_ticks=2, seconds=.3, initial_noise_high=0):
    """Render the exact integer arithmetic proposed for the foreground mixer.

    PWM's hardware carrier is not simulated. The return values are signed duty
    offsets at 18.75kHz; use interpolate() for the existing midpoint output.
    """
    _integer(first_stage_ticks, 1, 2, 'first-stage ticks')
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or not 0 < seconds <= 2:
        raise ValueError('Expected 0 < hit duration <= 2 seconds')
    _integer(initial_noise_high, 0, 255, 'initial noise high byte')
    timing, generator, envelope = hit['timing'], hit['generator'], hit['envelope']
    count = round(seconds * timing['synthesisHz'])
    samples = []
    # The actual trigger resets R14 to167 while the high LFSR byte survives.
    state = (initial_noise_high << 8) | hit['noise']['nonzeroSeed']
    stage, next_transition = 0, first_stage_ticks
    for i in range(count):
        if i * timing['cpuHz'] >= next_transition * timing['envelopeTickCycles'] * timing['synthesisHz']:
            stage += 1
            next_transition += envelope['ticksPerStep']
        if stage >= len(envelope['decayShifts']):
            samples.append(0)
            continue
        value = 0
        if generator['kind'] != 'triangle':
            state = lfsr_step(state)
            value = noise_sample(state, generator['noiseMode'], generator['noiseShift'])
        if generator['kind'] != 'noise':
            phase = generator['phaseStart'] + generator['phaseStep'] * i + generator['phaseOffset']
            value += triangle(phase, generator['triangleBias'], generator['triangleShift'])
        samples.append(value >> (envelope['decayShifts'][stage] + hit['gainShift']))
    return samples


def interpolate(samples):
    result = []
    for i, value in enumerate(samples):
        result.extend([value, (value + (samples[i + 1] if i + 1 < len(samples) else 0)) // 2])
    return result


def measure(bank=None):
    """Compare proposed arithmetic with the retained measured FluidR3 spectra."""
    import numpy as np
    bank = bank or load_bank()
    verify_source(bank)
    reference = json.loads((ROOT / bank['source']['measurement']).read_text(encoding='utf-8'))
    edges = np.array(reference['bandEdgesHz'])
    rate = bank['timing']['pwmHz']
    size = round(.032 * rate)
    hz = np.fft.rfftfreq(size, 1 / rate)
    results = {}
    for name in bank['profiles']:
        hit = select_hit(name, bank=bank)
        target = np.array(reference['references'][str(hit['gmNote'])]['bandPower'])
        candidates = []
        for first in (1, 2):
            for seed_high in (0, 113, 255):
                samples = np.array(interpolate(render_hit(hit, first, initial_noise_high=seed_high)))
                power = 0
                for age in (.005, .020, .035, .050):
                    segment = samples[round(age * rate):round(age * rate) + size]
                    segment = (segment - segment.mean()) * np.hanning(size)
                    power = power + abs(np.fft.rfft(segment)) ** 2
                bands = np.array([power[(hz >= lo) & (hz < hi)].sum() for lo, hi in zip(edges[:-1], edges[1:])])
                bands /= bands.sum()
                candidates.append(dict(firstStageTicks=first, initialNoiseHigh=seed_high,
                    spectralDistance=float(np.linalg.norm(np.sqrt(bands) - np.sqrt(target))),
                    bandPower=bands.tolist(), minimumDutyOffset=int(samples.min()), maximumDutyOffset=int(samples.max()),
                    silenceAfterMs=(first + 3 * 2) * bank['timing']['envelopeTickCycles'] / bank['timing']['cpuHz'] * 1000))
        results[name] = dict(gmNote=hit['gmNote'], referenceBandPower=target.tolist(), candidates=candidates)
    return dict(method='Existing integer synthesis at18.75kHz, exact floor-midpoint output37.5kHz; four32ms Hann PSDs at5/20/35/50ms; square-root band-power distance. Both global-clock decay phases and three starting high noise bytes checked.',
                profileBankSha256=hashlib.sha256(json.dumps(bank, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                sourceMeasurementSha256=bank['source']['measurementSha256'], bandEdgesHz=edges.tolist(), profiles=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', default='natural-kit')
    parser.add_argument('--attenuation-shift', type=int, default=0)
    parser.add_argument('--measure', action='store_true', help='Print measured spectral comparison (requires NumPy)')
    args = parser.parse_args()
    bank = load_bank()
    verify_source(bank)
    result = measure(bank) if args.measure else select_kit(args.kit, args.attenuation_shift, bank)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
