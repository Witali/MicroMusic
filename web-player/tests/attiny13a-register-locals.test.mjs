import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr,immediate} from './helpers/avr-test-state.mjs';
import {makePhaseProbe,phaseTrace,clearPhaseProbe,PHASE_EVENT as E} from './helpers/avr-phase-probe.mjs';

const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options={resumable:true,osccalHz,oscillatorHz:hz,fuseLow:0x72,fastIdle:false};
function image(instructions){const end=16+instructions.flat().length;
  return flash({instructions:[avr.rjmp(0,16)]},
    {at:16,instructions:[...instructions,avr.rjmp(end,end)]});}
function make(binary,extra={}){const c=new ATtiny13A(binary,null,{...options,...extra});c.clock(8);c.pc=16;return c;}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),
  flash:c.rom.slice(),eeprom:c.eeprom.slice(),irqFrames:Array.from(c.irqFrames)});
function same(a,b){assert.deepEqual(snapshot(a),snapshot(b));assert.equal(a.state().deviceFault,0);}
function oracleUntil(c,end){for(let at=c.state().timePs;at<end;){at=at+10000n<end?at+10000n:end;c.runUntilPs(at);}}

// Decode actual instructions, including their immediates: opcode values can
// occur inside addresses, signed LEB constants and floating-point literals.
function blockCode(core,start=16){
  const data=core.transpiledBytes;let p=8;
  function byte(){assert.ok(p<data.length);return data[p++];}
  function leb(signed=false){let value=0n,shift=0n,b;
    do{b=byte();value|=BigInt(b&127)<<shift;shift+=7n;assert.ok(shift<=70n);}while(b&128);
    if(signed&&(b&64))value-=1n<<shift;
    return Number(value);
  }
  while(p<data.length){const id=byte(),size=leb(),end=p+size;
    if(id!==10){p=end;continue;}
    const index=core.transpilation.blocks.findIndex(b=>b.start===start);assert.ok(index>=0);
    const target=core.transpilation.mapping.length+index,count=leb();assert.ok(target<count);
    for(let n=0;n<=target;n++){const length=leb(),bodyEnd=p+length;
      if(n!==target){p=bodyEnd;continue;}
      const groups=leb(),locals=[];
      for(let j=0;j<groups;j++){const count=leb(),type=byte();locals.push({count,type});}
      const instructions=[];
      while(p<bodyEnd){const op=byte(),ins={op};
        if([0x02,0x03,0x04].includes(op))ins.type=byte();
        else if([0x0c,0x0d,0x10,0x20,0x21,0x22,0x23,0x24].includes(op))ins.index=leb();
        else if(op>=0x28&&op<=0x3e){ins.align=leb();ins.offset=leb();}
        else if(op===0x41||op===0x42)ins.value=leb(true);
        else if(op===0x44){p+=8;assert.ok(p<=bodyEnd);}
        else assert.ok([0x05,0x0b,0x0f,0x1a].includes(op)||(op>=0x45&&op<=0xc4),'Unexpected opcode '+op.toString(16));
        instructions.push(ins);
      }
      assert.equal(p,bodyEnd);return {locals,instructions};
    }
  }
  assert.fail('Missing code section');
}
function gprTraffic(core,decoded){
  const {data}=core.transpilation.abi,loads=[],stores=[];
  decoded.instructions.forEach((ins,n,list)=>{
    const address=ins.op===0x2d?list[n-1]:ins.op===0x3a?list[n-2]:null;
    if(address?.op===0x41&&address.value>=data&&address.value<data+32)
      (ins.op===0x2d?loads:stores).push({register:address.value-data,index:n});
  });
  return {loads,stores};
}

for(const initialWrite of [false,true])
test(`generated register cache has one dirty flush and ${initialWrite?'no':'one'} incoming load`,()=>{
  const instructions=[...(initialWrite?[avr.ldi(16,1)]:[]),...Array.from({length:30},()=>avr.inc(16))];
  const binary=image(instructions),a=makePhaseProbe(binary,options),b=make(binary);
  a.clock(8);a.pc=16;clearPhaseProbe(a);
  const decoded=blockCode(a),traffic=gprTraffic(a,decoded);
  assert.deepEqual(decoded.locals,[{count:10,type:0x7f}]);
  assert.deepEqual(traffic.loads.map(v=>v.register),initialWrite?[]:[16]);
  assert.deepEqual(traffic.stores.map(v=>v.register),[16]);
  const retire=decoded.instructions.findIndex(ins=>ins.op===0x10&&ins.index===18);
  assert.ok(retire>traffic.stores[0].index,'dirty register is visible before native retirement');
  const imports=WebAssembly.Module.imports(a._translatedModule);
  assert.ok(imports.every(v=>v.module==='avr'&&(v.kind==='function'||v.name==='memory')));
  assert.equal(imports.length,20,'existing native bridges and memory only');
  assert.equal(a.run(instructions.length),instructions.length);
  for(let n=0;n<instructions.length;n++)b.step();same(a,b);
  assert.equal(a.r[16],30+Number(initialWrite));
  assert.equal(phaseTrace(a).filter(v=>v.kind===E.PHASE_ENTER)[0].argument,2*instructions.length);
});

