import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AVRCore } from '../lib/avr-core.js';

// Reviewed device instruction summary plus the individual instruction encodings
// in Microchip DS40002198A. The fixture is independent of the decoder source.
const { instructions }=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const valueOf=p=>parseInt(p.replaceAll(' ','').replace(/[^01]/g,'0'),2);
const maskOf=p=>parseInt(p.replaceAll(' ','').replace(/[01]/g,'1').replace(/[^01]/g,'0'),2);
test('every instruction-summary row has a unique reviewed status and encoding',()=>{
  assert.equal(instructions.length,123); assert.equal(new Set(instructions.map(i=>i.form)).size,123);
  for (const i of instructions) {
    assert.match(i.opcodePattern,/^[01a-zA-Z]{4}( [01a-zA-Z]{4}){3}$/);
    assert.ok(['implemented','unimplemented'].includes(i.status));
  }
});

for (const entry of instructions) test(`${entry.form}: documented timing/flags or explicit unsupported instruction`,()=>{
  const word=valueOf(entry.opcodePattern), c=new AVRCore(Uint8Array.of(word&255,word>>8,0,0));
  if (entry.status==='unimplemented') {
    assert.throws(()=>c.step(),/Unsupported opcode/); return;
  }
  if (entry.form==='RET' || entry.form==='RETI') c.pushPC(1);
  if (entry.form==='POP') c.push(0xa5);
  c.sreg=0x73;
  c.step();
  assert.ok(entry.cycles.includes(c.cyc),`${c.cyc} CPU clocks; expected ${entry.cycles}`);
  // BSET/BCLR choose the flag at runtime; other flag-preservation masks are fixed.
  assert.equal(c.sreg & ~entry.sregMask,0x73 & ~entry.sregMask);
});

test('all 65536 first words decode exactly the documented supported ATtiny13 patterns',()=>{
  const patterns=instructions.filter(i=>i.status==='implemented').map(i=>[maskOf(i.opcodePattern),valueOf(i.opcodePattern)]);
  const c=new AVRCore(Uint8Array.of(0,0));
  for (let word=0; word<65536; word++) {
    c.rom[0]=word; c.rom[1]=word>>8; c.decode(0);
    const expected=patterns.some(([mask,value])=>(word&mask)===value);
    assert.equal(c.op[0]!==0,expected,`opcode 0x${word.toString(16)}`);
  }
});
