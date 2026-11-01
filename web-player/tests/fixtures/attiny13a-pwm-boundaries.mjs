// Steady PWM formulas from DS40002307A 11.7.3/11.7.4; no Timer0 implementation reuse.
import assert from 'node:assert/strict';
import {ATtiny13A} from '../../lib/attiny13a.js';
import {executionOptions} from '../../lib/emulation-configurations.js';
import {AT13_MASK as M,AT13_BIT as B,AT13_VECTOR as V} from '../../lib/attiny13a-registers.js';
import {avr,IO,flash} from './attiny13a-system-firmware.mjs';

export const pwmBoundaryCases=Object.freeze([1,3,5,7].flatMap(mode=>
  (mode&4?[1]:[0,1]).flatMap(channel=>['zero','middle','top'].flatMap(duty=>[false,true].flatMap(inverted=>
    ['internal','clki'].flatMap(clock=>['verification','optimized'].map(policy=>({mode,channel,duty,inverted,clock,policy,
      id:`wgm${mode}/OC0${channel?'B':'A'}/${duty}/${inverted?'inverted':'normal'}/${clock}/${policy}`}))))))));

const cyclePs=1000000n,com=(a,b)=>(a<<B.COM0A0)|(b<<B.COM0B0),write=(address,value)=>[avr.ldi(16,value),avr.out(address,16)];
function program(spec){
  const top=spec.mode&4?7:255,value=spec.duty==='zero'?0:spec.duty==='top'?top:Math.floor(top/2),
    ocr=spec.channel?[top,value]:[value,top],initial=ocr.map(n=>Number(n!==0));
  initial[spec.channel]^=Number(spec.inverted);
  const outputs=[2,2];outputs[spec.channel]=spec.inverted?3:2;
  const setup=[...write(IO.DDRB,M.DDB0|M.DDB1),...write(IO.TCCR0A,com(...initial.map(n=>n?3:2))),
    ...write(IO.TCCR0B,M.FOC0A|M.FOC0B),...write(IO.OCR0A,ocr[0]),...write(IO.OCR0B,ocr[1]),
    ...write(IO.TCCR0A,com(...outputs)|(spec.mode&1?M.WGM00:0)|(spec.mode&2?M.WGM01:0)),
    ...write(IO.TIMSK0,M.TOIE0),avr.sei(),avr.nop(),...write(IO.TCCR0B,M.CS00|(spec.mode&4?M.WGM02:0))];
  assert.ok(setup.every(i=>i.length===1));const endPC=16+setup.length;
  const image=flash({instructions:[avr.rjmp(0,16)]},{at:V.TIM0_OVF,instructions:[avr.rjmp(V.TIM0_OVF,64)]},
    {at:16,instructions:[...setup,avr.rjmp(endPC,endPC)]},{at:64,instructions:[avr.inc(20),avr.reti()]});
  return {image,top,value,initial:initial[0]|(initial[1]<<1),endPC,startCycle:2+setup.length};
}

function expected(spec,{top,value,initial},start,cycles){
  const phase=spec.mode===1||spec.mode===5,period=phase?2*top:top+1,points=[];
  if(value===top||phase&&value===0)return points;
  let levels=initial;
  const edge=(n,high)=>{if(n>cycles)return;levels=(levels&~(1<<spec.channel))|(Number(high)<<spec.channel);
    points.push({timePs:start+BigInt(n)*cyclePs,levels});};
  for(let p=0;p<=Math.floor(cycles/period);p++){
    if(phase){edge(p*period+value+1,spec.inverted);edge(p*period+2*top-value+1,!spec.inverted);}
    else{
      // OCR=0 starts low/high until the first BOTTOM; its first compare changes nothing.
      if(value||p)edge(p*period+value+1,spec.inverted);
      edge((p+1)*period,!spec.inverted);
    }
  }
  return points;
}

export function runPwmBoundaryCase(spec){
  const p=program(spec),phase=spec.mode===1||spec.mode===5,period=phase?2*p.top:p.top+1,
    cycles=3*period,start=BigInt(p.startCycle)*cyclePs,end=start+BigInt(cycles)*cyclePs;
  const osccalHz=Array(128).fill(0);osccalHz[0]=1000000;
  const c=new ATtiny13A(p.image,null,{resumable:true,oscillatorHz:1000000,
    ...spec.policy==='verification'?executionOptions('verification'):
      {fastIdle:false,fastBlocks:true,optimizeFlags:true,boundedRegions:true,optimizePhaseLocals:true,sramBlocks:true},
    fuseLow:spec.clock==='clki'?0xf0:0xf2,
    ...spec.clock==='clki'?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz}});
  c.observePins(M.PINB0|M.PINB1);
  if(spec.clock==='clki')assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:300000n,lowPs:700000n,
    transitionCount:10000n,knownUntilPs:5000000000n}),true);
  c.runUntilPs(start);assert.equal(c.pc,p.endPC,'Timer starts at the final OUT bus boundary');
  assert.equal(c.state().clockDivisor,1);assert.equal(c.state().pins.levels&3,p.initial);
  assert.equal(c.readIO(IO.TCCR0B),M.CS00|(spec.mode&4?M.WGM02:0));
  assert.equal(c.readIO(IO.TIFR0)&(M.TOV0|M.OCF0A|M.OCF0B),0,'FOC/preload cannot assert timer flags');
  c.drainPinsPs();c.runUntilPs(end);
  const state=c.state(),pins=c.drainPinsPs();assert.equal(state.deviceFault,0);
  assert.equal(state.timePs,end);assert.equal(c.readIO(IO.TCNT0),0);
  assert.ok(state.irqs>0&&c.r[20]>0,'Timer overflow ISR must execute during PWM');
  for(const pin of pins){assert.equal(pin.driven&3,3);assert.equal(pin.contention&3,0);}
  const trace=pins.map(pin=>({timePs:pin.timePs,levels:pin.levels&3})),reference=expected(spec,p,start,cycles);
  assert.deepEqual(trace,reference,'Exact PWM edges under active IRQs');
  return {id:spec.id,flash:p.image,startPs:start,endPs:end,periodCycles:period,trace,expected:reference,
    state,data:c.data.slice(),registers:c.r.slice()};
}
