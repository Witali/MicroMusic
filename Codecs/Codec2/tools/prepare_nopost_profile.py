#!/usr/bin/env python3
"""Add debug attribution to the verified image, requiring identical machine code."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/nopost-profile'


def main():
    report = json.loads((ROOT / 'reports/nopost-decoder.json').read_text())
    for name, wanted in report['sources'].items():
        assert front.digest(ROOT / name) == wanted, name
    BUILD.mkdir(parents=True, exist_ok=True)
    flags = report['avr_build']['defines']
    memory = report['avr_build']['manufacturer_header_memory']
    sources = [ROOT / ('src/' + n) for n in ('nopost_decoder.c', 'adaptive_analysis.c',
        'matrix_analysis.c', 'fixed_inverse.c', 'compact_fft.c', 'parameters.c',
        'canonical_lpc.c', 'lpc_math.c')]
    front.run(['avr-gcc', '-mmcu=atmega64a', '-Os', '-g', '-std=c99', '-fstack-usage',
        '-fno-strict-aliasing', '-ffunction-sections', '-fdata-sections', *flags,
        *['-I' + str(ROOT / p) for p in ('include', 'src', 'vendor/codec2-1.2.0/src')],
        *sources, ROOT / 'tests/avr_hybrid.c', '-Wl,--gc-sections,-Map=' + str(BUILD / 'decoder.map'),
        '-Wl,--defsym=__DATA_REGION_ORIGIN__=' + str(0x800000 + memory['RAMSTART']),
        '-Wl,--defsym=__DATA_REGION_LENGTH__=' + str(memory['RAMEND'] - memory['RAMSTART'] + 1),
        '-Wl,--defsym=__TEXT_REGION_LENGTH__=' + str(memory['FLASHEND'] + 1),
        '-o', BUILD / 'decoder.elf', '-lm'], cwd=BUILD)
    front.run(['avr-objcopy', '-O', 'binary', BUILD / 'decoder.elf', BUILD / 'decoder.bin'])
    assert front.digest(BUILD / 'decoder.bin') == report['avr_build']['binary_sha256'], 'Debug attribution must not change code'
    with (BUILD / 'symbols.txt').open('wb') as output:
        front.run(['avr-nm', '-n', BUILD / 'decoder.elf'], stdout=output)
    size = (BUILD / 'decoder.bin').stat().st_size
    addresses = ''.join(f'{n:x}\n' for n in range(0, size, 2))
    output = front.run(['avr-addr2line', '-a', '-f', '-i', '-e', BUILD / 'decoder.elf'],
                       input=addresses, capture_output=True, text=True).stdout
    # Raw paths/debug output stay in ignored build/. Retained maps contain only
    # stage numbers and code addresses, without absolute compiler/user paths.
    (BUILD / 'addr2line.txt').write_bytes(output.encode())
    stages = ['other_parameters', 'main_lpc_spectrum', 'phases_and_inverse_power',
              'harmonic_amplitudes', 'background_filter', 'inverse_fft',
              'spectral_synthesis_and_ola', 'lsp_lpc_and_angles']
    source = (ROOT / 'src/nopost_decoder.c').read_text()
    ranges = {}
    for function in ('initial_phases', 'amplitudes', 'background_filter', 'synthesise'):
        match = re.search(r'static void ' + function + r'\(', source)
        start = source.index('{', match.start()); depth = 1; end = start + 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}'); end += 1
        ranges[function] = (source.count('\n', 0, match.start()) + 1, source.count('\n', 0, end) + 1)
    ids = {'initial_phases': 2, 'amplitudes': 3, 'background_filter': 4, 'synthesise': 6}
    analysis_files = ('adaptive_analysis.c', 'faithful_analysis.c', 'matrix_analysis.c',
                      'fixed_weight_sums32.c', 'compact_analysis_helpers.inc')
    def classify(frames):
        for function, location in frames:
            name = function.split('.')[0]
            if name in ids:
                return ids[name]
            normalized = location.replace('\\', '/')
            if any('/' + x + ':' in normalized for x in analysis_files):
                return 1
            if '/fixed_inverse.c:' in normalized:
                return 5
            if any('/' + x + ':' in normalized for x in ('canonical_lpc.c', 'lsp.c', 'lpc_math.c')):
                return 7
            line = re.search(r'/nopost_decoder\.c:(\d+)', normalized)
            if line:
                n = int(line[1])
                for function, (first, last) in ranges.items():
                    if first <= n <= last:
                        return ids[function]
                return 0
        return -1  # Library/helper code inherits its calling stage.
    mapping = [-1] * ((size + 1) // 2)
    at = None; frames = []
    for line in output.splitlines() + ['0xffffffff']:
        if re.fullmatch(r'0x[0-9a-fA-F]+', line):
            if at is not None:
                assert len(frames) % 2 == 0
                mapping[at // 2] = classify(list(zip(frames[::2], frames[1::2])))
            at = int(line, 16); frames = []
        else:
            frames.append(line)
    front.dump(BUILD / 'attribution.json', {'stages': stages, 'stage_by_word_pc': mapping,
        'binary_sha256': front.digest(BUILD / 'decoder.bin'), 'symbols_sha256': front.digest(BUILD / 'symbols.txt'),
        'generator_sha256': front.digest(Path(__file__)),
        'scope': 'DWARF source/inline attribution on debug ELF whose binary exactly equals the verified release image. Library helpers inherit caller stage.'})
    print('Debug image byte-identical; source/inline stage map prepared', flush=True)


if __name__ == '__main__':
    main()
