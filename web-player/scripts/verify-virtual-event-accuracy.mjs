// Software timing fixtures for the full verification model; no silicon oracle.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';
import {compareVerificationEvents} from './lib/avr-verification-events.mjs';
import {avr,sequential} from '../tests/fixtures/attiny13a-system-firmware.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{output:{type:'string',default:'build/virtual-event-accuracy.json'},'test-tap':{type:'string'}}});
const read=p=>readFileSync(resolve(root,p)),normal=p=>read(p).toString('utf8').replaceAll('\r\n','\n');
const hash=b=>createHash('sha256').update(b).digest('hex');
const stringify=v=>JSON.stringify(v,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n';
const metadata={configuration:'verification',device:'attiny13a'},results=[];
const idle=sequential([avr.rjmp(0,0)]),second=1000000000000n;
const ideal=(half,hz)=>BigInt(half)*second/(2n*BigInt(hz));
const ceilTime=(cycles,hz)=>(BigInt(cycles)*second+BigInt(hz)-1n)/BigInt(hz);
function make(hz,image=idle,extra={}){
  const osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  return new ATtiny13A(image,null,{...executionOptions('verification'),resumable:true,
    oscillatorHz:hz,osccalHz,factoryOsccal96:0,fuseLow:0x72,fuseStartupProfile:0,vccMicrovolts:5000000,...extra});
}
function retain(id,reference,actual,details={}){
  const comparison=compareVerificationEvents(reference,actual,metadata);
  results.push({id,...details,...comparison,
    referenceSha256:hash(stringify(reference)),actualSha256:hash(stringify(actual))});
}
const pinEvents=(events,bit,kind='pin')=>events.map(e=>({timePs:e.timePs,kind,signal:'PB'+bit,
  level:Number(!!(e.levels&(1<<bit))),driven:Number(!!(e.driven&(1<<bit)))}));
for(const hz of [9000000,9600000,9696000]){
  const c=make(hz),reference=[],actual=[];let halves=0;
  // Large irregular spans retain the exact fractional source-clock residue.
  for(const span of [1,1,3,7,31,257,4095,65537,1999999]){
    c.clock(span/2);halves+=span;
    assert.equal(c.cyc,halves/2);assert.equal(c.state().deviceFault,0);
    reference.push({timePs:ideal(halves,hz),kind:'clock-checkpoint',half:BigInt(halves)});
    actual.push({timePs:c.state().timePs,kind:'clock-checkpoint',half:BigInt(c.cyc*2)});
  }
  assert.equal(c.pc,0);assert.equal(c.state().cpuPhase.retired,0n);
  retain('internal-clock-'+hz,reference,actual,{hz,halfCycles:halves,observation:'Clock API checkpoints, not a CLKOUT pin'});
}
for(const hz of [9000000,9600000,9696000])for(const top of [0,1,3,31,255]){
  const c=make(hz),period=top+1,ticks=period*17,reference=[],actual=[];
  c.observePins(1);c.writeIO(IO.DDRB,MASK.DDB0);c.writeIO(IO.OCR0A,top);
  c.writeIO(IO.TCCR0A,MASK.COM0A0|MASK.WGM01);c.writeIO(IO.TCCR0B,MASK.CS00);c.drainPinsPs();
  for(let n=1;n<=ticks;n++){
    c.clock(1);
    const flags=MASK.OCF0B|(n>=period?MASK.OCF0A:0)|(top===255&&n>=256?MASK.TOV0:0);
    reference.push({timePs:ideal(2*n,hz),kind:'timer-counter',value:n%period,flags});
    actual.push({timePs:c.state().timePs,kind:'timer-counter',value:c.readIO(IO.TCNT0),flags:c.readIO(IO.TIFR0)});
  }
  retain('timer0-ctc-counter-'+hz+'-'+top,reference,actual,{hz,top,ticks});
  const pins=pinEvents(c.drainPinsPs(),0,'timer-pin');
  const expected=Array.from({length:17},(_,n)=>({timePs:ideal(2*period*(n+1),hz),
    kind:'timer-pin',signal:'PB0',level:(n+1)&1,driven:1}));
  retain('timer0-ctc-pin-'+hz+'-'+top,expected,pins,{hz,top,ticks});
  assert.equal(c.state().deviceFault,0);assert.equal(c.sreg,0);assert.equal(c.state().irqs,0);
}
const gpioImage=sequential([avr.ldi(16,1),avr.out(IO.DDRB,16),avr.ldi(17,0),
  avr.out(IO.PORTB,16),avr.out(IO.PORTB,17),avr.rjmp(5,3)]);
for(const hz of [9000000,9600000,9696000]){
  const limit=512,reference=[{timePs:ideal(4,hz),kind:'pin',signal:'PB0',level:0,driven:1}];
  for(let cycle=4;cycle<=limit;cycle+=4){
    reference.push({timePs:ideal(2*cycle,hz),kind:'pin',signal:'PB0',level:1,driven:1});
    if(cycle+1<=limit)reference.push({timePs:ideal(2*(cycle+1),hz),kind:'pin',signal:'PB0',level:0,driven:1});
  }
  const states=[];
  for(const partitioned of [false,true]){
    const c=make(hz,gpioImage);c.observePins(1);c.drainPinsPs();const raw=[];
    const end=ceilTime(limit,hz);
    if(partitioned){
      for(let n=1;n<=31;n++){c.runUntilPs(end*BigInt(n)/31n);raw.push(...c.drainPinsPs());}
    }else{c.runUntilPs(end);raw.push(...c.drainPinsPs());}
    retain('firmware-gpio-'+hz+(partitioned?'-partitioned':'-whole'),reference,pinEvents(raw,0),{hz,cycles:limit});
    assert.equal(c.pc,4);assert.equal(c.cyc,limit);assert.equal(c.sreg,0);
    assert.equal(c.state().cpuPhase.retired,385n);assert.equal(c.state().deviceFault,0);
    assert.deepEqual(Array.from(c.r),Array.from({length:32},(_,n)=>n===16?1:0));
    states.push({state:c.state(),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice()});
  }
  assert.deepEqual(states[0],states[1],'Partitioned verification architecture differs');
}
{
  const hz=20000000,cycles=512,half=25000n,end=BigInt(cycles)*2n*half;
  const c=make(9600000,idle,{fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  c.observePins(MASK.PINB3);c.drainPinsPs();
  assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:half,lowPs:half,
    transitionCount:BigInt(cycles)*2n,knownUntilPs:end}),true);
  c.runUntilPs(1n);assert.ok(c.state().pins.levels&MASK.PINB3);c.drainPinsPs();
  c.runUntilPs(end);
  const reference=Array.from({length:cycles*2},(_,n)=>({timePs:BigInt(n+1)*half,
    kind:'clock-input',signal:'PB3',level:(n+1)%2?0:1,driven:0}));
  retain('external-clki-20mhz',reference,pinEvents(c.drainPinsPs(),3,'clock-input'),{hz,cycles});
  assert.equal(c.state().deviceFault,0);assert.equal(c.pc,0);assert.equal(c.cyc,cycles);
  assert.equal(c.state().cpuPhase.retired,256n);
}
{
  const c=make(9600000),origin=(1n<<53n)+123n;
  c.observePins(1);c.injectPinsPs({at:0n,mask:MASK.PINB5,levels:0});c.drainPinsPs();
  const times=[origin,origin+1n,origin+9999n];
  for(const [n,at]of times.entries())c.injectPinsPs({at,mask:MASK.PINB5|1,levels:n%2?0:1});
  c.runUntilPs(origin+10000n);
  const reference=times.map((timePs,n)=>({timePs,kind:'pin-input',signal:'PB0',level:n%2?0:1,driven:0}));
  retain('large-time-neighboring-inputs',reference,pinEvents(c.drainPinsPs(),0,'pin-input'),
    {originPs:origin,minimumSeparationPs:1});
  assert.equal(c.state().deviceFault,0);assert.equal(c.state().resetHeld,true);
}
const sourcePaths=['web-player/scripts/verify-virtual-event-accuracy.mjs','web-player/scripts/lib/avr-verification-events.mjs',
  'web-player/tests/avr-verification-events.test.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
for(const [p,h]of Object.entries(AVR_CACHE_SOURCES))assert.equal(hash(normal(p)),h);
const native=read('web-player/wasm/attiny13a.wasm'),manifest=JSON.parse(read('web-player/wasm/device-build.json'));
assert.equal(hash(native),manifest.artifacts['attiny13a.wasm']);
for(const [p,h]of Object.entries(manifest.inputs))assert.equal(hash(normal(p)),h,'Stale native build input');
const report={schema:'micromusic-verification-event-accuracy-v1',...metadata,tolerancePs:10000n,
  node:process.version,native:{bytes:native.length,sha256:hash(native)},compilerIdentity:AVR_CACHE_COMPILER_ID,
  compilerSources:AVR_CACHE_SOURCES,nativeInputs:manifest.inputs,
  sources:Object.fromEntries(sourcePaths.map(p=>[p,hash(normal(p))])),results,
  maxErrorPs:results.reduce((max,r)=>r.maxErrorPs>max?r.maxErrorPs:max,0n),
  meaning:'Fixed physical-profile software fixtures and floor-projected ideal rational references, not measured silicon. Exact event identity/order/state and absolute timestamps are compared; no first-event alignment, cumulative allowance, site model change or runtime quantization.'};
if(values['test-tap']){
  const bytes=read(values['test-tap']),tap=bytes.toString();
  const counts=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(key=>{
    const match=tap.match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(match);return [key,Number(match[1])];
  }));
  assert.ok(counts.tests>0&&counts.tests===counts.pass);assert.equal(counts.fail+counts.cancelled+counts.skipped+counts.todo,0);
  report.tests={...counts,tapSha256:hash(bytes)};
}
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,stringify(report));
console.log(stringify({scenarios:results.length,events:results.reduce((n,r)=>n+r.eventCount,0),maxErrorPs:report.maxErrorPs,tolerancePs:report.tolerancePs}));
