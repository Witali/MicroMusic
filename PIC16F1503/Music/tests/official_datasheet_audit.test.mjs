import assert from 'node:assert/strict';
import test from 'node:test';
import {PIC16F1503, readPIC16Hex} from '../web/pic16-core.mjs';

// Microchip PIC16F1503 DS40001607D §§3,7,20,22; instruction table 27-3.
function cpu(...instr){const program=new Uint16Array(2048).fill(0);program.set(instr);return new PIC16F1503(program);}

for(const [mm,start,wantAddress,want] of [
 [0,0x20,0x21,0xB1], [1,0x21,0x20,0xA0],
 [2,0x20,0x21,0xA0], [3,0x21,0x20,0xB1]]){
 test(`MOVIW mode ${mm}: address modification and W`,()=>{
  const p=cpu(0x0010|mm);p.setFsr(0,start);p.mem[0x20]=0xA0;p.mem[0x21]=0xB1;
  assert.equal(p.step(),1);assert.equal(p.fsr(0),wantAddress);assert.equal(p.W,want);
 });
 test(`MOVWI mode ${mm}: address modification and RAM write`,()=>{
  const p=cpu(0x0018|mm);p.setFsr(0,start);p.W=0x5A;
  assert.equal(p.step(),1);assert.equal(p.fsr(0),wantAddress);
  const target=mm===0?0x21:mm===1?0x20:start;
  assert.equal(p.mem[target],0x5A);
 });
}

