const fs=require("fs");
/* Intel 8080 dual audio output emulator: INTE (level) /WR (pulses). Original implementation.
 * Actual 8080 T states; no Z80-only opcodes. The optional "z80compat" setting
 * applies Z80 timings to 8080-compatible instructions ONLY, not the Z80 ISA.
 * Hardware model: immutable 64 KiB ROM, no RAM, /WR on writes, INTE set/reset by EI/DI.
 */
"use strict";
const RATE = 44100;
const LP = [
  [0.0055285435091125, 0.0110570870182249, 0.0055285435091125, -0.6636798604751319, 0],
  [1, 1, 0, -1.5432302582555886, 0.6747369474933571]
];
const HP = [[0.9949753835075866, -1.9899507670151733, 0.9949753835075866, -1.989925520084925, 0.9899760139454205]];
const EVEN_PARITY = new Uint8Array(256);
for (let i=0;i<256;i++) { let n=i,b=0;while(n){b^=(n&1);n>>>=1;} EVEN_PARITY[i]=b?0:1; }
const R = ['B','C','D','E','H','L','M','A'];

class CPU8080 {
  constructor(rom, profile, hz, maxSeconds=30, pulseT=1, output="inte") {
    this.mem = new Uint8Array(65536);
    this.mem.set(rom.subarray(0,65536));
    this.profile=profile;
    this.hz=hz;
    this.pulseT=pulseT;
    this.output=output;
    this.inte=0;this.inteCycles=[];this.inteLevels=[];
    this.eiInstructions=0;this.diInstructions=0;
    this.maxCycles=Math.floor(maxSeconds*hz);
    this.samples=new Float32Array(Math.ceil(maxSeconds*RATE)+16);
    this.pulseCycles=[];
    this.B=0; this.C=0; this.D=0; this.E=0; this.H=0; this.L=0; this.A=0;
    this.PC=0; this.SP=0;this.cycles=0;this.inst=0;
    this.S=0;this.Z=0;this.P=0;this.CY=0;this.AC=0;
    this.writes=0; this.portWrites=0;this.halted=false;
    this.snapshots=[];this.nextSnapshot=0; this.synthTicks=0;
    this.nextStatus=0;this.hzTick=Math.floor(hz/40);
    this.lastPC=0; this.lastOpcode=0;this.stoppedBy='limit';
  }
  get BC(){return (this.B<<8)|this.C;}
  set BC(x){this.B=(x>>8)&255;this.C=x&255;}
  get DE(){return (this.D<<8)|this.E;}
  set DE(x){this.D=(x>>8)&255;this.E=x&255;}
  get HL(){return (this.H<<8)|this.L;}
  set HL(x){this.H=(x>>8)&255;this.L=x&255;}
  rd(addr){return this.mem[addr&65535];}
  next(){let v=this.rd(this.PC);this.PC=(this.PC+1)&65535;return v;}
  next16(){const l=this.next();return l|(this.next()<<8);}
  getPair(p){return p===0?this.BC:p===1?this.DE:p===2?this.HL:this.SP;}
  setPair(p,v){v&=65535; if(p===0)this.BC=v; else if(p===1)this.DE=v;else if(p===2)this.HL=v;else this.SP=v;}
  getReg(r){return r===6?this.rd(this.HL):this[R[r]];}
  setReg(r,v){v&=255;if(r===6)this.writeMem(this.HL,v,5);else this[R[r]]=v;}
  flags(){return (this.S<<7)|(this.Z<<6)|(this.AC<<4)|(this.P<<2)|0x02|this.CY;}
  setFlags(v){this.S=v>>>7;this.Z=(v>>>6)&1;this.AC=(v>>>4)&1;this.P=(v>>>2)&1;this.CY=v&1;}
  szp(v){v&=255;this.S=v>>>7;this.Z=(v===0)?1:0;this.P=EVEN_PARITY[v];}
  cond(c){switch(c){case 0:return !this.Z;case 1:return !!this.Z;case 2:return !this.CY;case 3:return !!this.CY;case 4:return !this.P;case 5:return !!this.P;case 6:return !this.S;case 7:return !!this.S;}}
  pulse(offset, isPort=false){
    const t=this.cycles+offset;
    this.pulseCycles.push(t);
    const k=Math.floor(t*RATE/this.hz);
    if(this.output==="wr" && k<this.samples.length)this.samples[k]+=RATE*this.pulseT/this.hz;
    if (isPort)this.portWrites++;
    else this.writes++;
  }
  setINTE(value,offset=4){
    // INTE reflects the enable flip-flop. EI and DI take 4 T.
    // EI interrupt *acceptance* delay is separate; the physical pin follows
    // the state at instruction completion. INT is assumed held inactive.
    if(this.inte!==value){
      this.inte=value;this.inteCycles.push(this.cycles+offset);this.inteLevels.push(value);
    }
  }
  writeMem(addr,v,offset){ // no RAM installed; still drive CPU's /WR output
    this.pulse(offset);
  }
  push16(v){this.SP=(this.SP-1)&65535;this.writeMem(this.SP,v>>>8,7);
    this.SP=(this.SP-1)&65535;this.writeMem(this.SP,v&255,10);}
  pop16(){let lo=this.rd(this.SP);this.SP=(this.SP+1)&65535;
    let hi=this.rd(this.SP);this.SP=(this.SP+1)&65535;return lo|(hi<<8);}
  alu(group,v){
    const a=this.A;
    let c,n;
    if(group===0||group===1){ // ADD/ADC
      c=(group===1)?this.CY:0;n=a+v+c;
      this.CY=n>255?1:0;this.A=n&255;
      this.AC=((a&15)+(v&15)+c)>15?1:0;this.szp(this.A);
    }else if(group===2||group===3||group===7){ // SUB/SBB/CMP
      c=group===3?this.CY:0;n=a-v-c;
      this.CY=n<0?1:0;this.AC=((a&15)-(v&15)-c)<0?1:0;
      this.szp(n&255);if(group!==7)this.A=n&255;
    }else if(group===4){this.A=a&v;this.CY=0;this.AC=1;this.szp(this.A);}
    else if(group===5){this.A=a^v;this.CY=0;this.AC=0;this.szp(this.A);}
    else if(group===6){this.A=a|v;this.CY=0;this.AC=0;this.szp(this.A);}
  }
  markSnapshot(){this.snapshots.push({t:this.cycles/this.hz,cy:this.cycles,pc:this.PC,
    a:this.A,b:this.B,c:this.C,d:this.D,e:this.E,h:this.H,l:this.L,sp:this.SP,
    s:this.S,z:this.Z,p:this.P,cyFlag:this.CY,ac:this.AC,wr:this.pulseCycles.length,
    inte:this.inte,inteChanges:this.inteCycles.length,
    ins:this.inst,lastPC:this.lastPC,op:this.lastOpcode});}
  step(){
    const at=this.PC, op=this.next();this.lastPC=at;this.lastOpcode=op;this.inst++;
    const z80=this.profile==='z80compat';
    let t=0;
    // register-to-register and register/memory transfers
    if(op>=0x40 && op<=0x7f){
      if(op===0x76){this.halted=true;t=7;}
      else{
        const dst=(op>>3)&7,src=op&7;
        const v=this.getReg(src);
        if(dst===6)this.writeMem(this.HL,v,5);
        else this[R[dst]]=v;
        t=(src===6||dst===6)?7:(z80?4:5);
      }
    }else if(op>=0x80 && op<=0xbf){
      const src=op&7;this.alu((op>>3)&7,this.getReg(src));t=src===6?7:4;
    }else if((op&0xcf)===0x01){ // LXI rp,data
      this.setPair((op>>4)&3,this.next16());t=10;
    }else if((op&0xcf)===0x03){ // INX rp
      const rp=(op>>4)&3;this.setPair(rp,this.getPair(rp)+1);t=z80?6:5;
    }else if((op&0xcf)===0x0b){ // DCX rp
      const rp=(op>>4)&3;this.setPair(rp,this.getPair(rp)-1);t=z80?6:5;
    }else if((op&0xcf)===0x09){ // DAD rp
      const n=this.HL+this.getPair((op>>4)&3);this.CY=n>65535?1:0;this.HL=n&65535;t=z80?11:10;
    }else if((op&0xc7)===0x04){ // INR r
      const r=(op>>3)&7,v=this.getReg(r),n=(v+1)&255;
      this.AC=((v&15)===15)?1:0;this.szp(n);
      if(r===6)this.writeMem(this.HL,n,8);else this[R[r]]=n;
      t=(r===6)?10:(z80?4:5);
    }else if((op&0xc7)===0x05){ // DCR r
      const r=(op>>3)&7,v=this.getReg(r),n=(v-1)&255;
      this.AC=((v&15)===0)?1:0;this.szp(n);
      if(r===6)this.writeMem(this.HL,n,8);else this[R[r]]=n;
      t=(r===6)?10:(z80?4:5);
    }else if((op&0xc7)===0x06){ // MVI r,imm
      const r=(op>>3)&7, v=this.next();
      if(r===6)this.writeMem(this.HL,v,8);else this[R[r]]=v;
      t=r===6?10:7;
    }else if((op&0xc7)===0xc6){ // Arithmetic immediate
      this.alu((op>>3)&7,this.next());t=7;
    }else if((op&0xc7)===0xc2){ // Jcond addr
      const addr=this.next16();if(this.cond((op>>3)&7))this.PC=addr;t=10;
      if(op===0xc2)this.synthTicks++; // official note-loop opcode
    }else if((op&0xc7)===0xc4){ // CALL cond
      const addr=this.next16();if(this.cond((op>>3)&7)){this.push16(this.PC);this.PC=addr;t=17;}else t=11;
    }else if((op&0xc7)===0xc0){ // RET cond
      if(this.cond((op>>3)&7)){this.PC=this.pop16();t=11;}else t=5;
    }else if((op&0xc7)===0xc7){ // RST vector
      this.push16(this.PC);this.PC=op&0x38;t=11;
    }else if((op&0xcf)===0xc1){ // POP rp
      const v=this.pop16();if((op&0x30)===0x30){this.A=(v>>8)&255;this.setFlags(v&255);}else this.setPair((op>>4)&3,v);t=10;
    }else if((op&0xcf)===0xc5){ // PUSH rp
      this.push16((op===0xf5)?((this.A<<8)|this.flags()):this.getPair((op>>4)&3));t=11;
    }else if(op===0x00){t=4;}
    else if(op===0x02 || op===0x12){this.writeMem(op===0x02?this.BC:this.DE,this.A,5);t=7;}
    else if(op===0x0a || op===0x1a){this.A=this.rd(op===0x0a?this.BC:this.DE);t=7;}
    else if(op===0x07){const x=this.A;this.A=((x<<1)|(x>>>7))&255;this.CY=x>>>7;t=4;}
    else if(op===0x0f){const x=this.A;this.A=((x>>>1)|((x&1)<<7))&255;this.CY=x&1;t=4;}
    else if(op===0x17){const x=this.A;this.A=((x<<1)|this.CY)&255;this.CY=x>>>7;t=4;}
    else if(op===0x1f){const x=this.A;this.A=(x>>>1)|(this.CY<<7);this.CY=x&1;t=4;}
    else if(op===0x22){const x=this.next16();this.writeMem(x,this.L,11);this.writeMem((x+1)&65535,this.H,14);t=16;}
    else if(op===0x2a){const x=this.next16();this.L=this.rd(x);this.H=this.rd(x+1);t=16;}
    else if(op===0x32){const x=this.next16();this.writeMem(x,this.A,11);t=13;}
    else if(op===0x3a){this.A=this.rd(this.next16());t=13;}
    else if(op===0x27){ // 8080 DAA; addition-oriented BCD adjustment
      const a=this.A;const low=((a&15)>9||this.AC)?6:0;
      const high=(a>0x99||this.CY||((a+low)>0x99))?0x60:0;
      const n=a+low+high;
      this.A=n&255;this.AC=((a&15)+(low&15))>15?1:0;
      this.CY=(this.CY||n>255||high!==0)?1:0;this.szp(this.A);t=4;
    }else if(op===0x2f){this.A^=255;t=4;}
    else if(op===0x37){this.CY=1;t=4;}
    else if(op===0x3f){this.CY^=1;t=4;}
    else if(op===0xc3){this.PC=this.next16();t=10;}
    else if(op===0xc9){this.PC=this.pop16();t=10;}
    else if(op===0xcd){const x=this.next16();this.push16(this.PC);this.PC=x;t=17;}
    else if(op===0xd3){this.next();this.pulse(8,true);t=10;}
    else if(op===0xdb){this.next();this.A=255;t=10;}
    else if(op===0xe3){const l=this.rd(this.SP),h=this.rd(this.SP+1);
      this.writeMem(this.SP,this.L,13);this.writeMem(this.SP+1,this.H,16);
      this.L=l;this.H=h;t=18;}
    else if(op===0xe9){this.PC=this.HL;t=z80?4:5;}
    else if(op===0xeb){const x=this.HL;this.HL=this.DE;this.DE=x;t=z80?4:5;}
    else if(op===0xf3){this.diInstructions++;this.setINTE(0);t=4;}
    else if(op===0xfb){this.eiInstructions++;this.setINTE(1);t=4;}
    else if(op===0xf9){this.SP=this.HL;t=z80?6:5;}
    else throw new Error('Недопустимый код '+op.toString(16).toUpperCase().padStart(2,'0')+'h по адресу '+at.toString(16).toUpperCase().padStart(4,'0')+'h (Intel 8080)');
    this.cycles+=t;
    if(this.cycles>=this.nextSnapshot){this.markSnapshot();this.nextSnapshot+=this.hzTick;}
    return t;
  }
  run(onProgress){
    const maxInst=150000000;
    while(this.cycles<this.maxCycles && this.inst<maxInst){
      this.step();
      if(this.PC===0 && this.inst>1 && this.cycles>=1000){this.stoppedBy='loop';break;}
      if(this.halted){this.stoppedBy='hlt';break;}
      if(this.cycles>=this.nextStatus){onProgress?.(this.cycles/this.maxCycles);this.nextStatus+=8_000_000;}
    }
    if(this.inst>=maxInst){this.stoppedBy='instruction-limit';}
    this.markSnapshot();
    return this;
  }
}



