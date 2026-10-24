import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A section11.7.2: CTC OCR0A=0 toggles OC0A at clkI/O/2.
// SPM short-command duration is an explicit model parameter, not a silicon
// timing assertion. A4800-cycle phase spans four8kHz samples at9.6MHz.
const image=sequential([[0x95e8],avr.inc(20)]);
function make(hz,mask=63){
  const calibration=Array(128).fill(0);calibration[0]=hz;
  const c=new ATtiny13A(image,null,{resumable:true,oscillatorHz:hz,
    osccalHz:calibration,fuseLow:0x72,spmCommandCycles:4800});
  c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,0);
  c.writeIO(IO.TCCR0A,MASK.COM0A0|MASK.WGM01);c.writeIO(IO.TCCR0B,MASK.CS00);
  c.observePins(mask,{retainDuringAudio:false});return c;
}
function equalHardware(actual,reference){
  assert.deepEqual(actual.state(),reference.state());assert.deepEqual(actual._state,reference._state);
  for(const name of ['data','rom','eeprom'])assert.deepEqual(actual[name],reference[name]);
  assert.deepEqual(Array.from(actual.irqFrames),Array.from(reference.irqFrames));
}
// Independent observation policy: no native audio subscription or collector.
// Advance the original CPU/board in short absolute-time slices and integrate
// the full physical host trace with integer arithmetic on the8kHz sample grid.
function traceOracle(c,rate,channels){
  let level=c.state().pins.levels,frame=0n;
  const start=c.state().timePs;c.drainPinsPs();
  return ()=>{
    const from=start+frame*1000000000000n/BigInt(rate),
      end=start+(++frame)*1000000000000n/BigInt(rate),events=[];
    while(c.state().timePs<end){
      const next=c.state().timePs+3000000n;
      c.runUntilPs(next<end?next:end);events.push(...c.drainPinsPs());
    }
    assert.equal(c.state().timePs,end);let at=from;const high=[0n,0n];
    const accumulate=until=>{for(let pin=0;pin<2;pin++)if(level&(1<<pin))high[pin]+=until-at;at=until;};
    for(const event of events){assert.ok(event.timePs>=at&&event.timePs<=end);accumulate(event.timePs);level=event.levels;}
    accumulate(end);
    return Float32Array.from({length:channels},(_,ch)=>
      2*Number(high[channels===1?1:ch])/Number(end-from)-1);
  };
}

for(const {hz,rate,frames} of [{hz:9600000,rate:8000,frames:5},
  {hz:9000000,rate:11025,frames:8},{hz:20000000,rate:8000,frames:3}])
  for(const mask of [0,63])for(const channels of [1,2])
  test(`long internal SPM phase streams across sample and ring boundaries, ${hz}Hz/${rate}Hz, mask${mask}, channels${channels}`,()=>{
    const actual=make(hz,mask),reference=make(hz),next=traceOracle(reference,rate,channels);
    for(let frame=0;frame<frames;frame++){
      const expected=next();
      if(hz===9600000&&rate===8000)
        assert.deepEqual(expected,channels===1?Float32Array.of(-1):Float32Array.of(0,-1));
      assert.deepEqual(actual.capturePhysical(1,rate,channels),expected);
      equalHardware(actual,reference);
      const end=BigInt(frame+1)*1000000000000n/BigInt(rate);
      assert.equal(actual.cyc,Number(end*BigInt(hz)*2n/1000000000000n)/2);
      assert.equal(actual.state().deviceFault,0);
      if(!frame){assert.equal(actual.state().cpuPhase.retired,0n);assert.equal(actual.r[20],0);}
    }
    assert.equal(actual.r[20],1,'the instruction following SPM commits exactly once');
  });
