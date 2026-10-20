
/* Minimal, cycle-counting AVR interpreter for the actual ATtiny13A firmware.
 * Supported opcodes cover synth.S (NOT a general ATtiny13A emulator).
 * PWM compare writes are read as 37,500 duty-cycle averages; actual
 * 9.6 MHz PB1 carrier edges are analog-filtered in hardware.
 */
class AVRCore {
  constructor(binary,eeprom) {
    this.eeprom=new Uint8Array(64).fill(255);
    if(eeprom)this.eeprom.set(eeprom);
    this.rom = new Uint8Array(1024).fill(255);
    this.rom.set(binary);
    this.r = new Uint8Array(32);
    this.io = new Uint8Array(64); this.ram = new Uint8Array(64);
    this.pc = 0; this.cyc = 0; this.z=0; this.c=0; this.i=0; this.t=0; this.workLost=0;
    this.stack=[]; this.timer=false; this.overflowAt=Infinity; this.pending=false;
    this.inIRQ=false; this.irqStart=0; this.irqCount=0; this.lost=0; this.maxIRQ=0;
    this.samples=[]; this.writes=0;
  }
  step() {
    let rr=this.r, p=this.pc<<1;
    if(p+1>=this.rom.length)throw new Error('PC out of Flash at 0x'+p.toString(16));
    let w=this.rom[p] | this.rom[p+1]<<8, n=1;
    this.pc++;
    if(w===0){}
    else if(w===0x9468){if(this.t&&this.inIRQ)this.workLost++;this.t=1;}
    else if(w===0x94e8)this.t=0;
    else if(w===0x94f8) this.i=0;
    else if(w===0x9478) this.i=1;
    else if(w===0x9518){
      if(!this.stack.length)throw new Error('RETI without interrupt');
      this.pc=this.stack.pop();this.i=1;n=4;this.inIRQ=false;
      if(this.cyc+n-this.irqStart>this.maxIRQ){
        this.maxIRQ=this.cyc+n-this.irqStart;
        this.peakInfo={sec:this.cyc/9600000,cycles:this.maxIRQ,env:[rr[19],rr[20],rr[21]],beat:rr[29],tick:rr[24],step:[rr[5],rr[9],rr[13]],cursor:(rr[31]<<8)|rr[30]};
      }
    }
    else if(w===0x9508){ if(!this.stack.length)throw new Error('RET without RCALL');this.pc=this.stack.pop();n=4; }
    else if((w&0xf000)===0xd000){let k=w&4095;if(k&2048)k-=4096;this.stack.push(this.pc);this.pc+=k;n=3;}
    else if((w&0xf000)===0xc000){ // RJMP
      let k=w&4095;if(k&2048)k-=4096;this.pc+=k;n=2;
    }
    else if((w&0xfc00)===0xf000 || (w&0xfc00)===0xf400){ // BRBS/BRBC
      let f=w&7;if(f>1&&f!==6)throw new Error('Unsupported branch flag');
      let bit=f===0?this.c:f===6?this.t:this.z;
      if(bit===Number((w&0xfc00)===0xf000)){
        let k=(w>>3)&127;if(k&64)k-=128;this.pc+=k;n=2;
      }
    }
    else if((w&0xfe08)===0xfc00 || (w&0xfe08)===0xfe00){ // SBRC/SBRS
      let r=(w>>4)&31,bit=w&7;
      if(((rr[r]>>bit)&1)===Number((w&0xfe08)===0xfe00)){
        let next=this.rom[this.pc<<1]|this.rom[(this.pc<<1)+1]<<8;
        let words=[0x940c,0x940e,0x9000,0x9200].includes(next&0xfe0e)?2:1;
        this.pc+=words;n=1+words;
      }
    }
    else if((w&0xf000)===0xe000){ // LDI
      rr[16+((w>>4)&15)]=(w&15)|((w>>4)&240);
    }
    else if([0x3000,0x5000,0x6000,0x7000].includes(w&0xf000)){
      let d=16+((w>>4)&15),k=(w&15)|((w>>4)&240),x=rr[d];
      if((w&0xf000)===0x7000){rr[d]=x&k;this.z=Number(rr[d]===0)}
      else if((w&0xf000)===0x6000){rr[d]=x|k;this.z=Number(rr[d]===0)}
      else {let v=(x-k)&255;if((w&0xf000)===0x5000)rr[d]=v;
        this.c=Number(x<k);this.z=Number(v===0)}
    }
    else if((w&0xff00)===0x0100){ // MOVW
      let d=2*((w>>4)&15),r=2*(w&15);rr[d]=rr[r];rr[d+1]=rr[r+1];
    }
    else if([0x0c00,0x1c00,0x1800,0x2000,0x2400,0x2800,0x2c00].includes(w&0xfc00)){
      let d=(w>>4)&31,r=(w&15)|((w>>5)&16),x=rr[d],y=rr[r],mode=w&0xfc00;
      if(mode===0x0c00 || mode===0x1c00){
        let val=x+y+(mode===0x1c00?this.c:0);
        rr[d]=val&255;this.c=Number(val>255);
        this.z=Number(rr[d]===0 && (mode!==0x1c00 || this.z));
      } else if(mode===0x1800){rr[d]=(x-y)&255;this.c=Number(x<y);this.z=Number(rr[d]===0)}
      else if(mode===0x2000){rr[d]=x&y;this.z=Number(rr[d]===0)}
      else if(mode===0x2400){rr[d]=x^y;this.z=Number(rr[d]===0)}
      else if(mode===0x2800){rr[d]=x|y;this.z=Number(rr[d]===0)}
      else rr[d]=y;
    }
    else if([0x9403,0x940a,0x9400,0x9406,0x9405,0x9407,0x9402].includes(w&0xfe0f)){
      let d=(w>>4)&31,x=rr[d],op=w&0xfe0f;
      if(op===0x9403){rr[d]=(x+1)&255;this.z=Number(rr[d]===0)}
      else if(op===0x940a){rr[d]=(x-1)&255;this.z=Number(rr[d]===0)}
      else if(op===0x9400){rr[d]=x^255;this.z=Number(rr[d]===0);this.c=1}
      else if(op===0x9402){rr[d]=((x&15)<<4)|(x>>4)} // SWAP leaves SREG unchanged
      else if(op===0x9407){rr[d]=(x>>1)|(this.c<<7);this.z=Number(rr[d]===0);this.c=x&1}
      else if(op===0x9405){rr[d]=((x>>1)|(x&128))&255;this.z=Number(rr[d]===0);this.c=x&1}
      else{rr[d]=x>>1;this.z=Number(rr[d]===0);this.c=x&1}
    }
    else if((w&0xfe0f)===0x9000 || (w&0xfe0f)===0x9200){
      let d=(w>>4)&31,a=this.rom[p+2]|this.rom[p+3]<<8;
      if(a<96||a>=160)throw new Error('SRAM address out of range');
      if((w&0xfe0f)===0x9000)rr[d]=this.ram[a-96];else this.ram[a-96]=rr[d];
      this.pc++;n=2;
    }
    else if((w&0xf800)===0xb000){ // IN Rd,A
      let r=(w>>4)&31,a=((w>>5)&48)|(w&15);
      rr[r]=this.io[a];
    }
    else if((w&0xf800)===0xb800){ // OUT
      let r=(w>>4)&31,a=((w>>5)&48)|(w&15),v=rr[r];
      this.io[a]=v;
      if(a===0x33 && v===1 && !this.timer){this.timer=true;this.overflowAt=this.cyc+256}
      if(a===0x29 && this.timer){this.samples.push(v);this.writes++}
    }
    else if((w&0xff00)===0x9a00){ // SBI
      let a=(w>>3)&31, b=w&7;
      this.io[a]|=1<<b;n=2;
      if(a===0x1c && b===0){ // EEPROM read + 4-cycle CPU stall, per datasheet
        this.io[0x1d]=this.eeprom[this.io[0x1e]&63];
        this.io[0x1c]&=254;n+=4;
      }
    }
    else if((w&0xfe0f)===0x920f){ // PUSH r
      this.stack.push(rr[(w>>4)&31]);n=2;
    }
    else if((w&0xfe0f)===0x900f){ // POP r
      rr[(w>>4)&31]=this.stack.pop();n=2;
    }
    else if((w&0xfe0f)===0x9201){ // ST Z+,Rr
      let r=(w>>4)&31,z=rr[30]|rr[31]<<8;
      if(z>=96&&z<160)this.ram[z-96]=rr[r];else if(z<32)rr[z]=rr[r];else throw new Error('Data write out of range');z=(z+1)&65535;rr[30]=z&255;rr[31]=z>>8;n=2;
    }
    else if((w&0xfe0f)===0x9004 || (w&0xfe0f)===0x9005){ // LPM Rd,Z[+]
      let r=(w>>4)&31,z=rr[30]|rr[31]<<8;
      if(z>=this.rom.length)throw new Error('LPM out of Flash');
      rr[r]=this.rom[z];
      if(w&1){z++;rr[30]=z&255;rr[31]=z>>8}
      n=3;
    }
    else throw new Error('Unknown opcode 0x'+w.toString(16)+' at 0x'+p.toString(16));
    this.cyc+=n;
    if(this.timer){
      if(this.overflowAt<=this.cyc){
        // No assumption about overflow latency: pending TOV0 is a 1-bit flag.
        if(this.pending)this.lost++;
        this.pending=true;
        this.overflowAt+=256;
        while(this.overflowAt<=this.cyc){this.lost++;this.overflowAt+=256}
      }
      if(this.i && (this.io[0x39]&2) && this.pending){
        this.pending=false;this.stack.push(this.pc);this.pc=3;this.i=0;
        this.irqStart=this.cyc;this.cyc+=4;this.inIRQ=true;this.irqCount++;
      }
    }
  }
  nextDuty(){
    while(this.samples.length===0)this.step();
    return this.samples.shift();
  }
  static fromHex(hex,eepromHex){
    let rows=hex.trim().split(/\s+/),data=[];
    for(let row of rows){
      if(!row.startsWith(':'))continue;
      let b=[];
      for(let j=1;j+1<row.length;j+=2)b.push(parseInt(row.slice(j,j+2),16));
      if(b.reduce((a,x)=>a+x,0)%256!==0)throw new Error('HEX checksum mismatch');
      if(b[3]===1)break;
      if(b[3]!==0)throw new Error('Only flat 1KB HEX supported');
      let addr=b[1]*256+b[2];
      for(let j=0;j<b[0];j++)data[addr+j]=b[4+j];
    }
    if(data.length>1024 || data.length===0 || data.length%2 || Array.from({length:data.length},(_,i)=>i).some(i=>data[i]===undefined))
      throw new Error('Некорректный или неполный Flash HEX');
    let eeprom=null;
    if(eepromHex){
      const bytes=[];
      for(const row of eepromHex.trim().split(/\s+/)){
        if(!row.startsWith(':'))continue;
        const b=[];for(let j=1;j+1<row.length;j+=2)b.push(parseInt(row.slice(j,j+2),16));
        if(b.reduce((a,x)=>a+x,0)%256)throw new Error('EEPROM HEX checksum mismatch');
        if(b[3]===1)break;
        if(b[3]!==0)throw new Error('Invalid EEPROM HEX record type');
        const addr=b[1]*256+b[2];
        for(let j=0;j<b[0];j++)bytes[addr+j]=b[4+j];
      }
      if(bytes.length!==64||Array.from({length:64},(_,i)=>i).some(i=>bytes[i]===undefined))
        throw new Error('EEPROM HEX должен содержать ровно 64 байта');
      eeprom=Uint8Array.from(bytes);
    }
    return new AVRCore(Uint8Array.from(data),eeprom);
  }
}
if(typeof module!=='undefined' && module.exports)module.exports={AVRCore};
