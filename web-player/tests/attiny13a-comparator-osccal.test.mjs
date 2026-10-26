import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

// DS40002307A6.4.1 describes OSCCAL frequency changes;13.2.2 separates analog
// settling from clocked ACO visibility. The exact integer-ps edge ordering and
// two-stage sampling below are the project's selected digital-profile contract,
// not silicon oscillator settling or setup/hold measurements. Calibration steps
// are one register value and +/-1% frequency, within the documented restrictions.
// https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf
// No production clock/comparator timing helper is used to derive expectations.
const image=Uint8Array.of(0xff,0xcf); // RJMP .
const frequencyPairs=[[9000000,9090000],[9000000,8910000],
  [10000000,10100000],[10000000,9900000],[9600000,9696000],[9600000,9504000]];
const changes=[1n,50000n,55555n,55556n,100000n,111111n,111112n,150000n,
  199999n,200000n,200001n,222223n,250000n,333334n,500000n,600000n];
const ceil=(n,d)=>(n+d-1n)/d;
const describe=value=>JSON.stringify(value,(_,v)=>typeof v==='bigint'?v.toString():v);

function expectedAco({oldHz,newHz,divisor,changeAt,inputAt,delayNs}){
  const denominator=1000000000000n*BigInt(divisor);
  let now=0n,phase=0n,half=0n,hz=BigInt(oldHz),raw=0,sync1=0;
  let rawDone=false,changed=false;
  const rawAt=inputAt+BigInt(delayNs)*1000n;
  for(let events=0;events<100;events++){
    const rate=2n*hz;
    let next=now+ceil(denominator-phase,rate);
    if(!rawDone&&rawAt<next)next=rawAt;
    if(!changed&&changeAt<next)next=changeAt;
    phase+=(next-now)*rate;
    const delivered=phase/denominator;
    phase%=denominator;half+=delivered;now=next;
    // A delayed raw completion precedes a coincident rising edge. A zero-delay
    // ordinary input follows its edge and cannot reuse that already sampled edge.
    if(!rawDone&&rawAt===now&&delayNs){raw=1;rawDone=true;}
    if(delivered&&!(half&1n)){
      const output=sync1;sync1=raw;
      if(output)return now;
    }
    if(!rawDone&&rawAt===now){raw=1;rawDone=true;}
    // Host register writes happen after service at their observation timestamp.
    // The denominator is unchanged by OSCCAL, so retain the fractional phase.
    if(!changed&&changeAt===now){hz=BigInt(newHz);changed=true;}
  }
  assert.fail('Independent phase fixture did not reach ACO');
}

function checkInternal(scenario,{propagationNs,bandgapStartupNs}){
  const at=expectedAco(scenario);
  if(at<=scenario.changeAt)return false; // This case no longer has pending synchronization.
  const {oldHz,newHz,divisor,inputAt,changeAt,kind}=scenario;
  const factoryOsccal96=oldHz<newHz?0:1,selectedCal=1-factoryOsccal96;
  const osccalHz=Array(128).fill(0);osccalHz[factoryOsccal96]=oldHz;osccalHz[selectedCal]=newHz;
  const c=new ATtiny13A(image,null,{resumable:true,fastIdle:false,
    fuseLow:divisor===1?0x72:0x62,oscillatorHz:oldHz,osccalHz,factoryOsccal96,
    comparatorTimingProfile:{domain:'physical-ns-v1',propagationNs,bandgapStartupNs}});
  if(kind==='propagation')c.setAnalogPs({at:inputAt,pin:0,microvolts:3000000});
  else c.writeIO(IO.ACSR,0x40);
  const context=describe(scenario);
  c.runUntilPs(changeAt);assert.equal(c.data[32+IO.ACSR]&0x30,0,context);
  c.writeIO(IO.OSCCAL,selectedCal);assert.equal(c.state().oscillatorHz,newHz,context);
  assert.equal(c.state().timePs,changeAt,context);
  c.runUntilPs(at-1n);assert.equal(c.data[32+IO.ACSR]&0x30,0,context);
  c.clock(0);assert.equal(c.state().timePs,at-1n,context);
  assert.equal(c.data[32+IO.ACSR]&0x30,0,context);
  c.runUntilPs(at);assert.equal(c.data[32+IO.ACSR]&0x30,0x30,context);
  c.clock(0);assert.equal(c.state().timePs,at,context);
  assert.equal(c.data[32+IO.ACSR]&0x30,0x30,context);
  assert.equal(c.state().deviceFault,0,context);
  return true;
}

