#!/usr/bin/env python3
"""8080 PCM4 with lossless word RLE: two uniform 82T pulses/sample, no RAM."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
import pwm_tools as p

PERIOD, REPEATS, PAGE = 82, 2, 0x38


def storage_code(level):
    return 15 if level == 4 else 4 if level == 15 else level


def decode(phase):
    register, high = ('C' if phase < 2 else 'B'), 1-phase % 2
    ops = [p.ins(5, 'MOV A,'+register, 0x79 if register == 'C' else 0x78)]
    ops += [p.ins(4, 'RRC' if high else 'RLC', 0x0f if high else 0x07)]*(1 if high else 3)
    mask = 0x78
    ops += [p.ins(7, f'ANI {mask:03X}H', 0xe6, mask), p.ins(5, 'MOV L,A', 0x6f)]
    if phase == 3:
        # Decrement during the THIRD sample. Z is live until phase 3/4 JNZ.
        ops += [p.ins(5, 'DCR E', 0x1d), p.ins(5, 'MOV H,D', 0x62)]
    else:
        ops += [p.ins(7, f'MVI H,{PAGE+phase:03X}H', 0x26, PAGE+phase)]
    return tuple(ops+[p.ins(5, 'PCHL', 0xe9)])


def program(phase, level, period=PERIOD):
    name = f'P{phase}_L{level}'
    if phase < 3:
        tree = (decode(phase+1), ())
    else:
        normal, eof = name+'_WORD', name+'_EOF'
        prefix = (p.jump(normal, 'JNZ', 0xc2),)
        link = (p.ins(10, 'POP H', 0xe1), p.ins(5, 'SPHL', 0xf9), p.ins(10, 'POP D', 0xd1),
                p.ins(5, 'DCR E', 0x1d), p.jump(eof, 'JZ', 0xca))
        word = (p.ins(10, 'POP B', 0xc1),)+decode(0)
        same_word = decode(0) if phase == 4 else word
        halt = (p.ins(10, 'LXI H,HALT', 0x21, 0, 0, target='HALT'), p.ins(5, 'PCHL', 0xe9))
        tree = (prefix, ((None, (link, ((None, (word, ())), (eof, (halt, ()))))), (normal, (same_word, ()))))
    tree = ((p.jump(name+'_BODY'),)+tree[0], tree[1])
    return p.schedule(tree, 4+4*level, period, REPEATS, 9 if level == 4 else 8, phase == 2)


def compress(packed):
    """A record expands to 1..255 words; word RLE preserves every PCM4 code."""
    words = [packed[i:i+2] for i in range(0, len(packed), 2)]
    records, pending = [], []
    def flush():
        while pending:
            part = pending[:255]; del pending[:255]
            records.append({'repeat': False, 'words': len(part), 'data': b''.join(part)})
    i = 0
    while i < len(words):
        end = i+1
        while end < len(words) and words[end] == words[i]:
            end += 1
        if end-i >= 5:
            flush(); count = end-i
            while count:
                n = min(255, count); records.append({'repeat': True, 'words': n, 'data': words[i]}); count -= n
            i = end
        else:
            pending.extend(words[i:end]); i = end
            if len(pending) >= 255:
                flush()
    flush()
    assert b''.join(r['data']*r['words'] if r['repeat'] else r['data'] for r in records) == packed
    return records


def build(profile, hz, check):
    base = ROOT/('owl' if profile == 'owl' else '')
    root = base if hz == 3500000 else base/'clocks'/str(hz)
    source = json.loads((root/'pcm4.json').read_text())
    assert (source['cpu_hz'], source['period_t'], source['pulses_per_sample']) == (hz, PERIOD, REPEATS)
    logical = bytes.fromhex(source['packed_hex'])
    packed = bytes(storage_code(b & 15) << 4 | storage_code(b >> 4) for b in logical)
    records = compress(packed)
    old_root = ROOT.parent/'voice32'/('owl' if profile == 'owl' else '')
    old_root = old_root if hz == 3500000 else old_root/'clocks'/str(hz)
    old_name = 'owl-voice32' if profile == 'owl' else 'dualcrc-voice32'
    old_meta = json.loads((old_root/(old_name+'.json')).read_text())
    baseline = (old_root/(old_name+'.bin')).read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == old_meta['sha256']
    direct = profile == 'owl'
    rom = bytearray([0xff]*32768) if direct else bytearray(baseline)
    probes, checks = set(), []
    for pc in range(0x200, 0xff0-8):
        if baseline[pc] == 0x21 and baseline[pc+3:pc+5] == b'\x7e\xfe' and baseline[pc+6:pc+9] == b'\xc2\xc7\x0e':
            address = int.from_bytes(baseline[pc+1:pc+3], 'little') & 0x7fff
            probes.add(address); checks.append((pc+5, address))
    assert len(checks) == (0 if direct else 60)
    ranges = [(3, 32768)] if direct else [(0xfb0, 0xff0), (0x10b0, 0x1100), (0x1100, 0x7c40), (0x7f86, 0x7ff0)]
    available = {a for lo, hi in ranges for a in range(lo, hi)}-probes
    for bank in range(0 if direct else 8):
        available.difference_update(range(bank*4096+0xff0, bank*4096+0xff4))
    allocator = p.Allocator(available)
    for phase in range(5):
        allocator.reserve((PAGE+phase)*256, 129)
    head = p.Code(0x1100); head.label('VOICE'); head.emit('DI', 0xf3)
    head.word('LXI SP,STREAM', 0x31, 'STREAM'); head.emit('POP D', 0xd1); head.emit('DCR E', 0x1d); head.emit('POP B', 0xc1)
    p.emit(head, (decode(0), ())); allocator.reserve(head.origin, len(head.data))
    halt = p.Code(0); halt.label('HALT'); halt.emit('HLT', 0x76); allocator.place(halt)
    end_stream = p.Code(0); end_stream.label('END_STREAM'); end_stream.emit('DB 001H,000H', 1, 0); allocator.place(end_stream)
    codes = [head, halt, end_stream]
    for phase in range(5):
        for level in range(16):
            tree = program(phase, level); assert tree is not None, (phase, level)
            entry_tree, body_tree = p.split_entry(tree)
            name = f'P{phase}_L{level}'
            stride = 8
            entry = p.Code((PAGE+phase)*256+storage_code(level)*stride); entry.label(name); p.emit(entry, entry_tree)
            assert len(entry.data) <= (9 if level == 4 else 8)
            body = p.Code(0); body.label(name+'_BODY'); p.emit(body, body_tree); allocator.place(body)
            codes += [entry, body]
    labels = {k: a for code in codes for k, a in code.labels.items()}
    parts = []
    for record in records:
        index = 0
        while index < record['words']:
            span = next(((lo, hi) for lo, hi in allocator.spans() if hi-lo >= 6), None)
            assert span is not None, f'PCM stream exceeds available ROM; {len(allocator.available)} bytes left'
            lo, hi = span
            count = record['words'] if record['repeat'] else min(record['words']-index, (hi-lo-4)//2)
            data = record['data'] if record['repeat'] else record['data'][index*2:(index+count)*2]
            page = PAGE+(4 if record['repeat'] else 3)
            rom[lo:lo+2] = bytes([(count+1) & 255, page]); rom[lo+2:lo+2+len(data)] = data
            parts.append({'header': lo, 'words': count, 'repeat': record['repeat'], 'data': lo+2, 'data_bytes': len(data), 'link': lo+2+len(data)})
            allocator.reserve(lo, 4+len(data)); index += count
    assert sum(part['words'] for part in parts)*4 == source['sample_count']
    for i, part in enumerate(parts):
        part['target'] = parts[i+1]['header'] if i+1 < len(parts) else labels['END_STREAM']
        rom[part['link']:part['link']+2] = part['target'].to_bytes(2, 'little')
    labels['STREAM'] = parts[0]['header']
    for code in codes:
        code.resolve(labels); rom[code.origin:code.pc] = code.data
    for dest, address in checks:
        if dest != address:
            rom[dest] = rom[address]
    footers = []
    for bank in range(0 if direct else 8):
        at = bank*4096+0xff0; rom[at:at+4] = p.legacy.footer(rom[bank*4096:(bank+1)*4096])
        footers.append({'address': f'{at:04X}', 'hex': rom[at:at+4].hex()})
    if direct:
        rom[:3] = bytes([0xc3, 0, 0x11])
    else:
        for bit in range(15):
            assert rom[0] != rom[1 << bit] and rom[0x7fff] != rom[0x7fff ^ (1 << bit)]
    name = ('owl' if direct else 'dualcrc')+'-voice-pwm82'
    meta = {'name': name, 'backend': 'i8080-asm', 'cpu_hz': hz, 'bytes': len(rom),
        'sha256': hashlib.sha256(rom).hexdigest(), 'period_t': PERIOD, 'carrier_hz': hz/PERIOD,
        'pulses_per_sample': REPEATS, 'sample_t': PERIOD*REPEATS, 'sample_rate_hz': hz/(PERIOD*REPEATS),
        'sample_count': source['sample_count'], 'width_t': '4+4*level', 'levels': 16,
        'storage_permutation': [storage_code(q) for q in range(16)],
        'storage_order': 'high-nibble-first', 'compression': 'Lossless repeated 16-bit PCM words; literal and repeat records; 1..255 words per record',
        'stored_data_bytes': sum(part['data_bytes'] for part in parts), 'stream_bytes': sum(4+part['data_bytes'] for part in parts)+2,
        'packed_bytes': len(packed), 'code_bytes': sum(len(c.data) for c in codes),
        'dispatch_reserved_bytes': 645, 'free_voice_region_bytes': len(allocator.available),
        'voice_code_start': '1100', 'ramp_start': None if direct else old_meta['ramp_start'],
        'ramp_stage_pc': [] if direct else old_meta['ramp_stage_pc'],
        'startup': 'direct' if direct else 'diagnostics', 'startup_baseline_sha256': old_meta['sha256'],
        'diagnostics': not direct, 'soft_start': not direct, 'segments': parts, 'footers': footers,
        'address_tests': len(checks), 'halt_tail_t': 7,
        'labels': {k: f'{a:04X}' for k, a in labels.items()},
        'hardware_tested': False, 'active_interrupts_supported': False}
    p.save(root, name+'.bin', rom, check); p.save(root, name+'.hex', p.legacy.hex_image(rom), check)
    p.save(root, name+'.json', meta, check)
    asm = ['; Intel 8080: lossless PCM4 word RLE, two uniform 82T pulses/sample. INT/WAIT/HOLD inactive.',
           '; BC=PCM word; E=word count; D=literal/RLE phase page; SP=ROM cursor. No RAM, CALL or PUSH.',
           '; High nibble first, codes 4/15 swapped. Five 129B dispatch pages: 8B cells, last cell 9B.',
           '; DCR E in phase 2; Z MUST survive until phase 3/4 JNZ. ORI 0 padding only when Z is dead.',
           '; C fallback: ../voice32/voice.c; ASM requires explicit architecture + enable flag.',
           '; Final full PWM period precedes a silent 7T HLT tail.']
    if direct:
        asm += ['    ORG 00000H', '    JMP VOICE']
    for code in codes:
        asm += ['', f'    ORG {code.origin:05X}H']+code.source
    p.save(root, name+'.asm', '\n'.join(asm)+'\n', check)
    print(f'{profile} {hz}: {hz/PERIOD:.3f} Hz PWM, {len(packed)} PCM bytes, {meta["code_bytes"]} code bytes, {len(allocator.available)} free')


if __name__ == '__main__':
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--backend', choices=['c', 'i8080-asm'], default='c'); a.add_argument('--architecture', default='portable')
    a.add_argument('--enable-asm', action='store_true'); a.add_argument('--profile', choices=['balloon', 'owl'], default='balloon')
    a.add_argument('--cpu-hz', type=int, choices=[2000000, 2500000, 3500000], default=3500000); a.add_argument('--check', action='store_true')
    args = a.parse_args()
    if args.backend == 'c':
        print('Portable C selected: ../voice32/voice.c. No assembly ROM is built.')
    else:
        if args.architecture != 'i8080' or not args.enable_asm:
            a.error('Assembly requires --architecture i8080 --enable-asm')
        build(args.profile, args.cpu_hz, args.check)
