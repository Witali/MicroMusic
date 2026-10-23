"""Reproduce tiny speech AVR/EEPROM boundary, arithmetic and failure checks.

Eight seeded dictionaries exercise wholly EEPROM-backed waves and every split
used during development. The real assembled image must match three execution
engines over three phrase loops. All generated files stay under ignored build/.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
spec = importlib.util.spec_from_file_location('tiny_builder', ROOT/'tools/build-tiny-speech.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

SEED = 6095
WORDS = (1, 2, 4, 5, 8, 10, 12, 16)
SOURCES = (
    Path(__file__), ROOT/'tools/build-tiny-speech.py', ROOT/'tools/verify-tiny-speech.mjs',
    ROOT/'tools/lib/tiny-work-profile.mjs',
    ROOT/'ATtiny13A/Sound/codec/tiny/firmware.S', ROOT/'ATtiny13A/Sound/codec/tiny_period.py',
    ROOT/'ATtiny13A/Sound/codec/fixed_period.py', ROOT/'ATtiny13A/Sound/codec/dc_blocker.py',
    ROOT/'web-player/lib/avr-reference.js', ROOT/'web-player/lib/avr-wasm.js', ROOT/'web-player/native/avr.c',
)


def source_hashes():
    return {str(path.relative_to(ROOT)).replace('\\','/'):
            hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest() for path in SOURCES}


def fixture(words):
    rng = np.random.default_rng(SEED)
    book = rng.integers(-7, 8, (16, 32)).tolist()
    # Constant extrema force gain, residual and DC saturation paths. Other
    # words keep varied adjacent nibbles so crossing tap31->tap0 is observable.
    book[0], book[1] = [7]*32, [-7]*32
    pitches = [128,128,129,128,130,128,131,128,132,128,133,128,134,0,255,128]
    frames = [[pitch,128 | ((i % 7+1) << 4) | (i % words),i % 16]
              for i,pitch in enumerate(pitches)]
    frames[3][1] = 0
    return dict(schema='period-fixed-v1',sample_rate=7500,samples=len(frames)*64,hop=64,
                phase_bits=4,dc_block_shift=7,initial_phase_u16=65535,noise_seed_u16=0xace1,
                frames=frames,codebook=book,noise_filters=[[0]*8 for _ in range(3)])


def save_json(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def validate(output, avr_bin=None, node='node'):
    output = Path(output).resolve()
    build_root = (ROOT/'build').resolve()
    if not output.is_relative_to(build_root):
        raise ValueError('Generated AVR validation artifacts must remain under this worktree build/')
    output.mkdir(parents=True,exist_ok=True)
    hashes = source_hashes()
    report = dict(schema='micromusic-tiny-avr-tests-v1',hardwareTested=False,
                  seed=SEED,expectedTests=len(WORDS)+2,completedTests=0,
                  normalizedSourceSha256=hashes,tests=[],error=None)
    report['pass'] = False
    try:
        total_clipped = 0
        for words in WORDS:
            folder = output/f'words-{words}'
            folder.mkdir(parents=True,exist_ok=True)
            model = fixture(words)
            save_json(folder/'model.json',model)
            result = builder.build(folder/'model.json',folder/'firmware',avr_bin,node)
            check(result['status']=='verified',f'{words} words: {result["status"]}: {result.get("verification")}')
            pcm = builder.expected_loops(model)
            clipped = int(np.count_nonzero((pcm==0) | (pcm==255)))
            total_clipped += clipped
            report['tests'].append(dict(name=f'{words}-word-layout',pass_=True,
                words=words,flashBytes=result['flashBytes'],codeBytes=result['codeBytes'],
                eepromUsedBytes=result['eepromUsedBytes'],verifiedSamples=result['verification']['verifiedSamples'],
                saturatedOutputSamples=clipped,modelSha256=result['modelSha256'],
                imageSha256=result['imageSha256'],eepromSha256=result['eepromSha256'],
                expectedPcmSha256=result['expectedPcmSha256'],verification=result['verification']))
            report['completedTests'] += 1
        check(total_clipped>0,'Extremal fixture did not exercise output saturation')
        report['saturatedOutputSamples'] = total_clipped

        # A one-word image obtains its very first nonzero sample from EEPROM.
        # Substitution with zero waves must fail immediately in the real engine.
        first = output/'words-1'/'firmware'
        bad_eeprom = output/'zero-wave-eeprom.bin'
        bad_eeprom.write_bytes(b'\x88'*64)
        mismatch_path = output/'bad-eeprom-verification.json'
        mismatch_path.unlink(missing_ok=True)
        command = [node,ROOT/'tools/verify-tiny-speech.mjs',first/'firmware.bin',first/'expected.raw',
                   mismatch_path,'--eeprom',bad_eeprom,'--phrase-samples',1024,'--loops',3,
                   '--minimum-sp',0x6a]
        negative = builder.run(command,ROOT,check=False)
        check(negative.returncode!=0 and mismatch_path.exists(),'Corrupted EEPROM was not rejected')
        mismatch = json.loads(mismatch_path.read_text(encoding='utf-8'))
        check(not mismatch['pass'] and mismatch['firstMismatch'] is not None and
              mismatch['firstMismatch']['sample']==0 and mismatch['mismatches']==1,
              f'Corrupted EEPROM did not change the first actual PWM sample: {mismatch}')
        report['tests'].append(dict(name='corrupted-eeprom-negative-control',pass_=True,
                                    expectedFailure=mismatch))
        report['completedTests'] += 1

        oversized = output/'oversized'
        oversized.mkdir(parents=True,exist_ok=True)
        model = fixture(16)
        model['frames'] *= 10
        model['samples'] = len(model['frames'])*64
        save_json(oversized/'model.json',model)
        # Stale successful products must disappear when a later build is too big.
        target = oversized/'firmware'
        target.mkdir(parents=True,exist_ok=True)
        for name in ('firmware.bin','firmware.hex','firmware.elf','verification.json','actual.raw'):
            (target/name).write_bytes(b'stale validation fixture')
        result = builder.build(oversized/'model.json',target,avr_bin,node)
        check(result['status']=='oversized' and result['flashBytes']>1024,'Oversized firmware was accepted')
        check(all(not (target/name).exists() for name in (
            'firmware.bin','firmware.hex','firmware.elf','verification.json','actual.raw')),
            'An oversized build left a stale executable or successful verification')
        report['tests'].append(dict(name='oversized-image-rejection',pass_=True,
                                    flashBytes=result['flashBytes'],flashLimitBytes=1024,
                                    modelSha256=result['modelSha256']))
        report['completedTests'] += 1
        check(hashes==source_hashes(),'Source changed during validation; rerun the fixed snapshot')
        report['pass'] = report['completedTests']==report['expectedTests']
    except Exception as error:
        report['error'] = str(error)
    save_json(output/'tests.json',report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/tiny-speech/avr-validation')
    parser.add_argument('--avr-bin',type=Path)
    parser.add_argument('--node',default='node')
    args = parser.parse_args()
    report = validate(args.output,args.avr_bin,args.node)
    print(json.dumps({key:report[key] for key in (
        'pass','seed','expectedTests','completedTests','error')},indent=2))
    print(f'Full report: {args.output.resolve()/"tests.json"}')
    return 0 if report['pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
