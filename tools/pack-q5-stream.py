"""Losslessly pack the retained head-Q5 teacher and check its AVR memory floor.

This is a stream feasibility check, not a firmware builder. It never emits HEX
or treats the isolated arithmetic kernel as a complete player.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/head5/best-intelligibility-model.json'
PROOF = ROOT/'ATtiny13A/Sound/research/word-q4/filter-head5-best.json'
NAMES = ('pitches', 'gains_q1', 'quarters', 'modes', 'phase_modes', 'durations')
METHODS = ('fixed', 'rice', 'delta-rice', 'zero-rice', 'zero-delta-rice')


class Bits:
    def __init__(self, data=None):
        self.data = bytearray() if data is None else bytearray(data)
        self.position = 0

    def write(self, value, width):
        if not 0 <= value < 1 << width:
            raise ValueError('Value does not fit its field')
        for shift in range(width):
            if self.position % 8 == 0:
                self.data.append(0)
            self.data[-1] |= ((value >> shift) & 1) << (self.position % 8)
            self.position += 1

    def read(self, width):
        if self.position + width > len(self.data)*8:
            raise ValueError('Truncated Q5 stream')
        value = 0
        for shift in range(width):
            value |= ((self.data[self.position//8] >> (self.position % 8)) & 1) << shift
            self.position += 1
        return value


def zigzag(value):
    return value*2 if value >= 0 else -value*2-1


def token(values, index, method):
    value = values[index]
    return zigzag(value-values[index-1]) if index and method in (2, 4) else value


def length(value, method, parameter):
    if method == 0:
        return parameter
    if method in (3, 4):
        return 1 if value == 0 else 2+parameter+((value-1) >> parameter)
    return 1+parameter+(value >> parameter)


def choose(values, allowed):
    choices = [(len(values)*max(values).bit_length(), 0, max(values).bit_length())]
    for method in allowed:
        if method == 0:
            continue
        for parameter in range(8):
            choices.append((sum(length(token(values, i, method), method, parameter)
                                for i in range(len(values))), method, parameter))
    return min(choices)


def write_token(bits, value, method, parameter):
    if method == 0:
        bits.write(value, parameter)
        return
    if method in (3, 4):
        bits.write(int(value != 0), 1)
        if not value:
            return
        value -= 1
    quotient = value >> parameter
    bits.write(0, quotient)
    bits.write(1, 1)
    bits.write(value & ((1 << parameter)-1), parameter)


def read_token(bits, method, parameter):
    if method == 0:
        return bits.read(parameter)
    if method in (3, 4) and bits.read(1) == 0:
        return 0
    quotient = 0
    while bits.read(1) == 0:
        quotient += 1
        if quotient > 1024:
            raise ValueError('Invalid Rice quotient')
    return (quotient << parameter) + bits.read(parameter) + int(method in (3, 4))


def columns(model):
    if (model['schema'] != 'mixed-lattice-pulse-v1' or model['sample_rate'] != 7500 or model['state_bits'] != 6
            or model['coefficient_bits'] != [5, 5, 4, 4, 4, 4, 4, 4]
            or model['wave_fraction_bits'] != 2 or model['pulse_length'] != 32
            or not model['nearest'] or model.get('phase_mode', 0) != 0):
        raise ValueError('Expected the exact Q2-pulse head-Q5 profile')
    values = [list(model[name]) for name in NAMES]
    values[5] = [value//64-1 for value in model['durations']]
    values += [list(row) for row in zip(*model['coefficients'])]
    count = len(values[0])
    limits = [(0, 126), (0, 30), (0, 3), (0, 7), (0, 3), (0, 3)] + [(-31, 31)]*2 + [(-15, 15)]*6
    if (not 1 <= count <= 65535 or len(values) != 14
            or len(model['coefficients']) != count or any(len(row) != 8 for row in model['coefficients'])
            or any(len(row) != count for row in values)
            or any(type(x) is not int or not low <= x <= high
                   for row, (low, high) in zip(values, limits) for x in row)
            or any(value not in (64, 128, 192, 256) for value in model['durations'])
            or len(model['wave_taps']) != 8
            or any(len(row) != 32 or any(type(x) is not int or not -14 <= x <= 14 for x in row)
                   for row in model['wave_taps'])):
        raise ValueError('Invalid Q5 controls or pulse book')
    return values


def pack(model, allowed=(0, 1, 2, 3, 4)):
    fields = columns(model)
    count = len(fields[0])
    header = bytearray(b'MQ5\x01'+count.to_bytes(2, 'little')+bytes((32, 2)))
    descriptions = []
    for field in fields:
        offset = min(field)
        values = [value-offset for value in field]
        cost, method, parameter = choose(values, allowed)
        descriptions.append((values, method, parameter, cost))
        header += bytes((offset & 255, method << 4 | parameter))
    bits = Bits()
    for i in range(count):
        for values, method, parameter, _ in descriptions:
            write_token(bits, token(values, i, method), method, parameter)
    waves = Bits()
    for row in model['wave_taps']:
        for value in row:
            waves.write(value & 31, 5)
    packed = bytes(header+bits.data+waves.data)
    return packed, dict(frames=count, headerBytes=len(header), frameBits=bits.position,
                        frameBytes=len(bits.data), pulseBytes=len(waves.data), dataBytes=len(packed),
                        fieldMethods=[dict(field=name, method=METHODS[method], parameter=parameter, bits=cost)
                                      for name, (_, method, parameter, cost) in zip(
                                          (*NAMES, *(f'k{i}' for i in range(8))), descriptions)])


def unpack(data):
    if len(data) < 36 or data[:4] != b'MQ5\x01' or data[6:8] != bytes((32, 2)):
        raise ValueError('Invalid Q5 stream header')
    count = int.from_bytes(data[4:6], 'little')
    if not count:
        raise ValueError('Empty Q5 stream')
    descriptors = [(data[i] if data[i] < 128 else data[i]-256, data[i+1] >> 4, data[i+1] & 15)
                   for i in range(8, 36, 2)]
    if any(method > 4 or parameter > 7 for _, method, parameter in descriptors):
        raise ValueError('Invalid Q5 field descriptor')
    bits = Bits(data[36:])
    fields = [[] for _ in descriptors]
    for index in range(count):
        for field, (offset, method, parameter) in zip(fields, descriptors):
            value = read_token(bits, method, parameter)
            if index and method in (2, 4):
                difference = -(value//2)-1 if value & 1 else value//2
                value = field[-1]-offset+difference
            field.append(value+offset)
    frame_bytes = (bits.position+7)//8
    if any((bits.data[bit//8] >> (bit % 8)) & 1 for bit in range(bits.position, frame_bytes*8)):
        raise ValueError('Nonzero Q5 padding')
    if len(data) != 36+frame_bytes+160:
        raise ValueError('Unexpected Q5 stream length')
    waves = Bits(data[36+frame_bytes:])
    taps = []
    for _ in range(8):
        row = []
        for _ in range(32):
            value = waves.read(5)
            row.append(value-32 if value >= 16 else value)
        taps.append(row)
    result = dict(schema='mixed-lattice-pulse-v1', sample_rate=7500,
                  state_bits=6, coefficient_bits=[5, 5, 4, 4, 4, 4, 4, 4], nearest=True,
                  phase_mode=0, wave_fraction_bits=2, pulse_length=32, wave_taps=taps,
                  **dict(zip(NAMES, fields[:6])), coefficients=list(map(list, zip(*fields[6:]))))
    result['durations'] = [(value+1)*64 for value in result['durations']]
    columns(result)
    return result


def run(model_path, output):
    model = json.loads(model_path.read_text(encoding='utf-8'))
    proof = json.loads(PROOF.read_text(encoding='utf-8'))
    arithmetic = proof['arithmeticBytes']
    output.mkdir(parents=True, exist_ok=True)
    candidates = []
    for name, allowed in (('fixed', (0,)), ('rice-delta', (0, 1, 2)),
                          ('rice-delta-zero', (0, 1, 2, 3, 4))):
        data, info = pack(model, allowed)
        restored = unpack(data)
        if (columns(restored) != columns(model) or restored['wave_taps'] != model['wave_taps']):
            raise ValueError('Q5 stream changed the retained speech parameters')
        (output/(name+'.mq5')).write_bytes(data)
        info.update(name=name, sha256=hashlib.sha256(data).hexdigest(), exactRoundTrip=True,
                    optimisticFlashFloorBytes=len(data)+arithmetic-64)
        candidates.append(info)
    best = min(candidates, key=lambda row: row['dataBytes'])
    report = dict(schema='micromusic-q5-flash-budget-v1',
                  modelSha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                  sourceSha256NormalizedLf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
                  phraseSamples=sum(model['durations']), sampleHz=7500,
                  source='tools/pack-q5-stream.py', candidates=candidates, best=best['name'],
                  arithmeticBytes=arithmetic, arithmeticProof='research/word-q4/filter-head5-best.json',
                  flashLimitBytes=1024, eepromLimitBytes=64,
                  optimisticFlashFloorBytes=best['optimisticFlashFloorBytes'],
                  omittedFromFloor=['startup and vectors', 'PWM and sample scheduling',
                                    'excitation and gain', 'stream unpacker', 'EEPROM access'],
                  fullFirmwareImplemented=False, flashQualified=False, hardwareTested=False,
                  status='oversized-even-before-player' if best['optimisticFlashFloorBytes'] > 1024 else 'player-not-implemented',
                  scope='Exact retained model and three measured lossless formats; no general impossibility claim.')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({key: report[key] for key in ('status', 'best', 'arithmeticBytes', 'optimisticFlashFloorBytes')}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=MODEL)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.model, args.output)
