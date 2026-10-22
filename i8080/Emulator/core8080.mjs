'use strict';
// Intel 8080A. Documented instruction T-states, no READY/wait states or active INT.
// Based on the user's ChatGPT player 2.0; provenance and corrections: SOURCE.json / README.md.
// The INTE level changes at EI/DI completion. Interrupt acceptance is a separate mechanism.
// /WR uses approximate one-T pulses at the end of each write machine cycle.
// 12 undocumented opcodes are deliberately rejected (not silently executed as NOPs).
export const INVALID_8080 = new Set([0x08,0x10,0x18,0x20,0x28,0x30,0x38,0xcb,0xd9,0xdd,0xed,0xfd]);
const IS_EVEN_PARITY=new Uint8Array(256);
for(let v=0;v<256;v++){let a=v,a1=0;for(let j=0;j<8;j++,a>>=1)a1^=a&1;IS_EVEN_PARITY[v]=a1^1}
export function is8080Opcode(op){return Number.isInteger(op)&&op>=0&&op<256&&!INVALID_8080.has(op)}
export class AudioBus {
 constructor(hz,rate,mode,seconds,wrLowT=1){
 if(!Number.isFinite(hz)||hz<100000||hz>10000000||!Number.isInteger(rate)||rate<8000||rate>192000||!Number.isFinite(seconds)||seconds<=0||seconds>120||!['inte','wr'].includes(mode)||!Number.isFinite(wrLowT)||wrLowT<=0||wrLowT>1)throw Error('Invalid audio settings');
 this.hz=hz;this.rate=rate;this.mode=mode;this.lowT=wrLowT;this.max=Math.ceil(seconds*rate)+1;
 this.samples=new Float32Array(this.max);this.i=0;this.position=0;this.area=0;this.level=mode==='wr'?1:0;this.edges=0;this.transitions=[];this.trackEvents=false;}
 advance(to){if(to+1e-8<this.position)throw Error('Out-of-order audio edge '+to+' before '+this.position);
 const scale=this.hz/this.rate;
 while(this.i<this.max&&(this.i+1)*scale<=to){let end=(this.i+1)*scale;this.area+=this.level*(end-this.position);this.samples[this.i++]=this.area/scale;this.position=end;this.area=0}
 this.area+=this.level*(to-this.position);this.position=to;
 }
 edge(v,at){this.advance(at);if(this.level!==v){this.edges++;this.level=v;if(this.trackEvents)this.transitions.push([at,v])}}
 finish(at){this.advance(at);if(this.i<this.max){const duration=at-this.i*this.hz/this.rate;if(duration>1e-8)this.samples[this.i++]=this.area/duration}return this.samples.slice(0,this.i)}
}
export class CPU8080 {
 constructor(rom,opts={}){
  if(!(rom instanceof Uint8Array))throw Error('ROM must be a Uint8Array');
  if(opts.memoryMode!==undefined&&!['rom','ramupper','allram'].includes(opts.memoryMode))throw Error('Invalid memory mode');
  for(const key of ['pc','sp'])if(opts[key]!==undefined&&(!Number.isInteger(opts[key])||opts[key]<0||opts[key]>65535))throw Error('Invalid '+key);
  if(opts.inputByte!==undefined&&(!Number.isInteger(opts.inputByte)||opts.inputByte<0||opts.inputByte>255))throw Error('Invalid input byte');
  if(opts.wrLowT!==undefined&&(!Number.isFinite(opts.wrLowT)||opts.wrLowT<=0||opts.wrLowT>1))throw Error('Invalid /WR pulse width');
  this.mem=new Uint8Array(65536).fill(0xff);this.memoryMode=opts.memoryMode||'rom';this.romSize=rom.length;
  if(rom.length>65536||rom.length<1)throw Error('ROM must contain 1...65536 bytes');
  this.mem.set(rom);if(this.memoryMode==='rom'&&rom.length===32768)this.mem.set(rom,32768);
  this.r=new Uint8Array(8);this.pc=opts.pc||0;this.sp=opts.sp||0;
  this.f={s:0,z:0,p:0,cy:0,ac:0};this.inte=0;this.halted=false;this.t=0;this.count=0;this.memWrites=0;this.ignoredWrites=0;this.ioWrites=0;this.lastOpcode=null;
  this.hz=opts.hz||3500000;this.mode=opts.mode||'inte';this.inputByte=opts.inputByte===undefined?0xff:opts.inputByte;
  this.audio=opts.audio||null;this.wrLowT=opts.wrLowT||1;
 }
 read(addr){return this.mem[addr&65535]}
 read16(addr){return this.read(addr)|(this.read(addr+1)<<8)}
 fetch(){let x=this.read(this.pc);this.pc=(this.pc+1)&65535;return x}
 fetch16(){let x=this.fetch();return x|(this.fetch()<<8)}
 hl(){return (this.r[4]<<8)|this.r[5]}
 pair(k){return k===0?(this.r[0]<<8)|this.r[1]:k===1?(this.r[2]<<8)|this.r[3]:k===2?this.hl():this.sp}
 setpair(k,x){x&=65535;if(k===3)this.sp=x;else{this.r[k*2]=x>>>8;this.r[k*2+1]=x&255}}
 get(k){return k===6?this.read(this.hl()):this.r[k]}
 put(k,x,off){if(k===6)this.write(this.hl(),x,off);else this.r[k]=x&255}
 pulse(off){if(this.audio&&this.mode==='wr'){let begin=this.t+off;this.audio.edge(0,begin);this.audio.edge(1,begin+this.wrLowT)}}
 write(addr,x,off=0){addr&=65535;this.memWrites++;
  if(this.memoryMode==='allram'||(this.memoryMode==='ramupper'&&addr>=32768))this.mem[addr]=x&255;
  else this.ignoredWrites++;
  this.pulse(off);
 }
 setSZP(x){x&=255;this.f.s=x>>>7;this.f.z=+(x===0);this.f.p=IS_EVEN_PARITY[x];return x}
 add(v,withCarry){let a=this.r[7],c=withCarry?this.f.cy:0,sum=a+v+c;
  this.f.ac=+(((a&15)+(v&15)+c)>15);this.f.cy=+(sum>255);this.r[7]=this.setSZP(sum)}
 sub(v,withBorrow,cmp=false){let a=this.r[7],c=withBorrow?this.f.cy:0,sum=a-v-c;
  // 8080 AC is carry out of the complemented low-nibble addition, not half borrow.
  this.f.ac=+(((a&15)+((~v)&15)+1-c)>15);this.f.cy=+(sum<0);
  let result=this.setSZP(sum);if(!cmp)this.r[7]=result}
 alu(k,v){let a=this.r[7];switch(k){
  case 0:this.add(v,false);break;case 1:this.add(v,true);break;
  case 2:this.sub(v,false);break;case 3:this.sub(v,true);break;
  case 4:this.r[7]=this.setSZP(a&v);this.f.cy=0;this.f.ac=+!!((a|v)&8);break; // 8080 ANA differs from 8085
  case 5:this.r[7]=this.setSZP(a^v);this.f.cy=this.f.ac=0;break;
  case 6:this.r[7]=this.setSZP(a|v);this.f.cy=this.f.ac=0;break;
  case 7:this.sub(v,false,true);break;
 }}
 cond(k){let f=this.f;return k===0?!f.z:k===1?!!f.z:k===2?!f.cy:k===3?!!f.cy:k===4?!f.p:k===5?!!f.p:k===6?!f.s:!!f.s}
 packFlags(){let f=this.f;return f.s*128|f.z*64|f.ac*16|f.p*4|2|f.cy}
 unpackFlags(b){this.f.s=(b>>>7)&1;this.f.z=(b>>>6)&1;this.f.ac=(b>>>4)&1;this.f.p=(b>>>2)&1;this.f.cy=b&1}
 push(x,offs=[8,11]){this.sp=(this.sp-1)&65535;this.write(this.sp,x>>8,offs[0]);this.sp=(this.sp-1)&65535;this.write(this.sp,x&255,offs[1]);}
 pop(){let v=this.read16(this.sp);this.sp=(this.sp+2)&65535;return v}
 daa(){let a=this.r[7],oldCarry=this.f.cy,oldAC=this.f.ac;let correction=0;
  if((a&15)>9||oldAC)correction|=0x06;
  if(a>0x99||oldCarry)correction|=0x60;
  this.f.ac=+(((a&15)+(correction&15))>15);
  this.f.cy=+(oldCarry||a+correction>255);
  this.r[7]=this.setSZP(a+correction);
 }
 step(){if(this.halted)return 0;
 let startPC=this.pc,op=this.fetch(),c=4,r=this.r;this.lastOpcode=op;
 if(INVALID_8080.has(op))throw Error('Undocumented 8080 opcode '+op.toString(16).padStart(2,'0').toUpperCase()+'h at '+startPC.toString(16).padStart(4,'0').toUpperCase()+'h');
 if(op>=0x40&&op<=0x7f){
   if(op===0x76){this.halted=true;c=7}
   else{let src=op&7,dst=(op>>>3)&7;this.put(dst,this.get(src),6);c=(src===6||dst===6)?7:5}
 }else if(op>=0x80&&op<=0xbf){this.alu((op>>>3)&7,this.get(op&7));c=(op&7)===6?7:4}
 else if((op&0xc7)===0x06){let dst=(op>>>3)&7,v=this.fetch();this.put(dst,v,dst===6?9:0);c=dst===6?10:7}
 else if((op&0xc7)===0x04){let dst=(op>>>3)&7,v=this.get(dst),res=this.setSZP(v+1);
   this.f.ac=+((v&15)===15);this.put(dst,res,9);c=dst===6?10:5}
 else if((op&0xc7)===0x05){let dst=(op>>>3)&7,v=this.get(dst),res=this.setSZP(v-1);
   this.f.ac=+((v&15)!==0);this.put(dst,res,9);c=dst===6?10:5}
 else if((op&0xcf)===0x01){this.setpair((op>>>4)&3,this.fetch16());c=10}
 else if((op&0xcf)===0x03){let k=(op>>>4)&3;this.setpair(k,this.pair(k)+1);c=5}
 else if((op&0xcf)===0x0b){let k=(op>>>4)&3;this.setpair(k,this.pair(k)-1);c=5}
 else if((op&0xcf)===0x09){let sum=this.hl()+this.pair((op>>>4)&3);this.f.cy=+(sum>65535);this.setpair(2,sum);c=10}
 else if((op&0xc7)===0xc2){let dest=this.fetch16();if(this.cond((op>>>3)&7))this.pc=dest;c=10}
 else if((op&0xc7)===0xc0){let yes=this.cond((op>>>3)&7);if(yes)this.pc=this.pop();c=yes?11:5}
 else if((op&0xc7)===0xc4){let dest=this.fetch16(),yes=this.cond((op>>>3)&7);
  if(yes){this.push(this.pc,[13,16]);this.pc=dest}c=yes?17:11}
 else if((op&0xcf)===0xc1){let k=(op>>>4)&3,v=this.pop();if(k===3){r[7]=v>>>8;this.unpackFlags(v&255)}else this.setpair(k,v);c=10}
 else if((op&0xcf)===0xc5){let k=(op>>>4)&3,v=k===3?(r[7]<<8)|this.packFlags():this.pair(k);this.push(v,[7,10]);c=11}
 else if((op&0xc7)===0xc7){this.push(this.pc,[7,10]);this.pc=op&0x38;c=11}
 else if((op&0xc7)===0xc6){this.alu((op>>>3)&7,this.fetch());c=7}
 else switch(op){
 case 0x00:break;
 case 0x02:this.write(this.pair(0),r[7],6);c=7;break;
 case 0x12:this.write(this.pair(1),r[7],6);c=7;break;
 case 0x0a:r[7]=this.read(this.pair(0));c=7;break;
 case 0x1a:r[7]=this.read(this.pair(1));c=7;break;
 case 0x07:this.f.cy=r[7]>>>7;r[7]=(r[7]<<1|this.f.cy)&255;break;
 case 0x0f:this.f.cy=r[7]&1;r[7]=(r[7]>>>1)|(this.f.cy<<7);break;
 case 0x17:{let cy=this.f.cy;this.f.cy=r[7]>>>7;r[7]=(r[7]<<1|cy)&255;break}
 case 0x1f:{let cy=this.f.cy;this.f.cy=r[7]&1;r[7]=(r[7]>>>1)|(cy<<7);break}
 case 0x22:{let addr=this.fetch16();this.write(addr,r[5],12);this.write(addr+1,r[4],15);c=16;break}
 case 0x2a:{let addr=this.fetch16();r[5]=this.read(addr);r[4]=this.read(addr+1);c=16;break}
 case 0x27:this.daa();break;
 case 0x2f:r[7]^=255;break;
 case 0x32:{let addr=this.fetch16();this.write(addr,r[7],12);c=13;break}
 case 0x3a:r[7]=this.read(this.fetch16());c=13;break;
 case 0x37:this.f.cy=1;break;
 case 0x3f:this.f.cy^=1;break;
 case 0xc3:this.pc=this.fetch16();c=10;break;
 case 0xc9:this.pc=this.pop();c=10;break;
 case 0xcd:{let dest=this.fetch16();this.push(this.pc,[13,16]);this.pc=dest;c=17;break}
 case 0xd3:{this.fetch();this.ioWrites++;this.pulse(9);c=10;break}
 case 0xdb:{this.fetch();r[7]=this.inputByte;c=10;break}
 case 0xe3:{let l=this.read(this.sp),h=this.read(this.sp+1);this.write(this.sp,r[5],14);this.write(this.sp+1,r[4],17);r[5]=l;r[4]=h;c=18;break}
 case 0xe9:this.pc=this.hl();c=5;break;
 case 0xeb:{let d=r[2],e=r[3];r[2]=r[4];r[3]=r[5];r[4]=d;r[5]=e;c=4;break}
 case 0xf3:this.inte=0;if(this.audio&&this.mode==='inte')this.audio.edge(0,this.t+4);break;
 case 0xfb:this.inte=1;if(this.audio&&this.mode==='inte')this.audio.edge(1,this.t+4);break;
 case 0xf9:this.sp=this.hl();c=5;break;
 default:throw Error('Decoder error at '+startPC.toString(16)+' opcode '+op.toString(16));
 }
 this.t+=c;this.count++;
 if(this.audio)this.audio.advance(this.t);
 return c;
 }
}
