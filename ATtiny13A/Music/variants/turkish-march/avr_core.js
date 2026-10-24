// Strict Intel HEX parser shared by the player, tests, and catalog checks.
function parseHex(text, limit = 1024) {
  const memory = new Uint8Array(limit).fill(255);
  const present = new Uint8Array(limit);
  let end = 0, eof = false;
  for (const line of text.trim().split(/\s+/)) {
    if (eof) throw new Error('Data after HEX end record');
    if (!/^:(?:[\da-f]{2})+$/i.test(line)) throw new Error('Invalid HEX record');
    const bytes = Uint8Array.from(line.slice(1).match(/../g), x => parseInt(x, 16));
    const count = bytes[0], address = (bytes[1] << 8) | bytes[2], type = bytes[3];
    if (bytes.length !== count + 5 || bytes.reduce((a, b) => a + b, 0) % 256) throw new Error('HEX length or checksum mismatch');
    if (type === 1) {
      if (count || address) throw new Error('Invalid HEX end record');
      eof = true;
    } else if (type === 0) {
      if (address + count > limit) throw new Error('HEX exceeds device memory');
      for (let i = 0; i < count; i++) {
        if (present[address + i]) throw new Error('Overlapping HEX records');
        memory[address + i] = bytes[4 + i]; present[address + i] = 1;
      }
      end = Math.max(end, address + count);
    } else throw new Error('Unsupported HEX record type');
  }
  if (!eof || !end || present.subarray(0, end).some(x => !x)) throw new Error('Incomplete HEX image');
  return memory.slice(0, end);
}

// Specialized interpreter for the archived synth firmware, derived from its
// HTML players. ROM bytes are immutable; decode once, execute integer op IDs.
// ATtiny13A, AVRe timings. See reports/attiny13a-audit.txt for instruction coverage
// and peripheral limitations; this remains a firmware-oriented AVR subset.
const OP = { NOP:1, CLI:2, SEI:3, RETI:4, RET:5, CALL:6, JUMP:7, BRANCH:8,
  SKIP:9, LDI:10, CPI:11, SUBI:12, ORI:13, ANDI:14, MOVW:15, ADD:16,
  ADC:17, SUB:18, AND:19, EOR:20, MOV:21, INC:22, DEC:23, COM:24,
  LSR:25, ASR:26, SWAP:27, IN:28, OUT:29, SBI:30, PUSH:31, POP:32, ST:33, LPM:34, FLAG:35,
  ROR:36, LDS:37, STS:38, OR:39, LD:40, CP:41, NEG:42, SBC:43, SBCI:44, ADIW:45, SBIW:46 };
const sign = (v, bit) => v & bit ? v - bit * 2 : v;
// Maximum cycles for instructions that can execute without observing I/O.
// Everything else remains in step(), including all peripheral and stack access.
const BATCH_CYCLES = new Uint8Array(47);
for (const op of [OP.NOP, OP.LDI, OP.CPI, OP.SUBI, OP.ORI, OP.ANDI, OP.MOVW,
  OP.ADD, OP.ADC, OP.SUB, OP.AND, OP.EOR, OP.OR, OP.MOV, OP.INC, OP.DEC,
  OP.COM, OP.LSR, OP.ASR, OP.ROR, OP.SWAP, OP.SBC, OP.SBCI]) BATCH_CYCLES[op] = 1;
for (const op of [OP.JUMP, OP.BRANCH, OP.LD, OP.ST, OP.ADIW, OP.SBIW]) BATCH_CYCLES[op] = 2;
BATCH_CYCLES[OP.SKIP] = BATCH_CYCLES[OP.LPM] = 3;
const NZ = Uint8Array.from({length:256}, (_, v) => (v === 0 ? 2 : 0) | (v & 128 ? 0x14 : 0));
// NZ assumes V=0 (S=N). XOR 0x18 sets V and flips S when overflow is set.
const wordArithmetic = (flags, x, k, subtract) => {
  const total = subtract ? x-k : x+k, value = total&65535, negative = value>>15;
  const overflow = ((subtract ? x&~value : ~x&value)>>15)&1;
  flags = (flags&0xe0) | ((negative^overflow)<<4) | (overflow<<3) | (negative<<2) |
    (Number(value===0)<<1) | Number(subtract ? total<0 : total>65535);
  return (flags<<16)|value;
};

