import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {createPackage,DEFAULT_CONFIGURATION,PACKAGE_ABI,PACKAGE_FORMAT} from '../lib/attiny13a-package.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {Renderer as DeviceRenderer} from '../lib/renderer-device.js';
import {createPackageRenderer} from '../lib/renderer-package.js';
import {avr,IO,sequential,sleepFixture} from './fixtures/attiny13a-system-firmware.mjs';

// Independent observers must not change CPU/peripheral state or the native
// physical-pin box integral. These tests intentionally drain only one host.
const loop=sequential([]),runtime=new Uint8Array(await readFile(new URL('../wasm/attiny13a.wasm',import.meta.url)));
const abi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports);
const clockTable=()=>{const table=Array(128).fill(0);table[0]=9600000;return table;};
const options=physical=>physical?{osccalHz:clockTable()}:{};
const core=(physical=false,image=loop)=>new ATtiny13A(image,null,options(physical));
const drain=c=>c._ps?c.drainPinsPs():c.drainPins();
const now=c=>c._ps?c.state().timePs:c.state().baseHalf;
function pwm(c){
  c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,191);c.writeIO(IO.OCR0B,63);
  c.writeIO(IO.TCCR0A,0xa3);c.writeIO(IO.TCCR0B,1);return c;
}
function sameHardware(a,b){assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);}
async function pack(image=loop){
  return createPackage({flash:image,runtime,translated:transpileAVR(image,abi).bytes});
}

for(const physical of [false,true]){
  const domain=physical?'physical ps':'legacy baseHalf';
  test(`${domain}: draining host history between captures cannot steal PCM transitions`,()=>{
    const a=pwm(core(physical)),b=pwm(core(physical));
    assert.deepEqual(a.capturePhysical(1,48000,2),b.capturePhysical(1,48000,2));
    a.clock(400);b.clock(400);
    assert.ok(drain(b).length>1,'exercise actual PWM history between batches');
    const expected=a.capturePhysical(4,48000,2),actual=b.capturePhysical(4,48000,2);
    assert.ok(expected.some(value=>value!==-1&&value!==1),'nontrivial pin integration');
    assert.deepEqual(actual,expected);sameHardware(a,b);
  });

  for(const channels of [1,2])for(const sampleRate of [8000,48000,192000])
    test(`${domain}: host masks do not change ${channels}-channel PCM at ${sampleRate}Hz`,()=>{
      const reference=pwm(core(physical)),muted=pwm(core(physical)),partial=pwm(core(physical));
      muted.observePins(0,{retainDuringAudio:false});partial.observePins(0x10);
      const expected=reference.capturePhysical(21,sampleRate,channels);
      const actual=new Float32Array(21*channels);
      actual.set(muted.capturePhysical(3,sampleRate,channels));
      actual.set(muted.capturePhysical(18,sampleRate,channels),3*channels);
      assert.deepEqual(actual,expected);
      assert.deepEqual(partial.capturePhysical(21,sampleRate,channels),expected);
      sameHardware(reference,muted);sameHardware(reference,partial);
      assert.deepEqual(drain(muted),[]);
    });

  test(`${domain}: retained host snapshots and private PCM can be consumed independently`,()=>{
    const a=pwm(core(physical)),b=pwm(core(physical));
    a.observePins(63);b.observePins(63);
    assert.deepEqual(a.capturePhysical(3,48000,2),b.capturePhysical(3,48000,2));
    const first=drain(a);assert.ok(first.length>1);
    assert.deepEqual(a.capturePhysical(6,48000,2),b.capturePhysical(6,48000,2));
    const second=drain(a),all=drain(b);
    assert.deepEqual([...first,...second],all);sameHardware(a,b);
  });

  test(`${domain}: mask changes return the live baseline without clearing or replaying history`,()=>{
    const c=core(physical);c.writeIO(IO.DDRB,3);drain(c);
    c.clock(3);c.writeIO(IO.PORTB,2);
    const saved=now(c);c.observePins(0);c.clock(3);c.writeIO(IO.PORTB,0);
    const baseline=c.observePins(2);
    assert.equal(baseline.pins.levels&3,0);
    assert.equal(baseline[physical?'timePs':'baseHalf'],now(c));
    assert.deepEqual(baseline.pinObservation,{supported:true,mask:2,retainDuringAudio:true});
    const old=drain(c);assert.equal(old.length,1);
    assert.equal(old[0][physical?'timePs':'baseHalf'],saved);assert.equal(old[0].levels&3,2);
    assert.deepEqual(drain(c),[],'subscription does not enqueue a baseline row');
    c.clock(3);c.writeIO(IO.PORTB,1);assert.deepEqual(drain(c),[],'unselected changes stay out of host history');
    c.writeIO(IO.PORTB,3);c.writeIO(IO.PORTB,2);
    const selected=drain(c);assert.equal(selected.length,1);
    assert.equal(selected[0].levels&3,2,'same-time full snapshot includes later unselected pin change');
  });

  test(`${domain}: a new stream uses live levels rather than retained old host rows`,()=>{
    const c=core(physical);c.observePins(63);c.writeIO(IO.DDRB,2);
    c.clock(3);c.writeIO(IO.PORTB,2);c.observePins(0);c.clock(3);c.writeIO(IO.PORTB,0);
    assert.deepEqual(c.capturePhysical(4,48000),Float32Array.of(-1,-1,-1,-1));
    assert.ok(drain(c).some(event=>event.levels&2),'retained host history survives stream initialization');
  });

  test(`${domain}: reset transitions remain in PCM even with host history disabled`,()=>{
    const a=pwm(core(physical)),b=pwm(core(physical));b.observePins(0,{retainDuringAudio:false});
    for(const c of [a,b]){
      c.capturePhysical(1,48000,2);c.clock(40);
      const at=now(c);
      if(physical){c.injectPinsPs({at,mask:32,levels:0});c.injectPinsPs({at:at+1000000n,mask:32,levels:32});}
      else {c.injectPins({at,mask:32,levels:0});c.injectPins({at:at+20n,mask:32,levels:32});}
    }
    assert.deepEqual(a.capturePhysical(8,48000,2),b.capturePhysical(8,48000,2));
    sameHardware(a,b);assert.equal(a.state().resetCount,1);
    assert.deepEqual(b.pinObservation,{supported:true,mask:0,retainDuringAudio:false});
  });

  test(`${domain}: clock-stopped sleep and watchdog wake retain the observation policy`,()=>{
    const a=core(physical,sleepFixture(2)),b=core(physical,sleepFixture(2));
    b.observePins(0,{retainDuringAudio:false});
    for(const c of [a,b])c.run(7);
    assert.equal(a.state().sleeping,true);
    assert.deepEqual(a.capturePhysical(900,48000),b.capturePhysical(900,48000));
    sameHardware(a,b);assert.ok(a.r[20]>0,'watchdog ISR executed after power-down');
  });
}

