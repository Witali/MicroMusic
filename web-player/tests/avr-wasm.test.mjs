import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { AVRCore } from '../lib/avr-core.js';
import { AVRCore as Reference } from '../lib/avr-reference.js';
import { Renderer } from '../lib/renderer.js';
import { parseHex } from '../lib/hex.js';
import { ReferenceFilter, ReferenceRenderer } from './helpers/reference-audio.mjs';
const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const same=(a,b)=>{
  assert.deepEqual(a.data,b.data);assert.deepEqual(a.irqFrames,b.irqFrames);
  for(const key of ['pc','cyc','timer','timerDivisor','prescalerAt','overflowAt','irqDelay',
    'irqStart','irqCount','lost','maxIRQ','writes','inIRQ','minSP','workLost','duty','eempeUntil','clkprUntil'])
    assert.equal(a[key],b[key],key);
};
const rr=(op,d,s)=>op|(d<<4)|(s&15)|((s&16)<<5);
const imm=(op,d,k)=>op|((d-16)<<4)|(k&15)|((k&240)<<4);
const make=(Core,rom,options)=>new Core(rom,null,options);

test('published WASM matches C/build inputs, has no imports and fixed isolated memory',async()=>{
  const info=JSON.parse(readFileSync(new URL('../wasm/build.json',import.meta.url)));
  const hash=b=>createHash('sha256').update(b).digest('hex');
  for(const [path,expected] of Object.entries(info.inputs))
    assert.equal(hash(readFileSync(new URL('../../'+path,import.meta.url),'utf8').replaceAll('\r\n','\n')),expected,path);
  const binary=readFileSync(new URL('../wasm/avr.wasm',import.meta.url));
  assert.equal(hash(binary),info.artifacts['avr.wasm']);
  const module=await WebAssembly.compile(binary);assert.deepEqual(WebAssembly.Module.imports(module),[]);
  const a=new AVRCore(Uint8Array.of(0,0)),b=new AVRCore(Uint8Array.of(0,0));
  assert.equal(a._exports.memory.buffer.byteLength,65536);assert.notEqual(a._exports.memory.buffer,b._exports.memory.buffer);
  a.r[0]=77;assert.equal(b.r[0],0);
});

test('C decoder agrees with JS on every opcode, operand and cached cycle class',()=>{
  const a=new AVRCore(Uint8Array.of(0,0)),b=new Reference(Uint8Array.of(0,0));
  for(let word=0;word<65536;word++){
    for(const c of [a,b]){c.rom[0]=word;c.rom[1]=word>>8;c.decode(0);}
    for(const key of ['op','d','s','k','batch','idle'])assert.equal(a[key][0],b[key][0],key+' '+word.toString(16));
  }
});

test('seeded mixed programs preserve complete CPU/timer/IRQ state, including large clocks',()=>{
  let seed=0x13a032,random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;};
  for(let run=0;run<48;run++){
    const rom=new Uint8Array(1024).fill(255),put=(p,w)=>{rom[p*2]=w;rom[p*2+1]=w>>8;};
    put(3,0xbc89);put(4,0x9518); // OUT OCR0B,r8; RETI
    for(let p=16;p<220;p++){
      const d=random()%24,s=random()%24,k=random()&255,choice=random()%12;
      const words=[rr(0x0c00,d,s),rr(0x1c00,d,s),rr(0x1800,d,s),rr(0x2000,d,s),
        rr(0x2400,d,s),rr(0x2800,d,s),rr(0x2c00,d,s),imm(0xe000,16+d%8,k),
        imm(0x5000,16+d%8,k),0x9407|(d<<4),0x900d|(d<<4),
        0xf400|((random()%5)<<3)|(random()%8)];
      put(p,words[choice]);
    }
    put(220,0xcf33); // jump back into the program
    const a=make(AVRCore,rom),b=make(Reference,rom);
    const origin=[0,2**31-40,2**32-40][run%3];
    for(const c of [a,b]){
      c.pc=16;c.cyc=origin;c.prescalerAt=origin-3;c.r[26]=96;
      c.writeIO(0x2f,run%2?3:0);c.writeIO(0x33,1+run%5);c.writeIO(0x39,2);c.i=1;
    }
    for(let n=0;n<1000;n++){
      const errors=[];
      for(const c of [a,b])try{if(!(run%2&&c.runBlock()))c.step();errors.push(null);}catch(e){errors.push(e.message);}
      assert.equal(errors[0],errors[1],`seed run ${run}, step ${n}`);same(a,b);
      if(errors[0])break;
    }
  }
});

