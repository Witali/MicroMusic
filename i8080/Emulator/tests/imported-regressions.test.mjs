// Adapted from the original ChatGPT tests; incorrect AC and XCHG expectations corrected.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CPU8080, AudioBus, is8080Opcode, INVALID_8080 } from '../core8080.mjs';
const __dirname = fileURLToPath(new URL('./roms/', import.meta.url));
let checks=0;function check(ok,msg){checks++;if(!ok)throw Error('TEST FAILED: '+msg)};
function testCpu(code,mode='allram'){let c=new CPU8080(Uint8Array.from(code),{memoryMode:mode});c.sp=0x2000;return c}
function expectedCycles(op,conditionTaken){
 if(!is8080Opcode(op))return null;
 if(op>=0x40&&op<=0x7f)return op===0x76?7:((op&7)===6||((op>>3)&7)===6)?7:5;
 if(op>=0x80&&op<=0xbf)return (op&7)===6?7:4;
 if((op&0xc7)===0x06)return (op&0x38)===0x30?10:7;
 if((op&0xc7)===0x04||(op&0xc7)===0x05)return (op&0x38)===0x30?10:5;
 if((op&0xcf)===0x01)return 10;
 if((op&0xcf)===0x03||(op&0xcf)===0x0b)return 5;
 if((op&0xcf)===0x09)return 10;
 if((op&0xc7)===0xc2)return 10;
 if((op&0xc7)===0xc0)return conditionTaken?11:5;
 if((op&0xc7)===0xc4)return conditionTaken?17:11;
 if((op&0xcf)===0xc1)return 10;
 if((op&0xcf)===0xc5)return 11;
 if((op&0xc7)===0xc7)return 11;
 if((op&0xc7)===0xc6)return 7;
 const opstates={
 '00':4,'02':7,'0a':7,'12':7,'1a':7,'07':4,'0f':4,'17':4,'1f':4,'22':16,'2a':16,'27':4,'2f':4,'32':13,'3a':13,'37':4,'3f':4,
 'c3':10,'c9':10,'cd':17,'d3':10,'db':10,'e3':18,'e9':5,'eb':4,'f3':4,'fb':4,'f9':5
 };
 return opstates[op.toString(16).padStart(2,'0')]??null;
}
// Every documented opcode: runnable and not accidentally decoded as undocumented.
let count=0;for(let op=0;op<256;op++){
 let c=testCpu([op,0x70,0x00,0x76]);c.mem[0x2000]=0x01;c.mem[0x2001]=0;
 // Set selected condition flags such that conditional tests can both be explored below.
 if(is8080Opcode(op)){
  let c0=expectedCycles(op,op>=0xc0&&((op&0xc7)===0xc0||(op&0xc7)===0xc4)?c.cond((op>>3)&7):false);
  check(Number.isInteger(c0),'timing coverage 0x'+op.toString(16));
  c.step();check(c.t===c0,`opcode ${op.toString(16)} T got ${c.t} expected ${c0}`);count++;
  if((op&0xc7)===0xc0||(op&0xc7)===0xc4){
    // Force the same branch NOT to execute and compare the alternate timing.
    let no=testCpu([op,0x70,0x00,0x76]);let k=(op>>3)&7;
    let flagField=k<=1?'z':k<=3?'cy':k<=5?'p':'s';
    no.f[flagField]=(k&1)?0:1;
    check(!no.cond(k),'test conditional branch setup');no.step();
    check(no.t===expectedCycles(op,false),`conditional op 0x${op.toString(16)} not taken`);
  }
 }else{
  let threw=false;try{c.step()}catch(e){threw=/Undocumented/.test(e.message)}check(threw,'illegal trap 0x'+op.toString(16));
 }
}
check(count===244,'244 documented opcodes');
// Arithmetic / flags / BCD validation
let bcdCases=0;for(let a=0;a<100;a++)for(let b=0;b<100;b++){
 const bcd=x=>(Math.floor(x/10)<<4)|x%10;
 let cpu=testCpu([0x3e,bcd(a),0xc6,bcd(b),0x27,0x76]);cpu.step();cpu.step();cpu.step();
 check(cpu.r[7]===bcd((a+b)%100)&&cpu.f.cy===+(a+b>=100),`DAA ${a}+${b}`);bcdCases++;
}
{
 let c=testCpu([0x3e,0x00,0x06,0x08,0xa0,0x76]);c.step();c.step();c.step();check(c.f.ac===1,'8080 ANA AC flag ORs bit 3');
 let d=testCpu([0x3e,0x00,0x06,0x00,0xa0,0x76]);d.step();d.step();d.step();check(d.f.ac===0,'8080 ANA AC clear without bit 3');
}
{
 let c=testCpu([0x31,0,0x30,0x21,0x34,0x12,0xe5,0x21,0xcd,0xab,0xe1,0x76]);while(!c.halted)c.step();
 check(c.hl()===0x1234&&c.sp===0x3000,'PUSH/POP real RAM');
 check(c.mem[0x2ffe]===0x34&&c.mem[0x2fff]===0x12,'PUSH little-endian');
}
{
 let c=testCpu([0x31,0x00,0x30,0xcd,0x09,0x00,0x3e,0x77,0x76,0x3e,0x11,0xc9]);
 while(!c.halted&&c.count<40)c.step();
 check(c.halted&&c.r[7]===0x77&&c.sp===0x3000,'CALL and RET with RAM');
}
{
 let c=testCpu([0x31,0,0x30,0x21,0x34,0x12,0xe3,0x76]);c.mem[0x3000]=0x78;c.mem[0x3001]=0x56;
 while(!c.halted)c.step();check(c.hl()===0x5678&&c.mem[0x3000]===0x34&&c.mem[0x3001]===0x12,'XTHL swap registers and stack');
}
{
 let c=testCpu([0x21,0x00,0x80,0x36,0x72,0x34,0x35,0x76]);c.r[7]=0;
 while(!c.halted)c.step();check(c.mem[0x8000]===0x72&&c.memWrites===3,'MVI M, INR M, DCR M actual write');
}
{
 let c=new CPU8080(new Uint8Array([0x21,0,0x80,0x36,0x11,0x76]),{memoryMode:'rom'});while(!c.halted)c.step();
 check(c.mem[0x8000]===0xff&&c.ignoredWrites===1,'ROM write ignored');
}
{
 let rom=new Uint8Array(32768);rom[0]=0x3a;rom[1]=0x00;rom[2]=0x80;rom[3]=0x76;rom[0x0000]=0x3a;
 let c=new CPU8080(rom,{memoryMode:'rom'});check(c.mem[0x8000]===0x3a,'A15 disconnected mirror');
}
{
 let c=testCpu([0xdb,0x04,0xd3,0x09,0x76]);c.inputByte=0x2b;while(!c.halted)c.step();check(c.r[7]===0x2b&&c.ioWrites===1,'IN and OUT I/O');
}
{
 let a=new AudioBus(3500000,96000,'inte',1,1),c=new CPU8080(new Uint8Array([0xfb,0x00,0xf3,0x76]),{audio:a,mode:'inte'});
 while(!c.halted)c.step();let out=a.finish(c.t);
 check(c.t===19&&c.count===4&&a.edges===2,'INTE EI+NOP+DI+HLT timing and edges');
 check(out.length===1&&out[0]>=0&&out[0]<=1,'sub-sample accurate averaging');
}
{
 let a=new AudioBus(3500000,96000,'wr',1,1),c=new CPU8080(new Uint8Array([0x21,0x00,0x80,0x77,0x76]),{audio:a,mode:'wr'});
 while(!c.halted)c.step();let out=a.finish(c.t);
 check(c.t===24&&c.memWrites===1&&a.edges===2,'/WR MOV M,A one pulse');check(out.length===1,'/WR audio integration');
}
// Cross-check ALU against independent scalar arithmetic for edge cases and random operands.
let seed=0x13579BDF;
function nextRandom(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0}
const p8=x=>{let n=0;for(let i=0;i<8;i++)n+=(x>>i)&1;return +(n%2===0)};
let aluCases=0;
for(let i=0;i<25000;i++){
 const av=i<256?i:nextRandom()&255,bv=i<256?(255-i):nextRandom()&255,carry=i&1,op=i%8;
 let c=new CPU8080(Uint8Array.from([0]));c.r[7]=av;c.f.cy=carry;c.alu(op,bv);
 let result=0,cy=0,ac=0;
 if(op<=1){let sum=av+bv+(op===1?carry:0);result=sum&255;cy=+(sum>255);ac=+(((av&15)+(bv&15)+(op===1?carry:0))>15)}
 else if(op<=3||op===7){let borrow=(op===3?carry:0),diff=av-bv-borrow;result=diff&255;cy=+(diff<0);ac=+((av&15)>=((bv&15)+borrow))}
 else if(op===4){result=av&bv;cy=0;ac=+!!((av|bv)&8)}
 else if(op===5){result=av^bv;cy=0;ac=0}
 else{result=av|bv;cy=0;ac=0}
 const actual=op===7?av:result;
 check(c.r[7]===actual&&c.f.cy===cy&&c.f.ac===ac&&c.f.z===+(result===0)&&c.f.s===(result>>>7)&&c.f.p===p8(result),
 `ALU operation ${op} ${av.toString(16)} ${bv.toString(16)} carry ${carry}`);
 aluCases++;
}
// Long running firmware from previous independent verification reports
// XCHG is 4 T: the original reports overcounted 48,128 / 49,664 occurrences by 1 T.
const known=[['uniform26.bin',266506117,54399333,11069,29088],['balanced27.bin',261000805,52909359,11069,29168]];
let romChecks=[];
for(const [file,t,steps,pc,sp] of known){let b=new Uint8Array(fs.readFileSync(path.join(__dirname,file))),c=new CPU8080(b,{memoryMode:'rom'});
while(!c.halted&&c.count<=60000000)c.step();check(c.halted&&c.t===t&&c.count===steps&&c.pc===pc&&c.sp===sp&&c.memWrites===0,file+' verified timing/registers');romChecks.push({file,t,steps,pc,sp});}
const diagfile=path.join(__dirname,'diagnostic_dualcrc.bin');if(fs.existsSync(diagfile)){
 let b=new Uint8Array(fs.readFileSync(diagfile)),c=new CPU8080(b);while(!c.halted&&c.count<5000000)c.step();check(c.halted&&c.count===3869609&&c.t===19827541&&c.memWrites===0,'32K diagnostic/voice full regression');romChecks.push({file:'diagnostic_dualcrc.bin',t:c.t,steps:c.count,pc:c.pc,sp:c.sp});
}
let summary={version:'2.1.0',documentedOpcodes:count,undocumentedOpcodes:Array.from(INVALID_8080).map(x=>x.toString(16)),bcdPairs:bcdCases,aluCases,assertions:checks,romChecks};
console.log(JSON.stringify(summary,null,2));