for(const divisor of [1,8])for(const kind of ['propagation','startup','startup-plus-propagation'])
test(`selected comparator physical profile preserves ${kind} through OSCCAL changes at /${divisor}`,t=>{
  let scenarios=0;
  for(const [oldHz,newHz] of frequencyPairs)for(const delay of [0,37,111,200,500])
  for(const inputAt of kind==='propagation'?[0n,111n,113n]:[0n])for(const change of changes){
    const propagationNs=kind==='propagation'?delay:kind==='startup'?0:37;
    const bandgapStartupNs=kind==='propagation'?0:delay;
    const scenario={kind,oldHz,newHz,divisor,changeAt:change*BigInt(divisor),inputAt,
      delayNs:propagationNs+bandgapStartupNs};
    if(checkInternal(scenario,{propagationNs,bandgapStartupNs}))scenarios++;
  }
  assert.ok(scenarios>0);
  t.diagnostic(`${scenarios} independent scenarios; ${scenarios*10+1} assertions`);
});

test('selected quantized rising-edge tie remains exact after either OSCCAL frequency direction',t=>{
  let scenarios=0;
  for(const divisor of [1,8])for(const [oldHz,newHz] of frequencyPairs)
  for(const change of [50000n,55556n,111112n,150000n]){
    const base={oldHz,newHz,divisor,changeAt:change*BigInt(divisor)};
    // Use independently computed reset-phase rises solely to place a physical
    // analog completion one ps before, exactly on and one ps after a real rise.
    const tie=expectedAco({...base,inputAt:0n,delayNs:0});
    for(const offset of [-1n,0n,1n]){
      const scenario={...base,kind:'propagation',inputAt:tie+offset-37000n,delayNs:37};
      assert.ok(scenario.inputAt>=0n);
      assert.equal(checkInternal(scenario,{propagationNs:37,bandgapStartupNs:0}),true);
      scenarios++;
    }
  }
  t.diagnostic(`${scenarios} independent scenarios; ${scenarios*12} assertions`);
});

test('inactive RC calibration cannot replay a comparator sampling edge during held external CLKI',t=>{
  let scenarios=0;
  for(const initialLevel of [0,1])for(const kind of ['propagation','startup','startup-plus-propagation']){
    const c=new ATtiny13A(image,null,{resumable:true,fastIdle:false,fuseLow:0x70,
      clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel},
      comparatorTimingProfile:{domain:'physical-ns-v1',propagationNs:kind==='startup'?0:200,
        bandgapStartupNs:kind==='propagation'?0:200}});
    if(kind==='propagation')c.setAnalogPs({at:1000000n,pin:0,microvolts:3000000});
    else c.writeIO(IO.ACSR,0x40);
    assert.equal(c.injectClkiPs({edges:[],knownUntilPs:10000000n}),true);
    c.runUntilPs(1000n);c.writeIO(IO.OSCCAL,1);
    c.runUntilPs(10000000n);assert.equal(c.readIO(IO.ACSR)&0x30,0);
    c.writeIO(IO.OSCCAL,127);assert.equal(c.state().oscillatorHz,0);
    const firstRise=initialLevel?10100000n:10050000n;
    const firstEdges=initialLevel?[{timePs:10050000n,level:0},{timePs:firstRise,level:1}]:[{timePs:firstRise,level:1}];
    assert.equal(c.injectClkiPs({edges:firstEdges,knownUntilPs:20000000n}),true);
    c.runUntilPs(firstRise);assert.equal(c.readIO(IO.ACSR)&0x30,0);
    for(const cal of [63,0,127,1]){
      // The RC source is inactive: these writes may neither change CLKI nor
      // turn repeated same-half service into another synchronization clock.
      c.writeIO(IO.OSCCAL,cal);assert.equal(c.readIO(IO.OSCCAL),cal);
      assert.equal(c.readIO(IO.ACSR)&0x30,0);
    }
    c.runUntilPs(20000000n);assert.equal(c.readIO(IO.ACSR)&0x30,0);
    assert.equal(c.injectClkiPs({edges:[{timePs:24000000n,level:0},{timePs:25000000n,level:1}],knownUntilPs:26000000n}),true);
    c.runUntilPs(24999999n);assert.equal(c.readIO(IO.ACSR)&0x30,0);
    c.runUntilPs(25000000n);assert.equal(c.readIO(IO.ACSR)&0x30,0x30);
    assert.equal(c.state().deviceFault,0);scenarios++;
  }
  t.diagnostic(`${scenarios} held-source scenarios; ${scenarios*18} assertions`);
});
