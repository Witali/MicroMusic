import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,unlinkSync,rmdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-transpiled.js';
import {decodeAVR,transpileAVR,runtimeABI} from '../lib/avr-transpiler.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {parseHex} from '../lib/hex.js';
import {sameCPU,rr,immediate,put,out} from './helpers/avr-test-state.mjs';

const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const valueOf=p=>parseInt(p.replaceAll(' ','').replace(/[^01]/g,'0'),2);
const maskOf=p=>parseInt(p.replaceAll(' ','').replace(/[01]/g,'1').replace(/[^01]/g,'0'),2);
const image=words=>{const rom=new Uint8Array(1024).fill(255);words.forEach((w,p)=>put(rom,p,w));return rom;};

test('independent binary decoder matches every official supported opcode pattern',()=>{
  const patterns=instructions.map(i=>[maskOf(i.opcodePattern),valueOf(i.opcodePattern)]);
  for(let word=0;word<65536;word++)assert.equal(decodeAVR(word).name!=='unsupported',patterns.some(([mask,value])=>(word&mask)===value),'word '+word.toString(16));
});

test('all 123 official forms have a lowering, documented timing/flags and explicit device-service boundaries',()=>{
  const rom=image([]);instructions.forEach((entry,n)=>{put(rom,n*3,valueOf(entry.opcodePattern));put(rom,n*3+1,0);});
  const actual=new AVRCore(rom);
  for(const [n,entry]of instructions.entries()){
    actual._call('avr_reset',0,0);const expected=new Reference(rom,null,{fastIdle:false,fastBlocks:false});
    for(const core of [actual,expected]){
      core.pc=n*3;
      if(entry.form==='RET'||entry.form==='RETI')core.pushPC(1);
      if(entry.form==='POP')core.push(0xa5);
      if(/^(LD|LDD|ST|STD) /.test(entry.form))for(const pointer of [26,28,30])core.r[pointer]=97;
      core.sreg=0x73;
    }
    if(entry.form==='SPM'){
      assert.throws(()=>actual.step(),/Flash-controller/,entry.form);assert.equal(actual.controlRequest,2);actual.acknowledgeControl(7);continue;
    }
    actual.step();
    if(entry.status==='implemented'){expected.step();sameCPU(actual,expected,entry.form);}
    if(Array.isArray(entry.cycles))assert.ok(entry.cycles.includes(actual.cyc),entry.form+' documented cycle count');
    assert.equal(actual.sreg&~entry.sregMask,0x73&~entry.sregMask,entry.form+' preserved flags');
  }
  const imports=WebAssembly.Module.imports(new WebAssembly.Module(actual.transpiledBytes));
  assert.deepEqual(imports.map(i=>i.name),['memory','clock','interrupt','writeIO','idle']);
});

test('all byte pairs for ADD/ADC/SUB/CP and all input flags for unary shifts match independent execution',()=>{
  const words=[rr(0x0c00,16,17),rr(0x1c00,16,17),rr(0x1800,16,17),rr(0x1400,16,17),
    ...[0x9401,0x9403,0x940a,0x9400,0x9406,0x9405,0x9407,0x9402].map(w=>w|(16<<4))];
  const rom=image(words),a=new AVRCore(rom),b=new Reference(rom,null,{fastIdle:false});
  for(let pc=0;pc<4;pc++)for(let x=0;x<256;x++)for(let y=0;y<256;y++){
    const flags=(x^y)&255;
    for(const c of [a,b]){c.pc=pc;c.r[16]=x;c.r[17]=y;c.sreg=flags;}
    a._translated.step();b.step();
    assert.equal(a.r[16],b.r[16],`${pc} ${x} ${y}`);assert.equal(a.sreg,b.sreg,`${pc} flags ${x} ${y}`);
  }
  for(let pc=4;pc<words.length;pc++)for(let x=0;x<256;x++)for(let flags=0;flags<256;flags++){
    for(const c of [a,b]){c.pc=pc;c.r[16]=x;c.sreg=flags;}
    a._translated.step();b.step();assert.equal(a.r[16],b.r[16]);assert.equal(a.sreg,b.sreg,`${pc} flags ${x} ${flags}`);
  }
  assert.equal(a.cyc,b.cyc);
});

test('backward flag liveness removes overwritten flags but preserves carry consumers and exact block exits',()=>{
  const rom=image([]);[immediate(0xe000,16,255),immediate(0xe000,17,1),rr(0x0c00,16,17),rr(0x1c00,18,17),
    rr(0x2400,19,19),0x9403|(20<<4),0x940a|(21<<4),0xcff8].forEach((w,n)=>put(rom,16+n,w));
  const optimized=new AVRCore(rom),unoptimized=new AVRCore(rom,null,{optimizeFlags:false}),reference=new Reference(rom,null,{fastIdle:false});
  for(const c of [optimized,unoptimized,reference])c.pc=16;
  assert.ok(optimized.transpilation.stats.flagBitsEliminated>0);
  assert.ok(optimized.transpiledBytes.length<unoptimized.transpiledBytes.length);
  assert.equal(optimized.transpilation.blocks[0].masks[2],1,'ADD carry is consumed by ADC; its other flags are dead');
  for(let n=0;n<100;n++){
    optimized.run(8);unoptimized.run(8);for(let i=0;i<8;i++)reference.step();
    sameCPU(optimized,reference);sameCPU(unoptimized,reference);
  }
  assert.throws(()=>optimized.run(-1),/instruction count/);
  assert.throws(()=>transpileAVR(new Uint8Array(),runtimeABI(optimized._exports)),/Flash/);
});

