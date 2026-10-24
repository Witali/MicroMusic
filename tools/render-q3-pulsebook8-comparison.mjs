import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {parseArgs} from 'node:util';
import {createRenderer} from '../web-player/lib/engines.js';
import {parseHex} from '../web-player/lib/hex.js';

const {values:options}=parseArgs({options:{before:{type:'string',default:'build/q3-short-eeprom/4-raw-prefix-48'},after:{type:'string',default:'build/q3-pulsebook8/refit4/guarded/avr'},output:{type:'string',default:'build/q3-pulsebook8/listening'},'before-name':{type:'string',default:'before-four-forms'},'after-name':{type:'string',default:'after-eight-forms'}}});
const root=process.cwd(),output=path.resolve(options.output);
fs.mkdirSync(output,{recursive:true});
const read=p=>fs.readFileSync(path.join(root,p));
const json=p=>JSON.parse(read(p));
const hash=data=>createHash('sha256').update(data).digest('hex');
const base=json('web-player/hq4-firmware.json').entries.find(e=>e.id==='hq4-vinni');
const records=[[options['before-name'],options.before],[options['after-name'],options.after]];
assert.ok(records.every(([name])=>/^[a-z0-9-]+$/.test(name)),'Use simple output labels');
function wavFloat(name,data){
 const bytes=Buffer.from(data.buffer,data.byteOffset,data.byteLength),header=Buffer.alloc(44);
 header.write('RIFF');header.writeUInt32LE(bytes.length+36,4);header.write('WAVEfmt ',8);
 header.writeUInt32LE(16,16);header.writeUInt16LE(3,20);header.writeUInt16LE(1,22);
 header.writeUInt32LE(48000,24);header.writeUInt32LE(48000*4,28);header.writeUInt16LE(4,32);header.writeUInt16LE(32,34);
 header.write('data',36);header.writeUInt32LE(bytes.length,40);
 fs.writeFileSync(path.join(output,name),Buffer.concat([header,bytes]));
}
const results=[],audio=[];
for(const [name,folder] of records){
 const report=json(folder+'/build.json'),v=report.verification;
 assert.equal(report.status,'verified');assert.equal(v.pass,true);
 assert.equal(v.cpuHz,9600000);assert.equal(v.sampleHz,7500);
 assert.equal(v.phraseSamples,report.phrase_samples);assert.equal(v.verifiedSamples,report.phrase_samples*3);
 assert.deepEqual(v.engines,['reference','wasm','wasm-unoptimized']);
 const n=report.phrase_samples,image=read(folder+'/firmware.bin'),raw=read(folder+'/actual.raw');
 assert.equal(hash(image),report.firmware_sha256);assert.equal(hash(raw),v.actualPcmSha256);
 assert.equal(hash(raw.subarray(0,n)),report.phrase_pcm_sha256);
 assert.ok(raw.subarray(n).every(x=>x===128));
 const entry={...base,id:name,flashBytes:report.flash_bytes,eepromBytes:64,phraseSamples:n,flashSha256:report.firmware_sha256,eepromSha256:report.eeprom_sha256,
  flashHex:read(folder+'/firmware.hex').toString(),eepromHex:read(folder+'/eeprom.hex').toString()};
 assert.equal(hash(parseHex(entry.flashHex)),report.firmware_sha256);
 assert.equal(hash(parseHex(entry.eepromHex,64)),report.eeprom_sha256);
 const controls={cutoff:9000,volume:.65};
 const renderer=await createRenderer(entry,48000,controls,'wasm');
 const frames=Math.round((n/7500+.15)*48000),samples=new Float32Array(frames);
 for(let at=0;at<frames;at+=4096)samples.set(renderer.render(Math.min(4096,frames-at)),at);
 assert.ok(samples.every(x=>Number.isFinite(x)&&Math.abs(x)<1));
 wavFloat(name+'.wav',samples);audio.push(samples);
 results.push({file:name+'.wav',flashBytes:image.length,eepromBytes:64,controls,
  firmwareSha256:hash(image),rawPhraseSha256:hash(raw.subarray(0,n)),
  wavSha256:hash(fs.readFileSync(path.join(output,name+'.wav')))});
}
const pause=14400,comparison=new Float32Array(audio[0].length+pause+audio[1].length);
comparison.set(audio[0]);comparison.set(audio[1],audio[0].length+pause);wavFloat('before-then-after.wav',comparison);
fs.copyFileSync(path.join(root,'web-player/audio/originals/vinni.wav'),path.join(output,'original.wav'));
fs.writeFileSync(path.join(output,'listening.json'),JSON.stringify({schema:'q3-pulsebook8-listening-v1',sampleRate:48000,
 description:'Actual paired Flash/EEPROM images through unmodified site WASM renderer; same 9 kHz filter and 0.65 volume; native firmware level without extra normalization.',
 results,comparison:`${options['before-name']}, 0.3 seconds pause, ${options['after-name']}`},null,2)+'\n');
console.log(JSON.stringify(results.map(r=>({file:r.file,flash:r.flashBytes,eeprom:r.eepromBytes}))));