test('outside capture, default observation remains the complete physical trace',()=>{
  const c=core();assert.deepEqual(c.pinObservation,{supported:true,mask:63,retainDuringAudio:false});
  assert.equal(Object.hasOwn(c.state(),'pinObservation'),false);
  drain(c);c.clock(2);c.writeIO(IO.DDRB,31);c.writeIO(IO.PORTB,31);
  c.clock(2);c.writeIO(IO.PORTB,0);
  const events=drain(c);assert.equal(events.length,2);
  assert.equal(events[0].levels&31,31);assert.equal(events[1].levels&31,0);
});

test('invalid observation arguments are rejected without changing policy, time or host rows',()=>{
  const c=core();c.writeIO(IO.DDRB,2);c.clock(2);c.writeIO(IO.PORTB,2);
  const state=c.state(),policy=c.pinObservation;
  for(const mask of [-1,64,1.5,NaN,'2',null,undefined])assert.throws(()=>c.observePins(mask),/Invalid pin observation/);
  for(const opt of [null,0,true,[],new Date(),{unknown:true},{retainDuringAudio:0},{retainDuringAudio:'true'}])
    assert.throws(()=>c.observePins(2,opt),/Invalid pin observation/);
  assert.deepEqual(c.state(),state);assert.deepEqual(c.pinObservation,policy);
  assert.ok(drain(c).some(event=>event.levels&2));
  for(const [mask,retain] of [[-1,0],[64,0],[0,-1],[0,2]])
    assert.equal(c._exports.avr_device_pin_trace_config(mask,retain),0);
  assert.deepEqual(c.pinObservation,policy);assert.equal(c.state().deviceFault,0);
});

test('GPIO input transitions survive host draining while capture channel/rate stay fixed',()=>{
  const a=core(),b=core();a.observePins(63);b.observePins(63);
  for(const c of [a,b]){
    c.capturePhysical(1,48000,2);
    const at=now(c);c.injectPins({at:at+10n,mask:3,levels:3});
    c.injectPins({at:at+110n,mask:3,levels:0});c.clock(100);
  }
  assert.ok(drain(b).length>=2);
  assert.deepEqual(a.capturePhysical(5,48000,2),b.capturePhysical(5,48000,2));sameHardware(a,b);
  assert.throws(()=>b.capturePhysical(1,44100,2),/sample rate/);
  assert.throws(()=>b.capturePhysical(1,48000,1),/channel count/);
  assert.equal(b.state().deviceFault,0);
});

