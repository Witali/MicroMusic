// Hardware expectations: Microchip DS40002198A instruction descriptions and
// DS40002307A sections 4, 5 and 21. No archived interpreter is used as an oracle.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AVRCore } from '../lib/avr-core.js';

const rr = (op, d = 17, r = 18) => op | (d << 4) | (r & 15) | ((r & 16) << 5);
const imm = (op, d, k) => op | ((d - 16) << 4) | (k & 15) | ((k & 240) << 4);
const io = (op, d, a) => op | (d << 4) | (a & 15) | ((a & 48) << 5);
function cpu(...words) {
  return new AVRCore(Uint8Array.from(words.flatMap(w => [w & 255, w >> 8])), null, {fastIdle:false});
}
const signed = x => x < 128 ? x : x - 256;
function aluFlags(x, y, carry, sub, previous) {
  const result = sub ? x - y - carry : x + y + carry;
  const value = result & 255;
  const signedResult = sub ? signed(x) - signed(y) - carry : signed(x) + signed(y) + carry;
  const v = Number(signedResult < -128 || signedResult > 127), n = value >> 7;
  const h = Number(sub ? (x & 15) - (y & 15) - carry < 0 : (x & 15) + (y & 15) + carry > 15);
  return (previous & 0xc0) | (h << 5) | ((n ^ v) << 4) | (v << 3) | (n << 2) |
    (Number(value === 0) << 1) | Number(sub ? result < 0 : result > 255);
}
function nzvs(value, v, previous) {
  const n = value >> 7;
  return (previous & 0xe1) | ((n ^ v) << 4) | (v << 3) | (n << 2) | (Number(value === 0) << 1);
}

for (const [name, op, sub, withCarry] of [
  ['ADD', 0x0c00, false, false], ['ADC', 0x1c00, false, true], ['SUB', 0x1800, true, false],
]) {
  test(`${name}: all byte operands, carry inputs and all six arithmetic flags`, () => {
    const c = cpu(rr(op));
    for (let x = 0; x < 256; x++) for (let y = 0; y < 256; y++) {
      for (const carry of withCarry ? [0, 1] : [0]) {
        c.pc = c.cyc = 0; c.r[17] = x; c.r[18] = y;
        // In particular ADC must set Z for zero even if previous Z was clear.
        const previous = 0xfc | carry; c.sreg = previous;
        c.step();
        assert.equal(c.r[17], (sub ? x - y - carry : x + y + carry) & 255);
        assert.equal(c.sreg, aluFlags(x, y, carry, sub, previous), `${name} ${x},${y},${carry}`);
        assert.equal(c.cyc, 1); assert.equal(c.pc, 1);
      }
    }
  });
}

for (const [name, op] of [['SUBI', 0x5000], ['CPI', 0x3000]]) {
  test(`${name}: all immediate operands and borrow/overflow flags`, () => {
    for (let k = 0; k < 256; k++) {
      const c = cpu(imm(op, 17, k));
      for (let x = 0; x < 256; x++) {
        c.pc = c.cyc = 0; c.r[17] = x; c.sreg = 0xc3; c.step();
        assert.equal(c.r[17], name === 'CPI' ? x : (x - k) & 255);
        assert.equal(c.sreg, aluFlags(x, k, 0, true, 0xc3)); assert.equal(c.cyc, 1);
      }
    }
  });
}

for (const [name, op, fn] of [
  ['AND', 0x2000, (x,y) => x & y], ['EOR', 0x2400, (x,y) => x ^ y],
  ['ANDI', 0x7000, (x,y) => x & y], ['ORI', 0x6000, (x,y) => x | y],
]) {
  test(`${name}: all byte operands, NZVS and preserved I/T/H/C`, () => {
    const c = cpu(rr(op));
    for (let y = 0; y < 256; y++) {
      if (name.endsWith('I')) { const w = imm(op, 17, y); c.rom[0] = w; c.rom[1] = w >> 8; c.decode(0); }
      for (let x = 0; x < 256; x++) {
        c.pc = c.cyc = 0; c.r[17] = x; c.r[18] = y; c.sreg = 255; c.step();
        assert.equal(c.r[17], fn(x,y)); assert.equal(c.sreg, nzvs(fn(x,y), 0, 255)); assert.equal(c.cyc, 1);
      }
    }
  });
}