const path=require('path');
const ROOT=__dirname;
const settings=JSON.parse(fs.readFileSync(path.join(ROOT,'build_report.json'),'utf8'));
const raw=new Uint8Array(fs.readFileSync(path.join(ROOT,'Intel8080_ROM64_A15_CONNECTED.bin')));
if(raw.length!==0x10000)throw new Error('Expected 64 KB physical ROM');
// A15 is CONNECTED: full 16-bit address map, no mirroring.
CPU8080.prototype.rd=function(addr){return this.mem[addr&0xffff];};
const stage=x=>parseInt(settings.stage_addrs[x],16);
const scenarios=[
 {name:'normal',expect:'SUCCESS'},
 {name:'checksum_payload_corrupt',expect:'BAD_CHECKSUM',rom:rom=>{rom[0x1812]^=0x80}},
 {name:'checksum_field_corrupt',expect:'BAD_CHECKSUM',rom:rom=>{rom[0xfff0]^=1}},
 {name:'addr_pattern_corrupt',expect:'BAD_CHECKSUM',rom:rom=>{rom[0x4000]^=1}},
 {name:'data_pattern_corrupt',expect:'BAD_CHECKSUM',rom:rom=>{rom[0x1005]^=1}},
 // Byte swaps used to preserve SUM16. CRC-16 detects these changes at stage 1,
 // before the subsequent address/data line tests.
 {name:'addr_test_checksum_neutral_swap',expect:'BAD_CHECKSUM',rom:rom=>{
  let t=rom[0x4000];rom[0x4000]=rom[0x6000];rom[0x6000]=t;}},
 {name:'data_test_checksum_neutral_swap',expect:'BAD_CHECKSUM',rom:rom=>{
  let t=rom[0x1005];rom[0x1005]=rom[0x1800];rom[0x1800]=t;}},
 {name:'cpu_mov_register_corruption',expect:'BAD_CPU',cpu_fault:true},
 {name:'physical_A14_stuck_low',expect:'BAD_CHECKSUM',address_stuck_low:0x4000},
 {name:'physical_A15_stuck_low',expect:'BAD_CHECKSUM',address_stuck_low:0x8000},
 {name:'checksum_high_half_corrupt',expect:'BAD_CHECKSUM',rom:rom=>{rom[0xb123]^=0x08}},
 {name:'A15_high_half_checksum_neutral_swap',expect:'BAD_CHECKSUM',rom:rom=>{const t=rom[0x8000];rom[0x8000]=rom[0x8100];rom[0x8100]=t;}},
];
function testOne(o){
 const mem=new Uint8Array(raw);o.rom?.(mem);
 const cpu=new CPU8080(mem,'8080',3500000,9,1,'inte');
 let firstError=null,maxPc=0,dataWrites=0,success=false,tampered=false;
 if(o.address_stuck_low){
  const stuck=o.address_stuck_low;
  cpu.rd=function(addr){return this.mem[(addr&0xffff)&~stuck]};
 }
 const w=cpu.writeMem.bind(cpu);
 cpu.writeMem=function(a,v,off){dataWrites++;w(a,v,off)};
 const originalStep=cpu.step.bind(cpu);
 cpu.step=function(){
  const pc=this.PC,op=this.rd(pc);
  const errKeys=['BAD_CHECKSUM','BAD_ADDRESS','BAD_DATA','BAD_CPU'];
  for(const label of errKeys){
   if(pc===parseInt(settings.error_addrs[label],16)&&firstError===null)firstError=label;
  }
  if(pc===stage('SUCCESS'))success=true;
  maxPc=Math.max(pc,maxPc);
  const t=originalStep();
  if(o.cpu_fault&&!tampered&&pc>=stage('TEST_REGISTER_MOV')&&pc<stage('TEST_REGISTER_MOV')+80&&op===0x06){
   // Simulate a faulty MVI B,imm result after the instruction executes.
   this.B^=1;tampered=true;
  }
  return t;
 };
 cpu.run();
 const actual=firstError|| (success?'SUCCESS':'NO_DECISION');
 if(actual!==o.expect)throw new Error(o.name+': observed '+actual+' expected '+o.expect+' PC='+cpu.PC.toString(16));
 if(cpu.stoppedBy!=='hlt')throw new Error(o.name+': not halted '+cpu.stoppedBy);
 if(dataWrites)throw new Error(o.name+': used memory writes');
 if(cpu.inte!==0)throw new Error(o.name+': INTE not 0 at HLT');
 return {scenario:o.name,result:actual,halt:cpu.stoppedBy,
  elapsed_seconds:Number((cpu.cycles/3500000).toFixed(6)),t_states:cpu.cycles,
  instructions:cpu.inst,inte_level_changes:cpu.inteCycles.length,
  ei_count:cpu.eiInstructions,di_count:cpu.diInstructions,
  ram_writes:dataWrites,final_pc:cpu.PC.toString(16).toUpperCase()};
}
const results=scenarios.map(testOne);
fs.writeFileSync(path.join(ROOT,'emulator_tests.json'),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results,null,2));
