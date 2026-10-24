"""Assemble real integer-decoder sections inside the ATtiny13A's 1 KiB limit.

These isolated fixtures check arithmetic against independent PC expectations.
They do not establish that the complete decoder or its payload fit the MCU,
nor do they measure complete-player deadlines or interrupt stack usage.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from dc_blocker import block_dc, state_bounds
from compact_period import pack_compact
from fixed_period import avr_features, frame_sample, from_colored, pack_avr_data


def section(source, start, end):
    if source.count(start) != 1:
        raise ValueError('Firmware layout changed; review kernel extraction')
    tail = source.split(start, 1)[1]
    if end not in tail:
        raise ValueError('Firmware section end missing; review kernel extraction')
    return tail.split(end, 1)[0]


def run(command, cwd):
    return subprocess.run(list(map(str, command)), cwd=cwd, check=True,
                          text=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path, required=True)
    parser.add_argument('--node', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'build/fixed-avr-kernels')
    parser.add_argument('--special-model', type=Path, action='append', default=[],
                        help='Also test a retained, specialized period-fixed-v1 model')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    firmware = CODEC/'fixed/firmware.S'
    source = firmware.read_text(encoding='utf-8')
    # Extract the actual implementation, rather than reproducing its arithmetic.
    arithmetic = 'multiply:'+section(source, '\nmultiply:', '\n/* Compact sequential parameter reader.')
    reader = 'read_frame:'+section(source, '\nread_frame:', '\nirq:')
    noise = section(source, ' /* Shift the white-noise history; the last zero tap needs a 16th byte. */',
                    '\n mov r16,r2\n')
    blend = section(source, ' /* Signed (new-old)*time, rounded >>6, then old. */', '\n.if DC_SHIFT')
    dc = section(source, '\n.if DC_SHIFT', '\n.endif')
    phase = section(source, ' /* Phase pitch changes at block starts, fade frames at block centers. */', '\n inc r1')
    prelude = ('.section .text\n.global __vectors\n.set HIST,0x68\n.set BITBUF,0x60\n'
               '.set ENABLE_FIR,1\n.set ENABLE_UNVOICED,1\n.set SINGLE_FIR,0\n'
               '.set FIR_BYTES,24\n.set HISTORY_LENGTH,16\n.set WAVE_BYTES,256\n'
               '.set DCLO,0x61\n.set DCHI,0x62\n__vectors:\n rjmp __vectors\n')
    fixture_specs = []

    def build(name, assembly, data):
        folder = output/name
        folder.mkdir(exist_ok=True)
        (folder/'fixture.S').write_text(assembly, encoding='utf-8', newline='\n')
        (folder/'tables.bin').write_bytes(data)
        suffix = '.exe' if sys.platform == 'win32' else ''
        tool = lambda name: args.avr_bin/(name+suffix)
        run([tool('avr-gcc'), '-mmcu=attiny13a', '-nostdlib', '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024', '-x', 'assembler',
             'fixture.S', '-o', 'fixture.elf'], folder)
        run([tool('avr-objcopy'), '-O', 'binary', 'fixture.elf', 'fixture.bin'], folder)
        binary = (folder/'fixture.bin').read_bytes()
        if len(binary) > 1024:
            raise AssertionError(f'{name}: isolated fixture exceeds ATtiny13A Flash: {len(binary)}')
        symbols = {}
        for line in run([tool('avr-nm'), '-n', 'fixture.elf'], folder).splitlines():
            fields = line.split()
            if len(fields) == 3:
                symbols[fields[2]] = int(fields[0], 16)
        spec = dict(name=name, image=str(folder/'fixture.bin'), bytes=len(binary), symbols=symbols,
                    image_sha256=sha256(binary).hexdigest())
        fixture_specs.append(spec)
        return spec

    colored = json.loads((ROOT/'ATtiny13A/Sound/research/period-balanced/chego/model.json').read_text(encoding='utf-8'))
    model = from_colored(colored)
    book = np.asarray(model['codebook'], np.int64)
    filters = np.asarray(model['noise_filters'], np.int64)
    tables = pack_avr_data(model)[:280]
    core_fixtures = []
    def core_assembly(shift, features):
        selected = prelude
        for key, value in features.items():
            selected, count = re.subn(rf'(?m)^\.set {key},\d+$', f'.set {key},{value}', selected)
            if count != 1:
                raise ValueError('Missing feature in kernel prelude: '+key)
        return (selected+f'.set DC_SHIFT,{shift}\n'+arithmetic+
                '\nnoise_step:\n'+noise+'\n ret\nblend_step:\n'+blend+
                '\n ret\nphase_step:\n'+phase+'\n ret\ndc_step:\n'+dc+
                '\n ret\nwave_data:\n.incbin "tables.bin"\n.set noise_data,wave_data+WAVE_BYTES\n')
    for shift in (5, 6, 7):
        assembly = core_assembly(shift, {})
        spec = build(f'core-dc{shift}', assembly, tables)
        spec['shift'] = shift
        core_fixtures.append(spec)

    zero_noise = np.zeros((4, 1), np.int16)
    render_cases = []
    for word in range(16):
        for gain in range(1, 8):
            for index in range(32):
                for fraction in (0, 1, 7, 8, 15):
                    phase_value = (index << 11) | (fraction << 7) | ((word*53+gain*19) & 127)
                    header = 128 | gain << 4 | word
                    expected = int(frame_sample(header, 0, phase_value, book, zero_noise, 0, 4))
                    render_cases.append([header, 0, phase_value, None, expected])
    rng = np.random.default_rng(23107)
    for i in range(1024):
        history = rng.integers(-128, 128, 15).tolist()
        if i < 4:
            history = ([127, -128]*8 if i & 1 else [-128, 127]*8)[:15]
        noise_values = [history[0]-history[1]]
        for coefficients in filters:
            full = np.concatenate((coefficients, coefficients[-2::-1]))
            noise_values.append(int(np.dot(history, full)))
        header = int(rng.integers(256))
        residual = ((i % 4) << 4) | (1+(i//4) % 15)
        phase_value = int(rng.integers(65536))
        expected = int(frame_sample(header, residual, phase_value, book,
                                   np.asarray(noise_values, np.int16).reshape(4, 1), 0, 4))
        render_cases.append([header, residual, phase_value, history, expected])

    special_models = []
    for name in ('single-fir', 'white-only'):
        specialized = deepcopy(model)
        for frame in specialized['frames']:
            if not frame[1] & 128:
                frame[1] &= 143
            frame[2] = (16 if name == 'single-fir' and frame[2] >> 4 else 0) | (frame[2] & 15)
        if name == 'single-fir':
            specialized['noise_filters'] = [deepcopy(model['noise_filters'][0]) for _ in range(3)]
        special_models.append((name, specialized))
    for path in args.special_model:
        special_models.append((path.stem, json.loads(path.read_text(encoding='utf-8'))))
    special_readers = []
    for name, specialized in special_models:
        features = avr_features(specialized)
        data = pack_avr_data(specialized, specialize=True)
        size = features['WAVE_BYTES']+features['FIR_BYTES']
        spec = build('special-'+name, core_assembly(7, features), data[:size])
        spec.update(shift=7, specialized=True, features=features)
        spec['render_cases'] = []
        special_book = np.asarray(specialized['codebook'], np.int64)
        special_filters = np.asarray(specialized['noise_filters'], np.int64)
        # Actual frame parameters, extrema histories and arbitrary phase cover
        # the target-specific branches without feeding unsupported input modes.
        for i in range(max(1024, len(specialized['frames'])*4)):
            _, header, residual = specialized['frames'][i % len(specialized['frames'])]
            history = rng.integers(-128, 128, 15).tolist()
            if i < 4:
                history = ([127, -128]*8 if i & 1 else [-128, 127]*8)[:15]
            noise_values = [history[0]-history[1]]
            for coefficients in special_filters:
                noise_values.append(int(np.dot(history, np.concatenate((coefficients, coefficients[-2::-1])))))
            phase_value = int(rng.integers(65536))
            expected = int(frame_sample(header, residual, phase_value, special_book,
                                       np.asarray(noise_values, np.int16).reshape(4, 1), 0, 4))
            spec['render_cases'].append([header, residual, phase_value, history, expected])
        core_fixtures.append(spec)
        # The parser uses the same feature flags and its own bounded field data.
        selected = prelude
        for key, value in features.items():
            selected = re.sub(rf'(?m)^\.set {key},\d+$', f'.set {key},{value}', selected)
        parser_spec = build('special-reader-'+name, selected+reader+'\nfield_data:\n.incbin "tables.bin"\n', data[size:])
        parser_spec['frames'] = specialized['frames']
        special_readers.append(parser_spec)

    fir_cases = []
    for coefficient in range(-7, 8):
        for tap in range(8):
            for amplitude in (-128, -1, 0, 1, 127):
                history = [amplitude]*15
                coefficients = [0]*8
                coefficients[tap] = coefficient
                full = coefficients+coefficients[-2::-1]
                expected = sum(x*y for x, y in zip(history, full))
                packed = [(full+[0])[i] & 15 | (((full+[0])[i+1] & 15) << 4) for i in range(0, 16, 2)]
                fir_cases.append([packed, history, expected])

    dc_cases = {}
    for shift in (5, 6, 7):
        low, high = state_bounds(shift)
        cases = []
        for state in (low, low+1, -65, -64, -1, 0, 1, 63, 64, high-1, high):
            for pwm in range(256):
                result, final, clipped, peak = block_dc(np.asarray([pwm], np.uint8), shift, state)
                cases.append([state, pwm-128, int(result[0])-128, int(final)])
        dc_cases[str(shift)] = cases

    reader_fixtures = special_readers
    reader_models = []
    for clip in ('chego', 'otvechaesh', 'vinni'):
        reader_source = json.loads((ROOT/f'ATtiny13A/Sound/research/period-balanced/{clip}/model.json').read_text(encoding='utf-8'))
        # Parser-only coverage may include a float model whose FIR exceeds the
        # fixed synthesis bounds. No synthesis or fixed conversion is claimed.
        reader_models.append((clip, from_colored(reader_source), pack_compact(reader_source)[281:]))
    synthetic = dict(model)
    pitches = [128, 128, 129, 128, 130, 128, 131, 128, 132, 128, 133, 128, 134, 0, 255, 128]
    synthetic['samples'] = len(pitches)*64
    synthetic['frames'] = [[p, (i*113) & 255, (i*19) & 63] for i, p in enumerate(pitches)]
    reader_models.append(('pitch-prefixes', synthetic, pack_avr_data(synthetic)[280:]))
    for name, reader_model, fields in reader_models:
        spec = build('reader-'+name, prelude+reader+'\nfield_data:\n.incbin "tables.bin"\n',
                     fields)
        spec['frames'] = reader_model['frames']
        reader_fixtures.append(spec)

    manifest = dict(schema='fixed-avr-kernel-test-v1', source=str(firmware),
                    source_sha256=sha256(source.encode()).hexdigest(), core=core_fixtures,
                    reader=reader_fixtures, render_cases=render_cases, fir_cases=fir_cases,
                    dc_cases=dc_cases)
    manifest_path = output/'fixtures.json'
    manifest_path.write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8', newline='\n')
    report = run([args.node, ROOT/'tools/verify-fixed-avr-kernels.mjs', manifest_path], ROOT)
    (output/'verification.json').write_text(report, encoding='utf-8', newline='\n')
    print(report, end='')


if __name__ == '__main__':
    main()
