import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {avr,sequential,IO} from './fixtures/attiny13a-system-firmware.mjs';
const moduleURL=process.env.MICROMUSIC_DEVICE_MODULE?pathToFileURL(process.env.MICROMUSIC_DEVICE_MODULE):new URL('../lib/attiny13a.js',import.meta.url);
const {ATtiny13A}=await import(moduleURL.href);
const forms=[['ADD',0x0f01,false,true],['INC',0x9503,false,true],['BST',0xfb00,false,true],
  ['SEI',0x9478,false,true],['CLI',0x94f8,false,true],['RETI',0x9518,false,true],
  ['CLT',0x94e8,false,true],['SEC',0x9408,false,true],['SET',0x9468,true,true],
  ['ADC',0x1f01,true,true],['SBC',0x0b01,true,true],['CPC',0x0701,true,true],
  ['ROR',0x9507,true,true],['BLD',0xf900,true,false],['BRNE',0xf401,true,false],
  ['OUT',avr.out(IO.PORTB,16)[0],false,false],['NOP',0,false,false]];
function bodies(bytes){
  let p=8;const u32=()=>{let n=0;for(let shift=0;shift<35;shift+=7){const b=bytes[p++];n+=(b&127)*2**shift;if(!(b&128))return n;}throw Error('Invalid WASM');};
  while(p<bytes.length){const id=bytes[p++],size=u32(),end=p+size;
    if(id===10){const count=u32();return Array.from({length:count},()=>{const size=u32(),code=Buffer.from(bytes.subarray(p,p+size));p+=size;return code;});}p=end;
  }throw Error('Missing code section');
}
function loadBytes(value){const out=[0x41];let more;
  do{const b=value&127;value>>=7;more=!((value===0&&!(b&64))||(value===-1&&(b&64)));out.push(b|(more?128:0));}while(more);
  return Buffer.from([...out,0x2d,0,0]);
}
for(const mode of ['compatible','full-context','live-locals'])test(`${mode}: SREG loads match actual inputs and retirement needs`,()=>{
  const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const resumable=mode!=='compatible',options=resumable?
    {resumable:true,optimizePhaseLocals:mode==='live-locals',oscillatorHz:hz,osccalHz,fuseLow:0x72}:{};
  const c=new ATtiny13A(sequential(forms.map(([,word])=>[word])),null,options);
  const functions=bodies(c.transpiledBytes),needle=loadBytes(c.transpilation.abi.data+c.profile.system.sreg);
  for(const [pc,[name,,consumes,writes]] of forms.entries()){
    const code=functions[pc];let count=0;for(let at=0;(at=code.indexOf(needle,at))>=0;at+=needle.length)count++;
    assert.equal(count,resumable?Number(consumes)+Number(writes):Number(consumes||writes),name);
  }
});
