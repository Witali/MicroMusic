"""Losslessly pack the retained guitar parts into a small Flash-readable grammar.

Every pitch, part, channel, Note On velocity, Note Off velocity, onset, gate
and within-chord order survives. Chords are shared ordered pitch dictionaries;
rest/gate pairs are shared rhythms. Repeated adjacent symbols become bounded
Re-Pair rules. Decoding needs a current-symbol register and at most eight
pending-symbol bytes per part, no history window.
This packs a score; it does not claim the score and a synthesizer fit 1 KB.
"""
from pathlib import Path
from collections import Counter, defaultdict, deque
import argparse
import hashlib
import importlib.util
import json
import math

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b'MNC1'
MAX_DEPTH = 8


def module():
    spec = importlib.util.spec_from_file_location('lossless_events', ROOT / 'tools/midi-events.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def vlq(value):
    if type(value) is not int or value < 0:
        raise ValueError('VLQ needs a nonnegative integer')
    out = [value & 127]
    while value >> 7:
        value >>= 7
        out.append(128 | (value & 127))
    return bytes(reversed(out))


class Reader:
    def __init__(self, raw):
        self.raw, self.at = bytes(raw), 0

    def byte(self):
        if self.at >= len(self.raw):
            raise ValueError('Truncated score')
        value = self.raw[self.at]
        self.at += 1
        return value

    def integer(self):
        result = 0
        for _ in range(5):
            value = self.byte()
            result = result * 128 + (value & 127)
            if value < 128:
                return result
        raise ValueError('Overlong VLQ')


def extract(document, start_tick=0, end_tick=None):
    """Pair original Note Ons/Offs without reducing or sorting chord pitches."""
    if start_tick < 0 or end_tick is not None and end_tick <= start_tick:
        raise ValueError('Selection must be a positive-length interval')
    parts = []
    for track in document['tracks']:
        active = defaultdict(deque)
        notes = []
        for order, event in enumerate(track['events']):
            if event['type'] not in ('noteOn', 'noteOff'):
                continue
            key = (event['channel'], event['note'])
            if event['type'] == 'noteOn' and event['velocity']:
                active[key].append((event['tick'], event['velocity'], order))
            elif active[key]:
                on, velocity, on_order = active[key].popleft()
                if start_tick <= on and (end_tick is None or on < end_tick):
                    notes.append(dict(channel=key[0], pitch=key[1], on=on-start_tick,
                                      off=event['tick']-start_tick, velocity=velocity,
                                      offVelocity=event['velocity'], onOrder=on_order, offOrder=order))
            else:
                raise ValueError('Unmatched Note Off')
        if any(active.values()):
            raise ValueError('Unmatched Note On; exact Note Off required')
        if not notes:
            continue
        notes.sort(key=lambda n:n['onOrder'])
        channels = {n['channel'] for n in notes}
        if len(channels) != 1:
            raise ValueError('Split channels into parts before packing')
        programs = {e['program'] for e in track['events']
                    if e['type'] == 'programChange' and e['channel'] in channels}
        if len(programs) > 1:
            raise ValueError('Program changes need a separate event stream')
        off_velocities = {n['offVelocity'] for n in notes}
        if len(off_velocities) != 1:
            raise ValueError('Varying Note Off velocities need a separate event stream')
        groups = []
        by_on = defaultdict(list)
        for n in notes:
            by_on[n['on']].append(n)
        end = 0
        for on, chord in sorted(by_on.items()):
            if on < end or len({n['off'] for n in chord}) != 1 or len({n['velocity'] for n in chord}) != 1:
                raise ValueError('A part must be a non-overlapping sequence of common-gate chords')
            if sorted(chord, key=lambda n:n['offOrder']) != chord:
                raise ValueError('Different Note On/Off chord order needs a separate event stream')
            end = chord[0]['off']
            groups.append(dict(on=on, off=end, velocity=chord[0]['velocity'], pitches=[n['pitch'] for n in chord]))
        parts.append(dict(index=track['index'], channel=next(iter(channels)),
                          program=next(iter(programs), 0), offVelocity=next(iter(off_velocities)), groups=groups))
    return parts


def records(parts):
    return [(part['index'], part['channel'], group['on'], group['off'], pitch,
             group['velocity'], part['offVelocity'])
            for part in parts for group in part['groups'] for pitch in group['pitches']]


def grammar(symbols, bases):
    """Deterministic bounded Re-Pair; no optimality claim."""
    symbols = list(symbols)
    rules, depths = [], [0] * bases
    while bases + len(rules) < 256:
        candidates = []
        for pair, approximate in Counter(zip(symbols, symbols[1:])).items():
            depth = 1 + max(depths[pair[0]], depths[pair[1]])
            if approximate < 3 or depth > MAX_DEPTH:
                continue
            count, at = 0, 0
            while at + 1 < len(symbols):
                if (symbols[at], symbols[at+1]) == pair:
                    count += 1
                    at += 2
                else:
                    at += 1
            if count > 2:
                candidates.append((2-count, pair, depth))
        if not candidates:
            break
        _, pair, depth = min(candidates)
        code = bases + len(rules)
        result, at = [], 0
        while at < len(symbols):
            if at+1 < len(symbols) and (symbols[at], symbols[at+1]) == pair:
                result.append(code)
                at += 2
            else:
                result.append(symbols[at])
                at += 1
        rules.append(pair)
        depths.append(depth)
        symbols = result
    return symbols, rules, max(depths, default=0)


def pack(parts, ppqn):
    if type(ppqn) is not int or ppqn <= 0 or not 1 <= len(parts) <= 16:
        raise ValueError('Invalid timing/part count')
    indices = set()
    unit = 0
    extent = 0
    for part in parts:
        if (part['index'] in indices or type(part['index']) is not int or part['index'] < 0
                or not 0 <= part['channel'] <= 15 or not 0 <= part['program'] <= 127
                or not 0 <= part['offVelocity'] <= 127 or not part['groups']):
            raise ValueError('Invalid part header')
        indices.add(part['index'])
        end = 0
        for group in part['groups']:
            if (type(group['on']) is not int or type(group['off']) is not int
                    or group['on'] < end or group['off'] <= group['on']
                    or not 1 <= group['velocity'] <= 127
                    or not 1 <= len(group['pitches']) <= 127
                    or any(type(p) is not int or not 0 <= p <= 127 for p in group['pitches'])):
                raise ValueError('Invalid or overlapping note chord')
            end = group['off']
            unit = math.gcd(unit, group['on'])
            unit = math.gcd(unit, group['off'])
            extent = max(extent, group['off'])
    if not unit or not parts:
        raise ValueError('No notes to pack')
    out = bytearray(MAGIC + vlq(ppqn) + vlq(unit) + vlq(extent//unit) + vlq(len(parts)))
    stats = []
    for part in parts:
        shapes, rhythms, velocities, bases, symbols = [], [], [], [], []
        def index(table, value):
            if value not in table:
                table.append(value)
            return table.index(value)
        end = 0
        for group in part['groups']:
            shape = index(shapes, group['pitches'])
            rhythm = index(rhythms, ((group['on']-end)//unit, (group['off']-group['on'])//unit))
            velocity = index(velocities, group['velocity'])
            symbols.append(index(bases, (shape, rhythm | velocity << 7)))
            end = group['off']
        if len(shapes)>255 or len(rhythms)>127 or len(velocities)>2 or len(bases)>255:
            raise ValueError('Palette exceeds this score format')
        encoded, rules, depth = grammar(symbols, len(bases))
        at = len(out)
        out.extend(vlq(part['index']) + bytes([part['channel'],part['program'],part['offVelocity'],len(shapes)]))
        for shape in shapes:
            out.extend(bytes([len(shape),*shape]))
        out.append(len(rhythms))
        for gap, gate in rhythms:
            out.extend(vlq(gap) + vlq(gate))
        out.extend(bytes([len(velocities),*velocities,len(bases)]))
        for base in bases:
            out.extend(bytes(base))
        out.append(len(rules))
        for rule in rules:
            out.extend(bytes(rule))
        out.extend(vlq(len(encoded)) + bytes(encoded))
        stats.append(dict(track=part['index'], notes=sum(len(g['pitches']) for g in part['groups']),
                          chordAttacks=len(symbols), shapes=len(shapes), rhythms=len(rhythms),
                          baseSymbols=len(bases), rules=len(rules), grammarDepth=depth,
                          playbackSymbols=len(encoded), bytes=len(out)-at))
    return bytes(out), stats


def unpack(raw):
    reader = Reader(raw)
    if bytes(reader.byte() for _ in range(4)) != MAGIC:
        raise ValueError('Wrong score magic/version')
    ppqn, unit, extent, count = [reader.integer() for _ in range(4)]
    if not ppqn or not unit or not extent or not 1 <= count <= 16:
        raise ValueError('Invalid timing/part count')
    parts = []
    for _ in range(count):
        part = dict(index=reader.integer(), channel=reader.byte(), program=reader.byte(), offVelocity=reader.byte())
        if (part['channel'] > 15 or part['program'] > 127 or part['offVelocity'] > 127
                or any(p['index'] == part['index'] for p in parts)):
            raise ValueError('Invalid part header')
        shapes = [[reader.byte() for _ in range(reader.byte())] for _ in range(reader.byte())]
        rhythms = [(reader.integer(),reader.integer()) for _ in range(reader.byte())]
        velocities = [reader.byte() for _ in range(reader.byte())]
        bases = [(reader.byte(),reader.byte()) for _ in range(reader.byte())]
        if (not shapes or any(not shape or len(shape) > 127 or any(p>127 for p in shape) for shape in shapes)
                or not 1 <= len(rhythms) <= 127 or any(not gate for _,gate in rhythms)
                or not 1 <= len(velocities) <= 2 or any(not 1 <= v <= 127 for v in velocities)
                or not bases or any(s >= len(shapes) or (rv & 127) >= len(rhythms)
                                       or (rv >> 7) >= len(velocities) for s,rv in bases)):
            raise ValueError('Invalid palette/reference')
        rules = []
        depths = [0]*len(bases)
        for _ in range(reader.byte()):
            rule = (reader.byte(),reader.byte())
            if max(rule) >= len(bases)+len(rules):
                raise ValueError('Forward/cyclic grammar reference')
            depth = 1+max(depths[rule[0]],depths[rule[1]])
            if depth > MAX_DEPTH:
                raise ValueError('Invalid grammar depth')
            rules.append(rule)
            depths.append(depth)
        if len(bases)+len(rules)>256:
            raise ValueError('Too many grammar symbols')
        groups, end = [], 0
        for _ in range(reader.integer()):
            pending = [(reader.byte(),0)]
            while pending:
                code, depth = pending.pop()
                if depth > MAX_DEPTH or code >= len(bases)+len(rules):
                    raise ValueError('Invalid grammar depth/reference')
                if code >= len(bases):
                    left,right = rules[code-len(bases)]
                    pending.extend([(right,depth+1),(left,depth+1)])
                    continue
                shape, rhythm_velocity = bases[code]
                try:
                    gap,gate = rhythms[rhythm_velocity & 127]
                    pitches = shapes[shape]
                    velocity = velocities[rhythm_velocity >> 7]
                except IndexError as error:
                    raise ValueError('Invalid palette reference') from error
                if not gate or not pitches or any(p>127 for p in pitches) or not 1<=velocity<=127:
                    raise ValueError('Invalid note chord')
                on = end + gap * unit
                end = on + gate * unit
                if end > extent*unit:
                    raise ValueError('Score extent exceeded')
                groups.append(dict(on=on,off=end,velocity=velocity,pitches=pitches))
        part['groups'] = groups
        if not groups:
            raise ValueError('Empty part')
        parts.append(part)
    if reader.at != len(reader.raw):
        raise ValueError('Trailing score data')
    return parts,ppqn


def build(source, start_beat=0, end_beat=None):
    events = module()
    document = events.load(source)
    ppqn = document['ppqn']
    parts = extract(document,start_beat*ppqn,None if end_beat is None else end_beat*ppqn)
    raw,stats = pack(parts,ppqn)
    decoded, decoded_ppqn = unpack(raw)
    if decoded_ppqn != ppqn or records(decoded) != records(parts):
        raise ValueError('Lossless verification failed')
    normalized = json.dumps(records(parts),separators=(',',':')).encode()
    timeline = sorted([(g['on'],len(g['pitches'])) for p in parts for g in p['groups']] +
                      [(g['off'],-len(g['pitches'])) for p in parts for g in p['groups']])
    active = peak = 0
    for _,change in timeline:
        active += change
        peak = max(peak,active)
    return dict(schema='micromusic-lossless-notes',version=1,codec='MNC1 bounded Re-Pair chord grammar',
                sourceSha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                sourceMidiSha256=document['source']['sha256'],startBeat=start_beat,endBeat=end_beat,
                selection='All Note On attacks within the selected interval; each retains its complete original Note Off, including tails beyond endBeat.',
                ppqn=ppqn,notes=len(records(parts)),parts=stats,peakPolyphony=peak,
                sourceTempoEvents=[dict(track=t['index'],tick=e['tick'],microsecondsPerQuarter=e['microsecondsPerQuarter'])
                                   for t in document['tracks'] for e in t['events'] if e['type']=='tempo'],
                packedBytes=len(raw),packedSha256=hashlib.sha256(raw).hexdigest(),
                decodedNotesSha256=hashlib.sha256(normalized).hexdigest(),verifiedLossless=True,
                decoderStackBytesPerPart=MAX_DEPTH,
                decoderStackNote='Current symbol in a register plus up to eight pending symbols per part; excludes cursors and synthesizer state.',
                firmwareFitsAttiny13A=None,
                limitation='Score size only. AVR synthesis/decoder code is additional; no playback or firmware-fit claim.',
                packedData=list(raw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--start-beat',type=int,default=0)
    parser.add_argument('--end-beat',type=int)
    args=parser.parse_args()
    result=build(args.source,args.start_beat,args.end_beat)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:result[k] for k in ('notes','packedBytes','peakPolyphony','verifiedLossless')}))


if __name__=='__main__':
    main()
