"""Retain compact, auditable whole-file LG1 versus current LPX results.

Run after the encoder, full AVR matrix and controls. Source audio, binaries,
ELFs and raw simulation logs stay in ignored build/. This report preserves
every comparison row, input digest, relevant timing/memory metric and failure.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
FIELDS = '''samples ticks decode_calls producer_calls decode_cpu_cycles producer_cpu_cycles
    first_output_cycle last_output_cycle underruns min_queue sample_period_cycles actual_sample_hz
    irq_mean irq_max output_gap_min output_gap_max timer_event_gap_min timer_event_gap_max
    decode_cpu_mean decode_cpu_max decode_max decode_active_cpu_mean
    producer_cpu_mean producer_cpu_max producer_active_cpu_mean producer_active_cpu_max
    flash_bytes embedded_audio_bytes program_excluding_audio_bytes static_ram_bytes
    stack_bytes stack_margin total_static_and_observed_stack_bytes physical_sram_margin_bytes
    accepted pwm_exact valid_pwm_exact_when_available provided_pcm_pwm_exact
    hard_flash_fit tiny_standard_bootloader_fit fits_standard_bootloader
    valid_pwm_exact provided_pcm_exact eof error irq_registers_preserved'''.split()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(relative):
    return json.loads((REPO / relative).read_text())


def compact_row(row):
    result = {key: row[key] for key in ('case', 'variant', 'codec', 'target', 'backend',
              'repeat', 'status', 'source_sha256', 'failure_kind') if key in row}
    result.update({key: value for key, value in row.get('result', row.get('metrics', {})).items()
                   if key in FIELDS})
    return result


def weighted(rows, key):
    # Observer samples/ticks include inserted silence on an underrun. Weight
    # actual decoded source samples, so a slower file cannot gain extra weight.
    count = 'producer_calls' if key.startswith('producer_') else 'decode_calls'
    if key in ('producer_cpu_mean', 'decode_cpu_mean'):
        total = key.replace('_mean', '_cycles')
        return sum(r[total] for r in rows) / sum(r[count] for r in rows)
    return sum(r[count] * r[key] for r in rows) / sum(r[count] for r in rows)


def main():
    paths = dict(encoder='build/lbg1-encoder/manifest.json',
                 baseline='build/lbg1-avr/baseline-v1/results.json',
                 lg='build/lbg1-avr/lg-matrix-v2/results.json',
                 controls='build/lbg1-avr/controls-v2/results.json',
                 sanitizer='build/lbg1-validation/receipt.json',
                 observer='build/lbg1-avr/baseline-v1/observer-equivalence/proof.json',
                 encoder_validation='build/lbg1-encoder/encoder-validation.json',
                 sources='build/lbg1-common/sources.json')
    data = {key: read(path) for key, path in paths.items()}
    if len(data['encoder']['cases']) != 8 or len(data['baseline']['rows']) != 32 or len(data['lg']['rows']) != 96:
        raise ValueError('Comparison matrix is incomplete')
    if len(data['controls']['rows']) != 22:
        raise ValueError('Full player controls are incomplete')
    if any(row['status'] != 'measured' or not row['result']['valid_pwm_exact']
           for row in data['controls']['rows']):
        raise ValueError('A full player control failed output validation')
    avr = [compact_row(row) for key in ('baseline', 'lg') for row in data[key]['rows']]
    cases = []
    for case in data['encoder']['cases']:
        for item in [case['baseline'], *case['variants'].values()]:
            if sha(REPO / item['path']) != item['sha256']:
                raise ValueError('Comparison input changed')
        cases.append(dict(name=case['name'], reference_sha256=case['reference_sha256'],
                          baseline=case['baseline'], variants=case['variants']))
    pairs = []
    for target in ('attiny88', 'atmega328p'):
        for backend in ('asm', 'c'):
            for variant in ('exact', 'fine', 'compact'):
                selected = [r for r in avr if r.get('codec') == 'lg1' and r['target'] == target
                            and r['backend'] == backend and r['variant'] == variant and r['status'] == 'measured']
                names = {r['case'] for r in selected}
                baseline = [r for r in avr if r.get('codec') == 'baseline' and r['target'] == target
                            and r['backend'] == backend and r['case'] in names]
                if len(baseline) != len(selected):
                    raise ValueError('Missing matched baseline')
                entry = dict(target=target, backend=backend, variant=variant,
                             paired_files=len(selected), full_files_requested=8,
                             real_time_files=sum(r['accepted'] for r in selected),
                             flash_failures=8-len(selected), case_names=sorted(names))
                for key in ('decode_cpu_mean', 'producer_cpu_mean'):
                    old, new = weighted(baseline, key), weighted(selected, key)
                    entry[key] = dict(lpx=old, lg1=new, change_percent=(new/old-1)*100)
                # Foreground work plus measured ISR body/entry/return per output
                # sample at the requested 8 kHz. For underrunning C/Tiny this
                # is an estimate: the observed empty-FIFO ISR is cheaper.
                entry['required_cpu_percent_estimate'] = {
                    'lpx': (weighted(baseline, 'producer_cpu_mean') + weighted(baseline, 'irq_mean')) / 20,
                    'lg1': (weighted(selected, 'producer_cpu_mean') + weighted(selected, 'irq_mean')) / 20}
                pairs.append(entry)
    summaries = data['encoder']['summaries']
    for entry in summaries.values():
        entry['file_size_change_percent'] = (entry['bytes']/entry['baseline_bytes']-1)*100
        entry['pcm_sse_change_percent'] = (entry['pcm_sse']/entry['baseline_pcm_sse']-1)*100
        entry['mean_pcm_stoi_delta'] = entry['mean_pcm_stoi']-entry['mean_baseline_pcm_stoi']
    receipt = data['sanitizer']
    sanitizers = {key: json.loads(value['stdout']) for key, value in receipt['tests'].items()}
    # Controls are compacted in the same way; retain layout evidence proving
    # real AVR memory macros and explicitly selectable C arithmetic coexist.
    controls = []
    for row in data['controls']['rows']:
        compact = compact_row(row)
        for key in ('selection', 'layout', 'passed', 'source_bytes'):
            if key in row:
                compact[key] = row[key]
        controls.append(compact)
    report = dict(schema='lbg1-whole-decoder-comparison-v1', date='2026-11-26',
                  baseline_revision='24fd9416', physical_board_measured=False,
                  method=data['lg']['method'],
                  quality_scope='Four source clips, P4/P6, current calls4. STOI/SSE/full-band diagnostics; no blinded listening test.',
                  paired_cpu_scope='Decoded-source-sample-weighted complete files that fit each target/backend. Missing Flash rows are never simulated; see paired case names. Required CPU includes measured mean ISR cost and is an estimate for underrunning C/Tiny, whose empty FIFO ISR branch is cheaper.',
                  inputs=data['sources'], file_quality_summaries=summaries,
                  cases=cases, avr_rows=avr, paired_cpu=pairs,
                  controls=controls, sanitizer=sanitizers, observer_equivalence=data['observer'],
                  source_receipts={key: dict(path=path, sha256=sha(REPO/path)) for key, path in paths.items()},
                  encoder_build=data['encoder']['build'],
                  decoder_snapshot=read('build/lbg1-avr/lg-matrix-v2/stage.json')['decoder_inputs'])
    validation = data['encoder_validation']
    report['encoder_validation'] = {key: value for key, value in validation.items() if key != 'build'}
    builds = {}
    for run in ('baseline-v1', 'lg-matrix-v2'):
        for target in ('attiny88', 'atmega328p'):
            for backend in ('asm', 'c'):
                variant = 'baseline' if run == 'baseline-v1' else 'compact'
                cost = read(f'build/lbg1-avr/{run}/chego-p4/{variant}/{target}/{backend}/build.json')
                selected = {key: cost[key] for key in ('compiler', 'compiler_options', 'source_sha256',
                            'cpu_hz', 'sample_hz', 'queue', 'prefill')}
                selected['compiler_options'] = [value.replace(str(REPO) + '/', '<repo>/')
                                                 for value in selected['compiler_options']]
                builds[f'{run}/{target}/{backend}'] = selected
    report['avr_representative_builds'] = builds
    refit_path = REPO / 'build/lbg1-encoder/refit-manifest.json'
    if refit_path.exists():
        refit = json.loads(refit_path.read_text())
        if len(refit.get('cases', [])) == 8 and 'summaries' in refit:
            report['optional_refit'] = dict(summaries=refit['summaries'],
                cases=refit['cases'], sha256=sha(refit_path),
                scope='Whole-output admitted pulse changes only; not part of frozen AVR matrix.')
    destination = HERE / 'results.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(file_quality=summaries, paired_cpu=pairs,
                         avr=data['lg']['summary'], sanitizer=sanitizers), indent=2))


if __name__ == '__main__':
    main()
