/* PIC16F1503 enhanced mid-range CPU + Timer2/PWM3 emulator.
 * DS40001607D: sections 3 (FSR mapping), 5 (oscillator), 20 (Timer2),
 * 22 (PWM), 27 (14-bit instruction encodings and cycle counts).
 * This is a transparent instruction-level partial PIC emulator, NOT MPLAB SIM.
 * Unsupported peripherals and opcodes fail loudly rather than produce fake audio.
 */
export class PIC16F1503 {
  static FOSC = 16000000;
  static FCY = 4000000;
  constructor(words=null){ this.load(words??new Uint16Array(2048)); }
  load(words){
    this.program=new Uint16Array(2048); this.program.fill(0x3fff);
    this.program.set(words.slice(0,2048)); this.reset();
  }
  reset(){
    this.mem=new Uint8Array(4096); this.PC=0; this.W=0; this.cycle=0;
    this.stack=[];this.halted=false;this.breakReason='';this.totalInstructions=0;
    this.inIRQ=false; this.context=null;this.irqCount=0; this.timerCount=0;
    this.prescale=0;this.postscale=0;this.pwmDuty=0;this.pwmPeriodCount=0;
    this.samples=[]; this.dutyEvents=[]; this.unknownSfrWrites=[];
    this.mem[0x03]=0x18;this.mem[0x0b]=0;this.mem[0x1b]=0xff;
    this.mem[0x099]=0x38; // IRCF 0111: factory reset 500kHz; firmware should switch to 16MHz.
    this.mem[0x08]=0;
  }
  get bsr(){return this.mem[8] & 31;} set bsr(v){this.mem[8]=v&31;}
  get Z(){return !!(this.mem[3]&4);} get C(){return !!(this.mem[3]&1);}
  setZ(v){this.mem[3]=(this.mem[3]&~4)|(v?4:0);}
  setC(v){this.mem[3]=(this.mem[3]&~1)|(v?1:0);}
  setDC(v){this.mem[3]=(this.mem[3]&~2)|(v?2:0);}
  add8(a,b,c=0){const s=a+b+c,r=s&255;this.setC(s>255);this.setDC(((a&15)+(b&15)+c)>15);this.setZ(r===0);return r;}
  sub8(a,b,c=0){const s=a-b-c,r=s&255;this.setC(s>=0);this.setDC(((a&15)-(b&15)-c)>=0);this.setZ(r===0);return r;}
  addr(f){return f<12?f:(f>=0x70?f:(this.bsr*128+f));}
  fsr(n){return this.mem[n?7:5]*256+this.mem[n?6:4];}
  setFsr(n,a){this.mem[n?6:4]=a&255;this.mem[n?7:5]=(a>>8)&255;}
  // Device map DS40001607D Table 3-3: 80 bank-0 GPR, 32 bank-1 GPR;
  // common RAM 70h..7Fh and core registers 00h..0Bh mirror in all banks.
  // The linear 2000h space contains only 112 implemented GPR bytes.
  physicalGpr(a){
    const off=a-0x2000;
    if(off<0 || off>=112)return -1;
    return off<80 ? 0x20+off : 0xA0+off-80;
  }
  unimplementedGpr(a){
    const bank=a>>7, f=a&127;
    return f>=0x20 && f<=0x6f &&
      (bank>1 || (bank===1 && f>0x3f));
  }
  getMemory(a){
    a &= 0xffff;
    if(a>=0x8000){const off=a-0x8000;return off<this.program.length?this.program[off]&255:0;}
    if(a>=0x2000 && a<0x3000){const g=this.physicalGpr(a);return g<0?0:this.mem[g];}
    if(a>=0x1000)return 0;
    const f=a&127;
    if(f<12)return this.readDirect(f);
    if(f>=0x70)return this.mem[f];
    if(this.unimplementedGpr(a))return 0;
    return this.mem[a];
  }
  setMemory(a,v){
    a &= 0xffff;v &=255;
    if(a>=0x8000)return; // Program Flash writes require the NVM controller.
    if(a>=0x2000 && a<0x3000){const g=this.physicalGpr(a);if(g>=0)this.mem[g]=v;return;}
    if(a>=0x1000)return;
    const f=a&127;
    if(f<12){this.writeDirect(f,v);return;}
    if(f>=0x70){this.mem[f]=v;return;}
    if(this.unimplementedGpr(a))return;
    this.mem[a]=a===0x617?(v&0xc0):v;
    if(a===0x1a){ // TMR2 is writable, and a write clears both divider counters.
      this.timerCount=v;this.prescale=0;this.postscale=0;
    }
    if(a===0x1c){ // A T2CON write resets both dividers, but NOT TMR2 itself.
      this.prescale=0;this.postscale=0;
    }
  }
  readDirect(f){
    if(f===0 || f===1){
      const a=this.fsr(f);
      // INDF is virtual; reading through a self-reference returns zero.
      if((a&127)<2 && a<0x1000)return 0;
      if(a&0x8000)this.indirectFlashAccess=true;
      return this.getMemory(a);
    }
    if(f===2)return this.PC&255;
    if(f===9)return this.W;
    return this.mem[f];
  }
  writeDirect(f,v){
    v &=255;
    if(f===0 || f===1){
      const a=this.fsr(f);
      if((a&127)<2 && a<0x1000)return;
      if(a&0x8000)this.indirectFlashAccess=true;
      this.setMemory(a,v);return;
    }
    if(f===2){ // computed goto via PCLATH and PCL, instruction takes two cycles
      this.PC=(((this.mem[10]&0x7f)<<8)|v)&0x7fff;
      this.pcModified=true;return;
    }
    if(f===9){this.W=v;return;}
    if(f===8){this.mem[8]=v&31;return;}
    if(f===3){this.mem[3]=(v&7)|(this.mem[3]&0x18);return;}
    this.mem[f]=v;
  }
  rf(f){return this.getMemory(this.addr(f));}
  wf(f,v){this.setMemory(this.addr(f),v);}
  setW(v){this.W=v&255;}
  advanceCycles(n){
    this.cycle+=n;
    const tcon=this.mem[0x1c];
    if(!(tcon&4))return;
    const prescaler=(1 << (2*(tcon&3)));
    for(let c=0;c<n;c++){
      if(++this.prescale<prescaler)continue;
      this.prescale=0;
      if(++this.timerCount>this.mem[0x1b]){
        this.timerCount=0;this.mem[0x1a]=0;
        this.pwmPeriodCount++;
        const dch=this.mem[0x618], dcl=this.mem[0x617];
        this.pwmDuty=((dch<<2)|(dcl>>6)) & 1023; // double-buffered at Timer2 PR2 match
        const max=4*(this.mem[0x1b]+1);
        const out=(this.mem[0x619]&0xC0)===0xC0 ? Math.min(255,Math.round((256*this.pwmDuty)/max)) : 128;
        this.samples.push(out);
        if(++this.postscale>=(((tcon>>3)&15)+1)){
          this.postscale=0;this.mem[0x11]|=2;
        }
      }else this.mem[0x1a]=this.timerCount;
    }
  }
  push(pc){if(this.stack.length>=16)throw new Error('16-level hardware return stack overflow');this.stack.push(pc&0x7fff);}
  pop(){if(!this.stack.length)throw new Error('PIC hardware return stack underflow');return this.stack.pop();}
  tryIRQ(){
    if((this.mem[0x0b]&0xC0)===0xC0 && (this.mem[0x091]&2) && (this.mem[0x011]&2)){
      this.context={W:this.W,STATUS:this.mem[3],BSR:this.mem[8],FSR0:this.fsr(0),FSR1:this.fsr(1),PCLATH:this.mem[10]};
      this.push(this.PC);this.PC=4;this.mem[0x0b]&=~0x80;this.inIRQ=true;this.irqCount++;
      // Synchronous peripheral IRQ latency is 3-4 cycles (DS section 7.2).
      // A fixed three-cycle approximation is used; Q-phase alignment is not modeled.
      this.advanceCycles(3);
    }
  }
  readIndirect(n,mm){
    let addr=this.fsr(n);
    if(mm===0){addr=(addr+1)&0xffff;this.setFsr(n,addr);} // ++FSRn
    if(mm===1){addr=(addr-1)&0xffff;this.setFsr(n,addr);} // --FSRn
    const val=this.getMemory(addr);
    if(mm===2)this.setFsr(n,(addr+1)&0xffff); // FSRn++
    if(mm===3)this.setFsr(n,(addr-1)&0xffff); // FSRn--
    return {val,cycles:addr>=0x8000?2:1};
  }
  writeIndirect(n,mm,v){
    let addr=this.fsr(n);
    if(mm===0){addr=(addr+1)&0xffff;this.setFsr(n,addr);}
    if(mm===1){addr=(addr-1)&0xffff;this.setFsr(n,addr);}
    this.setMemory(addr,v);
    if(mm===2)this.setFsr(n,(addr+1)&0xffff);
    if(mm===3)this.setFsr(n,(addr-1)&0xffff);
    return addr>=0x8000?2:1;
  }
  step(){
    if(this.halted)throw new Error(this.breakReason);
    if(this.PC>=this.program.length)throw new Error(`PC outside 2K program memory: ${this.PC.toString(16)}`);
    this.pcModified=false;
    this.indirectFlashAccess=false;
    const op=this.program[this.PC++]&0x3fff;this.totalInstructions++;
    let cycles=1, f=op&127, d=(op>>7)&1, v,r,top=op&0x3f00;
    const store=(x)=>{if(d)this.wf(f,x);else this.setW(x);};
    const shiftAndCarry=(newVal,carry)=>{store(newVal);this.setC(carry);this.setZ((newVal&255)===0);};
    if(op===0x0000){} // NOP
    else if(op===0x0008){this.PC=this.pop();cycles=2;}
    else if(op===0x0009){this.PC=this.pop();cycles=2;this.mem[0x0b]|=0x80;
      if(this.context){const s=this.context;this.W=s.W;this.mem[3]=(s.STATUS&7)|(this.mem[3]&0x18);this.mem[8]=s.BSR;this.setFsr(0,s.FSR0);this.setFsr(1,s.FSR1);this.mem[10]=s.PCLATH;this.context=null;}this.inIRQ=false;}
    else if(op===0x000b){this.PC=(this.PC+this.W)&0x7fff;cycles=2;}
    else if(op===0x000a){this.push(this.PC);this.PC=((this.mem[10]&0x7f)<<8)|this.W;cycles=2;}
    else if(op===0x0001){this.reset();return 1;} // RESET instruction
    else if(op===0x0063){this.halted=true;this.breakReason='SLEEP reached';}
    else if((op&0x3fe0)===0x0020){this.bsr=op&31;}
    else if((op&0x3f80)===0x3180){this.mem[10]=op&127;}
    else if((op&0x3ff8)===0x0100){this.setW(0);this.setZ(true);} // CLRW: only 0001 0000 0xxx
    else if((op&0x3f80)===0x0180){this.wf(f,0);this.setZ(true);}
    else if((op&0x3f80)===0x0080){this.wf(f,this.W);}
    else if((op&0x3f00)===0x0700){r=this.add8(this.rf(f),this.W);store(r);}
    else if((op&0x3f00)===0x0500){r=this.rf(f)&this.W;store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0400){r=this.rf(f)|this.W;store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0600){r=this.rf(f)^this.W;store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0200){r=this.sub8(this.rf(f),this.W);store(r);}
    else if((op&0x3f00)===0x0300){r=(this.rf(f)-1)&255;store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0800){r=this.rf(f);store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0900){r=(~this.rf(f))&255;store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0a00){r=(this.rf(f)+1)&255;store(r);this.setZ(r===0);}
    else if((op&0x3f00)===0x0b00){r=(this.rf(f)-1)&255;store(r);if(r===0){this.PC++;cycles=2;}}
    else if((op&0x3f00)===0x0f00){r=(this.rf(f)+1)&255;store(r);if(r===0){this.PC++;cycles=2;}}
    else if((op&0x3f00)===0x0e00){r=this.rf(f);store(((r<<4)|(r>>4))&255);}
    else if((op&0x3f00)===0x0c00){v=this.rf(f);r=(v>>1)|(this.C?128:0);store(r);this.setC(v&1);}
    else if((op&0x3f00)===0x0d00){v=this.rf(f);r=((v<<1)|(this.C?1:0))&255;store(r);this.setC(v&128);}
    else if((op&0x3f00)===0x3d00){r=this.add8(this.rf(f),this.W,this.C?1:0);store(r);}
    else if((op&0x3f00)===0x3b00){r=this.sub8(this.rf(f),this.W,this.C?0:1);store(r);}
    else if((op&0x3f00)===0x3700){v=this.rf(f);r=(v>>1)|(v&128);shiftAndCarry(r,v&1);}
    else if((op&0x3f00)===0x3500){v=this.rf(f);r=(v<<1)&255;shiftAndCarry(r,v&128);}
    else if((op&0x3f00)===0x3600){v=this.rf(f);r=v>>1;shiftAndCarry(r,v&1);}
    else if((op&0x3c00)===0x1000){this.wf(f,this.rf(f)&~(1<<((op>>7)&7)));}
    else if((op&0x3c00)===0x1400){this.wf(f,this.rf(f)|(1<<((op>>7)&7)));}
    else if((op&0x3c00)===0x1800){if(!(this.rf(f)&(1<<((op>>7)&7)))){this.PC++;cycles=2;}}
    else if((op&0x3c00)===0x1c00){if(this.rf(f)&(1<<((op>>7)&7))){this.PC++;cycles=2;}}
    else if((op&0x3800)===0x2000){this.push(this.PC);this.PC=((this.mem[10]&0x78)<<8)|(op&0x7ff);cycles=2;}
    else if((op&0x3800)===0x2800){this.PC=((this.mem[10]&0x78)<<8)|(op&0x7ff);cycles=2;}
    else if((op&0x3e00)===0x3200){let off=op&511;if(off&256)off-=512;this.PC=(this.PC+off)&0x7fff;cycles=2;}
    else if((op&0x3f80)===0x3100){let imm=op&63;if(imm&32)imm-=64;const n=(op>>6)&1;this.setFsr(n,(this.fsr(n)+imm)&0xffff);}
    else if((op&0x3ff8)===0x0010){const x=this.readIndirect((op>>2)&1,op&3);this.W=x.val;cycles=x.cycles;this.setZ(this.W===0);}
    else if((op&0x3ff8)===0x0018){cycles=this.writeIndirect((op>>2)&1,op&3,this.W);}
    else if((op&0x3f80)===0x3f00){const n=(op>>6)&1, k=op&63;const off=k&32?k-64:k;const addr=(this.fsr(n)+off)&0xffff;this.W=this.getMemory(addr);this.setZ(this.W===0);cycles=addr>=0x8000?2:1;}
    else if((op&0x3f80)===0x3f80){const n=(op>>6)&1, k=op&63;const off=k&32?k-64:k;this.setMemory((this.fsr(n)+off)&0xffff,this.W);}
    else if((op&0x3f00)===0x3e00){this.W=this.add8(this.W,op&255);}
    else if((op&0x3f00)===0x3900){this.W&=op&255;this.setZ(this.W===0);}
    else if((op&0x3f00)===0x3800){this.W|=op&255;this.setZ(this.W===0);}
    else if((op&0x3f00)===0x3a00){this.W^=op&255;this.setZ(this.W===0);}
    else if((op&0x3f00)===0x3c00){this.W=this.sub8(op&255,this.W);}
    else if((op&0x3f00)===0x3000){this.W=op&255;}
    else if((op&0x3c00)===0x3400){this.W=op&255;this.PC=this.pop();cycles=2;}
    else throw new Error(`Unsupported PIC16 opcode ${op.toString(16).padStart(4,'0')} at PC ${((this.PC-1)&0x7fff).toString(16)}`);
    if(this.pcModified)cycles=Math.max(cycles,2);
    if(this.indirectFlashAccess)cycles++;
    this.advanceCycles(cycles);this.tryIRQ();return cycles;
  }
  run(maxInstructions=1000000, maxPWM=0){
    for(let i=0;i<maxInstructions;i++){
      this.step();
      if(maxPWM&&this.samples.length>=maxPWM)break;
    }
    return {cycles:this.cycle,instructions:this.totalInstructions,pwmPeriods:this.pwmPeriodCount,irq:this.irqCount,PC:this.PC,output:this.samples};
  }
}

export function readPIC16Hex(content){
  const bytes=new Map();let upper=0;
  for(const line0 of content.split(/\r?\n/)){
    const line=line0.trim();if(!line)continue;
    if(!/^:[0-9a-fA-F]+$/.test(line))throw Error('Not an Intel HEX record: '+line.slice(0,30));
    const data=[];for(let i=1;i<line.length;i+=2)data.push(parseInt(line.slice(i,i+2),16));
    const count=data[0], a=(data[1]<<8)|data[2], type=data[3];
    if(data.length!==5+count || (data.reduce((x,y)=>x+y,0)&255)!==0)throw Error('Intel HEX checksum or record length mismatch');
    if(type===0x04){upper=((data[4]<<8)|data[5])<<16;continue;}
    if(type===0x01)break;
    if(type!==0)continue;
    for(let j=0;j<count;j++)bytes.set(upper+a+j,data[4+j]);
  }
  const words=new Uint16Array(2048);words.fill(0x3fff);
  for(let addr=0;addr<4096;addr+=2){if(bytes.has(addr)||bytes.has(addr+1))words[addr/2]=((bytes.get(addr)||0)|((bytes.get(addr+1)||0)<<8))&0x3fff;}
  return words;
}