test('Indexed MOVIW FSR0 reads low 8 bits of 14-bit Flash word with extra cycle',()=>{
 const p=cpu(0x3f00);p.program[3]=0x32AB;p.setFsr(0,0x8003);
 assert.equal(p.step(),2);assert.equal(p.W,0xAB);assert.equal(p.fsr(0),0x8003);
});
test('MOVF INDF0,W program-memory access costs extra cycle',()=>{
 const p=cpu(0x0800);p.program[3]=0x34C1;p.setFsr(0,0x8003);
 assert.equal(p.step(),2);assert.equal(p.W,0xC1);
});
test('INDF self-reference has no recursive dereference',()=>{
 const p=cpu(0x3f00);p.setFsr(0,0);assert.equal(p.step(),1);assert.equal(p.W,0);
});
test('Core SFRs and common RAM mirror in every bank',()=>{
 const p=cpu(0);p.mem[3]=0x1c;p.bsr=3;
 assert.equal(p.rf(3),0x1C);
 p.setMemory(0x3F0,0x55);assert.equal(p.getMemory(0x70),0x55);
 p.setMemory(0x103,0x05);assert.equal(p.mem[3],0x1d); // TO,PD protected
});
test('Only 80+32 GPR bytes exist; linear GPR address maps correctly',()=>{
 const p=cpu(0);
 p.setMemory(0x2000,11);p.setMemory(0x204f,12);p.setMemory(0x2050,13);p.setMemory(0x206f,14);
 assert.equal(p.mem[0x20],11);assert.equal(p.mem[0x6f],12);
 assert.equal(p.mem[0xA0],13);assert.equal(p.mem[0xBF],14);
 p.setMemory(0x2070,0xF0);assert.equal(p.getMemory(0x2070),0);
 p.setMemory(0xC0,0xF0);assert.equal(p.getMemory(0xC0),0);
 p.setMemory(0x120,0xF0);assert.equal(p.getMemory(0x120),0);
});
test('Writing PCL branches and costs two machine cycles',()=>{
 const p=cpu(0x3004,0x0082,0x0000,0x0000,0x0000);
 p.step();assert.equal(p.step(),2);assert.equal(p.PC,4);
});
test('Unsupported opcode 0x007f must not become a valid instruction',()=>{
 const p=cpu(0x007f);assert.throws(()=>p.step(),/Unsupported PIC16 opcode/);
});
test('Timer2 PR2=3, postscale /2: second PWM period sets TMR2IF',()=>{
 const p=cpu(0);p.setMemory(0x1B,3);p.setMemory(0x1C,0x0C);
 p.advanceCycles(4);assert.equal(p.pwmPeriodCount,1);assert.equal(p.mem[0x11]&2,0);
 p.advanceCycles(4);assert.equal(p.pwmPeriodCount,2);assert.equal(p.mem[0x11]&2,2);
});
test('Writing TMR2 loads count and clears pre/postscalers',()=>{
 const p=cpu(0);p.setMemory(0x1B,3);p.setMemory(0x1C,0x0C);
 p.advanceCycles(4);assert.equal(p.postscale,1);
 p.setMemory(0x1A,2);assert.equal(p.timerCount,2);assert.equal(p.postscale,0);
 p.advanceCycles(2);assert.equal(p.pwmPeriodCount,2);assert.equal(p.mem[0x11]&2,0);
});
test('Writing T2CON clears pre/postscale but leaves TMR2 intact',()=>{
 const p=cpu(0);p.setMemory(0x1B,5);p.setMemory(0x1C,0x0C);
 p.advanceCycles(6);assert.equal(p.postscale,1);
 p.setMemory(0x1C,0x0C);assert.equal(p.timerCount,0);assert.equal(p.postscale,0);
});
test('PWM3 8-bit duty is split DCH/DCL; latched at Timer2 period boundary',()=>{
 const p=cpu(0);p.setMemory(0x1B,63);p.setMemory(0x1C,0x04);p.setMemory(0x619,0xc0);
 for(const val of [0,1,64,128,200,255]){
  p.setMemory(0x617,(val&3)<<6);p.setMemory(0x618,val>>2);
  p.advanceCycles(64);assert.equal(p.samples.at(-1),val);
 }
});
test('RETFIE restores W, STATUS flags, BSR, both FSR and PCLATH',()=>{
 const p=cpu(0x0000,0,0,0,0x0009);
 p.W=0xA5;p.mem[3]=0x1F;p.bsr=5;p.setFsr(0,0x2012);p.setFsr(1,0x8666);p.mem[10]=0x11;
 p.mem[0x0B]=0xC0;p.mem[0x091]=2;p.mem[0x011]=2;
 p.step();assert.equal(p.PC,4);
 p.W=0xFF;p.mem[3]=0x18;p.bsr=1;p.setFsr(0,0);p.setFsr(1,0);p.mem[10]=0;
 p.mem[0x011]=0; p.step();assert.equal(p.PC,1);
 assert.equal(p.W,0xA5);assert.equal(p.mem[3],0x1F);assert.equal(p.bsr,5);
 assert.equal(p.fsr(0),0x2012);assert.equal(p.fsr(1),0x8666);assert.equal(p.mem[10],0x11);
});
test('Official saved firmware HEX parses to 2K 14-bit words',()=>{
 const text=':020000000030CE\n:00000001FF\n';
 const p=readPIC16Hex(text);assert.equal(p.length,2048);assert.equal(p[0],0x3000);
});

test('CLRW decodes only 0x0100..0x0107, not reserved opcode range',()=>{
 const valid=cpu(0x0107);valid.W=0xEE;valid.step();assert.equal(valid.W,0);assert.equal(valid.Z,true);
 assert.throws(()=>cpu(0x0108).step(),/Unsupported PIC16 opcode/);
});
test('FSR1 post- and pre-increment work independently of FSR0',()=>{
 const p=cpu(0x0014|2,0x001C|0);p.setFsr(0,0x20);p.setFsr(1,0xA0);p.mem[0xA0]=0x44;
 p.step();assert.equal(p.W,0x44);assert.equal(p.fsr(1),0xA1);assert.equal(p.fsr(0),0x20);
 p.W=0x99;p.step();assert.equal(p.mem[0xA2],0x99);assert.equal(p.fsr(1),0xA2);
});
