"""Bounded full-player CPU screening of existing current-LPX build settings.

No decoder, player, audio bitstream or default is edited. Run in Linux/WSL.
Reuses the original full-player builder/verifier and the previously validated
host-only valid-PWM observer extension. Every run uses real physical limits.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
HELPER = REPO / 'Codecs/LPX/experimental/LBG1/avr/run_full.py'
spec = importlib.util.spec_from_file_location('lpx_tuning_full_helpers', HELPER)
full = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = full
spec.loader.exec_module(full)

PROFILES = {
    'tiny-unroll4': dict(target='attiny88', unroll=4, tuning=0),
    'tiny-unroll8': dict(target='attiny88', unroll=8, tuning=0),
    'tiny-unroll16': dict(target='attiny88', unroll=16, tuning=0),
    'mega-tuning1': dict(target='atmega328p', unroll=2, tuning=1),
    'mega-tuning7': dict(target='atmega328p', unroll=2, tuning=7),
}


def baseline_index(manifest, baseline, provenance):
    """Admit reuse only for identical input, sources and hardware recipe."""
    cases = {name: (source, pcm) for name, _, source, pcm in full.cases_from_manifest(manifest)}
    report = json.loads(baseline.read_text())
    recipes = json.loads(provenance.read_text())['recipes']
    result = {}
    for row in report['rows']:
        if row['backend'] != 'asm' or row['case'] not in cases:
            continue
        if row['status'] != 'measured' or not row['result']['accepted']:
            raise ValueError('Reference baseline is not admitted')
        if full.sha(cases[row['case']][0]) != row['source_sha256']:
            raise ValueError('Audio differs from the measured baseline')
        recipe = recipes[row['build_recipe_sha256']]
        for name, digest in recipe['source_sha256'].items():
            if full.sha(REPO / name) != digest:
                raise ValueError('Current source differs from measured baseline: ' + name)
        if recipe['queue'] != 32 or recipe['prefill'] != 24 or not recipe['universal'] or not recipe['asm_isr']:
            raise ValueError('Baseline hardware/queue recipe changed')
        result[row['case'], row['target']] = row
    if len(result) != 16:
        raise ValueError('Need eight admitted source-matched baselines on both targets')
    return result


def run_one(job):
    case, source, pcm, profile_name, output_name, observer, baseline = job
    settings = PROFILES[profile_name]
    output = Path(output_name)
    output.mkdir(parents=True)
    row = dict(case=case, profile=profile_name, settings=settings, source_sha256=full.sha(source),
               complete_file_requested=True, physical_board_measured=False)
    try:
        _, verifier = full.modules('baseline', observer_source=observer)
        flags = () if not settings['tuning'] else (
            '-ULPX4_FUNCTION_TUNING', '-DLPX4_FUNCTION_TUNING=' + str(settings['tuning']))
        result = verifier.verify(Path(source), output, assembly=True, asm_isr=True,
                                 queue=32, repeat=1, flash_limit=8192 if settings['target']=='attiny88' else 32768,
                                 universal=True, normalize_output=False, target=settings['target'],
                                 sample_rate=8000, mul16_unroll=settings['unroll'], extra_flags=flags)
        build = json.loads((output / 'build.json').read_text())
        if build['input_sha256'] != row['source_sha256'] or build['input_sha256'] != baseline['source_sha256']:
            raise AssertionError('Embedded audio differs from frozen baseline')
        expected = (output / 'expected.pwm').read_bytes()
        if full.sha(output / 'expected.pwm') != baseline['portable_expected_pwm_sha256']:
            raise AssertionError('Portable reference output differs from baseline')
        valid = output / 'actual.pwm.valid'
        if valid.exists() and valid.read_bytes() != expected:
            raise AssertionError('Valid AVR PWM differs from portable reference')
        data = Path(pcm).read_bytes()
        provided_pwm = bytes(max(0, min(255, 128 + (((int.from_bytes(data[i:i+2], 'little', signed=True)+1)//2*130+8192)>>14)))
                             for i in range(0, len(data), 2))
        if provided_pwm != expected:
            raise AssertionError('Provided baseline PCM differs from portable reference')
        if result['decode_calls'] != len(expected) or result['producer_calls'] != len(expected):
            raise AssertionError('Incomplete source-sample accounting')
        row.update(status='measured', result=result,
                   embedded_audio_identical=True, portable_pwm_identical=True,
                   provided_pcm_pwm_identical=True,
                   valid_pwm_identical=valid.read_bytes()==expected if valid.exists() else result['pwm_exact'],
                   elf_sha256=full.sha(output/'player.elf'), image_sha256=build['image_sha256'],
                   portable_expected_pwm_sha256=full.sha(output/'expected.pwm'),
                   complete_actual_pwm_sha256=full.sha(output/'actual.pwm'),
                   build=build)
        row['baseline'] = baseline['result']
        row['comparison'] = {}
        for field in ('decode', 'producer'):
            old = baseline['result'][field+'_cpu_cycles']/baseline['result'][field+'_calls']
            new = result[field+'_cpu_cycles']/result[field+'_calls']
            row['comparison'][field+'_cpu_cycles_per_source_sample'] = dict(baseline=old, candidate=new, change_percent=100*(new/old-1))
        row['comparison']['program_flash_change_bytes'] = result['program_excluding_audio_bytes']-baseline['result']['program_excluding_audio_bytes']
    except Exception as error:
        row.update(status='failed', failure=full.normalized(error))
        if 'will not fit' in row['failure'] or 'overflowed by' in row['failure'] or 'Complete image is' in row['failure']:
            row['failure_kind']='physical_flash_fit'
    full.write_json(output/'case-result.json', row)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=REPO/'build/lsf1-common/baselines.json')
    parser.add_argument('--baseline', type=Path, default=REPO/'Codecs/LPX/experimental/LBG1/avr/baseline-results.json')
    parser.add_argument('--provenance', type=Path, default=REPO/'Codecs/LPX/experimental/LBG1/avr/build-provenance.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profiles', nargs='+', choices=tuple(PROFILES), default=['tiny-unroll4','tiny-unroll8','tiny-unroll16','mega-tuning7'])
    parser.add_argument('--cases', nargs='+', default=['chego-p4','bread-p6'])
    parser.add_argument('--jobs', type=int, choices=(1,2), default=2)
    args=parser.parse_args()
    output=full.safe_build(args.output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    baselines=baseline_index(args.manifest,args.baseline,args.provenance)
    selected=[row for row in full.cases_from_manifest(args.manifest) if row[0] in args.cases]
    if len(selected)!=len(set(args.cases)):
        raise ValueError('Unknown or repeated selected cases')
    output.mkdir(parents=True)
    frozen=full.freeze_inputs(selected,output)
    observer=full.prepare_observer(output)
    jobs=[(name,source,pcm,profile,str(output/name/profile),str(observer),baselines[name,PROFILES[profile]['target']])
          for name,_,source,pcm in frozen for profile in args.profiles]
    report=dict(schema='lpx-existing-settings-full-pilot-v1',
                method='Unchanged current LPX complete files and ROM player. 16 MHz/8 kHz, original Timer0/Timer1, FIFO32/prefill24, Q7 gain128, assembly ISR, explicit supported arithmetic. Only existing unroll/function-tuning selectors change. No physical board.',
                runner_sha256=full.sha(Path(__file__)), helper_sha256=full.sha(HELPER),
                baseline_report_sha256=full.sha(args.baseline), baseline_provenance_sha256=full.sha(args.provenance),
                manifest_sha256=full.sha(args.manifest), observer_sha256=full.sha(observer),
                requested_profiles=args.profiles, rows=[])
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as executor:
        pending=[executor.submit(run_one,job) for job in jobs]
        for future in concurrent.futures.as_completed(pending):
            row=future.result()
            report['rows'].append(row)
            full.write_json(output/'results.json',report)
            print(json.dumps({key:row.get(key) for key in ('case','profile','status','comparison','failure')}),flush=True)
    report['rows'].sort(key=lambda row:(row['case'],row['profile']))
    report['summary']=dict(requested=len(jobs), measured=sum(row['status']=='measured' for row in report['rows']),
                           admitted=sum(row.get('result',{}).get('accepted',False) for row in report['rows']))
    full.write_json(output/'results.json',report)
    print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':
    main()
