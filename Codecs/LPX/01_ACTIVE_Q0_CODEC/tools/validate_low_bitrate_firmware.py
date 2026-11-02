"""Admit completed low-rate corpus selections as full active-IRQ AVR players.

Only PASS completion receipts are eligible. Encoding may continue in parallel;
--wait watches for the remaining completed jobs. Every image gets exact linked
costs and an independent expanded-v5/model PWM oracle. Logs, media and source
fingerprints stay in ignored build storage; summary.json contains anonymous
case ordinals and numerical measurements only.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
from pathlib import Path
import re
import time
import traceback

import build_release_player as player
import speech_compact
import speech_sparse80
from standard_metrics import pwm_duties


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    temporary = path.with_suffix('.writing')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def completed(root, expected_samples):
    result = []
    for receipt_path in sorted(root.glob('case-*/rate-*-complete-private.json')):
        match = re.fullmatch(r'case-(\d+)', receipt_path.parent.name)
        rate = re.fullmatch(r'rate-([23])-complete-private\.json', receipt_path.name)
        if match is None or rate is None:
            continue
        try:
            receipt = load(receipt_path)
        except (json.JSONDecodeError, OSError):
            continue
        if receipt.get('status') != 'PASS':
            continue
        ordinal, kbps = int(match[1]), int(rate[1])
        if receipt['ordinal'] != ordinal or receipt['kbps'] != kbps or receipt['samples'] != expected_samples:
            raise ValueError('Completion receipt disagrees with its case or duration')
        if not receipt['source_frozen'] or not receipt['common_and_v5_only_native_exact']:
            raise ValueError('Encoder completion lacks frozen native reference checks')
        folder = receipt_path.parent / ('rate-'+str(kbps))
        report = load(folder/'report-private.json')
        selected = next(row for row in report['candidates'] if row['id'] == report['selected_id'])
        blob = (folder/'selected.lpx').read_bytes()
        if (selected['file_bytes'] != len(blob) or receipt['selected']['id'] != selected['id']
                or receipt['bytes'] != len(blob) or report['samples'] != expected_samples
                or int.from_bytes(blob[8:12], 'little') != expected_samples
                or not selected['native_reference_bridge_exact'] or not selected['admissible']
                or len(blob)*8*8000 > kbps*1000*expected_samples):
            raise ValueError('Completed selection or exact byte cap is inconsistent')
        result.append((ordinal, kbps, blob, folder/'selected.lpx'))
    return result


def verify(item, args):
    ordinal, kbps, blob, source = item
    folder = args.output / ('case-'+str(ordinal).zfill(3)) / ('rate-'+str(kbps))
    expected = pwm_duties(speech_compact.decode_model(speech_sparse80.expand(blob) if kbps == 2 else blob)).tobytes()
    result = player.simulate([blob], folder, args.avr_bin, args.observer,
        queue=256, assembly=True, sparse80=kbps == 2, lib=args.lib, wsl=args.wsl,
        expected_pwm=expected, require_valid=False)
    if source.read_bytes() != blob:
        raise ValueError('Selected stream changed during admission')
    cost, timing = result['cost'], result['report']
    private = dict(ordinal=ordinal, kbps=kbps, stream_sha256=hashlib.sha256(blob).hexdigest(),
                   verification=result)
    save(folder/'admission-private.json', private)
    return dict(ordinal=ordinal, kbps=kbps, passed=result['passed'],
        samples=timing['played'], audioBytes=len(blob), fullFlashBytes=cost['flash_bytes'],
        programFlashBytes=cost['program_flash_bytes'], staticSramBytes=cost['static_sram_bytes'],
        peakStackBytes=2303-timing['minimum_stack_pointer_all'],
        freeSramAtPeakBytes=timing['stack_margin_all_bytes'],
        queueBytes=cost['queue'], prefillSamples=cost['prefill'],
        completePwmExact=(folder/'valid.pcm8').read_bytes() == expected,
        underruns=timing['underruns'], decoderError=timing['decoder_error'],
        observerErrors=timing['observer_errors'], minimumQueueBeforeEof=timing['min_queue_before_producer_eof'],
        timerIntervalCycles=[timing['tick_interval_min_cycles'],timing['tick_interval_max_cycles']],
        totalCycles=timing['total_cycles'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['corpus-ready-dir', 'output', 'avr-bin', 'observer', 'lib']:
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--wsl')
    parser.add_argument('--cases', type=int, default=27)
    parser.add_argument('--samples', type=int, default=32000)
    parser.add_argument('--workers', type=int, choices=[1, 2], default=2)
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    if args.cases < 1 or args.samples < 1:
        parser.error('Positive case and sample counts required')
    for name in ['corpus_ready_dir', 'output', 'avr_bin', 'observer', 'lib']:
        setattr(args, name, getattr(args, name).resolve())
    player.guard(args.output)
    rows, failures, submitted, active = {}, {}, set(), {}
    expected_jobs = args.cases*2

    def summary():
        output = dict(schemaVersion=1, scope='Full production ASM players of completed selected streams',
            target='ATmega328P', cpuHz=16000000, sampleHz=8000, pwmHz=62500,
            compiler='AVR-GCC 7.3.0', simulator='simavr1.6', includesInterrupts=True,
            physicalBoardTested=False, expectedJobs=expected_jobs,
            completedJobs=len(rows), passedJobs=sum(row['passed'] for row in rows.values()),
            failedJobs=sum(not row['passed'] for row in rows.values())+len(failures),
            complete=len(rows)+len(failures)==expected_jobs,
            measurements=[rows[key] for key in sorted(rows)],
            failures=[dict(ordinal=key[0],kbps=key[1],reason='Admission exception; inspect ignored job log') for key in sorted(failures)])
        save(args.output/'summary.json', output)
        return output

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while True:
            for item in completed(args.corpus_ready_dir, args.samples):
                key = item[:2]
                if item[0] >= args.cases:
                    raise ValueError('Unexpected corpus case ordinal')
                if key not in submitted and len(active) < args.workers:
                    submitted.add(key)
                    active[pool.submit(verify, item, args)] = key
            if active:
                finished, _ = wait(active, timeout=5, return_when=FIRST_COMPLETED)
                for future in finished:
                    key = active.pop(future)
                    try:
                        rows[key] = future.result()
                        print('PASS' if rows[key]['passed'] else 'FAIL', 'case-'+str(key[0]).zfill(3), 'rate-'+str(key[1]), flush=True)
                    except Exception:
                        failures[key] = True
                        (args.output/('case-'+str(key[0]).zfill(3)+'-rate-'+str(key[1])+'-failure-private.log')).write_text(traceback.format_exc(), encoding='utf-8')
                        print('FAIL', 'case-'+str(key[0]).zfill(3), 'rate-'+str(key[1]), flush=True)
                state = summary()
            else:
                state = summary()
                if not args.wait or len(submitted) == expected_jobs:
                    break
                time.sleep(5)
            if len(rows)+len(failures) == expected_jobs:
                break
    if state['failedJobs']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
