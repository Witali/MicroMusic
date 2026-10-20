// Specialized interpreter for the archived synth firmware, derived from its
// HTML players. ROM bytes are immutable; decode once, execute integer op IDs.
// ATtiny13(A), AVRe timings. See reports/avr-audit.md for instruction coverage
// and peripheral limitations; this remains a firmware-oriented AVR subset.
const OP = { NOP:1, CLI:2, SEI:3, RETI:4, RET:5, CALL:6, JUMP:7, BRANCH:8,
  SKIP:9, LDI:10, CPI:11, SUBI:12, ORI:13, ANDI:14, MOVW:15, ADD:16,
  ADC:17, SUB:18, AND:19, EOR:20, MOV:21, INC:22, DEC:23, COM:24,
  LSR:25, ASR:26, SWAP:27, IN:28, OUT:29, SBI:30, PUSH:31, POP:32, ST:33, LPM:34, FLAG:35 };
const sign = (v, bit) => v & bit ? v - bit * 2 : v;

export class AVRCore {
  constructor(binary, eeprom, { fastIdle = true } = {}) {
    if (!binary.length || binary.length > 1024) throw new Error('Flash must contain 1–1024 bytes');
    if (eeprom && eeprom.length !== 64) throw new Error('EEPROM must contain 64 bytes');
    this.rom = new Uint8Array(1024).fill(255); this.rom.set(binary);
    this.eeprom = new Uint8Array(64).fill(255); if (eeprom) this.eeprom.set(eeprom);
    this.data = new Uint8Array(160);
    this.r = this.data.subarray(0, 32); this.io = this.data.subarray(32, 96);
    this.sram = this.data.subarray(96);
    this.op = new Uint8Array(512); this.d = new Uint8Array(512);
    this.s = new Uint8Array(512); this.k = new Int16Array(512);
    this.sp = 0x9f; // SPL resets to RAMEND; return addresses occupy TWO bytes.
    this.pc = this.cyc = this.z = this.c = this.i = 0;
    this.irqDelay = 0;
    this.timer = this.pending = this.inIRQ = false; this.overflowAt = Infinity;
    this.irqStart = this.irqCount = this.lost = this.maxIRQ = this.writes = 0;
    this.duty = 128; this.fastIdle = fastIdle; this.idleCycles = 0;
    for (let p = 0; p < 512; p++) this.decode(p);
  }
  get sreg() { return this.io[0x3f]; }
  set sreg(value) { this.io[0x3f] = value; }
  get c() { return this.sreg & 1; }
  set c(value) { this.sreg = (this.sreg & ~1) | (value & 1); }
  get z() { return (this.sreg >> 1) & 1; }
  set z(value) { this.sreg = (this.sreg & ~2) | ((value & 1) << 1); }
  get i() { return this.sreg >> 7; }
  set i(value) { this.sreg = (this.sreg & 127) | ((value & 1) << 7); }
  get sp() { return this.io[0x3d]; }
  set sp(value) { this.io[0x3d] = value; }
  nzvs(value, overflow = 0) {
    const negative = value >> 7;
    this.sreg = (this.sreg & 0xe1) | (Number(value === 0) << 1) |
      (negative << 2) | (overflow << 3) | ((negative ^ overflow) << 4);
  }
  arithmetic(x, y, carry = 0, subtract = false) {
    const total = subtract ? x - y - carry : x + y + carry, value = total & 255;
    const overflow = Number(!!((subtract ? (x ^ y) : ~(x ^ y)) & (x ^ value) & 128));
    this.nzvs(value, overflow);
    this.sreg = (this.sreg & 0xde) | Number(subtract ? total < 0 : total > 255) |
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
    else if ([0x3000,0x5000,0x6000,0x7000].includes(w & 0xf000)) {
      o = ({12288:OP.CPI,20480:OP.SUBI,24576:OP.ORI,28672:OP.ANDI})[w & 0xf000];
      d = 16 + ((w >> 4) & 15); k = (w & 15) | ((w >> 4) & 240);
    } else if ((w & 0xff00) === 0x0100) { o = OP.MOVW; d = 2 * ((w >> 4) & 15); s = 2 * (w & 15); }
    else if ([0x0c00,0x1c00,0x1800,0x2000,0x2400,0x2c00].includes(w & 0xfc00))
      o = ({3072:OP.ADD,7168:OP.ADC,6144:OP.SUB,8192:OP.AND,9216:OP.EOR,11264:OP.MOV})[w & 0xfc00];
    else if ([0x9403,0x940a,0x9400,0x9406,0x9405,0x9402].includes(w & 0xfe0f))
      o = ({37891:OP.INC,37898:OP.DEC,37888:OP.COM,37894:OP.LSR,37893:OP.ASR,37890:OP.SWAP})[w & 0xfe0f];
    else if ((w & 0xf800) === 0xb000) { o = OP.IN; k = ((w >> 5) & 48) | (w & 15); }
    else if ((w & 0xf800) === 0xb800) { o = OP.OUT; k = ((w >> 5) & 48) | (w & 15); }
    else if ((w & 0xff00) === 0x9a00) { o = OP.SBI; d = (w >> 3) & 31; k = w & 7; }
    else if ((w & 0xfe0f) === 0x920f) o = OP.PUSH;
    else if ((w & 0xfe0f) === 0x900f) o = OP.POP;
    else if ((w & 0xfe0f) === 0x9201) o = OP.ST;
    else if ((w & 0xfe0f) === 0x9004 || (w & 0xfe0f) === 0x9005) { o = OP.LPM; k = w & 1; }
    this.op[p] = o; this.d[p] = d; this.s[p] = s; this.k[p] = k;
  }
  push(value) {
    if (this.sp < 0x60 || this.sp > 0x9f) throw new Error('Stack overflow or invalid SPL');
    this.data[this.sp--] = value;
  }
  pop() {
    if (this.sp < 0x5f || this.sp >= 0x9f) throw new Error('Stack underflow or invalid SPL');
    return this.data[++this.sp];
  }
  pushPC(value) { this.push(value & 255); this.push(value >> 8); }
  popPC() { const high = this.pop(); return ((high << 8) | this.pop()) & 511; }
  clock(n) {
    this.cyc += n;
    if (this.timer && this.overflowAt <= this.cyc) {
      if (this.pending) this.lost++;
      this.pending = true; this.overflowAt += 256;
      while (this.overflowAt <= this.cyc) { this.lost++; this.overflowAt += 256; }
    }
  }
  interrupt() {
    if (this.irqDelay) { this.irqDelay--; return; }
    if (!this.i || !(this.io[0x39] & 2) || !this.pending) return;
    this.pending = false; this.pushPC(this.pc); this.pc = 3; this.i = 0;
    this.irqStart = this.cyc; this.clock(4); this.inIRQ = true; this.irqCount++;
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
      case OP.FLAG: this.sreg = (this.sreg & ~(1 << d)) | (k << d); break;
      case OP.RETI:
        this.pc = this.popPC(); this.i = 1; this.irqDelay = 1; n = 4; this.inIRQ = false;
        this.maxIRQ = Math.max(this.maxIRQ, this.cyc + n - this.irqStart); break;
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
      case OP.ADD: r[d] = this.arithmetic(r[d], r[s]); break;
      case OP.ADC: r[d] = this.arithmetic(r[d], r[s], this.c); break;
      case OP.SUB: r[d] = this.arithmetic(r[d], r[s], 0, true); break;
      case OP.AND: r[d] &= r[s]; this.nzvs(r[d]); break;
      case OP.EOR: r[d] ^= r[s]; this.nzvs(r[d]); break;
      case OP.MOV: r[d] = r[s]; break;
      case OP.INC: r[d]++; this.nzvs(r[d], Number(r[d] === 128)); break;
      case OP.DEC: r[d]--; this.nzvs(r[d], Number(r[d] === 127)); break;
      case OP.COM: r[d] ^= 255; this.nzvs(r[d]); this.c = 1; break;
      case OP.LSR: this.c = r[d] & 1; r[d] >>= 1; this.nzvs(r[d], this.c); break;
      case OP.ASR: this.c = r[d] & 1; r[d] = (r[d] >> 1) | (r[d] & 128); this.nzvs(r[d], (r[d] >> 7) ^ this.c); break;
      case OP.SWAP: r[d] = ((r[d] & 15) << 4) | (r[d] >> 4); break;
      case OP.IN: r[d] = this.io[k]; break;
      case OP.OUT:
        this.io[k] = r[d];
        if (k === 0x33 && r[d] === 1 && !this.timer) { this.timer = true; this.overflowAt = this.cyc + 256; }
        if (k === 0x29 && this.timer) { this.duty = r[d]; this.writes++; } break;
      case OP.SBI:
        this.io[d] |= 1 << k; n = 2;
        if (d === 0x1c && k === 0) { this.io[0x1d] = this.eeprom[this.io[0x1e] & 63]; this.io[0x1c] &= 254; n += 4; } break;
      case OP.PUSH: this.push(r[d]); n = 2; break;
      case OP.POP: r[d] = this.pop(); n = 2; break;
      case OP.ST:
        z = r[30] | r[31] << 8;
        if (d >= 30) throw new Error('Undefined ST Z+ with source in Z');
        if (z >= this.data.length) throw new Error('Data write out of range');
        if (z >= 32 && z < 96) throw new Error('ST Z+ to I/O is not implemented');
        this.data[z] = r[d]; z = (z + 1) & 65535; r[30] = z & 255; r[31] = z >> 8; n = 2; break;
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
  nextDuty() {
    const before = this.writes, deadline = this.cyc + 9600000;
    while (this.writes === before) {
      // The firmware's two-cycle RJMP-to-self has no observable side effects.
      // Jump to the same instruction boundary as repeated RJMPs, then service
      // the exact pending overflow. Never skip an ISR or disabled-IRQ loop.
      if (this.fastIdle && this.op[this.pc] === OP.JUMP && this.k[this.pc] === -1 &&
          this.timer && this.i && !this.irqDelay && !this.pending && (this.io[0x39] & 2)) {
        const n = Math.max(2, Math.ceil((this.overflowAt - this.cyc) / 2) * 2);
        this.idleCycles += n; this.clock(n); this.interrupt();
      } else this.step();
      if (this.cyc > deadline) throw new Error('Firmware produced no PWM for one emulated second');
    }
    return this.duty;
  }
  state() {
    return { pc:this.pc * 2, cycles:this.cyc, irqs:this.irqCount, maxISR:this.maxIRQ,
      lost:this.lost, duty:this.duty, registers:Array.from(this.r), idleCycles:this.idleCycles };
  }
}
