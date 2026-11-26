"""Profile an unchanged full-player ELF with a host-only instruction histogram.

Run in Linux/WSL. Existing complete PWM and every original timing counter must
remain exact. This is flat instruction attribution, not an inclusive call tree.
No profiling counter, marker or instruction is added to AVR firmware.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

REPO = Path(__file__).resolve().parents[5]
OBSERVER = REPO / 'Codecs/LPX/validation/attiny88/sim_player.c'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Observer source changed: ' + old[:80])
    return text.replace(old, new)


def functions(path):
    """Read STT_FUNC ranges from the actual linked little-endian AVR ELF32."""
    data = Path(path).read_bytes()
    if data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected ELF32 little endian')
    shoff = struct.unpack_from('<I', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 46)
    sections = [struct.unpack_from('<10I', data, shoff + i * size) for i in range(count)]
    rows = []
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for at in range(section[4], section[4] + section[5], section[9]):
            name, value, length, info, _, _ = struct.unpack_from('<IIIBBH', data, at)
            if info & 15 == 2 and length:
                rows.append((value, value + length, names[name:names.index(0, name)].decode()))
    return sorted(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.case_run.resolve(), args.output.resolve()
    if (REPO / 'build').resolve() not in output.parents:
        raise ValueError('Output must be a fresh ignored build subdirectory')
    if output.exists():
        raise ValueError('Output already exists')
    build = json.loads((source / 'build.json').read_text())
    for name, digest in build['source_sha256'].items():
        if sha(REPO / name) != digest:
            raise ValueError('Current production source does not match original ELF: ' + name)
    output.mkdir(parents=True)
    text = OBSERVER.read_text()
    text = replace_once(text, 'static unsigned decoding,decode_active;',
                        'static unsigned decoding,decode_active;\n'
                        'static uint64_t pc_cycles[H_FLASHEND+1];')
    text = replace_once(text, '  state=avr_run(&cpu);',
                        '  const unsigned profile_active=decoding && !in_irq;\n'
                        '  const uint32_t profile_pc=cpu.pc;\n'
                        '  const uint64_t profile_cycle=cpu.cycle,profile_irq=irq_clock();\n'
                        '  state=avr_run(&cpu);\n'
                        '  if(profile_active){\n'
                        '   const uint64_t elapsed=cpu.cycle-profile_cycle,interrupted=irq_clock()-profile_irq;\n'
                        '   if(interrupted>elapsed || profile_pc>H_FLASHEND)return 10;\n'
                        '   pc_cycles[profile_pc]+=elapsed-interrupted;\n'
                        '  }')
    text = replace_once(text, ' fclose(out);FILE *report=',
                        ' char *profile_name=malloc(strlen(argv[2])+13);if(!profile_name)return 2;\n'
                        ' sprintf(profile_name,"%s.profile.tsv",argv[2]);\n'
                        ' FILE *profile=fopen(profile_name,"w");free(profile_name);if(!profile)return 2;\n'
                        ' for(unsigned pc=0;pc<=H_FLASHEND;++pc)if(pc_cycles[pc])\n'
                        '  fprintf(profile,"%u\\t%llu\\n",pc,(unsigned long long)pc_cycles[pc]);\n'
                        ' fclose(profile);\n'
                        ' fclose(out);FILE *report=')
    observer = output / 'observer-profile.c'
    observer.write_text(text, encoding='utf-8', newline='\n')

    def run(*command):
        result = subprocess.run(list(map(str, command)), capture_output=True, check=True)
        return result.stdout

    run('gcc', '-O2', '-std=c11', '-I' + str(source), '-I/usr/include/simavr',
        observer, '-lsimavr', '-lelf', '-o', output / 'observer')
    log = run(output / 'observer', source / 'player.elf', output / 'actual.pwm', output / 'timing.json')
    (output / 'observer.log').write_bytes(log)
    original = json.loads((source / 'timing.json').read_text())
    current = json.loads((output / 'timing.json').read_text())
    if original != current:
        raise AssertionError('Profiling changed an original observer timing counter')
    if (output / 'actual.pwm').read_bytes() != (source / 'actual.pwm').read_bytes():
        raise AssertionError('Profiling changed complete PWM')
    ranges = functions(source / 'player.elf')
    buckets = {}
    histogram = []
    for line in (output / 'actual.pwm.profile.tsv').read_text().splitlines():
        pc, cycles = map(int, line.split())
        owner = next((name for start, end, name in ranges if start <= pc < end), '<unmapped>')
        buckets[owner] = buckets.get(owner, 0) + cycles
        histogram.append(dict(pc=pc, cycles=cycles, function=owner))
    total = sum(buckets.values())
    if total != current['decode_cpu_cycles']:
        raise AssertionError('Flat counters do not sum to complete decode CPU counter')
    report = dict(schema='lsf1-flat-full-elf-profile-v1', target=build['target'],
                  method='Full playback, active original IRQ; flat PC cycles inside original decode markers, IRQ excluded. Inlined work remains in its containing function.',
                  production_sources_verified=True, original_timing_fields_identical=True,
                  complete_pwm_identical=True, physical_board_measured=False,
                  original_elf_sha256=sha(source / 'player.elf'),
                  original_build_json_sha256=sha(source / 'build.json'),
                  original_observer_sha256=sha(OBSERVER), diagnostic_observer_sha256=sha(observer),
                  runner_sha256=sha(Path(__file__)), compiler=run('gcc', '--version').decode().splitlines()[0],
                  decode_calls=current['decode_calls'], decode_cpu_cycles=total,
                  decode_cpu_mean=total / current['decode_calls'],
                  flat_functions=[dict(function=name, cycles=cycles, percent=100 * cycles / total,
                                       cycles_per_source_sample=cycles/current['decode_calls'])
                                  for name, cycles in sorted(buckets.items(), key=lambda item: -item[1])],
                  pc_histogram=histogram)
    (output / 'profile.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'pc_histogram'}, indent=2))


if __name__ == '__main__':
    main()
