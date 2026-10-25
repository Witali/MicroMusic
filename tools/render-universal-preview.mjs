// PCM from execution of the shipped HEX, through the player's PWM/filter path.
import fs from 'node:fs';
import path from 'node:path';
import {universalPackageEntry} from '../web-player/lib/universal-package.js';
import {createRenderer} from '../web-player/lib/engines.js';
const folder=path.resolve(process.argv[2]),seconds=Number(process.argv[3]||8),sampleRate=48000;
if(!Number.isFinite(seconds)||seconds<.1||seconds>60)throw Error('Preview must be 0.1..60 seconds');
const entry=await universalPackageEntry(fs.readFileSync(path.join(folder,'player-package.json'),'utf8'));
const renderer=await createRenderer(entry,sampleRate,{volume:1,cutoff:4000},'wasm');
const count=Math.ceil(Math.min(seconds,entry.durationSeconds)*sampleRate),pcm=new Float32Array(count);
let at=0,peak=0,square=0,sum=0,clipped=0;
while(at<count){
 const chunk=renderer.render(Math.min(4096,count-at));pcm.set(chunk,at);at+=chunk.length;
 for(const x of chunk){peak=Math.max(peak,Math.abs(x));square+=x*x;sum+=x;if(Math.abs(x)>=1)clipped++;}
}
const wave=Buffer.alloc(44+count*2);
wave.write('RIFF');wave.writeUInt32LE(36+count*2,4);wave.write('WAVEfmt ',8);wave.writeUInt32LE(16,16);
wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);wave.writeUInt32LE(sampleRate,24);wave.writeUInt32LE(sampleRate*2,28);
wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(count*2,40);
for(let i=0;i<count;i++)wave.writeInt16LE(Math.round(Math.max(-1,Math.min(1,pcm[i]))*32767),44+i*2);
fs.writeFileSync(path.join(folder,'preview.wav'),wave);
const report={source:'Executed AVR HEX through player PWM resampling and 4 kHz filter; no normalization',
 flashSha256:entry.flashSha256,cpuHz:entry.cpuHz,sampleRate,channels:1,seconds:count/sampleRate,
 peak,rms:Math.sqrt(square/count),mean:sum/count,clippedPcmSamples:clipped,physicalRecording:false};
fs.writeFileSync(path.join(folder,'listening-report.json'),JSON.stringify(report,null,2)+'\n');
console.log('Listening preview:',JSON.stringify(report));
