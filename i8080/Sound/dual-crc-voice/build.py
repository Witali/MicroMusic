#!/usr/bin/env python3
"""Rebuild constant-period 8080 voice variants from the retained original ROM.

No assembler dependency, no RAM, no new audio encoding. Emitted ASM is the
readable source for the replacement voice engine; diagnostics/ramp are inherited.
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
BASE = ROOT / '../../Emulator/tests/roms/diagnostic_dualcrc.bin'
ORIGINAL_SHA = '90fc9de477eb9b2b9f15a2b0d9bdaff390e124df24c024e77aaf4a42555007b1'
META = json.loads((ROOT / 'original-manifest.json').read_text())


def save(name, content):
    data = content.encode('utf-8') if isinstance(content, str) else bytes(content)
    path = ROOT / name
    if '--check' in sys.argv:
        actual = path.read_text(encoding='utf-8') if isinstance(content, str) else path.read_bytes()
        assert actual == content, f'Stale generated file: {name}'
    else:
        path.write_bytes(data)


class Code:
    def __init__(self, origin):
        self.origin, self.data, self.labels, self.fixups, self.source = origin, bytearray(), {}, [], []

    @property
    def pc(self):
        return self.origin + len(self.data)

    def label(self, name):
        assert name not in self.labels
        self.labels[name] = self.pc
        self.source.append(name + ':')

    def emit(self, text, *values):
        self.source.append('    ' + text)
        self.data.extend(values)

    def word(self, text, op, target):
        self.emit(text, op, 0, 0)
        self.fixups.append((len(self.data) - 2, target))

    def resolve(self, labels):
        for offset, name in self.fixups:
            self.data[offset:offset + 2] = labels[name].to_bytes(2, 'little')


def padding(ticks):
    """Shortest sequence of 4T NOP / 5T MOV A,A. Neither changes any flag."""
    best = {0: []}
    for n in range(1, ticks + 1):
        options = [best[n - t] + [(op, text)] for t, op, text in
                   [(4, 0x00, 'NOP'), (5, 0x7f, 'MOV A,A')] if n - t in best]
        if options:
            best[n] = min(options, key=len)
    return best.get(ticks)


def pad(code, ticks):
    instructions = padding(ticks)
    assert instructions is not None, ticks
    for op, text in instructions:
        code.emit(text, op)


def balance(code, ticks):
    # Between frames the next decoder overwrites A. A 7T MVI therefore fills
    # the otherwise impossible 7T / 11T slots without changing branch flags.
    if padding(ticks) is None:
        code.emit('MVI A,000H', 0x3e, 0)
        ticks -= 7
    pad(code, ticks)


def pwm_kernel(phase, level):
    code = Code(0)
    high, low = level * 4, (15 - level) * 4
    work = []
    if phase == 3:
        # D < 40h: sign comes solely from the stream word's marker B7.
        work = [(5, 'MOV A,D', (0x7a,)), (4, 'ORA B', (0xb0,))]
    elif phase == 4:
        work = [(5, 'DCR H', (0x25,))]  # 1Dh -> 1Ch; Z=0 for normal group.
    elif phase == 5:
        # Consume the ROM link inside existing PWM padding. Z=1 only at EOF.
        work = [(10, 'POP H', (0xe1,)), (5, 'SPHL', (0xf9,)),
                (5, 'MOV A,H', (0x7c,)), (4, 'ORA L', (0xb5,)),
                (7, 'MVI H,01CH', (0x26, 0x1c))]
    for split in range(len(work) + 1):
        before, after = work[:split], work[split:]
        hi = high - sum(item[0] for item in before)
        lo = low - sum(item[0] for item in after)
        if hi >= 0 and lo >= 0 and padding(hi) is not None and padding(lo) is not None:
            break
    else:
        raise ValueError(('Cannot balance width', phase, level))
    code.label(f'WIDTH_{phase}_{level}')
    code.emit('EI', 0xfb)
    for _, text, values in before:
        code.emit(text, *values)
    pad(code, hi)
    code.emit('DI', 0xf3)
    for _, text, values in after:
        code.emit(text, *values)
    pad(code, lo)
    code.word(f'JMP AFTER_{min(phase, 4)}', 0xc3, f'AFTER_{min(phase, 4)}')
    return code


def extract_words(original):
    words = []
    for part in META['voice_segment_links']:
        start, size = int(part['from'], 16), part['bytes']
        for at in range(start, start + size, 2):
            words.append((original[at], original[at + 1] & 0x7f))
    assert len(words) * 5 == 63085
    return words


def crc_table(poly):
    result = []
    for value in range(256):
        value <<= 8
        for _ in range(8):
            value = ((value << 1) ^ (poly if value & 0x8000 else 0)) & 0xffff
        result.append(value)
    return result


TABLES = [crc_table(p) for p in (7, 9)]


def crc(data, table):
    value = 0
    for byte in data:
        value = ((value << 8) & 0xffff) ^ table[(value >> 8) ^ byte]
    return value


def pair(data):
    return crc(data, TABLES[0]) | (crc(data, TABLES[1]) << 16)


def footer(block):
    block = bytearray(block)
    block[0xff0:0xff4] = bytes(4)
    rhs, columns = pair(block), []
    for bit in range(32):
        block[0xff0 + bit // 8] ^= 1 << (bit % 8)
        columns.append(pair(block) ^ rhs)
        block[0xff0 + bit // 8] ^= 1 << (bit % 8)
    rows = [sum(((columns[c] >> r) & 1) << c for c in range(32)) |
            (((rhs >> r) & 1) << 32) for r in range(32)]
    for col in range(32):
        pivot = next(r for r in range(col, 32) if rows[r] & (1 << col))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for row in range(32):
            if row != col and rows[row] & (1 << col):
                rows[row] ^= rows[col]
    value = sum(((rows[c] >> 32) & 1) << c for c in range(32)).to_bytes(4, 'little')
    block[0xff0:0xff4] = value
    assert pair(block) == 0
    return value


def hex_image(rom):
    lines = []
    for at in range(0, len(rom), 16):
        record = bytes([16, at >> 8, at & 255, 0]) + rom[at:at + 16]
        lines.append(':' + (record + bytes([-sum(record) & 255])).hex().upper())
    return '\n'.join(lines) + '\n:00000001FF\n'


def build(period):
    original = BASE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == ORIGINAL_SHA
    rom = bytearray(original)
    words = extract_words(original)
    extra = period - 152
    assert extra in (0, 7)
    head = Code(0x1100)
    head.label('VOICE')
    head.emit('DI', 0xf3)
    head.word('LXI SP,STREAM', 0x31, 'STREAM')
    head.emit('MVI D,020H', 0x16, 0x20)
    head.emit('MVI E,0F0H', 0x1e, 0xf0)
    head.emit('MVI H,01CH', 0x26, 0x1c)
    head.emit('POP B', 0xc1)
    head.word('JMP PHASE_0', 0xc3, 'PHASE_0')
    head.label('AFTER_4')
    head.word('JZ DONE', 0xca, 'DONE')
    head.emit('POP B', 0xc1)
    balance(head, 4 + extra)
    decoders = [
        [('MOV A,C', 0x79), ('RLC', 7), ('RLC', 7)],
        [('MOV A,C', 0x79), ('RRC', 15)],
        [('MOV A,B', 0x78), ('RRC', 15), ('MOV A,C', 0x79),
         ('RAR', 31), ('RRC', 15), ('RRC', 15), ('RRC', 15)],
        [('MOV A,B', 0x78), ('RLC', 7)],
    ]
    for phase, decoder in enumerate(decoders):
        head.label(f'PHASE_{phase}')
        for text, op in decoder:
            head.emit(text, op)
        head.emit('ANA H', 0xa4)
        head.emit('ADD E', 0x83)
        head.emit('ADD D', 0x82)
        head.emit('MOV D,A', 0x57)
        if phase:
            head.emit(f'ORI {phase * 64:03X}H', 0xf6, phase * 64)
        head.emit('MOV L,A', 0x6f)
        head.emit('PCHL', 0xe9)
        head.label(f'AFTER_{phase}')
        if phase < 3:
            balance(head, [21, 0, 21][phase] + extra)
        else:
            head.word('JM PHASE_4_LINK', 0xfa, 'PHASE_4_LINK')
    # Both branch paths cost 7T plus the optional 7T tempo-profile padding.
    for link in (False, True):
        if link:
            head.label('PHASE_4_LINK')
        head.emit('MVI A,000H', 0x3e, 0)
        balance(head, extra)
        if not link:
            head.label('PHASE_4')
        for text, op in [('MOV A,B', 0x78), ('RRC', 15), ('RRC', 15),
                         ('ANA H', 0xa4), ('ADD E', 0x83), ('ADD D', 0x82), ('MOV D,A', 0x57)]:
            head.emit(text, op)
        page = 0x1e if link else 0x1d
        head.emit(f'MVI H,{page:03X}H', 0x26, page)
        head.emit('MOV L,A', 0x6f)
        head.emit('PCHL', 0xe9)
    head.label('DONE')
    head.emit('DI', 0xf3)
    head.emit('HLT', 0x76)
    assert head.pc <= 0x1200, hex(head.pc)
    codes, cursor = [head], 0x1200
    for phase in range(6):
        for level in range(16):
            block = pwm_kernel(phase, level)
            block.labels = {k: v + cursor for k, v in block.labels.items()}
            block.origin = cursor
            cursor = block.pc
            codes.append(block)
    assert cursor <= 0x1980, hex(cursor)
    labels = {k: v for code in codes for k, v in code.labels.items()}
    occupied = set(range(0x1100, head.pc)) | set(range(0x1200, cursor))
    # Dispatch entries are four-byte aligned, selected by decoded amplitude*4.
    tables = [(0x1c00 + phase * 64, phase) for phase in range(4)] + [(0x1d00, 4), (0x1e00, 5)]
    for start, phase in tables:
        for level in range(16):
            target = labels[f'WIDTH_{phase}_{level}']
            rom[start + level * 4:start + level * 4 + 4] = bytes([0xc3, target & 255, target >> 8, 0])
        occupied.update(range(start, start + 64))
    # Keep address-bus probe bytes intact, including the A15 mirror tests.
    probes = set()
    checks = []
    for pc in range(0x200, 0xff0 - 8):
        if original[pc] == 0x21 and original[pc + 3] == 0x7e and original[pc + 4] == 0xfe and original[pc + 6:pc + 9] == bytes([0xc2, 0xc7, 0x0e]):
            address = int.from_bytes(original[pc + 1:pc + 3], 'little')
            probes.add(address & 0x7fff)
            checks.append((pc + 5, address & 0x7fff))
    assert len(checks) == 60, len(checks)
    occupied |= probes
    for bank in range(8):
        occupied.update(range(bank * 0x1000 + 0xff0, bank * 0x1000 + 0xff4))
    # Voice/data regions plus known unused holes; never overwrite diagnostics/ramp.
    ranges = [(0xfb0, 0xff0), (0x10b0, 0x1100), (0x1100, 0x7c40), (0x7f86, 0x7ff0)]
    free = sorted({at for a, b in ranges for at in range(a, b)} - occupied)
    spans = []
    for at in free:
        if spans and spans[-1][1] == at:
            spans[-1][1] += 1
        else:
            spans.append([at, at + 1])
    fragments, index = [], 0
    for start, end in spans:
        count = min((end - start - 2) // 2, len(words) - index)
        if count <= 0:
            continue
        for n in range(count):
            c, b = words[index + n]
            rom[start + n * 2:start + n * 2 + 2] = bytes([c, b | (0x80 if n == count - 1 else 0)])
        fragments.append({'from': start, 'bytes': count * 2, 'link': start + count * 2})
        index += count
        if index == len(words):
            break
    assert index == len(words), (index, len(words), hex(cursor))
    for i, part in enumerate(fragments):
        target = fragments[i + 1]['from'] if i + 1 < len(fragments) else 0
        part['target'] = target
        rom[part['link']:part['link'] + 2] = target.to_bytes(2, 'little')
    labels['STREAM'] = fragments[0]['from']
    for code in codes:
        code.resolve(labels)
        rom[code.origin:code.pc] = code.data
    # Expected address-test values include patched voice code bytes.
    for dest, address in checks:
        if dest != address:
            rom[dest] = rom[address]
    for bit in range(15):
        assert rom[0] != rom[1 << bit], bit
        assert rom[0x7fff] != rom[0x7fff ^ (1 << bit)], bit
    footers = []
    for bank in range(8):
        at = bank * 0x1000 + 0xff0
        rom[at:at + 4] = footer(rom[bank * 0x1000:(bank + 1) * 0x1000])
        footers.append({'address': f'{at:04X}', 'hex': rom[at:at + 4].hex(), 'crc0007': 0, 'crc0009': 0})
    name = f'dualcrc-uniform{period}'
    save(name + '.bin', rom)
    save(name + '.hex', hex_image(rom))
    source = [f'; Intel 8080, uniform {period}T PWM, 3.5 MHz, 16 levels.',
              '; Baseline diagnostics/ramp and DPCM words: original-manifest.json.',
              '; INTE changes at EI/DI completion; no READY, INT must stay low.',
              '; Build complete ROM: python build.py; data/tables/footers: manifest.',
              '; Only ROM reads through SP; no CALL/PUSH or memory writes.']
    for code in codes:
        source.extend(['', f'    ORG {code.origin:05X}H'] + code.source)
    save(name + '.asm', '\n'.join(source) + '\n')
    result = {'name': name, 'sha256': hashlib.sha256(rom).hexdigest(), 'original_sha256': ORIGINAL_SHA,
              'bytes': len(rom), 'cpu_hz': 3500000, 'period_t': period, 'carrier_hz': 3500000 / period,
              'levels': 16, 'width_t': '4+4*level', 'sample_count': 63085,
              'voice_code_start': '1100', 'kernel_end': f'{cursor:04X}',
              'ramp_start': META['ramp_start'], 'ramp_stage_pc': META['ramp_stage_pc'],
              'labels': {k: f'{v:04X}' for k, v in labels.items()},
              'segments': fragments, 'footers': footers, 'address_tests': len(checks)}
    save(name + '.json', json.dumps(result, indent=2) + '\n')
    print(name, result['sha256'], 'kernel end', hex(cursor), 'segments', len(fragments))


if __name__ == '__main__':
    for period in (152, 159):
        build(period)