for (const [name, op] of [['INC',0x9403],['DEC',0x940a],['COM',0x9400],['LSR',0x9406],['ASR',0x9405],['SWAP',0x9402]]) {
  test(`${name}: every input byte and preserved flags`, () => {
    const c = cpu(op | (17 << 4));
    for (let x = 0; x < 256; x++) for (const previous of [0,255]) {
      c.pc = c.cyc = 0; c.r[17] = x; c.sreg = previous;
      let value, flags;
      if (name === 'INC' || name === 'DEC') {
        value = (x + (name === 'INC' ? 1 : -1)) & 255;
        flags = nzvs(value, Number(x === (name === 'INC' ? 127 : 128)), previous);
      } else if (name === 'COM') { value = x ^ 255; flags = nzvs(value, 0, previous) | 1; }
      else if (name === 'SWAP') { value = ((x << 4) | (x >> 4)) & 255; flags = previous; }
      else { value = (x >> 1) | (name === 'ASR' ? x & 128 : 0); flags = nzvs(value, (value >> 7) ^ (x & 1), previous & 254) | (x & 1); }
      c.step(); assert.equal(c.r[17], value); assert.equal(c.sreg, flags); assert.equal(c.cyc, 1);
    }
  });
}

test('NOP/LDI/MOV/MOVW and aliases preserve all flags and decode register high bits', () => {
  for (let d = 0; d < 32; d++) for (let s = 0; s < 32; s++) {
    const c = cpu(rr(0x2c00, d, s)); c.r[s] = 213; c.sreg = 255; c.step();
    assert.equal(c.r[d], 213); assert.equal(c.sreg,255); assert.equal(c.cyc,1);
  }
  for (let d = 0; d < 32; d += 2) for (let s = 0; s < 32; s += 2) {
    const c = cpu(0x0100 | ((d / 2) << 4) | (s / 2)); c.r[s] = 0x21; c.r[s+1] = 0x43;
    c.sreg=255; c.step(); assert.equal(c.r[d],0x21); assert.equal(c.r[d+1],0x43); assert.equal(c.sreg,255); assert.equal(c.cyc,1);
  }
  for (let d = 16; d < 32; d++) for (const k of [0,15,16,127,128,255]) {
    const c = cpu(imm(0xe000,d,k),0); c.sreg=255; c.step(); c.step();
    assert.equal(c.r[d],k); assert.equal(c.sreg,255); assert.equal(c.cyc,2);
  }
});

test('all eight SREG flags can be set, cleared, read and restored through I/O', () => {
  for (let bit=0; bit<8; bit++) {
    const c=cpu(0x9408 | (bit<<4), io(0xb000,17,63), 0x9488 | (bit<<4), io(0xb800,17,63));
    c.step(); assert.equal(c.sreg,1<<bit); c.step(); assert.equal(c.r[17],1<<bit);
    c.step(); assert.equal(c.sreg,0); c.step(); assert.equal(c.sreg,1<<bit); assert.equal(c.cyc,4);
  }
});

test('all branch flags and signed offsets use 1/2 cycles and wrap the 9-bit PC', () => {
  for (let bit=0; bit<8; bit++) for (const set of [false,true]) for (const value of [0,1]) for (const k of [-64,-1,0,63]) {
    const c=cpu((set?0xf000:0xf400) | ((k&127)<<3) | bit); c.sreg=value<<bit; c.step();
    const taken=!!value===set; assert.equal(c.pc,(1+(taken?k:0))&511); assert.equal(c.cyc,taken?2:1);
  }
  const c=cpu(0xcffe); c.step(); assert.equal(c.pc,511); assert.equal(c.cyc,2);
  c.rom[1022]=c.rom[1023]=0; c.decode(511); c.step(); assert.equal(c.pc,0);
});

test('SBRC/SBRS use 1/2/3 cycles and distinguish ST Z+ from two-word STS', () => {
  for (const set of [false,true]) for (const value of [0,1]) for (let bit=0; bit<8; bit++) {
    for (const [word,width] of [[0,1],[0x9201,1],[0x9000,2],[0x9200,2],[0x940c,2],[0x940e,2]]) {
      const c=cpu((set?0xfe00:0xfc00) | (17<<4) | bit,word,0); c.r[17]=value<<bit; c.sreg=255;
      c.step(); const skip=!!value===set; assert.equal(c.pc,1+(skip?width:0)); assert.equal(c.cyc,1+(skip?width:0)); assert.equal(c.sreg,255);
    }
  }
});