class AVRCore {
  constructor(binary, eeprom, { fastIdle = true, fastBlocks = fastIdle } = {}) {
    if (!binary.length || binary.length > 1024) throw new Error('Flash must contain 1–1024 bytes');
    if (eeprom && eeprom.length !== 64) throw new Error('EEPROM must contain 64 bytes');
    this.rom = new Uint8Array(1024).fill(255); this.rom.set(binary);
    this.eeprom = new Uint8Array(64).fill(255); if (eeprom) this.eeprom.set(eeprom);
    this.data = new Uint8Array(160);
    this.r = this.data.subarray(0, 32); this.io = this.data.subarray(32, 96);
    this.sram = this.data.subarray(96);
    this.ram = this.sram; // Preserve the SRAM inspection alias used by firmware tools.
    this.op = new Uint8Array(512); this.d = new Uint8Array(512);
    this.s = new Uint8Array(512); this.k = new Int16Array(512);
    this.batch = new Uint8Array(512);
    this.sp = 0x9f; // SPL resets to RAMEND; return addresses occupy TWO bytes.
    this.minSP = this.sp;
    this.pc = this.cyc = this.z = this.c = this.i = 0;
    this.irqDelay = 0;
    this.timer = this.pending = this.inIRQ = false; this.overflowAt = Infinity;
    this.timerDivisor = 0; this.prescalerAt = 0;
    this.irqStart = this.irqCount = this.lost = this.maxIRQ = this.writes = 0;
    this.irqFrames = [];
    this.workLost = 0;
    this.duty = this.dutyLeft = 128; this.leftWrites=0; this.fastIdle = fastIdle; this.idleCycles = 0;
    this.fastBlocks = fastBlocks; this.blockInstructions = 0;
    for (let p = 0; p < 512; p++) this.decode(p);
    this.idle = new Uint8Array(512);
    for (let p = 0; p < 512; p++) this.decodeIdle(p);
  }
  get sreg() { return this.io[0x3f]; }
  set sreg(value) { this.io[0x3f] = value; }
  get c() { return this.sreg & 1; }
  set c(value) { this.sreg = (this.sreg & ~1) | (value & 1); }
  get z() { return (this.sreg >> 1) & 1; }
  set z(value) { this.sreg = (this.sreg & ~2) | ((value & 1) << 1); }
  get i() { return this.sreg >> 7; }
  set i(value) { this.sreg = (this.sreg & 127) | ((value & 1) << 7); }
  get t() { return (this.sreg >> 6) & 1; }
  set t(value) { this.sreg = (this.sreg & ~64) | ((value & 1) << 6); }
  get sp() { return this.io[0x3d]; }
  set sp(value) { this.io[0x3d] = value; }
  get pending() { return !!(this.io[0x38] & 2); }
  set pending(value) { this.io[0x38] = (this.io[0x38] & ~2) | (value ? 2 : 0); }
  nzvs(value, overflow = 0) {
    const negative = value >> 7;
    this.sreg = (this.sreg & 0xe1) | (Number(value === 0) << 1) |
      (negative << 2) | (overflow << 3) | ((negative ^ overflow) << 4);
  }
  arithmetic(x, y, carry = 0, subtract = false) {
    const total = subtract ? x - y - carry : x + y + carry, value = total & 255;
    const overflow = ((subtract ? (x ^ y) : ~(x ^ y)) & (x ^ value) & 128) >> 7;
    const negative = value >> 7;
    this.sreg = (this.sreg & 0xc0) | (Number(value === 0) << 1) |
      (negative << 2) | (overflow << 3) | ((negative ^ overflow) << 4) |
      Number(subtract ? total < 0 : total > 255) |
      (Number(subtract ? (x & 15) < (y & 15) + carry : (x & 15) + (y & 15) + carry > 15) << 5);
    return value;
  }
  decode(p) {
    const w = this.rom[p * 2] | this.rom[p * 2 + 1] << 8;
    let o = 0, d = (w >> 4) & 31, s = (w & 15) | ((w >> 5) & 16), k = 0;
    if (w === 0) o = OP.NOP;
    else if (w === 0x94f8) o = OP.CLI;
    else if (w === 0x9478) o = OP.SEI;
    else if (w === 0x9518) o = OP.RETI;
    else if (w === 0x9508) o = OP.RET;
    else if ((w & 0xff0f) === 0x9408) { o = OP.FLAG; d = (w >> 4) & 7; k = Number(!(w & 0x80)); }
    else if ((w & 0xf000) === 0xd000) { o = OP.CALL; k = sign(w & 4095, 2048); }
    else if ((w & 0xf000) === 0xc000) { o = OP.JUMP; k = sign(w & 4095, 2048); }
    else if ((w & 0xfc00) === 0xf000 || (w & 0xfc00) === 0xf400) {
      o = OP.BRANCH; d = w & 7; s = Number((w & 0xfc00) === 0xf000); k = sign((w >> 3) & 127, 64);
    } else if ((w & 0xfe08) === 0xfc00 || (w & 0xfe08) === 0xfe00) {
      o = OP.SKIP; s = w & 7; k = Number((w & 0xfe08) === 0xfe00);
    } else if ((w & 0xf000) === 0xe000) { o = OP.LDI; d = 16 + ((w >> 4) & 15); k = (w & 15) | ((w >> 4) & 240); }
    else if ([0x3000,0x4000,0x5000,0x6000,0x7000].includes(w & 0xf000)) {
      o = ({12288:OP.CPI,16384:OP.SBCI,20480:OP.SUBI,24576:OP.ORI,28672:OP.ANDI})[w & 0xf000];
      d = 16 + ((w >> 4) & 15); k = (w & 15) | ((w >> 4) & 240);
    } else if ((w & 0xff00) === 0x9600 || (w & 0xff00) === 0x9700) {
      o = (w & 0xff00) === 0x9600 ? OP.ADIW : OP.SBIW;
      d = 24 + ((w >> 3) & 6); k = (w & 15) | ((w >> 2) & 48);
    } else if ((w & 0xff00) === 0x0100) { o = OP.MOVW; d = 2 * ((w >> 4) & 15); s = 2 * (w & 15); }
    else if ([0x0c00,0x1c00,0x1800,0x2000,0x2400,0x2800,0x2c00].includes(w & 0xfc00))
      o = ({3072:OP.ADD,7168:OP.ADC,6144:OP.SUB,8192:OP.AND,9216:OP.EOR,10240:OP.OR,11264:OP.MOV})[w & 0xfc00];
    else if ((w & 0xfc00) === 0x0800) o = OP.SBC;
    else if ((w & 0xfc00) === 0x1400) o = OP.CP;
    else if ((w & 0xfe0f) === 0x9401) o = OP.NEG;
    else if ([0x9403,0x940a,0x9400,0x9406,0x9405,0x9407,0x9402].includes(w & 0xfe0f))
      o = ({37891:OP.INC,37898:OP.DEC,37888:OP.COM,37894:OP.LSR,37893:OP.ASR,37895:OP.ROR,37890:OP.SWAP})[w & 0xfe0f];
    else if ((w & 0xfe0f) === 0x9000 || (w & 0xfe0f) === 0x9200) {
      o = (w & 0xfe0f) === 0x9000 ? OP.LDS : OP.STS;
      const next = ((p + 1) & 511) * 2;
      k = this.rom[next] | this.rom[next + 1] << 8;
    }
    else if ((w & 0xf800) === 0xb000) { o = OP.IN; k = ((w >> 5) & 48) | (w & 15); }
    else if ((w & 0xf800) === 0xb800) { o = OP.OUT; k = ((w >> 5) & 48) | (w & 15); }
    else if ((w & 0xff00) === 0x9a00) { o = OP.SBI; d = (w >> 3) & 31; k = w & 7; }
    else if ((w & 0xfe0f) === 0x920f) o = OP.PUSH;
    else if ((w & 0xfe0f) === 0x900f) o = OP.POP;
    else if ([0x900c,0x900d,0x900e,0x9009,0x900a,0x9001,0x9002,
              0x920c,0x920d,0x920e,0x9209,0x920a,0x9201,0x9202].includes(w & 0xfe0f)) {
      o = w & 0x200 ? OP.ST : OP.LD;
      const low = w & 15;
      s = low >= 12 ? 26 : low >= 9 ? 28 : 30;
      // 1: post-increment; -1: pre-decrement; 2+q: unchanged pointer + displacement.
      k = [1,9,13].includes(low) ? 1 : [2,10,14].includes(low) ? -1 : 2;
    }
    else if ((w & 0xd200) === 0x8000 || (w & 0xd200) === 0x8200) {
      o = w & 0x200 ? OP.ST : OP.LD; s = w & 8 ? 28 : 30;
      k = 2 + ((w & 7) | ((w >> 7) & 0x18) | ((w >> 8) & 0x20));
    }
    else if ((w & 0xfe0f) === 0x9004 || (w & 0xfe0f) === 0x9005) { o = OP.LPM; k = w & 1; }
    this.op[p] = o; this.d[p] = d; this.s[p] = s; this.k[p] = k;
    this.batch[p] = (o === OP.LD || o === OP.ST) && k !== 1 ? 0 : BATCH_CYCLES[o];
    // A re-decoded word can change any polling loop containing it.
    if (this.idle) for (let offset = 0; offset < 5; offset++) this.decodeIdle((p - offset) & 511);
  }
  decodeIdle(p) {
    const op = this.op, d = this.d, s = this.s, k = this.k;
    this.idle[p] = 0;
    if (k[p] === -1) {
      if (op[p] === OP.JUMP) this.idle[p] = 1;
      if (op[p] === OP.BRANCH && d[p] === 6 && s[p] === 0) this.idle[p] = 2;
    }
    const sub = (p + 1) & 511, mask = (p + 2) & 511;
    const cmp = (p + 3) & 511, branch = (p + 4) & 511, target = d[p];
    // MOV tmp, producer; SUB tmp, consumer; ANDI tmp, mask; CPI tmp, limit;
    // BRCC start. Only tmp and arithmetic flags change, identically each lap.
    if (op[p] === OP.MOV && op[sub] === OP.SUB && op[mask] === OP.ANDI &&
        op[cmp] === OP.CPI && op[branch] === OP.BRANCH &&
        d[sub] === target && d[mask] === target && d[cmp] === target &&
        s[p] !== target && s[sub] !== target &&
        d[branch] === 0 && s[branch] === 0 && k[branch] === -5) this.idle[p] = 3;
  }
  skipIdle() {
    if (!this.timer || !this.i || this.irqDelay || this.pending || !(this.io[0x39] & 2)) return false;
    const p = this.pc, kind = this.idle[p];
    if (!kind) return false;
    let n;
    if (kind === 3) {
      const value = (this.r[this.s[p]] - this.r[this.s[(p + 1) & 511]]) & this.k[(p + 2) & 511];
      const limit = this.k[(p + 3) & 511];
      if (value < limit) return false;
      // Keep the final, possibly interrupted lap in the single-step executor.
      // The IRQ must see even a partially calculated tmp/SREG at its real cycle.
      n = Math.floor((this.overflowAt - this.cyc - 1) / 6) * 6;
      if (n <= 0) return false;
      this.r[this.d[p]] = value;
      this.arithmetic(value, limit, 0, true);
    } else {
      if (kind === 2 && this.t) return false;
      n = Math.max(2, Math.ceil((this.overflowAt - this.cyc) / 2) * 2);
    }
    this.idleCycles += n; this.clock(n); this.interrupt();
    return true;
  }
  push(value) {
    if (this.sp < 0x60 || this.sp > 0x9f) throw new Error('Stack overflow or invalid SPL');
    this.data[this.sp--] = value;
    this.minSP = Math.min(this.minSP, this.sp);
  }
  pop() {
    if (this.sp < 0x5f || this.sp >= 0x9f) throw new Error('Stack underflow or invalid SPL');
    return this.data[++this.sp];
  }
  pushPC(value) { this.push(value & 255); this.push(value >> 8); }
  popPC() { const high = this.pop(); return ((high << 8) | this.pop()) & 511; }
  timerMode() { return (this.io[0x2f] & 3) | ((this.io[0x33] & 8) >> 1); }
  updateTimer() {
    const source = this.io[0x33] & 7, mode = this.timerMode();
    if (source >= 6) throw new Error('External Timer0 clock is not implemented');
    if (source && mode !== 0 && mode !== 3) throw new Error('Timer0 WGM mode ' + mode + ' is not implemented');
    this.timerDivisor = [0,1,8,64,256,1024][source];
    this.timer = !!this.timerDivisor && !(this.io[0x25] & 2) && (this.io[0x28] & 0x81) !== 0x81;
    if (!this.timer) { this.overflowAt = Infinity; return; }
    // Normal: TOV on FF -> 00. Fast PWM mode 3: TOV when reaching TOP.
    const target = mode === 3 ? 255 : 0;
    const ticks = ((target - this.io[0x32]) & 255) || 256;
    this.overflowAt = this.prescalerAt +
      (Math.floor((this.cyc - this.prescalerAt) / this.timerDivisor) + ticks) * this.timerDivisor;
  }
  writeIO(address, value) {
    value &= 255;
    if (address === 0x37 && (value & 31)) throw new Error('Flash programming/fuse access is not implemented');
    if (address === 0x21 && (value & 0x58)) throw new Error('Watchdog operation is not implemented');
    if (address === 0x06 && (value & 0x80)) throw new Error('ADC operation is not implemented');
    if (address === 0x08 && (value & 8)) throw new Error('Analog comparator interrupts are not implemented');
    if (address === 0x3b && (value & 0x60)) throw new Error('External/pin-change interrupts are not implemented');
    if (address === 0x26) {
      if (value & 128) {
        if (value === 128 && !(this.clkprUntil > this.cyc)) {
          this.io[address] = 128; this.clkprUntil = this.cyc + 4;
        }
      } else if (this.clkprUntil > this.cyc) {
        if (value & 15) throw new Error('Runtime CPU clock division is not implemented');
        this.io[address] = 0; this.clkprUntil = 0;
      }
      return 0;
    }
    if (address === 0x38) { this.io[address] &= ~(value & 14); return 0; } // W1C
    if (address === 0x39 && (value & 12)) throw new Error('Timer0 compare interrupts are not implemented');
    if (address === 0x1c) {
      if (value & 10) throw new Error('EEPROM programming/ready interrupt is not implemented');
      this.io[address] = value & 0x3c;
      if (value & 4) this.eempeUntil = this.cyc + 4;
      if (value & 1) { this.io[0x1d] = this.eeprom[this.io[0x1e] & 63]; return 4; }
      return 0;
    }
    if (address === 0x1e) value &= 63;
    if (address === 0x39) value &= 14;
    if (address === 0x33) {
      if (value & 0xc0) throw new Error('Timer0 forced compare output is not implemented');
      value &= 15;
    }
    if (address === 0x28) {
      value &= 0x81;
      if ((value & 1) || (this.io[address] & 1)) this.prescalerAt = this.cyc;
      if (!(value & 128)) value &= ~1;
    }
    this.io[address] = value;
    if ([0x25,0x28,0x2f,0x32,0x33].includes(address)) this.updateTimer();
    if (address === 0x29 && this.timer) { this.duty = value; this.writes++; }
    if (address === 0x2a && this.timer) { this.dutyLeft=value;this.leftWrites++; }
    return 0;
  }
  clock(n) {
    const before = this.cyc;
    this.cyc += n;
    if (this.eempeUntil <= this.cyc) this.io[0x1c] &= ~4;
    if (this.clkprUntil <= this.cyc) this.io[0x26] &= ~128;
    if (this.timer && this.overflowAt <= this.cyc) {
      const events = 1 + Math.floor((this.cyc - this.overflowAt) / (256 * this.timerDivisor));
      this.lost += events - Number(!this.pending); this.pending = true;
      this.overflowAt += events * 256 * this.timerDivisor;
    }
    if (this.timer) {
      const ticks = this.timerDivisor === 1 ? n : Math.floor((this.cyc - this.prescalerAt) / this.timerDivisor) -
        Math.floor((before - this.prescalerAt) / this.timerDivisor);
      this.io[0x32] = (this.io[0x32] + ticks) & 255;
    }
  }
  interrupt() {
    if (this.irqDelay) { this.irqDelay--; return; }
    if (!this.i || !(this.io[0x39] & 2) || !this.pending) return;
    this.pending = false; this.pushPC(this.pc); this.pc = 3; this.i = 0;
    this.irqStart = this.cyc; this.irqFrames.push(this.irqStart);
    this.clock(4); this.inIRQ = true; this.irqCount++;
  }
  step() {
    const p = this.pc;
    if (p < 0 || p >= 512) throw new Error('PC out of Flash');
    const d = this.d[p], s = this.s[p], k = this.k[p], r = this.r;
    let n = 1, v, z;
    this.pc = (this.pc + 1) & 511;
    switch (this.op[p]) {
      case OP.NOP: break;
      case OP.CLI: this.i = 0; break;
      case OP.SEI: this.i = 1; this.irqDelay = 1; break;
      case OP.FLAG:
        if (d === 6 && k && this.t && this.inIRQ) this.workLost++;
        this.sreg = (this.sreg & ~(1 << d)) | (k << d); break;
      case OP.RETI:
        this.pc = this.popPC(); this.i = 1; this.irqDelay = 1; n = 4;
        v = this.irqFrames.pop();
        if (v !== undefined) this.maxIRQ = Math.max(this.maxIRQ, this.cyc + n - v);
        this.inIRQ = this.irqFrames.length > 0;
        this.irqStart = this.inIRQ ? this.irqFrames[this.irqFrames.length - 1] : 0;
        break;
      case OP.RET: this.pc = this.popPC(); n = 4; break;
      case OP.CALL: this.pushPC(this.pc); this.pc += k; n = 3; break;
      case OP.JUMP: this.pc += k; n = 2; break;
      case OP.BRANCH:
        if (((this.sreg >> d) & 1) === s) { this.pc += k; n = 2; } break;
      case OP.SKIP:
        if (((r[d] >> s) & 1) === k) {
          const w = this.rom[this.pc * 2] | this.rom[this.pc * 2 + 1] << 8;
          const words = (w & 0xfe0f) === 0x9000 || (w & 0xfe0f) === 0x9200 ||
            (w & 0xfe0e) === 0x940c || (w & 0xfe0e) === 0x940e ? 2 : 1;
          this.pc += words; n = 1 + words;
        } break;
      case OP.LDI: r[d] = k; break;
      case OP.CPI: this.arithmetic(r[d], k, 0, true); break;
      case OP.SUBI: r[d] = this.arithmetic(r[d], k, 0, true); break;
      case OP.ORI: r[d] |= k; this.nzvs(r[d]); break;
      case OP.ANDI: r[d] &= k; this.nzvs(r[d]); break;
      case OP.MOVW: r[d] = r[s]; r[d + 1] = r[s + 1]; break;
      case OP.ADIW:
      case OP.SBIW:
        v = wordArithmetic(this.sreg, r[d] | r[d+1]<<8, k, this.op[p] === OP.SBIW);
        r[d] = v; r[d+1] = v>>8; this.sreg = v>>16; n = 2; break;
      case OP.ADD: r[d] = this.arithmetic(r[d], r[s]); break;
      case OP.ADC: r[d] = this.arithmetic(r[d], r[s], this.c); break;
      case OP.SUB: r[d] = this.arithmetic(r[d], r[s], 0, true); break;
      case OP.SBC:
      case OP.SBCI: {
        const previous = this.sreg;
        r[d] = this.arithmetic(r[d], this.op[p] === OP.SBC ? r[s] : k, previous & 1, true);
        if (!(previous & 2)) this.z = 0;
        break;
      }
      case OP.CP: this.arithmetic(r[d], r[s], 0, true); break;
      case OP.NEG: r[d] = this.arithmetic(0, r[d], 0, true); break;
      case OP.AND: r[d] &= r[s]; this.nzvs(r[d]); break;
      case OP.EOR: r[d] ^= r[s]; this.nzvs(r[d]); break;
      case OP.OR: r[d] |= r[s]; this.nzvs(r[d]); break;
      case OP.MOV: r[d] = r[s]; break;
      case OP.INC: r[d]++; this.nzvs(r[d], Number(r[d] === 128)); break;
      case OP.DEC: r[d]--; this.nzvs(r[d], Number(r[d] === 127)); break;
      case OP.COM: r[d] ^= 255; this.nzvs(r[d]); this.c = 1; break;
      case OP.LSR: this.c = r[d] & 1; r[d] >>= 1; this.nzvs(r[d], this.c); break;
      case OP.ROR:
        v = r[d]; r[d] = (v >> 1) | (this.c << 7); this.c = v & 1;
        this.nzvs(r[d], (r[d] >> 7) ^ this.c); break;
      case OP.ASR: this.c = r[d] & 1; r[d] = (r[d] >> 1) | (r[d] & 128); this.nzvs(r[d], (r[d] >> 7) ^ this.c); break;
      case OP.SWAP: r[d] = ((r[d] & 15) << 4) | (r[d] >> 4); break;
      case OP.LDS:
      case OP.STS:
        if (k < 0 || k >= this.data.length) throw new Error('Data address out of range');
        v = r[d]; this.pc = (this.pc + 1) & 511; this.clock(2); n = 0;
        if (this.op[p] === OP.LDS) r[d] = this.data[k];
        else if (k >= 32 && k < 96) n = this.writeIO(k - 32, v);
        else this.data[k] = v;
        break;
      case OP.IN: this.clock(1); n = 0; r[d] = this.io[k]; break;
      case OP.OUT:
        this.clock(1); n = this.writeIO(k, r[d]); break;
      case OP.SBI:
        this.clock(2); n = this.writeIO(d, this.io[d] | (1 << k)); break;
      case OP.PUSH: this.push(r[d]); n = 2; break;
      case OP.POP: r[d] = this.pop(); n = 2; break;
      case OP.ST:
        z = (r[s] + (k < 0 ? -1 : k >= 2 ? k - 2 : 0)) & 255;
        if (k < 2 && (d === s || d === s+1)) throw new Error('Undefined ST with source in updating pointer');
        if (z >= this.data.length) throw new Error('Data write out of range');
        if (k < 0) r[s] = z;
        v = r[d]; this.clock(2); n = 0;
        if (z >= 32 && z < 96) n = this.writeIO(z - 32, v); else this.data[z] = v;
        if (k === 1) r[s] = (z + 1) & 255; break;
      case OP.LD:
        z = (r[s] + (k < 0 ? -1 : k >= 2 ? k - 2 : 0)) & 255;
        if (k < 2 && (d === s || d === s+1)) throw new Error('Undefined LD with destination in updating pointer');
        if (z >= this.data.length) throw new Error('Data read out of range');
        if (k < 0) r[s] = z;
        this.clock(2); n = 0; r[d] = this.data[z];
        if (k === 1) r[s] = (z + 1) & 255; break;
      case OP.LPM:
        if (k && d >= 30) throw new Error('Undefined LPM Z+ with destination in Z');
        z = r[30] | r[31] << 8;
        if (z >= 1024) throw new Error('LPM out of Flash');
        r[d] = this.rom[z]; if (k) { z++; r[30] = z & 255; r[31] = z >> 8; } n = 3; break;
      default: throw new Error('Unsupported opcode at 0x' + (p * 2).toString(16));
    }
    this.pc &= 511;
    this.clock(n);
    this.interrupt();
  }
  runBlock(deadline = Infinity) {
    // IRQ latency (SEI/RETI) and already-pending interrupts need one real step.
    if (this.irqDelay || this.pending) return false;
    const budget = Math.min(64, this.overflowAt - this.cyc - 1, deadline - this.cyc);
    const r = this.r, data = this.data, rom = this.rom;
    const op = this.op, dst = this.d, src = this.s, imm = this.k, batch = this.batch;
    let p = this.pc, flags = this.sreg, elapsed = 0, count = 0;
    execution: while (batch[p] && elapsed + batch[p] <= budget) {
      const o = op[p], d = dst[p], s = src[p], k = imm[p];
      let next = (p + 1) & 511, cycles = batch[p], x, y, v, total, address;
      switch (o) {
        case OP.NOP: break;
        case OP.LDI: r[d] = k; break;
        case OP.MOV: r[d] = r[s]; break;
        case OP.MOVW: r[d] = r[s]; r[d + 1] = r[s + 1]; break;
        case OP.ADIW:
        case OP.SBIW:
          v = wordArithmetic(flags, r[d] | r[d+1]<<8, k, o === OP.SBIW);
          r[d] = v; r[d+1] = v>>8; flags = v>>16; break;
        case OP.ADD:
        case OP.ADC:
          x = r[d]; y = r[s]; total = x + y + (o === OP.ADC ? flags & 1 : 0); v = total & 255;
          flags = (flags & 0xc0) | (NZ[v] ^ ((~(x ^ y) & (x ^ v) & 128) ? 0x18 : 0)) |
            ((total >> 8) & 1) | (((x ^ y ^ v) & 16) << 1);
          r[d] = v; break;
        case OP.CPI:
        case OP.SUBI:
        case OP.SUB:
          x = r[d]; y = o === OP.SUB ? r[s] : k; total = x - y; v = total & 255;
          flags = (flags & 0xc0) | (NZ[v] ^ (((x ^ y) & (x ^ v) & 128) ? 0x18 : 0)) |
            ((total >> 8) & 1) | (((x ^ y ^ v) & 16) << 1);
          if (o !== OP.CPI) r[d] = v;
          break;
        case OP.SBC:
        case OP.SBCI: {
          const previous = flags;
          x = r[d]; y = o === OP.SBC ? r[s] : k; total = x-y-(flags&1); v = total&255;
          flags = (flags&0xc0) | (NZ[v] ^ (((x^y)&(x^v)&128) ? 0x18 : 0)) |
            ((total>>8)&1) | (((x^y^v)&16)<<1);
          if (!(previous&2)) flags &= ~2;
          r[d] = v; break;
        }
        case OP.AND: v = r[d] &= r[s]; flags = (flags & 0xe1) | NZ[v]; break;
        case OP.EOR: v = r[d] ^= r[s]; flags = (flags & 0xe1) | NZ[v]; break;
        case OP.OR: v = r[d] |= r[s]; flags = (flags & 0xe1) | NZ[v]; break;
        case OP.ANDI: v = r[d] &= k; flags = (flags & 0xe1) | NZ[v]; break;
        case OP.ORI: v = r[d] |= k; flags = (flags & 0xe1) | NZ[v]; break;
        case OP.INC:
          r[d]++; v = r[d]; flags = (flags & 0xe1) | (NZ[v] ^ (v === 128 ? 0x18 : 0)); break;
        case OP.DEC:
          r[d]--; v = r[d]; flags = (flags & 0xe1) | (NZ[v] ^ (v === 127 ? 0x18 : 0)); break;
        case OP.COM: v = r[d] ^= 255; flags = (flags & 0xe0) | NZ[v] | 1; break;
        case OP.LSR:
        case OP.ASR:
        case OP.ROR:
          x = r[d]; v = (x >> 1) | (o === OP.ASR ? x & 128 : o === OP.ROR ? (flags & 1) << 7 : 0);
          r[d] = v; flags = (flags & 0xe0) | (NZ[v] ^ (((v >> 7) ^ (x & 1)) ? 0x18 : 0)) | (x & 1);
          break;
        case OP.SWAP: r[d] = ((r[d] & 15) << 4) | (r[d] >> 4); break;
        case OP.JUMP: next = (next + k) & 511; break;
        case OP.BRANCH:
          cycles = 1;
          if (((flags >> d) & 1) === s) { next = (next + k) & 511; cycles = 2; }
          break;
        case OP.SKIP:
          cycles = 1;
          if (((r[d] >> s) & 1) === k) {
            const w = rom[next * 2] | rom[next * 2 + 1] << 8;
            const words = (w & 0xfe0f) === 0x9000 || (w & 0xfe0f) === 0x9200 ||
              (w & 0xfe0e) === 0x940c || (w & 0xfe0e) === 0x940e ? 2 : 1;
            next = (next + words) & 511; cycles = 1 + words;
          }
          break;
        case OP.LD:
        case OP.ST:
          // ATtiny13A has <256 bytes of data space: XH/YH/ZH are unused here.
          address = r[s];
          // I/O needs its real access cycle. Invalid/undefined accesses retain
          // the single-step error path and the state preceding that instruction.
          if (address < 96 || address >= 160 || d === s || d === s + 1) break execution;
          if (o === OP.LD) r[d] = data[address]; else data[address] = r[d];
          r[s] = (address + 1) & 255;
          break;
        case OP.LPM:
          address = r[30] | r[31] << 8;
          if (address >= 1024 || (k && d >= 30)) break execution;
          r[d] = rom[address];
          if (k) { address++; r[30] = address & 255; r[31] = address >> 8; }
          break;
      }
      p = next; elapsed += cycles; count++;
      // Give the existing wait-loop accelerator the next opportunity to run.
      if (this.idle[p]) break;
    }
    if (!count) return false;
    this.pc = p; this.sreg = flags; this.clock(elapsed); this.blockInstructions += count;
    return true;
  }
  nextDuty() {
    const before = this.writes, deadline = this.cyc + 9600000;
    // Instruction hooks used by firmware audits must still observe every step.
    const blocks = this.fastBlocks && this.step === AVRCore.prototype.step;
    while (this.writes === before) {
      if (!(this.fastIdle && this.idle[this.pc] && this.skipIdle()) &&
          !(blocks && this.batch[this.pc] && this.runBlock(deadline))) this.step();
      if (this.cyc > deadline) throw new Error('Firmware produced no PWM for one emulated second');
    }
    return this.duty;
  }
  nextStereoDuty() {
    const before=this.leftWrites;this.nextDuty();
    if(this.leftWrites!==before+1)throw new Error('Stereo frame requires one OC0A write before OC0B');
    return this.dutyLeft|(this.duty<<8);
  }
  state() {
    return { pc:this.pc * 2, cycles:this.cyc, irqs:this.irqCount, maxISR:this.maxIRQ,
      lost:this.lost + this.workLost, timerLost:this.lost, workLost:this.workLost,
      duty:this.duty, registers:Array.from(this.r), idleCycles:this.idleCycles };
  }
}

AVRCore.fromHex=(flash,eeprom)=>new AVRCore(parseHex(flash),eeprom?parseHex(eeprom,64):null);
if(typeof module!=="undefined")module.exports={AVRCore};
