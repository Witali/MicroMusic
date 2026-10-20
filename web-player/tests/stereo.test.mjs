import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {AVRCore} from '../lib/avr-core.js';
import {Renderer} from '../lib/renderer.js';
import {AudioQueue} from '../lib/audio-queue.js';
const base=new URL('../../ATtiny13A/Music/variants/lumiere-stereo/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const {labels}=JSON.parse(read('build-report.json'));
const core=()=>new AVRCore(read('synth.bin'),read('eeprom.bin'));
const signed=x=>x&128 ? x-256 : x;

test('both PWM channels deliver every point and its exact midpoint as a synchronized frame',t=>{
  const c=core(),points=[],frames=[];
  const step=c.step.bind(c);
  c.step=()=>{
    const at=c.pc,word=c.rom[at*2]|c.rom[at*2+1]<<8;
    if(!c.inIRQ&&word===0x93b0&&c.rom[at*2+2]===98)points.push([c.r[26],c.r[27]]);
    step();
  };
  for(let i=0;i<75000;i++){
    const packed=c.nextStereoDuty();frames.push([packed&255,packed>>8]);
  }
  for(let i=0;i<frames.length;i++)for(let ch=0;ch<2;ch++){
    let expected=128;
    if(i>=2){const n=(i-2)>>1;expected=i%2 ? points[n][ch] : ((n ? points[n-1][ch] : 128)+points[n][ch])>>1;}
    assert.equal(frames[i][ch],expected,`frame ${i} channel ${ch}`);
  }
  assert.equal(c.io[0x17]&3,3);assert.equal(c.io[0x2f],0xa3);
  assert.equal(c.leftWrites,c.writes);assert.equal(c.lost+c.workLost,0);
  assert.ok(read('synth.bin').length<=1024);assert.ok(c.minSP>=103);
  assert.ok(frames.some(([l,r])=>l!==r));
  t.diagnostic(JSON.stringify({flash:read('synth.bin').length,isr:c.maxIRQ,stack:159-c.minSP,frames:frames.length}));
});

test('stereo ISR preserves foreground arithmetic flags in both interpolation phases',()=>{
  for(const phase of [1,16])for(const flags of [0,1,2,31,63]){
    const c=core();c.pc=labels.pwm_irq/2;c.r[23]=phase;c.ram.set([31,211],1);c.ram.set([51,203],5);
    c.sreg=flags;c.inIRQ=true;c.irqFrames.push(0);c.pushPC(0);
    while(c.inIRQ)c.step();
    assert.equal(c.sreg&63,flags);assert.equal(c.t,1);assert.equal(c.r[23],phase===1?16:1);
    assert.equal(c.io[0x2a],phase===1?51:203);assert.equal(c.io[0x29],phase===1?31:211);
  }
});

test('panorama uses 2:1 for violin, 1:2 for guitar and equal piano/drum levels',()=>{
  for(const instrument of ['lead','keys','pluck','drums'])for(let phase=0;phase<256;phase+=7){
    const c=core();c.pc=labels.render_sample/2;c.r[23]=1;c.r[21]=4;
    if(instrument==='lead'){c.r[1]=15;c.r[3]=phase;c.r[5]=3;}
    if(instrument==='keys'){c.r[19]=15;c.r[7]=phase;c.r[9]=3;}
    if(instrument==='pluck'){c.r[20]=15;c.r[11]=phase;c.r[13]=3;}
    if(instrument==='drums'){c.r[21]=0;c.r[29]=0;c.r[14]=phase;}
    while(c.pc!==labels.write_pwm/2)c.step();
    const l=signed(c.r[26]),r=signed(c.r[27]);
    if(instrument==='lead')assert.equal(r,Math.floor(l/2));
    else if(instrument==='pluck')assert.equal(l,Math.floor(r/2));
    else assert.equal(l,r);
  }
});

test('looped stereo tone scaling exactly preserves every waveform and envelope level',()=>{
  const ep=read('eeprom.bin');
  for(const offset of [0,16,32])for(const high of [false,true])for(let level=0;level<16;level++)for(let phase=0;phase<16;phase++){
    const c=core();c.pc=labels.render_tone/2;c.r[25]=128|offset|level;c.r[16]=high?4:3;c.r[17]=phase<<4;c.pushPC(0);
    do{c.step();}while(c.pc!==0);
    const packed=ep[offset+(high?8:0)+(phase>>1)],q=((phase&1)?packed>>4:packed&15)-8;
    assert.equal(c.r[17],Math.floor(q*level/4)&255);assert.equal(c.r[0],0);assert.equal(c.sp,159);
  }
});

test('stereo queue keeps channel pairing through wrap, underrun and mono upmix',()=>{
  const q=new AudioQueue(4,2),out=[new Float32Array(3),new Float32Array(3)];
  q.push(Float32Array.of(1,11,2,12,3,13));q.take(out);
  assert.deepEqual(Array.from(out[0]),[1,2,3]);assert.deepEqual(Array.from(out[1]),[11,12,13]);
  q.push(Float32Array.of(4,14,5,15));assert.equal(q.size,2);q.take(out);
  assert.deepEqual(Array.from(out[0]),[4,5,0]);assert.deepEqual(Array.from(out[1]),[14,15,0]);
  assert.throws(()=>q.push(Float32Array.of(1)),/Incomplete/);
  const mono=new AudioQueue(4);mono.push(Float32Array.of(.25,.5));mono.take(out);assert.deepEqual(out[0],out[1]);
});

test('stereo worklet preserves L/R, pause, reset and late-packet isolation with frame-based clocks',()=>{
  let Processor;const messages=[];
  const text=readFileSync(new URL('../audio-worklet.js',import.meta.url),'utf8').replace(/^import[^\n]+\n/,'');
  runInNewContext(text,{AudioQueue,AudioWorkletProcessor:class{constructor(){this.port={postMessage:m=>messages.push(m)};}},registerProcessor:(_,p)=>Processor=p});
  const p=new Processor(),source={start(){},close(){},postMessage(){}};
  p.port.onmessage({data:{type:'connect',session:1,channels:2,port:source}});
  p.port.onmessage({data:{type:'playing',value:true}});
  const samples=new Float32Array(8192*2);for(let i=0;i<8192;i++){samples[i*2]=.25;samples[i*2+1]=-.5;}
  source.onmessage({data:{type:'samples',samples}});
  const out=[new Float32Array(128),new Float32Array(128)];p.process([],[out]);
  assert.ok(out[0].every(x=>x===.25));assert.ok(out[1].every(x=>x===-.5));assert.equal(p.frames,128);assert.equal(p.clockFrames,128);
  p.port.onmessage({data:{type:'playing',value:false}});const size=p.queue.size;p.process([],[out]);
  assert.equal(p.queue.size,size);assert.ok(out.every(ch=>ch.every(x=>x===0)));
  p.port.onmessage({data:{type:'disconnect',session:2}});source.onmessage({data:{type:'samples',samples}});p.process([],[out]);
  assert.equal(p.queue.size,0);assert.equal(p.frames,0);assert.ok(out.every(ch=>ch.every(x=>x===0)));
});

for(const rate of [22050,44100,48000,96000])test(`stereo resampling at ${rate} Hz matches both raw AVR outputs`,()=>{
  const entry={audioChannels:2,pwmHz:37500,flashHex:read('synth.hex').toString(),eepromHex:read('eeprom.hex').toString()};
  const renderer=new Renderer(entry,rate),c=core(),actual=renderer.render(4096);
  let a=c.nextStereoDuty(),b=c.nextStereoDuty(),phase=0;
  for(let i=0;i<4096;i++){
    for(let ch=0;ch<2;ch++){const v0=(a>>(8*ch))&255,v1=(b>>(8*ch))&255;
      assert.equal(actual[2*i+ch],Math.fround((v0+(v1-v0)*phase-128)/128));}
    phase+=37500/rate;while(phase>=1){phase--;a=b;b=c.nextStereoDuty();}
  }
  assert.equal(renderer.core.cyc,c.cyc);
});
