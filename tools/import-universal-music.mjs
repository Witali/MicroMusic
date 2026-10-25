// Import the retained, already arranged music into a device-independent control tape.
// Execute only the sequencer: no MIDI binary and no audio samples are retained.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {AVRCore} from '../web-player/lib/avr-reference.js';
import {VARIANTS} from './audit-attiny88-music.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const word=(a,p)=>a[p]|a[p+1]<<8;
const hash=a=>createHash('sha256').update(a).digest('hex');

export function importSong(name){
 const folder=path.join(root,'ATtiny88/Music/variants',name);
 const meta=JSON.parse(fs.readFileSync(path.join(folder,'build-report.json')));
 const rom=fs.readFileSync(path.join(folder,'synth.bin')),ep=fs.readFileSync(path.join(folder,'eeprom.bin'));
 assert.equal(hash(rom),meta.flashSha256);assert.equal(hash(ep),meta.eepromSha256);
 const c=new AVRCore(rom,ep,{target:'attiny88',fastIdle:false,fastBlocks:false});
 const labels=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
 while(c.pc!==labels.idle){c.step();assert.ok(c.cyc<100000);}
 c.i=0;c.data[0x81]=0;c.updateTimer();
 const poly=name.endsWith('-polyphonic')||name.endsWith('-sparse');
 const addresses=meta.memory.voiceAddresses,frames=[];
 const verified=JSON.parse(fs.readFileSync(path.join(folder,'verification.json'))).port;
 assert.equal(hash(rom),verified.flashSha256);
 const lastTick=verified.firstRestartControlTick,ticksHash=createHash('sha256');
 const hasDrum=['rhythmic','lumiere-stereo','cancion-del-mariachi','cancion-del-mariachi-sparse'].includes(name);
 const snapshot=()=>({voices:addresses.map((a,i)=>({
  envelope:poly?c.r[i<(name.endsWith('-sparse')?3:2)?4:5]:c.data[a],
  step:word(c.data,a+meta.memory.frequencyOffset),
 })),drum:poly?c.r[6]:c.r[20],beat:c.r[19],phase:c.r[poly?22:14]});
 frames.push(snapshot());
 let envelopeResults;
 const originalWrite=c.writeData.bind(c);
 c.writeData=(address,value)=>{
  const index=addresses.indexOf(address);
  if(!poly&&index>=0&&envelopeResults[index]===undefined)envelopeResults[index]=value;
  return originalWrite(address,value);
 };
 for(let tick=1;tick<=verified.controlTicks;tick++){
  envelopeResults=[];let group=0;
  if(hasDrum){c.r[poly?22:14]=123;c.r[poly?7:5]=117;}
  addresses.forEach((a,i)=>{const p=a+(poly?0:1);c.data[p]=17+i;c.data[p+1]=80+i;});
  c.pushPC(labels.idle);c.pc=labels.music_tick;
  const start=c.cyc;
  do {
   if(poly&&c.pc===labels.envelope_return){
    addresses.forEach((a,i)=>{if((i<(name.endsWith('-sparse')?3:2)?0:1)===group)envelopeResults[i]=c.r[20];});group++;
   }
   c.step();assert.ok(c.cyc-start<20000,`${name}: sequencer failed to return`);
  }while(c.pc!==labels.idle);
  // Independently recorded full-audio execution is the extraction oracle.
  const voices=addresses.map(a=>poly?[word(c.data,a+meta.memory.frequencyOffset)]:
   [c.data[a],word(c.data,a+meta.memory.frequencyOffset)]);
  const envelopes=poly?[c.r[4],c.r[5],...(name.endsWith('-sparse')?[c.r[6]]:[])]:[];
  ticksHash.update(JSON.stringify({voices,envelopes})+'\n');
  if(tick>lastTick)continue;
  const frame=snapshot();
  frame.envelopeResults=envelopeResults;
  if(hasDrum){
   if(c.r[poly?22:14]!==123)frame.drumReset=c.r[poly?22:14];
   if(c.r[poly?7:5]!==117)frame.noiseReset=c.r[poly?7:5];
  }
  frame.phaseOps=addresses.map((a,i)=>{
   const value=word(c.data,a+(poly?0:1));
   if(value===0)return -1;
   const from=addresses.findIndex((_,j)=>value===((17+j)|((80+j)<<8)));
   assert.ok(from>=0,`${name}: unknown phase transition ${value}`);return from;
  });
  frames.push(frame);
 }
 assert.equal(ticksHash.digest('hex'),verified.snapshotSha256,`${name}: extraction matches full-audio legacy snapshots`);
 return {schema:'micromusic-control-tape',version:1,name,controlHz:18750/256,
  source:{flashSha256:hash(rom),eepromSha256:hash(ep)},endTick:lastTick,
  channels:meta.audioChannels,hasDrum,poly,eeprom:[...ep],frames};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const names=process.argv.slice(2);
 for(const name of names.length?names:VARIANTS){
  const song=importSong(name),folder=path.join(root,'build/universal');fs.mkdirSync(folder,{recursive:true});
  fs.writeFileSync(path.join(folder,name+'.tape.json'),JSON.stringify(song));
  console.log(`${name}: ${song.frames.length} control frames`);
 }
}
