"""Create original/before/after WAVs from canonical input and actual AVR output.

Individual WAVs preserve their original levels and PCM. A fourth sequential
comparison uses the same 70 Hz high-pass and RMS matching as speech research.
All generated audio belongs in an ignored build directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from refine_period_helpers import atomic_json,matched_audio

CAPTURE = r"""
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const [root,output]=process.argv.slice(1);
const hash=x=>createHash('sha256').update(x).digest('hex');
const load=path=>JSON.parse(fs.readFileSync(root+'/'+path,'utf8'));
const {parseHex}=await import(pathToFileURL(root+'/web-player/lib/hex.js'));
const {AVRCore:JS}=await import(pathToFileURL(root+'/web-player/lib/avr-reference.js'));
const {AVRCore:Wasm}=await import(pathToFileURL(root+'/web-player/lib/avr-core.js'));
const catalog=load('web-player/hq4-firmware.json');
const entry=catalog.entries.find(e=>e.id==='hq4-chego-auto');
assert.ok(entry,'Retained public HQ4-T Auto is missing');
const frozen=load('ATtiny13A/Sound/codec/timbre/chego-auto/verification.json');
const image=parseHex(entry.flashHex);
assert.equal(hash(image),entry.flashSha256);
assert.equal(hash(image),frozen.imageSha256);
const cores=[new JS(image),new Wasm(image)];
const pcm=Buffer.alloc(frozen.samples);
for(let i=0;i<pcm.length;i++){
  pcm[i]=cores[0].nextDuty();
  assert.equal(cores[1].nextDuty(),pcm[i],`Old firmware PCM mismatch at ${i}`);
}
assert.equal(hash(pcm),frozen.pcmSha256);
assert.equal(hash(pcm.subarray(0,frozen.phraseSamples)),frozen.firstLoopPcmSha256);
for(const c of cores){assert.equal(c.lost,0);assert.equal(c.workLost,0);}
fs.writeFileSync(output,pcm.subarray(0,frozen.phraseSamples));
console.log(JSON.stringify({id:entry.id,flashBytes:image.length,
  imageSha256:hash(image),pcmSha256:hash(pcm),firstLoopPcmSha256:frozen.firstLoopPcmSha256,
  verifiedSamples:pcm.length,engines:['JS','WASM']}));
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pwm_wav(path,pcm):
    with wave.open(str(path),'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(7500)
        handle.writeframes(pcm)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--firmware',required=True,type=Path,help='Verified tiny firmware output directory')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--node',default='node')
    args=parser.parse_args()
    clip=next(c for c in json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
              if c['id']=='chego')
    if sha(args.reference.read_bytes())!=clip['sha256']:
        raise ValueError('Original audio does not match canonical chego SHA-256')
    report=json.loads((args.firmware/'build.json').read_text(encoding='utf-8'))
    verification=report.get('verification') or {}
    if report['status']!='verified' or not verification.get('pass'):
        raise ValueError('After audio requires a successfully verified firmware image')
    for name,key in [('firmware.bin','imageSha256'),('eeprom.bin','eepromSha256')]:
        if sha((args.firmware/name).read_bytes())!=report[key]:
            raise ValueError('After firmware/EEPROM files do not match their build report')
    after=(args.firmware/'actual.raw').read_bytes()
    if sha(after)!=verification['actualPcmSha256'] or len(after)!=verification['verifiedSamples']:
        raise ValueError('Captured AVR output does not match its verification report')
    samples=report['phraseSamples']
    after=after[:samples]
    original,sr=sf.read(args.reference)
    if sr!=7500 or original.shape!=(samples,):
        raise ValueError('Listening clips must have the same mono duration at 7500 Hz')
    args.output.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([args.node,'--input-type=module','--eval',CAPTURE,str(ROOT),
                           str((args.output/'before.raw').resolve())],check=True,capture_output=True,text=True)
    before_report=json.loads(result.stdout)
    before=(args.output/'before.raw').read_bytes()
    if len(before)!=samples:
        raise ValueError('Before/after duration differs')
    shutil.copyfile(args.reference,args.output/'01-original.wav')
    pwm_wav(args.output/'02-before-hq4-t-auto.wav',before)
    pwm_wav(args.output/'03-after-tiny.wav',after)
    audio=lambda data:(np.frombuffer(data,np.uint8).astype(float)-128)/128
    matched=args.output/'matched'
    matched.mkdir(exist_ok=True)
    matched_audio(matched,dict(Original=original,Before=audio(before),After=audio(after)),
                  SpectralObjective(original,sr),('Original','Before','After'))
    shutil.copyfile(matched/'comparison.wav',args.output/'04-comparison-matched.wav')
    files={path.name:dict(bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
           for path in sorted(args.output.glob('*.wav'))}
    listening=dict(schema='tiny-speech-listening-v1',clip='chego',sampleRate=sr,phraseSamples=samples,
                   originalSha256=clip['sha256'],originalFileExact=True,before=before_report,
                   after=dict(flashBytes=report['flashBytes'],eepromBytes=report['eepromUsedBytes'],
                              imageSha256=report['imageSha256'],eepromSha256=report['eepromSha256'],
                              pcmSha256=sha(after),allLoopsPcmSha256=verification['actualPcmSha256'],
                              engines=verification['engines'],verifiedLoops=report['verifiedLoops']),
                   individualProcessing='Original file copied byte-for-byte; before/after are exact unsigned8 DAC samples.',
                   comparisonProcessing='Original, Before, After: common 70Hz highpass, matched RMS, common peak scaling, 0.3s pauses.',
                   normalizedSourceSha256=sha(Path(__file__).read_text(encoding='utf-8').encode()),files=files)
    atomic_json(args.output/'listening.json',listening)
    print(json.dumps(listening,indent=2))


if __name__=='__main__':
    main()
