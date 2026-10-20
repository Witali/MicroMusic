import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';
const base=new URL('../../ATtiny13A/Music/variants/rhythmic/',import.meta.url);
const read=n=>readFileSync(new URL(n,base));
const {labels}=JSON.parse(read('build-report.json'));

test('PWM outputs every prepared point with its exact unsigned midpoint, without torn pairs',t=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),points=[],output=[];
  let start=null,startIrqs=0,wait=0,maxElapsed=0,maxCompute=0,maxStack=0,rendering=false,maxMixCompute=0,maxEventCompute=0;
  while(output.length<37500*2){
    const at=c.pc,word=c.rom[at*2]|c.rom[at*2+1]<<8,before=c.cyc,irqs=c.irqCount,writes=c.writes;
    if(at===labels.audio_step/2&&!c.inIRQ){start=before;startIrqs=irqs;wait=0;rendering=!!((c.r[15]+1)&1);}
    const waiting=!c.inIRQ&&(at===labels.publish_wait/2||at===labels.publish_wait/2+1);
    c.step();
    if(waiting)wait+=c.cyc-before-(c.irqCount-irqs)*4;
    maxStack=Math.max(maxStack,159-c.minSP);
    if(word===0x93a0&&c.rom[at*2+2]===98)points.push(c.r[26]);
    if(c.writes!==writes)output.push(c.duty);
    if(c.pc===(labels.idle+6)/2&&!c.inIRQ&&start!==null){
      const elapsed=c.cyc-start;maxElapsed=Math.max(maxElapsed,elapsed);
      const active=elapsed-wait-19*(c.irqCount-startIrqs);
      maxCompute=Math.max(maxCompute,active);
      if(rendering)maxMixCompute=Math.max(maxMixCompute,active);else maxEventCompute=Math.max(maxEventCompute,active);
      start=null;
    }
  }
  for(let i=0;i<output.length;i++){
    let expected=128;
    if(i>=3&&i%2){const n=(i-3)/2;expected=((n?points[n-1]:128)+points[n])>>1;}
    else if(i>=4)expected=points[(i-4)/2];
    assert.equal(output[i],expected,`Interpolated PWM write ${i}`);
  }
  assert.equal(c.maxIRQ,19);assert.equal(c.lost+c.workLost,0);
  assert.ok(maxElapsed<480,`${maxElapsed} elapsed cycles`);assert.ok(maxStack+4<=64);
  assert.ok(maxMixCompute<=256,`${maxMixCompute} active mixing cycles`);
  assert.ok(read('synth.bin').length<=1024);
  t.diagnostic(JSON.stringify({points:points.length,pwmWrites:output.length,maxElapsedCyclesIncludingWaitAndIrq:maxElapsed,maxComputeCyclesExcludingWaitAndIrq:maxCompute,maxMixCompute,maxEventCompute,isrCycles:c.maxIRQ,maxStackBytes:maxStack,lostEvents:c.lost+c.workLost}));
});

test('the phase-swapping ISR preserves all arithmetic flags while preparing either output',()=>{
  for(const phase of [1,16])for(const flags of [0,1,2,31,63]){
    const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
    c.pc=labels.pwm_irq/2;c.r[18]=117;c.r[23]=phase;c.ram[1]=51;c.ram[2]=203;
    c.sreg=flags;c.inIRQ=true;c.irqFrames.push(0);c.pushPC(0);
    while(c.inIRQ)c.step();
    assert.equal(c.sreg&63,flags);assert.equal(c.t,1);
    assert.equal(c.r[18],phase===1?51:203);assert.equal(c.r[23],phase===1?16:1);
  }
});

test('the compact tone routine exactly scales all sustain wave samples at every envelope level',()=>{
  const rom=read('synth.bin'),ep=read('eeprom.bin');
  for(const offset of [0,16,32])for(const high of [false,true])for(let level=0;level<16;level++)for(let phase=0;phase<16;phase++){
    const c=new AVRCore(rom,ep);c.pc=labels.render_tone/2;c.r[25]=128|offset|level;c.r[16]=high?4:3;c.r[17]=phase<<4;c.pushPC(0);
    do{c.step();}while(c.pc!==0);
    const packed=ep[offset+(high?8:0)+(phase>>1)],q=((phase&1)?packed>>4:packed&15)-8;
    assert.equal(c.r[17],Math.floor(q*level/4)&255,`${offset}/${high}/${level}/${phase}`);
    assert.equal(c.r[0],0);assert.equal(c.sp,159);
  }
});

test('actual percussion noise visits all 65535 nonzero states before repeating',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),seen=new Set();c.r[14]=167;
  const start=labels['.L298']/2,end=labels['.L2a0']/2+2;
  let expected=167;
  for(let i=0;i<65535;i++){
    c.pc=start;while(c.pc!==end)c.step();
    expected=((expected<<1)&65535)^((expected&32768)?45:0);
    const state=c.r[14]|c.ram[0]<<8;
    assert.equal(state,expected);assert.ok(state!==0&&!seen.has(state));seen.add(state);
  }
  assert.equal(expected,167);assert.equal(seen.size,65535);
});

test('all playlist boundaries and note-off paths fit the CPU and SRAM budgets',t=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),sections=new Set(),tokens=new Set();
  const entry=labels.audio_step/2,done=(labels.idle+6)/2;let maximum=0;
  for(let n=0;n<950;n++){
    while(c.pc!==entry||c.inIRQ)c.step();
    // Force one grid overflow and one score command on this envelope tick.
    c.r[15]=255;c.ram[3]=255;c.r[25]=255;c.ram[4]=255;c.r[22]=1;
    const before=c.cyc;
    do{
      if(c.pc===labels.read_event/2&&!c.inIRQ)tokens.add(c.rom[c.r[30]|c.r[31]<<8]);
      c.step();
    }while(c.pc!==done||c.inIRQ);
    maximum=Math.max(maximum,c.cyc-before);sections.add(c.r[28]);
  }
  for(let n=0;n<15;n++)assert.ok(sections.has(n));
  for(const token of [0xf2,0xf4,0xf6,0xf8,0xff])assert.ok(tokens.has(token));
  assert.ok(maximum<480,`${maximum} foreground cycles including IRQ`);
  assert.ok(c.minSP>=101,'Five state bytes do not overlap the hardware stack');
  assert.equal(c.ram.subarray(5,c.minSP-96+1).some(x=>x!==0),false);
  assert.equal(c.maxIRQ,19);assert.equal(c.lost+c.workLost,0);
  t.diagnostic(JSON.stringify({maximumForegroundCyclesIncludingIrq:maximum,maxStackBytes:159-c.minSP}));
});
