// Listening comparison, not a perceptual quality score. Both execute actual HEX.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRenderer} from '../web-player/lib/engines.js';
const root=new URL('../',import.meta.url),name=process.argv[2]||'greensleeves';
if(!/^[a-z0-9-]+$/.test(name))throw Error('Invalid song name');
const output=path.resolve(process.argv[3]||'build/universal/listening');fs.mkdirSync(output,{recursive:true});
const versions=[['legacy',new URL('ATtiny88/Music/variants/'+name+'/',root)],['um88',new URL('ATtiny88/Music/universal/songs/'+name+'/',root)]];
const report={song:name,comparison:'Same retained arrangement; actual AVR execution, mono 48 kHz PCM, 4 kHz player filter, unity volume, no normalization',
 hardwareTested:false,interpretation:'Numerical levels are descriptive. Different synthesis rates, phase rounding and startup queues prevent bit-identical audio; listen to attacks, balance and upper harmonics.',versions:[]};
for(const [label,folder] of versions){
 const meta=JSON.parse(fs.readFileSync(new URL('build-report.json',folder))),binary=fs.readFileSync(new URL('synth.bin',folder));
 const hash=createHash('sha256').update(binary).digest('hex');if(hash!==meta.flashSha256)throw Error('Stale firmware');
 const entry={device:'attiny88',audioChannels:1,cpuHz:meta.cpuHz,pwmHz:meta.pwmHz,
  flashHex:fs.readFileSync(new URL('synth.hex',folder),'utf8'),
  ...(label==='legacy'?{eepromHex:fs.readFileSync(new URL('eeprom.hex',folder),'utf8')}:{})};
 if((meta.channels??meta.audioChannels)!==1)throw Error('Listening comparison is mono');
 const renderer=await createRenderer(entry,48000,{volume:1,cutoff:4000},'wasm');
 const count=48000*8,wave=Buffer.alloc(44+count*2);let at=0,peak=0,square=0,sum=0,clipped=0;
 wave.write('RIFF');wave.writeUInt32LE(36+count*2,4);wave.write('WAVEfmt ',8);wave.writeUInt32LE(16,16);
 wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);wave.writeUInt32LE(48000,24);wave.writeUInt32LE(96000,28);
 wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(count*2,40);
 while(at<count){
  const pcm=renderer.render(Math.min(4096,count-at));
  for(const x of pcm){
   peak=Math.max(peak,Math.abs(x));square+=x*x;sum+=x;if(Math.abs(x)>=1)clipped++;
   wave.writeInt16LE(Math.round(Math.max(-1,Math.min(1,x))*32767),44+at*2);at++;
  }
 }
 const filename=name+'-'+label+'.wav';fs.writeFileSync(path.join(output,filename),wave);
 report.versions.push({label,file:filename,flashSha256:hash,cpuHz:meta.cpuHz,synthesisHz:meta.synthesisHz,
  seconds:8,peak,rms:Math.sqrt(square/count),mean:sum/count,clippedPcmSamples:clipped});
}
fs.writeFileSync(path.join(output,'comparison.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