test('RCALL/RET use two bytes of SRAM and SPL, interoperate with PUSH/POP', () => {
  const c=cpu(0xd001,0,0x920f|(17<<4),0x900f|(18<<4),0x9508);
  c.r[17]=0xa5; c.sreg=0x73;
  assert.equal(c.sp,159); c.step(); assert.equal(c.sp,157); assert.equal(c.pc,2); assert.equal(c.cyc,3);
  assert.equal(c.data[159],1); assert.equal(c.data[158],0);
  c.step(); assert.equal(c.sp,156); assert.equal(c.data[157],0xa5);
  c.step(); assert.equal(c.r[18],0xa5); assert.equal(c.sp,157);
  c.step(); assert.equal(c.pc,1); assert.equal(c.sp,159); assert.equal(c.cyc,11); assert.equal(c.sreg,0x73);
  const high=cpu(0xd000); high.pc=511; high.rom[1022]=0; high.rom[1023]=0xd0; high.decode(511);
  high.step(); assert.equal(high.data[159],0); assert.equal(high.data[158],0); // wrapped return PC
  assert.throws(()=>cpu(0x9508).step(),/Stack underflow/);
});

test('ST Z+ maps register file and SRAM and LPM addresses bytes, each with its own timing', () => {
  for (const address of [0,25,96,159]) {
    const c=cpu(0x9201|(17<<4)); c.r[30]=address; c.r[17]=0xa5; c.sreg=0x73; c.step();
    assert.equal(c.data[address],0xa5); assert.equal(c.r[30],address+1); assert.equal(c.cyc,2); assert.equal(c.sreg,0x73);
  }
  for (const post of [0,1]) for (const address of [0,1,1022,1023]) {
    const c=cpu(0x9004|(17<<4)|post); c.r[30]=address&255; c.r[31]=address>>8; const value=c.rom[address];
    c.sreg=0x73; c.step(); assert.equal(c.r[17],value); assert.equal(c.r[30]|c.r[31]<<8,address+post); assert.equal(c.cyc,3); assert.equal(c.sreg,0x73);
  }
  assert.throws(()=>cpu(0x9005|(30<<4)).step(),/Undefined/);
  assert.throws(()=>cpu(0x9201|(31<<4)).step(),/Undefined/);
});

test('SBI EEPROM read adds four CPU wait cycles and preserves SREG', () => {
  const c=cpu(0x9a00|(0x1c<<3)); c.eeprom[63]=0xa5; c.io[0x1e]=255; c.sreg=0x73; c.step();
  assert.equal(c.cyc,6); assert.equal(c.io[0x1d],0xa5); assert.equal(c.io[0x1c]&1,0); assert.equal(c.sreg,0x73);
});

function pendingIRQ(...words) { const c=cpu(...words); c.pending=true; c.io[0x39]=2; return c; }
test('SEI and RETI execute one following instruction; CLI disables immediately', () => {
  const c=pendingIRQ(0x9478,imm(0xe000,17,0xa5)); c.step(); assert.equal(c.pc,1); assert.equal(c.irqCount,0);
  c.step(); assert.equal(c.r[17],0xa5); assert.equal(c.pc,3); assert.equal(c.cyc,6); assert.equal(c.sp,157);
  const d=pendingIRQ(0x94f8); d.i=1; d.step(); assert.equal(d.irqCount,0); assert.equal(d.cyc,1);
  const e=pendingIRQ(0x9518,imm(0xe000,17,0x21)); e.pushPC(1); e.step(); assert.equal(e.pc,1); assert.equal(e.cyc,4);
  e.step(); assert.equal(e.r[17],0x21); assert.equal(e.pc,3); assert.equal(e.cyc,9);
});

test('unsupported instructions fail explicitly instead of acquiring accidental timing', () => {
  for (const word of [0xffff,0x940c,0x940e,0x95e8,0x9588,0x95a8,0x9c00,0x9000,0x9200]) {
    assert.throws(()=>cpu(word).step(),/Unsupported opcode/);
  }
});
