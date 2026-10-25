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
b.BASE=int(sys.argv[1]);cpu=int(sys.argv[2]);packing=sys.argv[3];mode=sys.argv[4];channels=int(sys.argv[5])
assert mode in ('normal','raw-terminal','raw-interior')
wave=list(range(16));packed=[wave[i]|(wave[i+1]<<4)for i in range(0,16,2)]
if mode=='normal':
 waves=packed*8
 contexts=[[0,i*8,3|(16 if i&1 else 0)|(64 if i&2 else 0)|(128 if i&4 else 0),128]for i in range(8)]
else:
 # Distinct banks make a missed context refresh observable. Raw gain itself
 # is independent of level; no level-dependent bank-selection flags are used.
 waves=[]
 for bank in range(8):
  row=[(phase*(1+2*(bank%4))+bank*3)&15 for phase in range(16)]
  waves.extend(row[i]|(row[i+1]<<4)for i in range(0,16,2))
 contexts=[[0,i*8,32|(i&1),160|(8 if i&1 else 16)]for i in range(8)]
 if mode=='raw-interior':
  contexts=[[0,i*8,32|(i&1),(160|(8 if i==6 else 16))if i>=6 else 0]for i in range(8)]
raw=[];ticks=0
for tick in range(12):
 for i in range(8):
  context=(i+tick)%8
  if mode!='normal':
   epoch=tick//2
   context=(i+epoch)%8
   if mode=='raw-interior':
    # Voice 3 and 7 always close the two four-voice groups. Contexts stay
    # constant for alternate event blocks so LEVEL-only reuse is exercised.
    context=6+((epoch+(i>>2))&1)if i in (3,7)else(i+epoch)%6
  raw.extend([64+i,context,72+i,1+(i+tick)%8])
  if tick%3!=2:raw.append(128+(i<<4)+(15-(i+tick)%4))
  if tick%3==1:raw.extend([88+i,(i+7)%8])
  elif i==tick%8:raw.append(80+i)
 raw.extend([96,128|(tick%3)|8,97,(tick*7)&255,98,1+(tick&15)])
 wait=1+(tick&1);raw.append(wait);ticks+=wait
raw.append(0)
score=dict(schema='micromusic-um88-score',version=1,name='control-ordering',voices=8,channels=channels,
 waves=waves,contexts=contexts,
 envelopes=[[v for level in range(16)for v in (max(0,level-1),0x55,0xaa)]],
 pitches=[None,48,52,55,60,64,67,72,76],commands=raw,controlTicks=ticks,
 groupGain=mode!='normal',normalizer=[],normalizerMinimum=0,masterShift=0,
 source=dict(kind='original deterministic control fixture',controlMode=mode,license='CC0-1.0'))
