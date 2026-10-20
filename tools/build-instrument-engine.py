"""Specialize the small AVR generator for build-time instrument assignments.

Unused oscillators, envelopes and percussion are removed from ordinary AVR
assembly. This module neither modifies canonical sources nor synthesizes audio
outside the MCU. specialize(score, describe_assignments(...)) returns source
and score metadata for the independent musical audit.
"""
from pathlib import Path
from functools import lru_cache
import importlib.util
import math

TEMPLATE = Path(__file__).with_name('avr-synth-template.S')
ROLES = ('lead', 'keys', 'pluck')
MODELS = {'bowed', 'piano', 'pluck', 'sustain', 'off'}


def between(text, start, end, replacement):
    """Replace a unique source region, retaining its end marker."""
    if text.count(start) != 1:
        raise ValueError(f'Expected one template marker: {start!r}')
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[:a] + replacement + text[b:]


def envelope(register, model, cap, name, attack_step=4, release_step=1, fast_lead_release=False):
    """Generate saturated attack, held/decaying sustain and safe release."""
    if model == 'off':
        return ''
    if model in ('piano', 'pluck'):
        return (f'  mov r16, r{register}\n  ldi r17, {3 if model == "piano" else 1}\n'
                f'  rcall update_envelope\n  mov r{register}, r16\n')
    if model not in ('bowed', 'sustain'):
        raise ValueError(f'Unknown envelope {model}')
    result = (f'  sbrs r{register}, 7\n  rjmp {name}_release\n  mov r16, r{register}\n'
              f'  subi r16, {256 - attack_step}\n  cpi r16, {129 + cap}\n  brcs {name}_attack\n'
              f'  ldi r16, {128 + cap}\n{name}_attack:\n  mov r{register}, r16\n'
              f'  rjmp {name}_done\n{name}_release:\n')
    if fast_lead_release:
        # Keep the historical bowed lead release; companions release linearly.
        result += (f'  tst r{register}\n  breq {name}_done\n  dec r{register}\n'
                   f'  sbrc r{register}, 3\n  dec r{register}\n')
    elif release_step == 1:
        result += f'  tst r{register}\n  breq {name}_done\n  dec r{register}\n'
    else:
        result += (f'  mov r16, r{register}\n  subi r16, {release_step}\n'
                   f'  brcc {name}_release_ready\n  clr r16\n{name}_release_ready:\n'
                   f'  mov r{register}, r16\n')
    return result + f'{name}_done:\n'


def _settings(roles):
    if not isinstance(roles, dict) or not all(role in roles for role in ROLES):
        raise ValueError('Resolved lead, keys and pluck assignments are required')
    result = {}
    for role in ROLES:
        entry = roles[role]
        model, cap = entry['envelope']['model'], entry['level']
        if model not in MODELS or type(cap) is not int or not 0 <= cap <= 15:
            raise ValueError(f'{role}: unsupported envelope or level')
        if model == 'off' or cap == 0:
            result[role] = dict(model='off', cap=0, attack=0, release=0, retrigger='off')
            continue
        attack = entry['envelope'].get('attackStep', 4) if model in ('bowed', 'sustain') else 0
        release = entry['envelope'].get('releaseStep', 2 if model == 'piano' else 1)
        if (model in ('bowed', 'sustain') and (type(attack) is not int or not 1 <= attack <= 15)) or type(release) is not int or not 1 <= release <= 15:
            raise ValueError(f'{role}: attack/release steps must be integers in 1..15')
        if model in ('piano', 'pluck') and release != (2 if model == 'piano' else 1):
            raise ValueError(f'{role}: shared {model} envelope has a fixed release step')
        retrigger = 'full' if model in ('piano', 'pluck') else 'half'
        requested = entry['envelope'].get('retrigger')
        if requested in ('peak', 'full'):
            retrigger = 'full'
        elif requested in ('half', 'half-current-level'):
            retrigger = 'half'
        elif requested is not None:
            raise ValueError(f'{role}: unsupported retrigger {requested!r}')
        result[role] = dict(model=model, cap=cap, attack=attack, release=release, retrigger=retrigger)
    return result


def _trigger(register, settings):
    if settings['model'] == 'off':
        return ''
    if settings['retrigger'] == 'full':
        return f'  ldi r16, {128 + settings["cap"]}\n'
    return f'  mov r16, r{register}\n  andi r16, 15\n  lsr r16\n  ori r16, 128\n'


