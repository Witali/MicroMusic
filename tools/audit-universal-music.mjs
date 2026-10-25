// Full firmware execution against an independent score/audio oracle, IRQs active.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../web-player/lib/avr-core.js';
import {UniversalReference} from './universal-reference.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const word=(b,p)=>b[p]|b[p+1]<<8;
const signed=v=>v&128?v-256:v;
const sha=b=>createHash('sha256').update(b).digest('hex');
const readJSON=p=>JSON.parse(fs.readFileSync(p));

export function audit(name,{directory=path.join(root,'ATtiny88/Music/universal/songs'),scorePath}={}){
 const folder=path.join(directory,name),meta=readJSON(path.join(folder,'build-report.json'));
 const localScore=path.join(folder,'score.json');
 const score=readJSON(scorePath||(fs.existsSync(localScore)?localScore:path.join(root,'ATtiny88/Music/universal/songs',name,'score.json')));
 const rom=fs.readFileSync(path.join(folder,'synth.bin'));
 assert.equal(sha(rom),meta.flashSha256);assert.equal(score.controlTicks,meta.controlTicks);
 const channels=meta.pwmBufferLayout==='mono'?1:2;
 const bufferFrames=meta.pwmBufferFrames||(192/channels),bufferBytes=bufferFrames*channels;
 const c=new AVRCore(rom,null,{target:'attiny88',cpuHz:meta.cpuHz}),ref=new UniversalReference(score,meta.cpuHz,{pwmChannels:channels,pwmFrames:bufferFrames});
 const at=key=>meta.labels[key]-0x800000;
 const state=at('um'),read=at('um_read'),write=at('um_write'),ring=at('um_ring');
 const mono=meta.pwmBufferLayout==='mono';
 const render=meta.labels.um_render/2,irq=meta.labels['__vector_'+c.profile.timer.vector]/2;
 const tick=meta.labels.um_tick/2,tickReturns=new Set();
 const returnPCs=new Set(),retiPCs=new Set();
 for(let pc=0;pc<meta.engineBytes/2;pc++){
  if(c.op[pc]===6&&pc+1+c.k[pc]===render)returnPCs.add(pc+1);
  if(c.op[pc]===6&&pc+1+c.k[pc]===tick)tickReturns.add(pc+1);
  if(c.op[pc]===4)retiPCs.add(pc);
 }
 assert.ok(returnPCs.size,'The auditable kernel must remain a function');
 for(const p of [render,tick,irq,...tickReturns,...returnPCs,...retiPCs])c.batch[p]=0;
 let checkedPhases=0,checkedWaves=0,observedIRQs=0,checkedIRQOutputs=0,checkedGeneratedFrames=0;
 let minQueued=bufferFrames,maxRender=0,startRender=0,startIrqs=0,expectedMix=0,irqExpected;
 let lastTick=-1,lastWrite=bufferBytes-4,done=false,failure=null;
 let tickStart=null,tickIrqs=0,maxControl=0,controlCalls=0;
 const start=performance.now(),stopTicks=score.controlTicks+Math.min(2,score.controlTicks);
 try {
  while(c.cyc<meta.cpuHz*(score.controlTicks/(18750/256)+1)){
   if(!c.inIRQ&&c.pc===tick){tickStart=c.cyc;tickIrqs=c.irqCount;}
   else if(!c.inIRQ&&tickStart!==null&&tickReturns.has(c.pc)){
    maxControl=Math.max(maxControl,c.cyc-tickStart-(c.irqCount-tickIrqs)*c.maxIRQ);controlCalls++;tickStart=null;
   }else if(!c.inIRQ&&c.pc===render){
    assert.equal(c.data[write],ref.write,'Producer committed the expected number of PWM frames');
    if(ref.samples){
     for(let i=0;i<4*channels;i++){
      const pos=(lastWrite+i)%bufferBytes;
      assert.equal(c.data[ring+pos],ref.ring[pos],name+': generated PWM sample '+ref.samples+', byte '+i);
     }
     checkedGeneratedFrames+=4;
    }
    if(ref.loops&&ref.totalTicks>=stopTicks){done=true;break;}
    lastWrite=ref.write;startRender=c.cyc;startIrqs=c.irqCount;expectedMix=ref.beginSample();
    assert.equal(word(c.data,state+212),ref.tick,name+': musical control time');
    for(let i=0;i<score.voices;i++){
     const a=state+i*23,v=ref.voices[i];
     assert.equal(word(c.data,a),ref.beforePhases[i],name+': DDS phase before sample '+ref.samples+', voice '+i);checkedPhases++;
     if(ref.totalTicks!==lastTick){
      assert.equal(c.data[a+20],v.level,name+': level tick '+ref.tick+', voice '+i);
      assert.equal(c.data[a+21],v.context,name+': context tick '+ref.tick+', voice '+i);
      assert.equal(word(c.data,a+2),v.step,name+': pitch tick '+ref.tick+', voice '+i);
      for(let p=0;p<16;p++){assert.equal(signed(c.data[a+4+p]),ref.wave(v,p),name+': cached waveform');checkedWaves++;}
     }
    }
    assert.equal(c.data[state+218],ref.drumMode,'Percussion mode');
    assert.equal(c.data[state+219],ref.drumPhase,'Percussion phase');
    assert.equal(c.data[state+220],ref.noiseHigh,'Percussion LFSR high byte');
    lastTick=ref.totalTicks;
   }else if(!c.inIRQ&&returnPCs.has(c.pc)){
    const actual=mono?c.r[24]|c.r[25]<<8:(c.r[22]|c.r[23]<<8|c.r[24]<<16|c.r[25]<<24)>>>0;
    assert.equal(actual,mono?expectedMix&65535:expectedMix,name+': signed tonal mix');
    for(let i=0;i<score.voices;i++){assert.equal(word(c.data,state+i*23),ref.voices[i].phase,'DDS phase after kernel');checkedPhases++;}
    maxRender=Math.max(maxRender,c.cyc-startRender-(c.irqCount-startIrqs)*c.maxIRQ);ref.finishSample();
   }else if(c.pc===irq){
    observedIRQs++;
    const consumer=c.data[read],queued=((c.data[write]-consumer+bufferBytes)%bufferBytes)/channels;
    assert.ok(queued>0,name+': PWM FIFO underrun at '+c.cyc/meta.cpuHz+' s, tick '+ref.tick);
    minQueued=Math.min(minQueued,queued);irqExpected=[ref.ring[consumer],ref.ring[consumer+(channels===2?1:0)]];
    assert.equal(c.data[ring+consumer],irqExpected[0],'FIFO left/mono byte');
    if(channels===2)assert.equal(c.data[ring+consumer+1],irqExpected[1],'FIFO right byte');
   }else if(c.inIRQ&&retiPCs.has(c.pc)){
    const expected=channels===1?[128,irqExpected[0]]:irqExpected;
    assert.deepEqual([word(c.data,c.profile.timer.ocra),word(c.data,c.profile.timer.ocrb)],expected,'Timer1 compare values after IRQ');checkedIRQOutputs++;
   }
   if(!c.runBlock())c.step();
  }
  assert.ok(done,name+': complete loop and restart');
  assert.equal(c.data[at('um_underruns')],0);assert.equal(c.lost,0);assert.equal(c.workLost,0);
  assert.ok(c.minSP>=ring+bufferBytes,'Stack remains above the FIFO');
 }catch(error){failure=error.message;}
 const passed=!failure;
 const report={variant:name,cpuHz:meta.cpuHz,backend:meta.backend,engineSha256:meta.engineSha256,
  flashSha256:meta.flashSha256,eepromSha256:meta.eepromSha256,scoreSha256:sha(JSON.stringify(score)),
  reference:'Independent uncompressed UM88 JSON, exact tonal/percussion/interpolation arithmetic',passed,
  simulatedSeconds:c.cyc/meta.cpuHz,controlFrames:meta.controlTicks,completeLoops:ref.loops,
  samples:ref.samples,observedIRQs,checkedIRQOutputs,checkedGeneratedFrames,checkedPhases,checkedWaveSamples:checkedWaves,
  pwmBufferLayout:meta.pwmBufferLayout||'stereo-pairs',fifoCapacityFrames:bufferFrames,
  minimumQueuedFrames:minQueued,maxRenderActiveCycles:maxRender,maxControlActiveCycles:maxControl,controlCalls,maxISRCycles:c.maxIRQ,
  fifoUnderruns:c.data[at('um_underruns')]+(failure?.includes('FIFO underrun')?1:0),lostInterrupts:c.lost,
  minimumStackPointer:c.minSP,stackBytes:767-c.minSP,staticStateEnd:at('__bss_end'),fifoEnd:ring+bufferBytes,stackMarginBytes:c.minSP-(ring+bufferBytes),
  allControlFramesMatch:passed,allTonalMixesMatch:passed,allPwmFramesMatch:passed,allPercussionStatesMatch:passed,
  clippedChannelSamples:ref.clippedSamples,peakTonalMix:ref.peakMix,
  monoMeanPwm:ref.samples?128+ref.sum/ref.samples:null,monoRmsPwm:ref.samples?Math.sqrt(ref.square/ref.samples):null,
  hardwareTested:false,wallSeconds:(performance.now()-start)/1000,...(failure?{failure}:{})};
 fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));if(failure)throw Error(failure);return report;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2),option=args.find(a=>a.startsWith('--directory=')),scoreOption=args.find(a=>a.startsWith('--score='));
 const directory=option?path.resolve(option.slice(12)):path.join(root,'ATtiny88/Music/universal/songs');
 const names=args.filter(a=>a!==option&&a!==scoreOption),folders=fs.readdirSync(directory).filter(n=>fs.statSync(path.join(directory,n)).isDirectory());
 try{for(const name of names.length?names:folders)audit(name,{directory,scorePath:scoreOption?.slice(8)});}
 catch(error){console.error('Audit failed:',error.message);process.exitCode=1;}
}