data,report=b.encode_score(score,cpu,packing)
print(json.dumps(dict(score=score,data=list(data))))
`;
const word=(data,at)=>data[at]|data[at+1]<<8;
const putWord=(data,at,value)=>{data[at]=value;data[at+1]=value>>8;};
const signed=value=>value&128?value-256:value;

export function checkControlOrdering({meta,engine,python,backend,configuration,mode='normal'}){
 assert.ok(['normal','raw-terminal','raw-interior'].includes(mode),'Known control fixture mode');
 const packing=meta.packingMode||(Number.isInteger(meta.labels.packedSymbols)?'fast':'compact');
 assert.ok(Number.isInteger(meta.songAddress)&&meta.songAddress>=engine.length,'Compiled song address');
 const generated=spawnSync(python,['-c',fixtureSource,String(meta.songAddress),String(meta.cpuHz),packing,mode,String(meta.configuredChannels??meta.channels??2)],
  {encoding:'utf8',maxBuffer:4*1024*1024});
 assert.equal(generated.status,0,generated.stderr);
 const {score,data}=JSON.parse(generated.stdout),binary=new Uint8Array(meta.songAddress+data.length);
 binary.set(engine);binary.set(data,meta.songAddress);
 assert.ok(binary.length<=8192,'Control fixture fits ATtiny88 Flash');
 const core=new AVRCore(binary,null,{target:'attiny88',cpuHz:meta.cpuHz,fastIdle:false,fastBlocks:false});
 const ref=new UniversalReference(score,meta.cpuHz),state=meta.labels.um-0x800000;
 let maxCallCycles=0,checkedVoices=0,checkedWaveSamples=0,contextRefreshChecks=0,levelOnlyCacheReuseChecks=0;
 if(mode!=='normal')assert.ok(Number.isInteger(meta.labels.um_scale_wave),'Auditable waveform refresh');
 const call=name=>{
  assert.ok(Number.isInteger(meta.labels[name]),'Callable '+name);
  core.pushPC(0);core.pc=meta.labels[name]/2;const before=core.cyc;let waveRefreshes=0;
  do{
    if(core.pc===meta.labels.um_scale_wave/2)waveRefreshes++;
    core.step();assert.ok(core.cyc-before<1000000,'Bounded '+name);
  }while(core.pc!==0);
  assert.equal(core.r[1],0);assert.equal(core.sp,767);
  maxCallCycles=Math.max(maxCallCycles,core.cyc-before);
  return waveRefreshes;
 };
 const check=()=>{
  if(mode!=='normal'){
   const groupEnds=[];
   for(let i=0;i<ref.voices.length;i++)
    if(score.contexts[ref.voices[i].context][3]&128)groupEnds.push(i);
   assert.deepEqual(groupEnds,mode==='raw-terminal'?[0,1,2,3,4,5,6,7]:[3,7],
    'Every raw state has the intended closed groups');
  }
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
 const initialRefreshes=call('um_init');check();
 if(mode!=='normal')assert.equal(initialRefreshes,8,'Raw initialization refreshes every voice');
 for(let tick=1;tick<=score.controlTicks+3;tick++){
  // Distinct nonzero phases expose source/destination order and reset mistakes.
  for(let i=0;i<8;i++){
   const phase=(7919*i+1237*tick+1)&65535;
   ref.voices[i].phase=phase;putWord(core.data,state+i*23,phase);
  }
  const before=ref.voices.map(v=>({context:v.context,level:v.level})),loops=ref.loops;
  ref.advanceControl();const refreshes=call('um_tick');check();
  if(mode!=='normal'){
   const changedContexts=ref.voices.filter((v,i)=>v.context!==before[i].context).length;
   const expected=ref.loops!==loops?8:changedContexts;
   assert.equal(refreshes,expected,'Raw refresh follows CONTEXT/LOOP, independently of LEVEL');
   if(expected)contextRefreshChecks++;
   else if(ref.voices.some((v,i)=>v.level!==before[i].level)){
    assert.equal(refreshes,0,'A raw LEVEL-only update reuses its exact cached wave');
    levelOnlyCacheReuseChecks++;
   }
  }
 }
 assert.ok(ref.loops>=1,'Control fixture completes LOOP and restart');
 assert.ok(core.minSP>=state+221,'Control stack remains above UMState');
 if(mode!=='normal'){
  assert.ok(contextRefreshChecks>0,'Context-dirty raw refresh was checked');
  assert.ok(levelOnlyCacheReuseChecks>0,'Level-only raw cache reuse was checked');
 }
 return {backend,configuration,mode,format:packing==='fast'?0:9,cpuHz:meta.cpuHz,
  engineSha256:meta.engineSha256,controlTicks:score.controlTicks+3,completeLoops:ref.loops,
  checkedVoices,checkedWaveSamples,maxCallCycles,minSP:core.minSP,
  allControlOrderingMatches:true,phaseCopyAndReset:true,envelopeBeforeEvents:true,
  ...(mode!=='normal'?{rawGroupsClosed:true,rawGroupSizes:mode==='raw-terminal'?[1,1,1,1,1,1,1,1]:[4,4],
   distinctWaveformBanks:true,contextRefreshChecks,levelOnlyCacheReuseChecks}:{})};
}