@lru_cache(maxsize=1)
def _score_format():
    # Reuse the compiler's legacy root/octave mapping and pitch conversion;
    # avoid a second set of musical constants that could drift apart.
    spec = importlib.util.spec_from_file_location('instrument_engine_score_format', TEMPLATE.with_name('score-format.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def needs_rest_check(score, voice):
    """Keep a runtime zero-DDS guard unless all referenced notes prove nonzero.

    The compiler includes every chord in chord_pairs/chord_overrides, even an
    unplayed pattern. Unknown or incomplete score structures remain guarded.
    A numeric MIDI note 0 is pitched; None/R and a pitch rounded to DDS zero
    require the guard.
    """
    if voice not in (0, 1):
        raise ValueError('Companion voice index must be 0 or 1')
    try:
        pairs = list(score['chord_pairs'])
        for bars in score.get('chord_overrides', {}).values():
            pairs.extend(bars)
        if any(not isinstance(pair, (tuple, list)) or len(pair) != 2 for pair in pairs):
            return True
        chords = list(dict.fromkeys(chord for pair in pairs for chord in pair))
        if not chords:
            return True
        compiler = _score_format()
        for chord in chords:
            if chord in score.get('chord_notes', {}):
                pair = score['chord_notes'][chord]
                if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                    return True
                note = pair[voice]
                if isinstance(note, str):
                    note = compiler.midi(note)
            else:
                root = score.get('chord_roots', {}).get(chord, compiler.ROOTS.get(chord))
                if root is None:
                    return True
                note = root + (compiler.KEY_VOICE_OFFSETS['piano'] if voice == 0 else compiler.BASS_VOICE_OFFSETS['guitar'])
            if note is None or type(note) not in (int, float) or not math.isfinite(note):
                return True
            step = round(440 * 2 ** ((note - 69) / 12) * 65536 / compiler.SYNTHESIS_HZ)
            if not 0 < step <= 65535:
                return True
        return False
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return True


def specialize(score, roles):
    settings = _settings(roles)
    models = {role: settings[role]['model'] for role in ROLES}
    percussion = roles.get('percussion', {}).get('enabled', False)
    if type(percussion) is not bool:
        raise ValueError('Resolved percussion.enabled must be boolean')
    if percussion and score.get('beats_per_bar', 4) != 4:
        raise ValueError('The natural kit needs a meter-specific generator outside 4/4')
    text = TEMPLATE.read_text(encoding='utf-8')
    for role, register in (('lead', 1), ('keys', 19), ('pluck', 20)):
        s = settings[role]
        generated = envelope(register, s['model'], s['cap'], role + '_env',
                             s['attack'], s['release'], role == 'lead' and s['model'] == 'bowed')
        text = between(text, f'  /* BEGIN {role.upper()} ENVELOPE */\n',
                       f'  /* END {role.upper()} ENVELOPE */\n', generated)

    if not percussion:
        text = between(text, '  /* Percussion decays', '.L0a8:', '')
        text = between(text, 'grid_step:\n', '.L0ba:', 'grid_step:\n')
        text = between(text, 'render_drum:\n', 'write_pwm:', '')
        text = text.replace('  sts 96, r0\n', '').replace('  ldi r29, 7\n', '')
        text = text.replace('  ldi r16, 4\n  mov r21, r16\n', '')
        text = text.replace('  ldi r16, 167\n  mov r14, r16\n', '')
        text = text.replace('  sbrc r16, 3\n  ldi r21, 3\n', '')

    text = between(text, '  /* BEGIN LEAD TRIGGER */\n', 'lead_commit:',
                   _trigger(1, settings['lead']) if models['lead'] != 'off' else '  clr r16\n')
    # A zero frequency is an immediate companion rest; freezing a nonzero
    # wavetable value would introduce DC. Note-off commands retain frequency
    # and run the normal release instead.
    triggers = ''
    rest_checks = {role: needs_rest_check(score, voice) for voice, role in enumerate(('keys', 'pluck'))}
    for role, register, lo, hi in (('keys', 19, 8, 9), ('pluck', 20, 12, 13)):
        if models[role] == 'off':
            continue
        triggers += _trigger(register, settings[role]) + f'  mov r{register}, r16\n'
        if rest_checks[role]:
            triggers += (f'  mov r16, r{lo}\n  or r16, r{hi}\n  brne {role}_sounding\n'
                         f'  clr r{register}\n{role}_sounding:\n')
    text = between(text, '  /* BEGIN COMPANION TRIGGERS */\n', '  /* END COMPANION TRIGGERS */\n', triggers)
    text = text.replace('  clr r7\n', '').replace('  clr r11\n', '')

    if models['lead'] == 'off':
        text = between(text, '  /* BEGIN LEAD FREQUENCY */\n', 'next_section:', '  rjmp hold_sample\n')
        text = text.replace('  sbrc r16, 0\n  rcall release_lead\n', '')
        text = between(text, 'release_lead:\n', 'chord_event:', '')
    for role, register, bit in (('keys', 19, 1), ('pluck', 20, 2)):
        if models[role] == 'off':
            text = text.replace(f'  sbrc r16, {bit}\n  andi r{register}, 15\n', '')
    if models['keys'] == models['pluck'] == 'off':
        text = between(text, 'chord_event:\n', 'melodic_event:', 'chord_event:\n  rjmp read_event\n')
    elif models['pluck'] == 'off':
        text = text.replace('  lpm r12, Z+\n  lpm r13, Z+\n', '')

    for role in ROLES:
        if models[role] == 'off':
            text = between(text, f'  /* BEGIN {role.upper()} RENDER */\n',
                           f'  /* END {role.upper()} RENDER */\n', '')
    if all(model == 'off' for model in models.values()):
        text = between(text, 'render_tone:\n', 'render_sample:\n', '')
    if not any(model in ('piano', 'pluck') for model in models.values()):
        text = between(text, 'update_envelope:\n', 'reset:', '')

    metadata = dict(lead_envelope_model=models['lead'], accompaniment_envelope_model=models['keys'],
                    pluck_envelope_model=models['pluck'], percussion_enabled=percussion,
                    keys_rest_check=models['keys'] != 'off' and rest_checks['keys'],
                    pluck_rest_check=models['pluck'] != 'off' and rest_checks['pluck'])
    for role in ROLES:
        s = settings[role]
        metadata[role + '_max_level'] = s['cap']
        metadata[role + '_attack_step'] = s['attack']
        metadata[role + '_release_step'] = s['release']
        metadata[role + '_retrigger'] = s['retrigger']
        metadata[role + '_release_model'] = ('fast-above-8' if role == 'lead' and s['model'] == 'bowed' else
                                            'shared-decay' if s['model'] in ('piano', 'pluck') else 'linear')
    return text, metadata
