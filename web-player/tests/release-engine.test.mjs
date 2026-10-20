import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';

const variants=['rhythmic','alicia','turkish-march','children','greensleeves'];
function image(name){
  const base=new URL(`../../ATtiny13A/Music/variants/${name}/`,import.meta.url);
  const read=n=>readFileSync(new URL(n,base));
  return {rom:read('synth.bin'),ep:read('eeprom.bin'),report:JSON.parse(read('build-report.json'))};
}

for(const name of variants)test(`${name}: PWM ring preserves every midpoint/full point and meets real-time deadlines`,t=>{
  const {rom,ep,report}=image(name),{labels,releaseChannels}=report,c=new AVRCore(rom,ep);
  assert.deepEqual(releaseChannels.voiceAddresses,[96,101,106,111,116]);
  assert.equal(releaseChannels.tailSlots,2);assert.equal(releaseChannels.pwmRingBytes,16);
  const queue=Array(14).fill(128);let previous=128,latched=128,points=0,reads=0,minQueued=16;
  let renderStart=null,renderIrqs=0,maxRender=0;
  while(c.cyc<9600000){
    if(!c.inIRQ&&c.pc===labels.render_sample/2){renderStart=c.cyc;renderIrqs=c.irqCount;}
    if(c.inIRQ&&c.pc===labels.ring_read/2){
      assert.equal(queue.length,(c.r[22]-c.r[28])&15,'Published producer/consumer distance matches the independent FIFO');
      minQueued=Math.min(minQueued,queue.length);assert.ok(queue.length>0,'No PWM underrun');
      assert.equal(c.data[c.r[28]],queue.shift(),'No prepared byte is overwritten, skipped or reordered');reads++;
    }
    const writes=c.writes,inIRQ=c.inIRQ,at=c.pc;
    c.step();
    // MOV producer,X publishes both bytes before the following wrap ANDI.
    // Observe the completed instruction even when it immediately enters an IRQ;
    // waiting for the foreground label would publish too late in this oracle.
    if(!inIRQ&&at===labels.ring_published/2-2){
      const point=c.r[21],midpoint=(previous+point)>>1,address=128|((c.r[22]-2)&15);
      assert.equal(c.r[16],midpoint);assert.equal(c.data[address],midpoint);assert.equal(c.data[address+1],point);
      queue.push(midpoint,point);previous=point;points++;
    }
    if(c.writes!==writes)assert.equal(c.duty,latched,'PWM uses the previously latched ring value');
    if(inIRQ&&at===labels.ring_read/2)latched=c.r[18];
    if(!c.inIRQ&&c.pc===labels.idle/2&&renderStart!==null){
      maxRender=Math.max(maxRender,c.cyc-renderStart-15*(c.irqCount-renderIrqs));renderStart=null;
    }
  }
  assert.ok(points>18000&&reads>37000);assert.ok(minQueued>=1);
  assert.ok(maxRender<=512,`${maxRender} active sample-render cycles exceeds the 18.75-kHz budget`);
  assert.equal(c.maxIRQ,15);assert.equal(c.lost+c.workLost,0);assert.ok(c.minSP>=144);
  assert.ok(rom.length<=1024);assert.equal(rom.length,report.flashBytes);
  t.diagnostic(JSON.stringify({points,pwmReads:reads,minQueued,maxRenderCycles:maxRender,isrCycles:c.maxIRQ,maxStackBytes:159-c.minSP}));
});

test('ring ISR preserves every arithmetic flag and foreground register at both wrap boundaries',()=>{
  const {rom,ep}=image('rhythmic');
  for(const pointer of [128,142,143])for(let flags=0;flags<128;flags++){
    const c=new AVRCore(rom,ep);c.r[18]=117;c.r[28]=pointer;c.data[pointer]=203;
    c.r[22]=140;c.r[23]=51;c.sreg=flags;c.inIRQ=true;c.irqFrames.push(0);c.pushPC(0);
    // The actual vector's two-cycle RJMP belongs to the ISR budget.
    c.pc=3;
    while(c.inIRQ)c.step();
    assert.equal(c.sreg,flags|128);assert.equal(c.r[18],203);
    assert.equal(c.r[28],pointer===143?128:pointer+1);
    assert.equal(c.r[22],140);assert.equal(c.r[23],51);assert.equal(c.r[29],0);
    assert.equal(c.cyc+4,15,'Hardware entry adds four cycles to the flag-preserving vector and handler');
  }
});

test('two release slots copy complete phase/pitch state and steal only the quieter tail',()=>{
  const {rom,ep,report:{labels,releaseChannels}}=image('rhythmic');
  const c=new AVRCore(rom,ep),[primary,,,tail0,tail1]=releaseChannels.voiceAddresses;
  function capture(state){
    c.data.set(state,primary);c.r[26]=primary;c.r[30]=0x23;c.r[31]=3;
    c.pushPC(0);c.pc=labels.capture_ram_tail/2;
    do{c.step();}while(c.pc!==0);
    assert.equal(c.r[26],primary+1);assert.equal(c.r[30]|c.r[31]<<8,0x323);
    assert.deepEqual(Array.from(c.data.subarray(primary,primary+5)),state,'Capture never moves the new note oscillator');
    assert.equal(c.sp,159);
  }
  const first=[128|64|15,52,18,120,3],second=[128|32|8,17,39,24,1],third=[128|16|12,3,4,23,2];
  capture(first);assert.deepEqual(Array.from(c.data.subarray(tail1,tail1+5)),[first[0]&127,...first.slice(1)]);
  capture(second);assert.deepEqual(Array.from(c.data.subarray(tail0,tail0+5)),[second[0]&127,...second.slice(1)]);
  assert.ok((c.data[tail0]&15)>0&&(c.data[tail1]&15)>0,'Both spare channels can be audible at once');
  capture(third);assert.deepEqual(Array.from(c.data.subarray(tail0,tail0+5)),[third[0]&127,...third.slice(1)]);
  assert.deepEqual(Array.from(c.data.subarray(tail1,tail1+5)),[first[0]&127,...first.slice(1)],'The louder tail is retained');
  const before=Array.from(c.data.subarray(tail0,tail1+5));capture([128|16,1,2,3,4]);
  assert.deepEqual(Array.from(c.data.subarray(tail0,tail1+5)),before,'A silent old voice does not steal an audible tail');
});