for(const entry of catalog.entries)test(`${entry.id}: C and JS match every PWM, memory byte and IRQ for three seconds`,()=>{
  const rom=parseHex(entry.flashHex),ep=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  const a=new AVRCore(rom,ep),b=new Reference(rom,ep);
  for(let i=0;i<3*37500;i++){assert.equal(a.nextDuty(),b.nextDuty());same(a,b);}
});

for(const rate of [22050,44100,48000,96000])test(`C resampling and filtered audio at ${rate} Hz match independent JS`,()=>{
  const entry=catalog.entries[0],controls={cutoff:9000,volume:.65};
  const a=new Renderer(entry,rate,controls),b=new ReferenceRenderer(entry,rate,controls);
  const output=a.render(8192),expected=b.render(8192);same(a.core,b.core);
  assert.deepEqual(a.core.rawSamples,b.rawSamples);
  let max=0;for(let i=0;i<output.length;i++)max=Math.max(max,Math.abs(output[i]-expected[i]));
  assert.ok(max<2e-7,`PCM error ${max}`);
  const raw=new Renderer(entry,rate,{filtered:false}),rawRef=new ReferenceRenderer(entry,rate,{filtered:false});
  assert.deepEqual(raw.render(8192),rawRef.render(8192));
});

for(const rate of [8000,22050,48000,192000])for(const cutoff of [4000,6000,9000,12000])
test(`C biquads: impulse, DC and high-frequency response at ${rate}/${cutoff}`,()=>{
  const core=new AVRCore(Uint8Array.of(0,0));core.configureAudio(rate,37500,{cutoff,volume:.65});
  const filter=new ReferenceFilter(rate,cutoff,.65);
  const settled=Math.ceil(rate*.15);
  const input=Float32Array.from({length:settled+4096},(_,i)=>i===0?1:i<settled?.25:Math.sin(i*2*Math.PI*.39)*.5);
  const actual=core.filterSamples(input),expected=filter.process(input);
  let max=0;for(let i=0;i<input.length;i++)max=Math.max(max,Math.abs(actual[i]-expected[i]));
  assert.ok(max<2e-7,`filter error ${max}`);assert.equal(core.cyc,0);assert.equal(core.irqCount,0);
  assert.ok(Math.abs(actual[settled-1])<1e-4,'High-pass must reject steady DC after 150 ms');
});

test('filter and gain changes stay continuous across arbitrary audio block boundaries',()=>{
  const entry=catalog.entries[0],a=new Renderer(entry,48000),b=new Renderer(entry,48000);
  assert.deepEqual(a.render(4096),b.render(4096));
  for(const renderer of [a,b])renderer.setAudioControls({cutoff:12000,volume:.2});
  const expected=a.render(8192),actual=new Float32Array(8192);let offset=0;
  for(const n of [1,127,4096,17,3951]){actual.set(b.render(n),offset);offset+=n;}
  assert.deepEqual(actual,expected);same(a.core,b.core);assert.ok(actual.every(Number.isFinite));
  for(const renderer of [a,b])renderer.setAudioControls({cutoff:4000,volume:0});
  const quiet=a.render(16384);b.render(16384);same(a.core,b.core);
  assert.ok(Math.max(...quiet.subarray(quiet.length-1024).map(Math.abs))<1e-8,'Volume converges to zero');
});
