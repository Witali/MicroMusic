// Function-level control regression. Full PWM/IRQ admission remains the job of
// audit-universal-music.mjs; this covers eight voices even with the C backend.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {AVRCore} from '../web-player/lib/avr-reference.js';
import {UniversalReference} from './universal-reference.mjs';

const fixtureSource=String.raw`
import importlib.util,json,sys
s=importlib.util.spec_from_file_location('control_builder','tools/build-universal-music.py')
b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
b.BASE=int(sys.argv[1]);cpu=int(sys.argv[2]);packing=sys.argv[3]
wave=list(range(16));packed=[wave[i]|(wave[i+1]<<4)for i in range(0,16,2)]
raw=[];ticks=0
for tick in range(12):
 for i in range(8):
  raw.extend([64+i,(i+tick)%8,72+i,1+(i+tick)%8])
  if tick%3!=2:raw.append(128+(i<<4)+(15-(i+tick)%4))
  if tick%3==1:raw.extend([88+i,(i+7)%8])
  elif i==tick%8:raw.append(80+i)
 raw.extend([96,128|(tick%3)|8,97,(tick*7)&255,98,1+(tick&15)])
 wait=1+(tick&1);raw.append(wait);ticks+=wait
raw.append(0)
score=dict(schema='micromusic-um88-score',version=1,name='control-ordering',voices=8,channels=2,
 waves=packed*8,contexts=[[0,i*8,3|(16 if i&1 else 0)|(64 if i&2 else 0)|(128 if i&4 else 0),128]for i in range(8)],
 envelopes=[[v for level in range(16)for v in (max(0,level-1),0x55,0xaa)]],
 pitches=[None,48,52,55,60,64,67,72,76],commands=raw,controlTicks=ticks,
 groupGain=False,normalizer=[],normalizerMinimum=0,masterShift=0,
 source=dict(kind='original deterministic control fixture',license='CC0-1.0'))
data,report=b.encode_score(score,cpu,packing)
print(json.dumps(dict(score=score,data=list(data))))
`;
const word=(data,at)=>data[at]|data[at+1]<<8;
const putWord=(data,at,value)=>{data[at]=value;data[at+1]=value>>8;};
const signed=value=>value&128?value-256:value;

export function checkControlOrdering({meta,engine,python,backend,configuration}){
 const packing=meta.packingMode||(Number.isInteger(meta.labels.packedSymbols)?'fast':'compact');
 assert.ok(Number.isInteger(meta.songAddress)&&meta.songAddress>=engine.length,'Compiled song address');
 const generated=spawnSync(python,['-c',fixtureSource,String(meta.songAddress),String(meta.cpuHz),packing],
  {encoding:'utf8',maxBuffer:4*1024*1024});
 assert.equal(generated.status,0,generated.stderr);
 const {score,data}=JSON.parse(generated.stdout),binary=new Uint8Array(meta.songAddress+data.length);
 binary.set(engine);binary.set(data,meta.songAddress);
 assert.ok(binary.length<=8192,'Control fixture fits ATtiny88 Flash');
 const core=new AVRCore(binary,null,{target:'attiny88',cpuHz:meta.cpuHz,fastIdle:false,fastBlocks:false});
 const ref=new UniversalReference(score,meta.cpuHz),state=meta.labels.um-0x800000;
 let maxCallCycles=0,checkedVoices=0,checkedWaveSamples=0;
 const call=name=>{
  assert.ok(Number.isInteger(meta.labels[name]),'Callable '+name);
  core.pushPC(0);core.pc=meta.labels[name]/2;const before=core.cyc;
  do{core.step();assert.ok(core.cyc-before<1000000,'Bounded '+name);}while(core.pc!==0);
  assert.equal(core.r[1],0);assert.equal(core.sp,767);
  maxCallCycles=Math.max(maxCallCycles,core.cyc-before);
 };
 const check=()=>{
  assert.equal(word(core.data,state+212),ref.tick,'Control time including LOOP');
  assert.equal(core.data[state+215],ref.wait,'WAIT dispatch');
  assert.equal(core.data[state+217],ref.tick&15,'Envelope phase including LOOP');
  assert.equal(core.data[state+218],ref.drumMode,'Percussion command order');
  assert.equal(core.data[state+219],ref.drumPhase,'Percussion phase reset');
  assert.equal(core.data[state+220],ref.noiseHigh,'LFSR phase reset');
  for(let i=0;i<8;i++){
   const at=state+i*23,v=ref.voices[i];
   assert.equal(word(core.data,at),v.phase,'Sequential phase-copy/reset voice '+i);
   assert.equal(word(core.data,at+2),v.step,'Pitch voice '+i);
   assert.equal(core.data[at+20],v.level,'Envelope before commands voice '+i);
   assert.equal(core.data[at+21],v.context,'Context command voice '+i);
   assert.equal(core.data[at+22],score.contexts[v.context][3],'Context mix voice '+i);
   checkedVoices++;
   for(let p=0;p<16;p++){
    assert.equal(signed(core.data[at+4+p]),ref.wave(v,p),'Refreshed waveform voice '+i+', sample '+p);
    checkedWaveSamples++;
   }
  }
 };
 call('um_init');check();
 for(let tick=1;tick<=score.controlTicks+3;tick++){
  // Distinct nonzero phases expose source/destination order and reset mistakes.
  for(let i=0;i<8;i++){
   const phase=(7919*i+1237*tick+1)&65535;
   ref.voices[i].phase=phase;putWord(core.data,state+i*23,phase);
  }
  ref.advanceControl();call('um_tick');check();
 }
 assert.ok(ref.loops>=1,'Control fixture completes LOOP and restart');
 assert.ok(core.minSP>=state+221,'Control stack remains above UMState');
 return {backend,configuration,format:packing==='fast'?0:9,cpuHz:meta.cpuHz,
  engineSha256:meta.engineSha256,controlTicks:score.controlTicks+3,completeLoops:ref.loops,
  checkedVoices,checkedWaveSamples,maxCallCycles,minSP:core.minSP,
  allControlOrderingMatches:true,phaseCopyAndReset:true,envelopeBeforeEvents:true};
}
