"""Retain full measured counters and deduplicated AVR build provenance.

Reads completed ignored runs only; never rebuilds firmware or changes source
inputs. Retained output contains JSON, hashes and compiler recipes, no media.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full as full


def normalized(value, case_dir, run_dir):
    if isinstance(value, dict):
        return {normalized(k, case_dir, run_dir): normalized(v, case_dir, run_dir) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v, case_dir, run_dir) for v in value]
    if isinstance(value, str):
        return (value.replace(str(case_dir), '<case>')
                .replace(case_dir.relative_to(full.REPO).as_posix(), '<case>')
                .replace(str(run_dir / 'stage'), '<stage>')
                .replace((run_dir / 'stage').relative_to(full.REPO).as_posix(), '<stage>')
                .replace(str(full.REPO), '<repo>'))
    return value


def retain(run_dir, recipes):
    run_dir = Path(run_dir).resolve()
    report = json.loads((run_dir / 'results.json').read_text())
    for row in report['rows']:
        case_dir = full.REPO / row['output'] if 'output' in row else run_dir / row['case'] / row['target'] / row['backend']
        build_path = case_dir / 'build.json'
        if build_path.exists():
            build = json.loads(build_path.read_text())
            recipe = normalized({key: build[key] for key in ('compiler', 'compiler_options', 'source_sha256', 'target', 'queue', 'prefill', 'assembly', 'asm_isr', 'universal')}, case_dir, run_dir)
            payload = json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode()
            key = hashlib.sha256(payload).hexdigest()
            recipes[key] = recipe
            row['build_recipe_sha256'] = key
            row['linked_image_sha256'] = build['image_sha256']
            row['embedded_audio_bytes'] = build['embedded_audio_bytes']
            row['embedded_audio_identical_to_input'] = build['input_sha256'] == row['source_sha256']
            if not row['embedded_audio_identical_to_input']:
                raise AssertionError('Build input provenance changed')
            if (case_dir / 'player.elf').exists():
                row['elf_sha256'] = full.sha(case_dir / 'player.elf')
        for file, label in [('expected.pwm', 'portable_expected_pwm_sha256'),
                            ('actual.pwm', 'complete_actual_pwm_sha256'),
                            ('actual.pwm.valid', 'valid_actual_pwm_sha256')]:
            if (case_dir / file).exists():
                row[label] = full.sha(case_dir / file)
    if (run_dir / 'stage.json').exists():
        report['stage_snapshot'] = json.loads((run_dir / 'stage.json').read_text())
    report['frozen_inputs'] = json.loads((run_dir / 'inputs.json').read_text()) if (run_dir / 'inputs.json').exists() else None
    return report


def paired_summary(baseline, experimental):
    index = {(row['case'], row['target'], row['backend']): row['result']
             for row in baseline['rows'] if row['status'] == 'measured'}
    rows = []
    for target in ('attiny88', 'atmega328p'):
        for backend in ('asm', 'c'):
            for variant in ('exact', 'fine', 'compact'):
                cohort = [row for row in experimental['rows'] if row['target'] == target and row['backend'] == backend and row['variant'] == variant and row['status'] == 'measured']
                before = [index[row['case'], target, backend] for row in cohort]
                after = [row['result'] for row in cohort]
                result = dict(target=target, backend=backend, variant=variant, paired_full_files=len(cohort),
                              admitted=sum(row['accepted'] for row in after),
                              omitted_physical_fit_failures=8 - len(cohort))
                for kind, count in (('decode', 'decode_calls'), ('producer', 'producer_calls')):
                    old = sum(row[kind + '_cpu_cycles'] for row in before) / sum(row[count] for row in before)
                    new = sum(row[kind + '_cpu_cycles'] for row in after) / sum(row[count] for row in after)
                    result[kind + '_cpu_cycles_per_sample'] = dict(baseline=old, experimental=new, change_percent=100 * (new / old - 1))
                for key in ('flash_bytes', 'program_excluding_audio_bytes', 'static_ram_bytes', 'stack_bytes', 'stack_margin', 'output_gap_min', 'output_gap_max', 'decode_cpu_max', 'producer_cpu_max'):
                    result[key + '_range'] = [min(row[key] for row in after), max(row[key] for row in after)]
                result['tiny_bootloader_fits'] = sum(row.get('tiny_standard_bootloader_fit', False) for row in after) if target == 'attiny88' else None
                rows.append(result)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--experimental', type=Path, required=True)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--observer-proof', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    output = args.output.resolve()
    if output != Path(__file__).resolve().parent:
        raise ValueError('Retained reports belong in this experiment avr/ directory')
    recipes = {}
    baseline = retain(args.baseline, recipes)
    experiment = retain(args.experimental, recipes)
    controls = retain(args.controls, recipes)
    for name, data in [('baseline-results.json', baseline), ('lg-results.json', experiment), ('controls-results.json', controls)]:
        full.write_json(output / name, data)
    provenance = dict(schema='lbg1-avr-build-provenance-v1', recipes=recipes,
                      hardware=dict(cpu_hz=16000000, sample_hz=8000, sample_period_cycles=2000,
                                    sample_timer='Timer0 CTC /8, OCR0A=249',
                                    pwm='Timer1 fast PWM8 /1, OC1A/PB1, 62500 Hz',
                                    fifo=32, prefill=24, playback_gain_q7=128),
                      observer_proof=json.loads(args.observer_proof.read_text()))
    tiny = full.REPO / 'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h'
    mega = Path('/usr/lib/avr/include/avr/iom328p.h')
    provenance['device_headers'] = {'ATtiny_DFP_3.4.278': full.sha(tiny)}
    if mega.exists():
        provenance['device_headers']['installed_avr_libc_iom328p.h'] = full.sha(mega)
    full.write_json(output / 'build-provenance.json', provenance)
    summary = dict(schema='lbg1-paired-full-avr-summary-v1',
                   method='Sums of complete decode/producer foreground CPU cycles divided by sums of corresponding calls, paired on identical full files that physically linked. No timing is inferred for Flash-overflow cases. Begin/startup outside the original sample regions is not included. C slow controls are not realtime admissions.',
                   paired=paired_summary(baseline, experiment),
                   baseline=baseline['summary'], experimental=experiment['summary'], controls=controls['summary'])
    full.write_json(output / 'summary.json', summary)
    print(json.dumps({key: summary[key] for key in ('baseline', 'experimental', 'controls')}, indent=2))


if __name__ == '__main__':
    main()
