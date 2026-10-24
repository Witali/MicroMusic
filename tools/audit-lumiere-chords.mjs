// Compare every actual AVR attack to the saved lead sheet and chord symbols.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../web-player/lib/avr-reference.js';

const midi=name=>{const m=/^([A-G])([#b]?)(\d)$/.exec(name);return (+m[3]+1)*12+({C:0,D:2,E:4,F:5,G:7,A:9,B:11}[m[1]])+(m[2]==='#'?1:m[2]==='b'?-1:0);};
const dds=pitch=>Math.round(440*2**((pitch-69)/12)*65536/18750);
const signed=n=>n&128?n-256:n;
// Independent harmonic specification; the stored DDS table is not its oracle.
const chords={Bm:[59,62,66,54],Gmaj7:[55,59,66,50],Em:[52,55,59,47],
 'F#m':[54,57,61,49],'F#':[54,58,61,49],'C#m7b5':[49,52,59,43]};

export function expectedAttacks(score){
 const events=[];let base=0;
 for(const section of score.playlist){let tie=null;
  for(const [bar,line] of score.patterns[section].entries()){
   const emptyOutro=section==='F'&&score.patterns[section].every(x=>x==='R:4');
   if(!emptyOutro){const pair=score.chord_overrides?.[section]?.[bar]??score.chord_pairs[bar%score.chord_pairs.length];
    for(let half=0;half<2;half++)chords[pair[half]].forEach((pitch,index)=>events.push({unit:base+half*8,address:101+index*5,pitch}));}
   let position=0;
   for(const [index,piece] of line.split(' ').entries()){
    const [note,raw]=piece.split(':'),units=Math.round(parseFloat(raw)*4);
    if(note!=='R'&&!(index===0&&tie===note))events.push({unit:base+position,address:96,pitch:midi(note)});
    tie=raw.endsWith('~')?note:null;position+=units;
   }
   assert.equal(position,16);base+=16;
  }
 }
 return {events:events.sort((a,b)=>a.unit-b.unit||a.address-b.address),units:base};
}

export function audit(folder){
 const read=n=>fs.readFileSync(path.join(folder,n));
 const meta=JSON.parse(read('build-report.json')),score=JSON.parse(read('score.json'));
 const rom=read('synth.bin'),ep=read('eeprom.bin'),c=new AVRCore(rom,ep),stereo=meta.audioChannels===2;
 const p=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
 const {events:expected,units}=expectedAttacks(score),actual=[];
 let grid=-1,finished=false,initializing=null,phaseChecks=0,maxStack=0,maxActive=0;
 let minQueued=16,maxQueued=0,underruns=0,points=0,renderStart=null,renderIrqs=0,maxRender=0;
 let mix=[0,0],unboundedMix=[0,0],minimum=[128,128],maximum=[128,128],mixMinimum=[0,0],mixMaximum=[0,0];
 let previous=[128,128],fifo=Array(stereo?6:14).fill(0).map(()=>stereo?[128,128]:[128]);
 const step=c.step.bind(c);
 c.step=()=>{
  const at=c.pc,inIRQ=c.inIRQ;
  if(!inIRQ){
   if(at===p.grid_step){grid++;if(grid===units)finished=true;}
   if(at===p.initialize_voice&&!finished){
    const a=c.r[26],z=c.r[30]|c.r[31]<<8,frequency=rom[z]|rom[z+1]<<8;
    initializing={a,phase:[c.data[a+1],c.data[a+2]],frequency};
    actual.push({unit:grid,address:a,frequency});
   }
   if(at===p.voice_initialized&&initializing){
    const {a,phase,frequency}=initializing;
    assert.deepEqual([c.data[a+1],c.data[a+2]],phase,'Every retrigger preserves DDS phase');
    assert.equal(c.data[a+3]|c.data[a+4]<<8,frequency);phaseChecks++;initializing=null;
   }
   if(at===p.render_sample){renderStart=c.cyc;renderIrqs=c.irqCount;unboundedMix=[0,0];
    maxActive=Math.max(maxActive,[96,101,106,111,116].filter(a=>c.data[a]&15).length);}
   if(at===p.primary_gain){const value=signed(c.r[17]);
    unboundedMix[0]+=stereo&&c.r[26]===121?Math.floor(value/2):value;
    if(stereo)unboundedMix[1]+=c.r[26]===101?Math.floor(value/2):value;
   }
   if(at===p.write_pwm-(stereo?2:1)){const drum=signed(c.r[17]);unboundedMix[0]+=drum;if(stereo)unboundedMix[1]+=drum;}
   if(at===p.write_pwm){mix=stereo?[signed(c.r[21]),signed(c.r[10])]:[signed(c.r[21])];
    mix.forEach((v,ch)=>{assert.ok(unboundedMix[ch]>=-128&&unboundedMix[ch]<=127,`No wrapped mix: ${unboundedMix[ch]}`);
     assert.equal(v,unboundedMix[ch],'Accumulator equals the unbounded contribution sum');
     mixMinimum[ch]=Math.min(mixMinimum[ch],v);mixMaximum[ch]=Math.max(mixMaximum[ch],v);});}
  }
  if(inIRQ&&at===p.ring_read){
   const queued=(c.r[22]-c.r[28])&15;minQueued=Math.min(minQueued,queued);maxQueued=Math.max(maxQueued,queued);
   if(queued<(stereo?2:1))underruns++;
   const frame=fifo.shift();assert.ok(frame,`Prepared frame exists at ${c.cyc}: queued=${queued}, maxRender=${maxRender}, points=${points}`);
   for(let ch=0;ch<frame.length;ch++)assert.equal(c.data[c.r[28]+ch],frame[ch],'Paired FIFO order');
  }
  step();maxStack=Math.max(maxStack,159-c.sp);
  // MOV producer,X is the actual publication point, before wrap ANDI.
  if(!inIRQ&&at===p.ring_published-2){
   const point=stereo?[c.r[21],c.r[17]]:[c.r[21]],mid=point.map((v,i)=>(v+previous[i])>>1);
   const start=128|((c.r[22]-(stereo?4:2))&15),bytes=stereo?[mid[0],mid[1],point[0],point[1]]:[mid[0],point[0]];
   assert.deepEqual(Array.from(c.data.subarray(start,start+bytes.length)),bytes,'Exact interpolated paired frames');
   point.forEach((v,i)=>{assert.equal(v,mix[i]+128,'PWM follows the signed mix');minimum[i]=Math.min(minimum[i],v);maximum[i]=Math.max(maximum[i],v);});
   fifo.push(mid,point);previous=point;points++;
  }
  if(!c.inIRQ&&c.pc===p.idle&&renderStart!==null){maxRender=Math.max(maxRender,c.cyc-renderStart-(stereo?18:15)*(c.irqCount-renderIrqs));renderStart=null;}
 };
 while(!finished&&c.cyc<224*9600000)stereo?c.nextStereoDuty():c.nextDuty();
 assert.ok(finished,'Whole saved song completed');
 actual.sort((a,b)=>a.unit-b.unit||a.address-b.address);
 assert.deepEqual(actual,expected.map(({unit,address,pitch})=>({unit,address,frequency:dds(pitch)})),'Every lead and chord attack matches the saved source');
 assert.equal(underruns,0);assert.equal(c.lost+c.workLost,0);assert.equal(maxActive,5);
 assert.ok(maxRender<512,`Sample render ${maxRender}`);assert.ok(c.minSP>=144);assert.ok(rom.length<=1024);
 const result={image:path.basename(folder),engine:meta.engine,flashSha256:meta.flashSha256,flashBytes:rom.length,
  completeSong:{quarterNotes:units/4,idealSeconds:units/4*60/score.tempo_bpm,attacks:actual.length,
   leadNotes:expected.filter(e=>e.address===96).length,pianoNotes:expected.filter(e=>e.address>=101&&e.address<=111).length,
   guitarNotes:expected.filter(e=>e.address===116).length,missingAttacks:0,phaseChecks},
  voices:{tonal:5,percussion:1,maxActiveTonal:maxActive,releaseTails:0},
  pwm:{points,channels:stereo?2:1,min:minimum.slice(0,stereo?2:1),max:maximum.slice(0,stereo?2:1),
   unboundedMixMin:mixMinimum.slice(0,stereo?2:1),unboundedMixMax:mixMaximum.slice(0,stereo?2:1),
   checkedMixSamples:points,fifoUnderruns:underruns,minQueuedBytes:minQueued,maxQueuedBytes:maxQueued},
  timing:{isrCycles:c.maxIRQ,maxRenderCycles:maxRender,lostTimerEvents:c.lost,lostWorkEvents:c.workLost},
  memory:{voiceStateBytes:25,pwmRingBytes:16,maxStackBytes:maxStack,minimumSP:c.minSP},
  sourceLimit:'Saved lead-sheet adaptation; new piano tones realize its chord symbols. No claim of an original orchestral transcription. Stereo uses a noise-only snare to fit the second PWM channel.'};
 fs.writeFileSync(`web-player/reports/${stereo?'lumiere-stereo-verification':'rhythmic-release-verification'}.json`,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result,null,2));return result;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))audit(process.argv[2]??'ATtiny13A/Music/variants/rhythmic');
