"""Build TABLE=1/0 ASM images from frozen sources, and C exports without running C decoders."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source'


def raw_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', required=True)
    args = parser.parse_args()
    compiler = str(Path(args.avr_gcc).resolve())
    frozen = json.loads((ROOT / 'source.json').read_text())
    for name, digest in frozen['sourceSha256'].items():
        assert source_sha(SOURCE / name) == digest, name
    sys.path.insert(0, str(SOURCE / 'tools'))
    import build
    import build_wb
    original_run = build.run
    commands = []
    table = None

    def capture_run(command, cwd=None):
        command = list(map(str, command))
        if Path(command[0]).resolve() == Path(compiler):
            assert table in (0, 1)
            command.insert(1, '-DSPEEX_NB1_PITCH_ROOT_TABLE=' + str(table))
            commands.append(command)
        original_run(command, cwd)

    build.run = capture_run
    rows = []
    for table in [0, 1]:
        for profile, width, wideband, low_rates, nb4 in [
                ('wb395', 10, True, 7, True), ('nb215-min', 6, False, 4, False)]:
            destination = ROOT / ('table' + str(table)) / profile
            builder = build_wb.avr if wideband else build.avr
            executable = builder(compiler, backend='asm', packet_bytes=width,
                                 low_rates=low_rates, enable_nb4=nb4, destination=destination)
            executable = destination / ('wb.elf' if wideband else 'speex-test.elf')
            prefix = str(Path(compiler).with_name('avr-'))
            extension = Path(compiler).suffix
            (destination / 'sizes.txt').write_text(subprocess.check_output(
                [prefix + 'size' + extension, '-A', executable], text=True), encoding='utf-8')
            (destination / 'disassembly.txt').write_text(subprocess.check_output(
                [prefix + 'objdump' + extension, '-d', executable], text=True), encoding='utf-8')
            binary = destination / ('wb.bin' if wideband else 'speex-test.bin')
            metadata = json.loads((destination / 'backend.json').read_text())
            assert metadata['binarySha256'] == raw_sha(binary)
            symbols = (destination / 'symbols.txt').read_text()
            end = int(next(line.split()[0] for line in symbols.splitlines() if line.endswith(' __bss_end')), 16) & 65535
            sanitize = lambda value: value.replace(str(SOURCE), '<frozen-source>').replace(str(ROOT), '<admission>').replace(compiler, '<avr-gcc>')
            row = dict(profile=profile, tableEnabled=bool(table), packetBytes=width,
                       lowRates=low_rates, nb4Enabled=nb4, flashBytes=binary.stat().st_size,
                       staticSramBytes=end - 256, binarySha256=raw_sha(binary),
                       command=[sanitize(value) for value in commands[-1]])
            (destination / 'admission-build.json').write_text(json.dumps(row, indent=2) + '\n', encoding='utf-8')
            rows.append(row)
            print('BUILT', profile, 'TABLE=' + str(table), row['flashBytes'], flush=True)

    # Rebuild only the isolated arithmetic fixtures; never invoke a C decoder.
    subprocess.run([sys.executable, SOURCE / 'tests/build_nb1_pitch.py', '--avr-gcc', compiler], check=True)
    scalar = []
    for backend in ['asm', 'c']:
        for enabled in [1, 0]:
            label = backend + '-table' + str(enabled)
            fresh = SOURCE / 'build/nb1-pitch-unit' / label
            prior = ROOT / 'scalar-prior' / label
            before = json.loads((prior / 'verification.json').read_text())
            expected = before['binarySha256']
            assert raw_sha(fresh / 'unit.bin') == raw_sha(prior / 'unit.bin') == expected
            assert before['all128PitchCodes'] and before['originalThresholdTableAndSelectionExact']
            assert before['calleeSavedAndR1Returns'] == 512
            scalar.append(dict(fixture=label, rebuiltBinaryIdentical=True, binarySha256=expected,
                               reportSha256=source_sha(prior / 'verification.json')))

    exports = []
    for name, wideband, low_rates, nb4 in [('portable-nb', False, 4, False), ('portable-wb', True, 7, True)]:
        destination = ROOT / name
        if not destination.exists():
            (build_wb.export_c if wideband else build.export_c)(destination, enable_nb4=nb4, low_rates=low_rates)
        assert source_sha(destination / 'src/nb1_pitch.h') == source_sha(SOURCE / 'src/nb1_pitch.h')
        assert source_sha(destination / 'src/lowrate_excitation.h') == source_sha(SOURCE / 'src/lowrate_excitation.h')
        header = (destination / 'src/nb1_pitch.h').read_text()
        assert '#if SPEEX_NB1_PITCH_ROOT_TABLE' in header and 'return speex_nb1_pitch_root_c(pitch);' in header
        manifest = json.loads((destination / 'sources.json').read_text())
        assert 'SPEEX_NB3_ENABLE_ASM=0' in manifest['definitions']
        exports.append(dict(export=name, helperIncluded=True, polynomialExplicitlySelectable=True,
                            sourcesManifestSha256=source_sha(destination / 'sources.json'),
                            helperSha256=source_sha(destination / 'src/nb1_pitch.h'), cDecoderExecuted=False))
    receipt = dict(scope='Frozen source whole-image ASM TABLE=1/0 controls; no full C decoder execution',
                   compilerSha256=raw_sha(Path(compiler)), rows=rows,
                   scalarBinaryIdentity=scalar, portableExports=exports)
    (ROOT / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print('Recorded frozen build controls, exact scalar binary reuse and portable export checks')


if __name__ == '__main__':
    main()
