"""Arrange retained musical-event JSON for the mono UM88 engine; no ROM import.

This is a bounded wavetable arranger, not a complete General MIDI renderer.
Original events stay unchanged. Every voice steal, unsupported message and
time quantization is reported separately from the compact playback source.
"""
from collections import Counter, defaultdict, deque
from fractions import Fraction
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
CONTROL_HZ = Fraction(18750, 256)


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bank_tools = module('um_arranger_bank', 'instrument-bank.py')
event_tools = module('um_arranger_events', 'midi-events.py')


def nearest(value):
    """Nonnegative exact fraction, ties toward the later control frame."""
    return (2*value.numerator+value.denominator)//(2*value.denominator)


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name}: expected integer {low}..{high}')
    return value


def arrange(document, settings, bank=None):
    bank = bank or bank_tools.load_bank()
    if not isinstance(document, dict) or not isinstance(settings, dict):
        raise ValueError('Events and arrangement must be JSON objects')
    if document.get('schema') != 'micromusic-midi-events' or document.get('version') != 1:
        raise ValueError('Expected micromusic-midi-events v1')
    ppqn = integer(document['ppqn'], 1, 32767, 'ppqn')
    allowed = {'schema', 'version', 'name', 'title', 'voices', 'tracks', 'instruments',
               'programs', 'overflow', 'phaseReset', 'waveSplitMidi', 'gainShift',
               'percussion', 'bendRangeSemitones'}
    if set(settings)-allowed:
        raise ValueError(f'Unknown arrangement settings: {sorted(set(settings)-allowed)}')
    if settings.get('schema') != 'micromusic-um88-arrangement' or settings.get('version') != 1:
        raise ValueError('Expected micromusic-um88-arrangement v1')
    if not isinstance(settings.get('name'), str) or not re.fullmatch('[a-z0-9-]+', settings['name']):
        raise ValueError('name must contain lowercase letters, digits and hyphens')
    limit = integer(settings.get('voices', 8), 1, 8, 'voices')
    policy = settings.get('overflow', 'error')
    if policy not in ('error', 'steal-quietest'):
        raise ValueError('overflow must be error or steal-quietest')
    phase_reset = settings.get('phaseReset', True)
    if type(phase_reset) is not bool:
        raise ValueError('phaseReset must be boolean')
    split = integer(settings.get('waveSplitMidi', 62), 0, 127, 'waveSplitMidi')
    bend_range = settings.get('bendRangeSemitones', 2)
    if type(bend_range) not in (int, float) or not math.isfinite(bend_range) or not 0 <= bend_range <= 24:
        raise ValueError('bendRangeSemitones must be 0..24')
    percussion = settings.get('percussion', False)
    if type(percussion) is not bool:
        raise ValueError('percussion must be boolean')
    rows = []
    track_ids = set()
    for track in document['tracks']:
        track_id = integer(track['index'], 0, 65535, 'track index')
        if track_id in track_ids:
            raise ValueError('Duplicate track index')
        track_ids.add(track_id)
        previous = 0
        for order, event in enumerate(track['events']):
            tick = integer(event['tick'], previous, 0x7fffffff, 'ordered event tick')
            previous = tick
            rows.append((tick, track_id, order, event))
    requested_tracks = settings.get('tracks', sorted(track_ids))
    if not isinstance(requested_tracks, list):raise ValueError('tracks must be a list')
    selected = set(requested_tracks)
    if not selected or not selected <= track_ids or any(type(t) is not int for t in selected):
        raise ValueError('tracks must select existing track indices')
    rows.sort(key=lambda row: row[:3])
    timeline = defaultdict(list)
    tempo = 500000
    previous = 0
    seconds = Fraction(0)
    max_error = Fraction(0)
    tempo_map = []
    for tick, track, order, event in rows:
        seconds += Fraction((tick-previous)*tempo, ppqn*1000000)
        previous = tick
        frame = nearest(seconds*CONTROL_HZ)
        max_error = max(max_error, abs(Fraction(frame)/CONTROL_HZ-seconds))
        if frame > 65530:
            raise ValueError('Source exceeds the UM88 v1 loop duration')
        timeline[frame].append((track, order, event))
        if event['type'] == 'tempo':
            tempo = integer(event['microsecondsPerQuarter'], 1, 0xffffff, 'tempo')
            tempo_map.append(dict(sourceTick=tick, controlTick=frame, microsecondsPerQuarter=tempo))
    end_frame = max(timeline, default=0)
    source_seconds = float(seconds)
    overrides = settings.get('instruments', {})
    programs = settings.get('programs', {})
    if not isinstance(overrides, dict) or not isinstance(programs, dict):
        raise ValueError('instruments and programs must be objects')
    for key in overrides:
        if not key.isdecimal() or int(key) not in track_ids:
            raise ValueError('Instrument overrides use existing track indices as keys')
    for key in programs:
        if not key.isdecimal() or not 0 <= int(key) <= 127:
            raise ValueError('Program overrides use zero-based GM program numbers')
    assignments = {}

    def resolve(track, program):
        value = overrides.get(str(track), programs.get(str(program)))
        if value is None:
            matches = [name for name, p in bank['instruments'].items() if p['gmProgram'] == program]
            if not matches:
                raise ValueError(f'GM program {program} has no bank instrument; assign track {track} explicitly')
            value = matches[0]
        if isinstance(value, str):
            value = {'instrument': value}
        if not isinstance(value, dict) or set(value)-{'instrument', 'level', 'envelope', 'transient'}:
            raise ValueError('Instrument assignment needs instrument, optional level/envelope/transient')
        name = value.get('instrument')
        if name not in bank['instruments'] or name == 'off':
            raise ValueError(f'Unsupported tonal instrument {name!r}')
        profile = copy.deepcopy(bank['instruments'][name])
        envelope = profile['envelope']
        changes = value.get('envelope', {})
        if not isinstance(changes, dict) or set(changes)-{'attackStep', 'attackMask', 'decayMask', 'releaseStep', 'releaseMask'}:
            raise ValueError('Unsupported envelope override')
        envelope.update(changes)
        if 'decayMask' in changes:envelope.pop('decayMaskByRegister', None)
        for key in ('attackStep', 'releaseStep'):
            if key in envelope:integer(envelope[key], 1, 15, key)
        for key in ('attackMask', 'decayMask', 'releaseMask'):
            if key in envelope and (type(envelope[key]) is not int or envelope[key] not in (0, 1, 3, 7, 15)):
                raise ValueError(f'{key} must be 0, 1, 3, 7 or 15')
        level = integer(value.get('level', envelope['defaultLevel']), 0, 15, 'instrument level')
        transient = value.get('transient', True)
        if type(transient) is not bool:raise ValueError('transient must be boolean')
        if not transient:profile.pop('transient', None)
        key = json.dumps([name, level, profile], sort_keys=True)
        if key not in assignments:
            assignments[key] = dict(name=name, level=level, profile=profile)
        return key

    # Context zero is permanently silent, including every unused voice at LOOP.
    identity = [x for level in range(16) for x in (level, 0, 0)]
    models = [identity]
    contexts = [[0, 0, 0, 128]]
    bank_pairs = []
    transient_pair = None
    used_instruments = {}

    def pair_for(assignment):
        nonlocal transient_pair
        profile = assignment['profile']
        pair = b''.join(bank_tools.pack_wave(profile['waves'][r]) for r in ('low', 'high'))
        if pair not in bank_pairs:bank_pairs.append(pair)
        if 'transient' in profile:
            attack = b''.join(bank_tools.pack_wave(profile['transient']['waves'][r]) for r in ('low', 'high'))
            if transient_pair is not None and attack != transient_pair:
                raise ValueError('UM88 v1 has one shared attack pair; disable one transient explicitly')
            transient_pair = attack
        if len(bank_pairs) > (3 if transient_pair is not None else 4):
            raise ValueError('Instrument waves exceed the 64-byte UM88 v1 bank; use fewer timbres')
        return bank_pairs.index(pair)*16

    def envelope_rows(v, released, cap):
        assignment = assignments[v['assignment']]
        profile = assignment['profile'];env = profile['envelope']
        model = env['model'];rows = []
        if released:
            step = env.get('releaseStep', 1);mask = env.get('releaseMask', 0)
        elif model in ('piano', 'pluck'):
            step = 1;mask = env.get('decayMask', 3 if model == 'piano' else 1)
            register = env.get('decayMaskByRegister')
            if register:
                mask = register['highMask' if v['pitch'] >= register['thresholdMidi'] else 'lowMask']
        else:
            step = env.get('attackStep', 4);mask = env.get('attackMask', 0)
        phases = sum(1 << p for p in range(16) if (p & mask) == 0)
        for level in range(16):
            new = max(0, level-step) if released or model in ('piano', 'pluck') else min(cap, level+step)
            rows.extend((new, phases & 255, phases >> 8))
        return rows

    def context(v, released=False):
        assignment = assignments[v['assignment']];profile = assignment['profile']
        rows = envelope_rows(v, released, v['cap'])
        if rows not in models:models.append(rows)
        wave = pair_for(assignment)+(8 if v['pitch'] >= split else 0)
        gain = 64 if 'transient' in profile else 0
        row = [models.index(rows), wave, gain, 128]
        if row not in contexts:contexts.append(row)
        used_instruments[v['assignment']] = assignment
        return contexts.index(row)

    channels = [dict(program=0, volume=127, expression=127, pedal=False, bend=8192) for _ in range(16)]
    voices = [dict(identity=None, level=0, rawLevel=0, context=0, pitch=None, released=True, sustained=False) for _ in range(limit)]
    waiting_notes = defaultdict(deque)
    report = dict(voiceSteals=[], ignoredEvents=dict(), omittedNotes=[], percussionReplacements=[],
                  forcedReleases=[], collapsedNotes=[], quantization=dict(controlHz=float(CONTROL_HZ), rule='nearest; ties later',
                  maximumErrorSeconds=float(max_error)), tempoMap=tempo_map, noteAttacks=0, drumAttacks=0)
    ignored = Counter();next_identity = 0;used_count = 1;note_origins = {}
    commands = [];frames = [];pitch_palette = [None];pending = []
    drum = None;previous_drum = 0
    peak_bounds = [[0, 0] for _ in range(8)]

    def emit(op, *args):pending.extend((op, *args))

    def set_level(index, level):
        if voices[index]['level'] != level:
            voices[index]['level'] = level;emit(128+(index<<4)+level)

    def set_context(index, released=False):
        value = context(voices[index], released)
        if voices[index]['context'] != value:
            voices[index]['context'] = value;emit(64+index, value)

    def pitch_for(v):
        result = v['note']+(channels[v['channel']]['bend']-8192)*bend_range/8192
        if not 0 <= result <= 127:raise ValueError('Pitch bend leaves the UM88 MIDI pitch range')
        return round(result, 9)

    def set_pitch(index):
        v = voices[index];value = pitch_for(v)
        if v['pitch'] != value:
            v['pitch'] = value
            if value not in pitch_palette:pitch_palette.append(value)
            if len(pitch_palette) > 256:raise ValueError('Pitch automation exceeds the 256-entry palette')
            emit(72+index, pitch_palette.index(value))

    def cap_for(v):
        ch = channels[v['channel']]
        return nearest(Fraction(v['baseCap']*ch['volume']*ch['expression'], 127**2))

    def release(index, immediate=False):
        v = voices[index]
        if immediate:
            set_level(index, 0);v['rawLevel'] = 0;v['identity'] = None;v['released'] = True;v['sustained'] = False
            emit(64+index, 0);v['context'] = 0
        elif channels[v['channel']]['pedal']:
            v['sustained'] = True
        else:
            v['sustained'] = False;v['released'] = True;set_context(index, True)

    def note_off(ch, note):
        queue = waiting_notes[(ch, note)]
        if queue:
            identity = queue.popleft()
            if note_origins[identity]['controlTick'] == frame:
                report['collapsedNotes'].append(dict(identity=identity, **note_origins[identity]))
            for index, v in enumerate(voices):
                if v['identity'] == identity:release(index);break

    for frame in range(65536):
        pending = []
        if frame == 0:
            for index in range(limit):emit(64+index, 0)
        else:
            for v in voices:
                row = models[contexts[v['context']][0]][v['level']*3:v['level']*3+3]
                if (row[1] | row[2]<<8) & (1 << (frame & 15)):v['level'] = row[0]
                if v['identity'] is not None:
                    rows = envelope_rows(v, v['released'], v['baseCap'])
                    row = rows[v['rawLevel']*3:v['rawLevel']*3+3]
                    if (row[1] | row[2]<<8) & (1 << (frame & 15)):v['rawLevel'] = row[0]
        for track, order, event in timeline.get(frame, []):
            kind = event['type']
            if kind in ('tempo', 'endOfTrack', 'text', 'meta', 'timeSignature'):continue
            if 'channel' not in event:
                ignored[kind] += 1;continue
            ch = integer(event['channel'], 0, 15, 'channel');channel = channels[ch]
            if kind == 'programChange':
                channel['program'] = integer(event['program'], 0, 127, 'program');continue
            if kind == 'controlChange':
                cc = integer(event['controller'], 0, 127, 'controller')
                value = integer(event['value'], 0, 127, 'controller value')
                if cc in (7, 11):
                    channel['volume' if cc == 7 else 'expression'] = value
                    for index, v in enumerate(voices):
                        if v['identity'] is not None and v['channel'] == ch:
                            v['cap'] = cap_for(v)
                            set_context(index, v['released'])
                elif cc == 64:
                    was = channel['pedal'];channel['pedal'] = value >= 64
                    if was and not channel['pedal']:
                        for index, v in enumerate(voices):
                            if v['identity'] is not None and v['channel'] == ch and v['sustained']:release(index)
                elif cc in (120, 123):
                    for index, v in enumerate(voices):
                        if v['identity'] is not None and v['channel'] == ch:release(index, cc == 120)
                    waiting_notes.update({key:deque() for key in list(waiting_notes) if key[0] == ch})
                else:ignored[f'CC{cc}'] += 1
                continue
            if kind == 'pitchBend':
                channel['bend'] = integer(event['value'], 0, 16383, 'pitch bend')
                for index, v in enumerate(voices):
                    if v['identity'] is not None and v['channel'] == ch:
                        set_pitch(index);set_context(index, v['released'])
                continue
            if kind not in ('noteOn', 'noteOff'):
                ignored[kind] += 1;continue
            note = integer(event['note'], 0, 127, 'note');velocity = integer(event['velocity'], 0, 127, 'velocity')
            if track not in selected:
                if kind == 'noteOn' and velocity:report['omittedNotes'].append(dict(track=track, note=note, sourceTick=event['tick'], reason='unselected track'))
                continue
            if ch == 9:
                if kind == 'noteOn' and velocity:
                    if not percussion:
                        report['omittedNotes'].append(dict(track=track, note=note, sourceTick=event['tick'], reason='percussion disabled'));continue
                    drum_kind = {35:0, 36:0, 38:2, 40:2, 42:1, 44:1, 46:1}.get(note)
                    if drum_kind is None:
                        raise ValueError(f'Unsupported percussion note {note}; select a track or disable percussion explicitly')
                    if drum is not None:report['percussionReplacements'].append(dict(controlTick=frame, oldNote=drum['note'], newNote=note))
                    drum = dict(kind=drum_kind, start=frame, duration=(10, 3, 7)[drum_kind], note=note, attenuation=2 if velocity >= 64 else 3)
                    report['drumAttacks'] += 1
                    emit(97, 0);emit(98, 1)
                continue
            if kind == 'noteOff' or not velocity:
                note_off(ch, note);continue
            assignment = resolve(track, channel['program']);next_identity += 1
            report['noteAttacks'] += 1
            candidates = [i for i, v in enumerate(voices) if v['identity'] is None or v['released'] and v['rawLevel'] == 0]
            if candidates:index = candidates[0]
            else:
                index = min(range(limit), key=lambda i:(not voices[i]['released'], voices[i]['level'], voices[i]['identity']))
                old = voices[index]
                if policy == 'error':
                    raise ValueError(f'Polyphony exceeds {limit} voices at control tick {frame}; choose more voices or explicit steal-quietest')
                report['voiceSteals'].append(dict(controlTick=frame, identity=old['identity'], note=old['note'], track=old['track'], releaseTail=old['released']))
            used_count = max(used_count, index+1)
            v = dict(identity=next_identity, track=track, channel=ch, note=note, velocity=velocity,
                     assignment=assignment, level=voices[index]['level'], context=voices[index]['context'], pitch=voices[index]['pitch'],
                     baseCap=nearest(Fraction(assignments[assignment]['level']*velocity,127)), released=False, sustained=False)
            voices[index] = v;v['cap'] = cap_for(v)
            waiting_notes[(ch, note)].append(next_identity)
            note_origins[next_identity] = dict(track=track, channel=ch, note=note, sourceTick=event['tick'], controlTick=frame)
            set_pitch(index);set_context(index)
            model = assignments[assignment]['profile']['envelope']['model']
            v['rawLevel'] = v['baseCap'] if model in ('piano', 'pluck') else min(v['baseCap'], assignments[assignment]['profile']['envelope'].get('attackStep', 4))
            if phase_reset:emit(80+index)
        if frame == end_frame:
            for channel in channels:channel['pedal'] = False
            for index, v in enumerate(voices):
                if v['identity'] is not None and not v['released']:
                    report['forcedReleases'].append(dict(identity=v['identity'], controlTick=frame));release(index)
        if drum is not None:
            age = frame-drum['start']
            if age >= drum['duration']:drum = None
        drum_mode = 0 if drum is None else 128 | drum['kind'] | (min(3, drum['attenuation']+(frame-drum['start'])*2//drum['duration']) << 2)
        if drum_mode != previous_drum:emit(96, drum_mode);previous_drum = drum_mode
        for index, v in enumerate(voices):
            if v['identity'] is not None:
                ch = channels[v['channel']]
                set_level(index, nearest(Fraction(v['rawLevel']*ch['volume']*ch['expression'],127**2)))
        # Bound all possible phase alignments, instead of attenuating according
        # to the configured voice limit when most voices are quiet.
        extrema = []
        for v in voices:
            if not v['level']:continue
            profile = assignments[v['assignment']]['profile']
            waveform = profile.get('transient', profile)['waves'] if v['level'] >= 14 else profile['waves']
            wave = waveform['high' if v['pitch'] >= split else 'low']
            extrema.append((min(wave)*v['level'], max(wave)*v['level']))
        drum_min,drum_max = (-16 >> ((drum_mode>>2)&3), 16 >> ((drum_mode>>2)&3)) if drum_mode else (0,0)
        for shift, bounds in enumerate(peak_bounds):
            bounds[0] = min(bounds[0], sum(low >> shift for low,high in extrema)+drum_min)
            bounds[1] = max(bounds[1], sum(high >> shift for low,high in extrema)+drum_max)
        # Retain frame boundaries here; the second pass joins waits and removes
        # unused trailing voices before the common binary grammar is applied.
        frames.append(pending)
        if frame >= end_frame+2 and drum is None and all(v['rawLevel'] == 0 for v in voices):break
    else:raise ValueError('Release tails exceed the UM88 v1 duration')
    if len(frames) > 65535:raise ValueError('Release tails exceed the UM88 v1 duration')
    if report['noteAttacks']+report['drumAttacks'] == 0:raise ValueError('No selected musical notes')
    shift = settings.get('gainShift', next(i for i,(low,high) in enumerate(peak_bounds) if low >= -128 and high <= 127))
    integer(shift, 0, 7, 'gainShift')
    for row in contexts:row[2] |= shift
    # The first frame must initialize contexts even on the second song loop.
    frames[0] = [x for i in range(used_count) for x in (64+i, 0)]+frames[0][limit*2:]
    wait = 0
    for ops in frames:
        if ops:
            while wait:amount = min(wait, 63);commands.append(amount);wait -= amount
            commands.extend(ops)
        wait += 1
    while wait:amount = min(wait, 63);commands.append(amount);wait -= amount
    commands.append(0)
    waves = b''.join(bank_pairs)
    if transient_pair is not None:waves = waves.ljust(48, bytes([136]))+transient_pair
    waves = waves.ljust(64, bytes([136]))
    score = dict(schema='micromusic-um88-score', version=1, name=settings['name'],
                 title=settings.get('title', settings['name']), voices=used_count, channels=1,
                 waves=list(waves), contexts=contexts, envelopes=models, pitches=pitch_palette,
                 commands=commands, controlTicks=len(frames), groupGain=False,
                 normalizer=[], normalizerMinimum=0, masterShift=0,
                 source=copy.deepcopy(document.get('source', {})))
    report.update(schema='micromusic-um88-arrangement-report', version=1, channels=1,
                  sourceSeconds=source_seconds, playbackSeconds=float(Fraction(len(frames))/CONTROL_HZ),
                  voices=used_count, voiceLimit=limit, gainShift=shift, sourceTracks=sorted(selected),
                  conservativePwmMixRange=peak_bounds[shift],
                  ignoredEvents=dict(sorted(ignored.items())), wavePairs=len(bank_pairs),
                  instrumentAssignments=[dict(instrument=a['name'], level=a['level'], envelope=a['profile']['envelope'],
                                              source=a['profile']['source']) for a in used_instruments.values()],
                  controls='CC7 volume, CC11 expression, CC64 pedal, CC120 sound off, CC123 notes off; fixed-range pitch bend',
                  limitations=['Mono output; CC10 pan is reported and not rendered',
                               'One procedural percussion generator; a new hit replaces its previous sound',
                               '7-bit velocity/volume/expression are quantized to 16 envelope levels'])
    return score, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', type=Path);parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.events.suffix.lower() != '.json':parser.error('Import external MIDI with tools/midi-events.py first')
    try:
        score, report = arrange(event_tools.load(args.events), json.loads(args.config.read_text(encoding='utf-8-sig')))
        module('um_arranger_validator', 'build-universal-music.py').validate_score(score)
        args.output.mkdir(parents=True, exist_ok=False)
        for name, data in [('score.json', score), ('arrangement-report.json', report)]:
            (args.output/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    except (ValueError, KeyError, TypeError, OSError) as error:parser.exit(1, f'Arrangement failed: {error}\n')
    print(f"{score['name']}: {score['voices']} voices, {report['noteAttacks']} attacks, {score['controlTicks']} ticks")


if __name__ == '__main__':main()
