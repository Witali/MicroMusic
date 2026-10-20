// Offline reference capture from the original FluidR3 SF2, one direct render
// per note. The SoundFont and its renderer are external, pinned source inputs.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,list)=>i%2 ? a : [...a,[v.replace(/^--/,''),list[i+1]]],[]));
if (!args.soundfont || !args.engine || !args.output) throw new Error('Usage: node tools/render-fluid-violin.mjs --soundfont FluidR3_GM.sf2 --engine spessasynth.js --output build/fluid-violin/reference');
const hash=b=>createHash('sha256').update(b).digest('hex');
const font=fs.readFileSync(args.soundfont),expected='74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0';
if (hash(font)!==expected) throw new Error('Expected original FluidR3 GM 3.1 SHA-256');
const {SoundBankLoader,SpessaSynthProcessor,SpessaLog}=await import(pathToFileURL(path.resolve(args.engine)).href);
SpessaLog.setLogLevel(false,false,false);
const bank=SoundBankLoader.fromArrayBuffer(font.buffer.slice(font.byteOffset,font.byteOffset+font.byteLength));
const profile=args.profile || 'violin', programs={violin:40,piano:0,guitar:24,drums:0};
if (!(profile in programs)) throw new Error('Profile must be violin, piano, guitar or drums');
const channel=profile==='drums'?9:0;
const program=args.program===undefined?programs[profile]:Number(args.program);
if(!Number.isInteger(program)||program<0||program>127)throw Error('Program must be 0..127');
const sampleRate=48000,gate=Number(args.gate || .85),tail=Number(args.tail || .45),velocity=100;
const notes=args.notes ? args.notes.split(',').map(Number) : [52,55,62,69,74];
if (![gate,tail].every(v=>Number.isFinite(v)&&v>0&&v<=10) || !notes.every(n=>Number.isInteger(n)&&n>=0&&n<=127)) throw new Error('Invalid capture range');
const synth=new SpessaSynthProcessor(sampleRate,{effectsEnabled:false,eventsEnabled:false,maxBufferSize:128});
synth.soundBankManager.addSoundBank(bank,'fluidr3');await synth.processorInitialized;synth.programChange(channel,program);
fs.mkdirSync(args.output,{recursive:true});
const manifest={soundfont:{name:'FluidR3 GM',version:'3.1',bytes:font.length,sha256:expected,license:'MIT'},
  renderer:{name:'SpessaSynth',sourceSha256:hash(fs.readFileSync(args.engine)),sampleRate,effectsEnabled:false},
  program,channel,profile,preset:synth.synthCore.midiChannels[channel].preset.name,velocity,gateSeconds:gate,tailSeconds:tail,
  conversion:'Each note directly from original SF2 PCM to 48000 Hz; no intermediate-rate source. Stereo and SF2 envelopes retained. No per-note normalization.',notes:[]};
function wav(pcm) {
  const b=Buffer.alloc(44+pcm.length*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);
  b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(2,22);b.writeUInt32LE(sampleRate,24);
  b.writeUInt32LE(sampleRate*4,28);b.writeUInt16LE(4,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(pcm.length*2,40);
  for(let i=0;i<pcm.length;i++)b.writeInt16LE(Math.max(-32768,Math.min(32767,Math.round(pcm[i]*32767))),44+i*2);
  return b;
}
for (const note of notes) {
  synth.stopAllChannels(true);
  const voices=synth.synthCore.getVoices(channel,note,velocity);
  const layers=voices.map(v=>({rootKey:v.rootKey,targetKey:v.targetKey,sampleFrames:v.sampleData.length,
    sourceRateHz:v.playbackStep*sampleRate,loopStart:v.loopStart,loopEnd:v.loopEnd,
    volumeGenerators:Array.from(v.generators).slice(33,41)}));
  const count=Math.round((gate+tail)*sampleRate),pcm=new Float32Array(count*2),l=new Float32Array(128),r=new Float32Array(128);
  synth.noteOn(channel,note,velocity);
  for(let offset=0;offset<count;) {
    if(offset===Math.round(gate*sampleRate))synth.noteOff(channel,note);
    const n=Math.min(128,count-offset,offset<gate*sampleRate ? Math.round(gate*sampleRate)-offset : count-offset);
    l.fill(0);r.fill(0);synth.process(l,r,0,n);
    for(let j=0;j<n;j++){pcm[(offset+j)*2]=l[j];pcm[(offset+j)*2+1]=r[j];}
    offset+=n;
  }
  const bytes=wav(pcm),file=`${profile}-${note}.wav`;fs.writeFileSync(path.join(args.output,file),bytes);
  manifest.notes.push({midi:note,file,sha256:hash(bytes),layers});
  console.log(`${manifest.preset} MIDI ${note}: ${bytes.length} bytes`);
}
synth.stopAllChannels(true);
fs.writeFileSync(path.join(args.output,'capture.json'),JSON.stringify(manifest,null,2)+'\n');
