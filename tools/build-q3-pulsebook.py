"""Build Q3/T1 with four signed 16-sample excitation templates in EEPROM.

EEPROM stores only the64-byte pulsebook; the complete speech stream and EOF
remain in Flash. Both HEX files must be programmed together. No quality claim
is inferred from an execution/size pass.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from q3_pulsebook import render

spec = importlib.util.spec_from_file_location('pulsebook_hq4_helpers', ROOT/'tools/build-hq4-oneshot.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
run, parse_symbols, intel_hex = helpers.run, helpers.parse_symbols, helpers.intel_hex


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_table(table_path):
    path = Path(table_path)
    data = path.read_bytes()
    if path.suffix.lower() == '.json':
        value = json.loads(data)
        if isinstance(value, dict):
            value = value.get('pulsebook')
        array = np.asarray(value)
        if array.shape != (4, 16) or array.dtype.kind not in 'iu':
            raise ValueError('Pulsebook JSON must contain exactly4x16 integer coefficients')
        if np.any(array < -7) or np.any(array > 7):
            raise ValueError('Pulsebook coefficients must be in[-7,7]')
        return array.astype(np.int8)
    if len(data) != 64:
        raise ValueError('Raw signed pulsebook must contain exactly64 bytes')
    array = np.frombuffer(data, np.int8).reshape(4, 16)
    if np.any(array < -7) or np.any(array > 7):
        raise ValueError('Pulsebook coefficients must be in[-7,7]')
    return array.copy()


def load_stream(stream, table, expected_samples=None, *, rounded=False):
    payload = Path(stream).read_bytes()
    core = 410 if rounded else 408
    maximum = 1024-core-1
    if not 1 <= len(payload) <= maximum:
        raise ValueError(f'Pulsebook Q3 requires1..{maximum} stream bytes')
    frames, durations = helpers.validate_stream(payload)
    samples = int(durations.sum())
    if expected_samples is not None and (isinstance(expected_samples, bool) or
            not isinstance(expected_samples, int) or expected_samples <= 0 or expected_samples != samples):
        raise ValueError('Stream must preserve the complete requested recording duration')
    if np.any((frames[:, 2:] & 15) == 0) or np.any((frames[:, 2:] >> 4) == 0):
        raise ValueError('Q3 coefficient-8 is excluded from the stable reflection range')
    phrase, wraps = render(frames, durations, table, tilt_shift=1, nearest=rounded)
    return payload, phrase, wraps


def build(stream_path, table_path, output, avr_bin=None, node='node', *, rounded=False, expected_samples=None):
    table = load_table(table_path)
    payload, phrase, wraps = load_stream(stream_path, table, expected_samples, rounded=rounded)
    samples = len(phrase)
    core = 410 if rounded else 408
    template = CODEC/'q3-pulsebook'/('hq4-t1-rounded.S' if rounded else 'hq4-t1.S')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('firmware.elf','firmware.bin','firmware.hex','eeprom.hex','verification.json','actual.raw','build.json'):
        (output/name).unlink(missing_ok=True)
    expected = np.r_[phrase, np.full(samples*2, 128, np.uint8)]
    eeprom = table.tobytes()
    shutil.copyfile(template, output/'firmware.S')
    (output/'speech.hq').write_bytes(payload)
    (output/'eeprom.bin').write_bytes(eeprom)
    (output/'eeprom.hex').write_text(intel_hex(eeprom), encoding='ascii', newline='\n')
    (output/'expected.raw').write_bytes(expected.tobytes())
    suffix = '.exe' if os.name == 'nt' else ''
    def executable(name):
        return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name
    compiler = executable('avr-gcc')
    version = run([compiler,'--version'], output).stdout.splitlines()[0]
    run([compiler,'-mmcu=attiny13','-nostdlib','-x','assembler','-c','firmware.S','-o','firmware.o'], output)
    symbols = parse_symbols(run([executable('avr-nm'),'-n','firmware.o'], output).stdout)
    sections = run([executable('avr-objdump'),'-h','firmware.o'], output).stdout
    match = re.search(r'^\s*\d+\s+\.text\s+([0-9a-fA-F]+)\b', sections, re.MULTILINE)
    if not match or not all(name in symbols for name in ('code_end','voice_data','STACK_FLOOR','wait_slot')):
        raise ValueError('Unexpected pulsebook Q3 code layout')
    object_bytes = int(match[1], 16)
    code_bytes, voice_start = symbols['code_end'], symbols['voice_data']
    if code_bytes != core or voice_start != core or object_bytes != core+len(payload)+1:
        raise ValueError('Measured pulsebook core size or speech layout differs')
    flash_bytes = (object_bytes+1) & ~1
    if flash_bytes > 1024:
        raise ValueError('Complete pulsebook decoder and speech exceed1024 Flash bytes')
    inputs = (template,Path(__file__),CODEC/'q3_pulsebook.py',CODEC/'hq4_core.py',
              ROOT/'tools/build-hq4-oneshot.py',ROOT/'tools/build-tiny-speech.py',
              ROOT/'tools/verify-tiny-speech.mjs',ROOT/'tools/lib/tiny-work-profile.mjs')
    report = dict(schema='micromusic-q3-pulsebook-build-v1',status='pending',playbackMode='once',
        hardwareTested=False,cpuHz=9600000,sampleHz=7500,flashLimitBytes=1024,
        flashBytes=flash_bytes,objectTextBytes=object_bytes,codeBytes=code_bytes,
        dataBytes=len(payload)+1,streamBytes=len(payload),maximumStreamBytes=1024-core-1,eofBytes=1,
        linkerPaddingBytes=flash_bytes-object_bytes,codePaddingBytes=0,eepromLimitBytes=64,
        eepromBytes=64,eepromUsedBytes=64,eepromSha256=sha(eeprom),pulsebook=table.tolist(),
        pulsebookShape=[4,16],pulsebookDtype='int8-row-major',phraseSamples=samples,
        verifiedLoops=0,silenceSamplesVerified=0,compiler=version,symbols=symbols,
        coefficientScale=8,productRounding='nearest, ties toward positive infinity' if rounded else 'floor',
        tiltShift=1,streamSha256=sha(payload),sourceStreamSha256=sha(Path(stream_path).read_bytes()),
        sourceTableSha256=sha(Path(table_path).read_bytes()),phrasePcmSha256=sha(phrase.tobytes()),
        expectedPcmSha256=sha(expected.tobytes()),intermediateWraps=wraps.tolist(),imageSha256=None,
        verification=None,storagePolicy='All64EEPROM bytes are signed pulse templates; full speech and EOF in Flash; program both HEX files',
        normalizedSourceSha256={p.relative_to(ROOT).as_posix():sha(p.read_text(encoding='utf-8').encode()) for p in inputs})
    run([compiler,'-mmcu=attiny13','-nostdlib','-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
         '-Wl,-Ttext=0','-x','assembler','firmware.S','-o','firmware.elf'], output)
    run([executable('avr-objcopy'),'-O','binary','firmware.elf','firmware.bin'], output)
    image = (output/'firmware.bin').read_bytes()
    if len(image) != flash_bytes or image[voice_start:object_bytes] != payload+b'\xff' or image[object_bytes:] not in (b'',b'\x00'):
        raise ValueError('Linked pulsebook image changed speech or EOF bytes')
    report['imageSha256'] = sha(image)
    (output/'firmware.hex').write_text(intel_hex(image), encoding='ascii', newline='\n')
    (output/'disassembly.txt').write_text(run([executable('avr-objdump'),'-d','firmware.elf'], output).stdout,
                                        encoding='utf-8',newline='\n')
    command = [node,ROOT/'tools/verify-tiny-speech.mjs',output/'firmware.bin',output/'expected.raw',
        output/'verification.json','--eeprom',output/'eeprom.bin','--phrase-samples',samples,
        '--loops',3,'--playback','once','--minimum-sp',symbols['STACK_FLOOR'],
        '--wait-pc',symbols['wait_slot'],'--actual-raw',output/'actual.raw']
    checked = run(command,ROOT,check=False)
    if (output/'verification.json').exists():
        verification = json.loads((output/'verification.json').read_text(encoding='utf-8'))
        report.update(verification=verification,status='verified' if verification['pass'] else 'verification-failed',
                      verifiedLoops=verification['verifiedLoops'],silenceSamplesVerified=verification['silenceSamplesVerified'])
    else:
        report.update(status='verification-failed',verificationError=(checked.stdout+checked.stderr).strip())
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stream',type=Path,required=True)
    parser.add_argument('--table',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,required=True)
    parser.add_argument('--avr-bin',type=Path)
    parser.add_argument('--node',default='node')
    parser.add_argument('--rounded',action='store_true')
    args = parser.parse_args()
    report = build(args.stream,args.table,args.output,args.avr_bin,args.node,
                   rounded=args.rounded,expected_samples=args.samples)
    print(json.dumps({k:report[k] for k in ('status','codeBytes','flashBytes','eepromBytes','streamBytes','maximumStreamBytes')},indent=2))
    return 0 if report['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