test('event boundaries prevent block execution across timer overflows, SEI delay, EEPROM stall and SREG reads',()=>{
  const rom=image([]);
  // Main block at 16; ISR reads SREG before changing it and writes PWM.
  put(rom,3,0xb600|(8<<4)|15); // IN r8,SREG
  put(rom,4,out(0x29,8));put(rom,5,0x9518);
  const main=[0x9478,rr(0x0c00,16,17),rr(0x1c00,18,17),rr(0x2000,19,20),
    rr(0x2400,21,22),0x9407|(23<<4),0x9403|(24<<4),0xcff8];
  main.forEach((w,n)=>put(rom,16+n,w));
  const a=new AVRCore(rom);
  for(const origin of [0,2**31-16,2**32-16])for(const divisor of [1,2,3,4,5])for(const until of [1,2,3,7,8,31,32,33]){
    a._call('avr_reset',0,0);const b=new Reference(rom,null,{fastIdle:false,fastBlocks:false});
    for(const c of [a,b]){
      c.pc=16;c.cyc=origin;c.prescalerAt=origin-3;
      for(let r=0;r<32;r++)c.r[r]=(r*17+until)&255;
      c.writeIO(0x33,divisor);c.writeIO(0x39,2);c.io[0x32]=250;c.overflowAt=origin+until;
    }
    a.run(150);for(let i=0;i<150;i++)b.step();sameCPU(a,b,`${origin}/${divisor}/${until}`);
  }
  const stall=image([immediate(0xe000,16,128),out(0x26,16),immediate(0xe000,16,0),out(0x26,16),
    immediate(0xe000,17,1),out(0x1c,17),0xb000|(18<<4)|13|((0x1d&48)<<5)]);
  const x=new AVRCore(stall,new Uint8Array(64).fill(0xa5)),y=new Reference(stall,new Uint8Array(64).fill(0xa5),{fastIdle:false});
  x.run(7);for(let i=0;i<7;i++)y.step();sameCPU(x,y);assert.equal(x.r[18],0xa5);
});

test('direct memory operations and I/O aliases preserve SREG, pointer updates, diagnostics and return addresses',()=>{
  const words=[0x920d|(16<<4),0x900d|(17<<4),0x9200|(18<<4),95,0x9000|(19<<4),95,
    0x9005|(20<<4),0x920f|(21<<4),0x900f|(22<<4),0xd001,0xc001,0x9508];
  const rom=image(words),a=new AVRCore(rom),b=new Reference(rom,null,{fastIdle:false});
  for(const c of [a,b]){c.r[26]=94;c.r[30]=0;c.r[16]=0x81;c.r[18]=0x62;c.r[21]=99;}
  for(let i=0;i<10;i++){a.step();b.step();sameCPU(a,b,`memory ${i}`);}
  const invalid=new AVRCore(image([0xffff]));assert.throws(()=>invalid.step(),/Unsupported opcode at 0x0/);
  invalid.pc=512;assert.throws(()=>invalid.step(),/PC out of Flash/);
});

test('CLI output validates and executes with the recorded ABI, Flash and provenance',()=>{
  const directory=mkdtempSync(join(tmpdir(),'micromusic-avr-transpiler-')),output=join(directory,'synth.wasm');
  try{
    const input=new URL('../../ATtiny13A/Music/variants/lumiere-stereo/synth.hex',import.meta.url);
    const result=spawnSync(process.execPath,[fileURLToPath(new URL('../scripts/transpile-avr.mjs',import.meta.url)),fileURLToPath(input),output],{encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
    const generated=readFileSync(output),report=JSON.parse(readFileSync(output+'.json'));
    assert.equal(createHash('sha256').update(generated).digest('hex'),report.wasmSha256);
    assert.ok(WebAssembly.validate(generated));
    const rom=parseHex(readFileSync(input,'utf8')),runtime=new AVRCore(rom),reference=new Reference(rom,null,{fastIdle:false});
    assert.deepEqual(report.abi,runtimeABI(runtime._exports));
    const exported=new WebAssembly.Instance(new WebAssembly.Module(generated),{avr:{memory:runtime._exports.memory,
      clock:runtime._exports.avr_clock,interrupt:runtime._exports.avr_interrupt,writeIO:runtime._exports.avr_write_io,idle:runtime._exports.avr_idle}}).exports;
    exported.run(100);for(let i=0;i<100;i++)reference.step();sameCPU(runtime,reference);
  }finally{
    for(const path of [output,output+'.json'])try{unlinkSync(path);}catch(error){if(error.code!=='ENOENT')throw error;}
    rmdirSync(directory);
  }
});

const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const speech=JSON.parse(readFileSync(new URL('../hq4-firmware.json',import.meta.url)));
for(const entry of [...catalog.entries,...speech.entries])test(`${entry.id}: translated firmware preserves PWM, full memory, cycles and IRQ state`,()=>{
  const rom=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  const a=new AVRCore(rom,eeprom),b=new Reference(rom,eeprom,{fastIdle:false,fastBlocks:false});
  for(let i=0;i<2048;i++){
    const stereo=entry.audioChannels===2;
    assert.equal(stereo?a.nextStereoDuty():a.nextDuty(),stereo?b.nextStereoDuty():b.nextDuty(),`PWM ${i}`);
    sameCPU(a,b,`PWM ${i}`);
  }
});
