/* PIC16F1503 enhanced mid-range CPU + Timer2/PWM3 emulator.
 * DS40001607D: sections 3 (FSR mapping), 5 (oscillator), 20 (Timer2),
 * 22 (PWM), 27 (14-bit instruction encodings and cycle counts).
 * Timings: instruction TCY, internal Timer0/1/2, PWM buffered duty, configurable
 * INTOSC frequency, and interrupt pipeline bubbles. NOT MPLAB SIM.
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
    // Register reset conditions and oscillator default: datasheet §§3,5,18,20,22.
    this.mem[0x095]=0xFF; // OPTION_REG: TMR0 uses external T0CKI at reset.
    this.mem[0x08C]=0x3F; // TRISA: input; firmware must select RA2 as PWM output.
    this.mem[0x18C]=0x17; // ANSELA analog input selection (valid analog bits).
    this.mem[0x099]=0x38; // OSCCON IRCF=0111 => 500 kHz after Reset.
    this.mem[0x09A]=0x02; // OSCSTAT nominal LFIOFR ready; external-clock status not modeled.
    this.mem[0x01B]=0xFF; // PR2 reset value.
    this.foscHz=500000; this.timePs=0; this.clockPending=null;
    this.tmr0Prescale=0; this.tmr0WriteInhibit=0;
    this.tmr1Prescale=0; this.tmr1LfPhase=0;this.tmr1Value=0;
    this.t2MatchPending=false;
    this.pwmEdges=[];this.capturePwmEdges=false;this.pwmPinLevel=0;this.pwmFallTimePs=null;this.pwmRiseTimePs=null;
    this.irqSourceCounts={TMR0:0,TMR1:0,TMR2:0,other:0};
    this.lastIrqLatencyCycles=0;
    this.executingInstruction=false;this.pendingSfrWrites=[];
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
  // PIC instruction writes become visible at Q4. Defer timer/PWM/clock SFR writes
  // until after the instruction's TCY elapsed; external debugger writes are immediate.
  setMemory(a,v){
    a &= 0xffff;v &=255;
    if(this.executingInstruction && [0x015,0x016,0x017,0x018,0x01A,0x01B,0x01C,
       0x095,0x099,0x617,0x618,0x619].includes(a)){
      this.pendingSfrWrites.push([a,v]);return;
    }
    this.commitMemory(a,v);
  }
  commitMemory(a,v){
    a &= 0xffff;v &=255;
    if(a>=0x8000)return; // Program Flash writes require the NVM controller.
    if(a>=0x2000 && a<0x3000){const g=this.physicalGpr(a);if(g>=0)this.mem[g]=v;return;}
    if(a>=0x1000)return;
    const f=a&127;
    if(f<12){this.writeDirect(f,v);return;}
    if(f>=0x70){this.mem[f]=v;return;}
    if(this.unimplementedGpr(a))return;
    if(a===0x09A)return; // OSCSTAT is a read-only ready/stable register.
    // PIC16F1503 implemented-bit masks from DS40001607D registers 7-5..7-8,
    // 11-3. Also exercised by gpsim regression/p1xf18xx/p16f1503.asm.
    // Do not let reserved bits latch, or accidentally generate phantom IRQs.
    const sfrMasks={0x011:0xCB,0x012:0x6C,0x091:0xCB,0x092:0x6C};
    if(Object.hasOwn(sfrMasks,a))v &= sfrMasks[a];
    if(a===0x08C)v=(v&0x37)|0x08; // RA3: input-only, TRISA3 always 1.
    this.mem[a]=a===0x617?(v&0xc0):v;
    if(a===0x015){ // TMR0 write: inhibit the following two instruction clocks (§18.1.1).
      this.tmr0Prescale=0;this.tmr0WriteInhibit=2;
    }
    if(a===0x095){this.tmr0Prescale=0;}
    if(a===0x016 || a===0x017){
      this.tmr1Prescale=0;
      this.tmr1Value=(this.mem[0x017]<<8)|this.mem[0x016];
    }
    if(a===0x018){this.tmr1Prescale=0;}
    if(a===0x1a){ // TMR2 write clears both prescale and postscale; PR2 is untouched.
      this.timerCount=v;this.prescale=0;this.postscale=0;
      this.t2MatchPending=(v===this.mem[0x1b]);
    }
    if(a===0x1b){this.t2MatchPending=(this.timerCount===v);}
    if(a===0x1c){ // T2CON writes clear both dividers, but preserve TMR2 itself.
      this.prescale=0;this.postscale=0;
      this.t2MatchPending=(this.timerCount===this.mem[0x1b]);
    }
    if(a===0x099)this.selectOscillator(v);
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
    if(f===11){ // INTCON.IOCIF is read-only, derived from the IOC flags.
      this.mem[11]=(v&0xFE)|(this.mem[11]&1);return;
    }
    if(f===8){this.mem[8]=v&31;return;}
    if(f===3){this.mem[3]=(v&7)|(this.mem[3]&0x18);return;}
    this.mem[f]=v;
  }
  rf(f){return this.getMemory(this.addr(f));}
  wf(f,v){this.setMemory(this.addr(f),v);}
  setW(v){this.W=v&255;}
  static oscillatorFrequency(ircf){
    // DS40001607D Register 5-1, OSCCON IRCF<3:0>.
    return [31000,31000,31000,31000,62500,125000,250000,500000,
      125000,250000,500000,1000000,2000000,4000000,8000000,16000000][ircf&15];
  }
  selectOscillator(v){
    const selected=PIC16F1503.oscillatorFrequency((v>>3)&15);
    // For this firmware CONFIG1 FOSC=INTOSC, and SCS=00/1x select internal.
    // Clock changes to HFINTOSC are approximately 2us (§5.3 Table 5-2).
    // This is the documented nominal delay, not an analog startup simulator.
    if((v&3)===1)throw Error('OSCCON SCS=01 is reserved (datasheet Register 5-1)');
    if(selected===this.foscHz){this.clockPending=null;return;}
    const delay=(selected>=1000000 && this.foscHz<1000000)?2000000:0;
    this.clockPending={hz:selected,atPs:this.timePs+delay};
    if(!delay){this.foscHz=selected;this.clockPending=null;this.updateOscstat();}
  }
  updateOscstat(){
    // NOMINAL flag states only; revision A0 errata DS80530C warns HFIOFR
    // and HFIOFS can remain stuck high after oscillator deselection.
    this.mem[0x09A]=0x02|(this.foscHz>=1000000?0x10:0)|
      (this.foscHz===16000000?0x01:0);
  }
  get seconds(){return this.timePs/1e12;}
  get instructionHz(){return this.foscHz/4;}
  get pwmOutputEnabled(){
    // PWM3CON EN/OE, TRISA2 output, ANSELA2 digital: pin-level connection.
    return (this.mem[0x619]&0xC0)===0xC0 && !(this.mem[0x08C]&4) && !(this.mem[0x18C]&4);
  }
  pwmEdge(value,t){
    if(this.pwmPinLevel===value)return;
    this.pwmPinLevel=value;
    if(this.capturePwmEdges)this.pwmEdges.push({timePs:t,level:value});
  }
  flushPwmFall(timePs){
    if(this.pwmFallTimePs!==null && this.pwmFallTimePs<=timePs){
      this.pwmEdge(0,this.pwmFallTimePs);this.pwmFallTimePs=null;
    }
  }
  timer0Tick(){
    // Timer0 is frozen in external T0CKI mode unless pin transitions are supplied.
    const opt=this.mem[0x095];
    if(opt&0x20)return;
    if(this.tmr0WriteInhibit>0){this.tmr0WriteInhibit--;return;}
    if(!(opt&8)){
      const div=2<<(opt&7);
      if(++this.tmr0Prescale<div)return;
      this.tmr0Prescale=0;
    }
    this.mem[0x015]=(this.mem[0x015]+1)&255;
    if(!this.mem[0x015])this.mem[0x0b]|=4; // TMR0IF latches even when disabled.
  }
  timer1Tick(deltaPs){
    const ctl=this.mem[0x018];if(!(ctl&1))return;
    const src=(ctl>>6)&3;
    if(this.mem[0x019]&0x80)throw Error('Timer1 gated mode needs external/gate pin emulation');
    if(src===2)return; // External T1CKI edges must be supplied by a pin model.
    const divider=1<<((ctl>>4)&3);
    let ticks=src===0?1:src===1?4:0;
    if(src===3){ // LFINTOSC oscillator is independent of the CPU instruction clock.
      this.tmr1LfPhase+=31000*deltaPs;
      ticks=Math.floor(this.tmr1LfPhase/1e12);
      this.tmr1LfPhase-=ticks*1e12;
    }
    for(let k=0;k<ticks;k++){
      if(++this.tmr1Prescale<divider)continue;
      this.tmr1Prescale=0;
      this.tmr1Value=(this.tmr1Value+1)&0xffff;
      this.mem[0x016]=this.tmr1Value&255;this.mem[0x017]=this.tmr1Value>>8;
      if(!this.tmr1Value)this.mem[0x011]|=1; // TMR1IF
    }
  }
  timer2Tick(){
    const tcon=this.mem[0x1c];
    if(!(tcon&4))return;
    const divider=1 << (2*(tcon&3));
    if(++this.prescale<divider)return;
    this.prescale=0;
    // Comparator asserts T2_match when TMR2==PR2, and TMR2 clears on
    // the following input tick (§20.1), not as a greater-than comparison.
    if(this.t2MatchPending){
      this.timerCount=0;this.mem[0x1a]=0;
      this.t2MatchPending=(this.mem[0x1b]===0);
      this.pwmPeriodCount++;
      const dch=this.mem[0x618],dcl=this.mem[0x617];
      this.pwmDuty=((dch<<2)|(dcl>>6))&1023; // PWM3 double-buffer latch
      const max=4*(this.mem[0x1b]+1);
      const duty=Math.min(max,this.pwmDuty);
      const active=(this.mem[0x619]&0xC0)===0xC0;
      const inverted=!!(this.mem[0x619]&0x20);
      // Samples represent period-average duty, NOT a pin-level bitstream.
      const ratio=active?duty/max:0.5;
      this.samples.push(Math.max(0,Math.min(255,Math.round(256*(active?(inverted?1-ratio:ratio):0.5)))));
      if(this.capturePwmEdges){
        this.pwmFallTimePs=null;
        if(this.pwmOutputEnabled){
          this.pwmEdge(inverted?(duty===0?1:0):(duty>0?1:0),this.timePs);
          if(duty>0 && duty<max){
            const fall=this.timePs+(duty*divider*1e12/this.foscHz);
            if(!inverted)this.pwmFallTimePs=fall;
            // Inverse polarity gets a rising rather than falling edge.
            else this.pwmRiseTimePs=fall;
          }
        }else this.pwmEdge(0,this.timePs);
      }
      if(++this.postscale>=(((tcon>>3)&15)+1)){
        this.postscale=0;this.mem[0x11]|=2; // PIR1.TMR2IF
      }
    }else{
      this.timerCount=(this.timerCount+1)&255;this.mem[0x1a]=this.timerCount;
      if(this.timerCount===this.mem[0x1b])this.t2MatchPending=true;
    }
  }
  advanceCycles(n){
    // Time is tracked independently of machine-cycle count. Fosc may change.
    for(let c=0;c<n;c++){
      const dt=4e12/this.foscHz;
      this.timePs+=dt;this.cycle++;
      this.flushPwmFall(this.timePs);
      if(this.pwmRiseTimePs!==undefined && this.pwmRiseTimePs!==null && this.pwmRiseTimePs<=this.timePs){
        this.pwmEdge(1,this.pwmRiseTimePs);this.pwmRiseTimePs=null;
      }
      this.timer0Tick();this.timer1Tick(dt);this.timer2Tick();
      if(this.clockPending && this.timePs>=this.clockPending.atPs){
        this.foscHz=this.clockPending.hz;this.clockPending=null;this.updateOscstat();
      }
    }
  }
  push(pc){if(this.stack.length>=16)throw new Error('16-level hardware return stack overflow');this.stack.push(pc&0x7fff);}
  pop(){if(!this.stack.length)throw new Error('PIC hardware return stack underflow');return this.stack.pop();}
  tryIRQ(){
    const intcon=this.mem[0x0b],pir1=this.mem[0x11],pie1=this.mem[0x091];
    const timer0=(intcon&0x24)===0x24;
    const peripheral=(intcon&0x40)!==0 && (pir1&pie1)!==0;
    if(!(intcon&0x80) || !(timer0||peripheral))return;
    const source=timer0?'TMR0':(pir1&pie1&1)?'TMR1':(pir1&pie1&2)?'TMR2':'other';
    this.irqSourceCounts[source]++;
    this.context={W:this.W,STATUS:this.mem[3],BSR:this.mem[8],FSR0:this.fsr(0),FSR1:this.fsr(1),PCLATH:this.mem[10]};
    this.push(this.PC);this.PC=4;this.mem[0x0b]&=~0x80;this.inIRQ=true;this.irqCount++;
    // Pipeline flush uses two forced-NOP machine cycles AFTER the interrupted
    // instruction. Together with the completed instruction, this represents
    // 3+ TCY from its Q1 sample; exact Q-phase-dependent 3..4 TCY remains
    // below instruction granularity (datasheet Figures 7-2 and 7-3).
    this.lastIrqLatencyCycles=2;
    this.advanceCycles(2);
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
    this.executingInstruction=true;this.pendingSfrWrites=[];
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
    else if(op===0x0001){
      // Software reset takes one TCY and restarts instruction execution.
      // Preserve the emulator's monotonic physical time and diagnostic history.
      this.advanceCycles(1);
      const oldTime=this.timePs,oldCycles=this.cycle,oldInstr=this.totalInstructions;
      const samples=this.samples, oldPwmCount=this.pwmPeriodCount;
      this.reset();this.cycle=oldCycles;this.timePs=oldTime;
      this.totalInstructions=oldInstr;this.samples=samples;this.pwmPeriodCount=oldPwmCount;
      return 1;
    }
    else if(op===0x0063){this.halted=true;this.breakReason='SLEEP reached';this.mem[3]&=~8;}
    else if(op===0x0064){this.mem[3]|=0x18;} // CLRWDT: TO=PD=1. WDT counter not modeled.
    else if(op===0x0062){this.setMemory(0x095,this.W);} // Legacy OPTION instruction
    else if(op===0x0065){this.setMemory(0x08C,this.W);} // Legacy TRISA instruction
    else if(op===0x0067){this.setMemory(0x08E,this.W);} // Legacy TRISC instruction
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
    else if((op&0x3f80)===0x3f80){const n=(op>>6)&1, k=op&63;const off=k&32?k-64:k;const addr=(this.fsr(n)+off)&0xffff;this.setMemory(addr,this.W);cycles=addr>=0x8000?2:1;}
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
    this.advanceCycles(cycles);
    this.executingInstruction=false;
    for(const [a,v] of this.pendingSfrWrites)this.commitMemory(a,v);
    this.pendingSfrWrites=[];
    this.tryIRQ();return cycles;
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