test('blocks without register operands allocate no register cache locals',()=>{
  const c=make(image([avr.nop(),avr.nop()]));
  const decoded=blockCode(c);assert.deepEqual(decoded.locals,[{count:9,type:0x7f}]);
  assert.deepEqual(gprTraffic(c,decoded),{loads:[],stores:[]});
});

const cases=[
  ...[0x7f,0x80,0xff].map(value=>({name:'ASR cached '+value,
    code:[avr.ldi(16,value),[0x9505],[0x9505]],check:c=>assert.equal(c.r[16],(value>>2)|(value&128?0xc0:0))})),
  {name:'ADIW low byte truncation',code:[[0x9601],[0x9582]],init:c=>{c.r[24]=255;c.r[25]=0;},
    check:c=>{assert.equal(c.r[24],0);assert.equal(c.r[25],1);}},
  {name:'SBIW low byte borrow',code:[[0x9701],[0x9582]],init:c=>{c.r[24]=0;c.r[25]=1;},
    check:c=>{assert.equal(c.r[24],255);assert.equal(c.r[25],0);}},
  {name:'MOVW self and disjoint pairs',code:[[0x01cc],[0x01dc],[0x9611],[0x9711],[0x01cd],avr.inc(25)],
    init:c=>{c.r[24]=255;c.r[25]=0;},check:c=>{assert.equal(c.r[24],255);assert.equal(c.r[25],1);}},
  {name:'dependent carry chained Z and T',code:[avr.add(16,17),[rr(0x1c00,18,19)],
    [rr(0x0800,20,21)],[immediate(0x4000,20,31)],[rr(0x0400,20,22)],
    [0x9547],[0xfa00|(20<<4)|3],[0xf800|(23<<4)|5],avr.inc(16)]},
];
for(const entry of cases)for(const optimizeFlags of [false,true])
test(`locals preserve ${entry.name} (flag optimization ${optimizeFlags})`,()=>{
  const binary=image(entry.code);
  for(const seed of [0,1,63,127,128,255])for(const bounded of [false,true]){
    const a=make(binary,{optimizeFlags}),b=make(binary,{optimizeFlags});
    for(const c of [a,b]){for(let r=0;r<32;r++)c.r[r]=(seed+r*29)&255;c.sreg=seed;entry.init?.(c);}
    if(bounded){const block=a.transpilation.blocks.find(v=>v.start===16),end=a.state().timePs+BigInt(block.cycles)*100000n+1n;
      a.runUntilPs(end);oracleUntil(b,end);
    }else{assert.equal(a._execute('block',Infinity,64),entry.code.length);for(let n=0;n<entry.code.length;n++)b.step();}
    same(a,b);entry.check?.(a);
  }
});

test('all 32 register locals survive remapping in a 64-instruction block',()=>{
  const code=Array.from({length:64},(_,n)=>avr.inc(n%32)),binary=image(code);
  const a=make(binary,{maxBlockInstructions:64}),b=make(binary,{maxBlockInstructions:64});
  for(const c of [a,b])for(let r=0;r<32;r++)c.r[r]=r*8;
  const decoded=blockCode(a),traffic=gprTraffic(a,decoded);
  assert.deepEqual(decoded.locals,[{count:41,type:0x7f}]);
  assert.equal(Math.max(...decoded.instructions.filter(v=>[0x20,0x21].includes(v.op)).map(v=>v.index)),42);
  assert.equal(traffic.loads.length,32);assert.equal(traffic.stores.length,32);
  assert.equal(a.run(64),64);for(let n=0;n<64;n++)b.step();same(a,b);
  assert.deepEqual(Array.from(a.r),Array.from({length:32},(_,r)=>(r*8+2)&255));
});

test('fallback observes dirty pointers and values, then the next block reloads register aliases',()=>{
  for(const address of [0,16,32+IO.PORTB,0x60,0x9f]){
    const code=[avr.ldi(16,0x41),avr.ldi(17,0x52),avr.ldi(26,address),avr.inc(16),
      avr.stx(17),avr.inc(16),avr.inc(18),avr.ldx(19),avr.inc(19),avr.inc(20),
      avr.out(IO.PORTB,16),avr.in(16,IO.PORTB),avr.inc(16),avr.inc(21)];
    const binary=image(code),a=make(binary),b=make(binary);
    assert.equal(a.run(code.length),code.length);for(let n=0;n<code.length;n++)b.step();same(a,b);
    assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
  }
});

test('repeated entry reloads host mutations and retirement low-word carry remains exact',()=>{
  const binary=image([avr.inc(16),avr.inc(16)]),a=make(binary),b=make(binary);
  for(const value of [255,0,127,128,13]){
    for(const c of [a,b]){c.pc=16;c.r[16]=value;
      new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,0xffffffffn,true);}
    assert.equal(a.run(2),2);b.step();b.step();same(a,b);
    assert.equal(a.r[16],(value+2)&255);assert.equal(a.state().cpuPhase.retired,0x100000001n);
  }
});