test('bounded external-clock capture keeps PCM independent of host-drained source-edge history',()=>{
  const make=()=>pwm(new ATtiny13A(loop,null,{resumable:true,fuseLow:0x70,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}));
  const a=make(),b=make();
  for(const c of [a,b])assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,
    highPs:500000n,lowPs:500000n,transitionCount:500n,knownUntilPs:250000000n}),true);
  assert.deepEqual(a.capturePhysical(1,48000,2),b.capturePhysical(1,48000,2));
  a.runUntilPs(40000000n);b.runUntilPs(40000000n);
  assert.ok(drain(b).length>2,'real PB3 source transitions observed');
  assert.deepEqual(a.capturePhysical(4,48000,2),b.capturePhysical(4,48000,2));sameHardware(a,b);
});

test('renderers preserve explicit observers; packages retain default trace and permit explicit opt-out',async()=>{
  const a=pwm(core()),b=pwm(core());
  a.observePins(63);
  const renderer=new DeviceRenderer({pwmHz:37500,audioChannels:2},48000,{filtered:false},a);
  assert.deepEqual(a.pinObservation,{supported:true,mask:63,retainDuringAudio:true});
  assert.deepEqual(renderer.render(16),b.capturePhysical(16,48000,2));sameHardware(a,b);
  assert.ok(drain(a).length>1,'the renderer must not disable a connected observer');
  const image=sequential([avr.ldi(16,3),avr.out(IO.DDRB,16),avr.out(IO.PORTB,16)]);
  const packed=await createPackageRenderer({devicePackage:await pack(image),pwmHz:37500,audioChannels:2},48000,{filtered:false});
  assert.deepEqual(packed.core.pinObservation,{supported:true,mask:63,retainDuringAudio:false});
  packed.core.observePins(0,{retainDuringAudio:false});
  assert.equal(packed.render(16).length,32);assert.deepEqual(drain(packed.core),[]);
});

async function historicalPackage(version){
  const fixture=JSON.parse(await readFile(new URL(`./fixtures/attiny13a-runtime-v${version}.json`,import.meta.url),'utf8'));
  const runtime=gunzipSync(Buffer.from(fixture.data,'base64'));
  const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
  assert.equal(runtime.length,fixture.bytes);assert.equal(hash(runtime),fixture.sha256);
  const layout=runtimeABI(new WebAssembly.Instance(await WebAssembly.compile(runtime)).exports);
  const image=sequential([avr.ldi(16,2),avr.out(IO.DDRB,16),avr.out(IO.PORTB,16)]);
  const generated=transpileAVR(image,layout),assets=Object.fromEntries(Object.entries({
    flash:image,eeprom:new Uint8Array(64).fill(255),runtime,translated:generated.bytes,
  }).map(([name,bytes])=>[name,{encoding:'base64',bytes:bytes.length,sha256:hash(bytes),data:Buffer.from(bytes).toString('base64')}]));
  const configuration={...DEFAULT_CONFIGURATION};
  for(const name of version===1?['osccalHz','nvmClockProfile','nvmCalibrationReferenceHz','powerResetProfile','resetInputProfile']:['resetInputProfile'])delete configuration[name];
  delete configuration.resumable;delete configuration.clkiProfile;
  const pkg={format:PACKAGE_FORMAT,version,device:'ATtiny13A',abi:{id:PACKAGE_ABI,layout},configuration,manifest:generated.manifest,assets};
  const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
  pkg.integrity={algorithm:'SHA-256',sha256:hash(canonical(pkg))};return pkg;
}
for(const version of [1,3])test(`original package v${version} keeps legacy capture with explicit unsupported-observer fallback`,async()=>{
  const pkg=await historicalPackage(version),c=await ATtiny13A.fromPackage(pkg);c.run(3);
  assert.deepEqual(c.pinObservation,{supported:false,mask:63,retainDuringAudio:false});
  assert.throws(()=>c.observePins(0),/no independent pin observation/);
  assert.deepEqual(c.capturePhysical(3,48000),Float32Array.of(1,1,1));
  const renderer=await createPackageRenderer({devicePackage:pkg,pwmHz:37500},48000,{filtered:false});
  assert.equal(renderer.core.pinObservation.supported,false);
  assert.equal(renderer.render(4).length,4);assert.equal(renderer.core.state().deviceFault,0);
});
