// All core instruction families relevant to PIC16F1503 enhanced mid-range.
// Microchip DS40001607D Table 27-3, including branch flushes and skip cases.
import test from 'node:test';
import assert from 'node:assert/strict';
import {PIC16F1503} from '../web/pic16-core.mjs';
const cases=[
 ['NOP',0x0000,1],['RESET',0x0001,1],['RETURN',0x0008,2],
 ['RETFIE',0x0009,2],['CALLW',0x000a,2],['BRW',0x000b,2],
 ['MOVLB',0x0020,1],['MOVLP',0x3180,1],['CLRW',0x0100,1],
 ['CLRF',0x018c,1],['MOVWF',0x008c,1],['ADDWF',0x070c,1],
 ['ANDWF',0x050c,1],['IORWF',0x040c,1],['XORWF',0x060c,1],
 ['SUBWF',0x020c,1],['DECF',0x030c,1],['MOVF',0x080c,1],
 ['COMF',0x090c,1],['INCF',0x0a0c,1],['DECFSZ/not-taken',0x0b0c,1],
 ['INCFSZ/not-taken',0x0f0c,1],['SWAPF',0x0e0c,1],
 ['RRF',0x0c0c,1],['RLF',0x0d0c,1],['ADDWFC',0x3d0c,1],
 ['SUBWFB',0x3b0c,1],['ASRF',0x370c,1],['LSLF',0x350c,1],
 ['LSRF',0x360c,1],['BCF',0x100c,1],['BSF',0x140c,1],
 ['BTFSS/not-taken',0x1c0c,1],['BTFSC/taken',0x180c,2],
 ['CALL',0x2002,2],['GOTO',0x2802,2],['BRA',0x3200,2],
 ['ADDFSR',0x3100,1],['MOVIW-post',0x0012,1],
 ['MOVWI-post',0x001a,1],['MOVIW-index',0x3f00,1],
 ['MOVWI-index',0x3f80,1],['ADDLW',0x3e00,1],
 ['ANDLW',0x3900,1],['IORLW',0x3800,1],['XORLW',0x3a00,1],
 ['SUBLW',0x3c00,1],['MOVLW',0x3000,1],['RETLW',0x3400,2],
 ['CLRWDT',0x0064,1],['OPTION',0x0062,1],['SLEEP',0x0063,1],
 ['TRISA',0x0065,1],['TRISC',0x0067,1],
];
for(const [name,opcode,want] of cases){
 test(`PIC instruction ${name} has ${want} TCY`,()=>{
  const p=new PIC16F1503(new Uint16Array(2048).fill(0));p.program[0]=opcode;
  p.setFsr(0,0x20);p.stack=[1];
  const returned=p.step();
  assert.equal(returned,want);
  assert.equal(p.cycle,want);
 });
}
for(const [name,op,value] of [
 ['DECFSZ/taken',0x0b0c,1],['INCFSZ/taken',0x0f0c,255],
 ['BTFSS/taken',0x1c0c,1],['BTFSC/not-taken',0x180c,1]]){
 test(`PIC conditional ${name}`,()=>{
  const p=new PIC16F1503(new Uint16Array(2048).fill(0));p.program[0]=op;p.mem[0x0c]=value;
  const cycles=p.step();assert.equal(cycles,name==='BTFSC/not-taken'?1:2);
  assert.equal(p.PC,name==='BTFSC/not-taken'?1:2);
 });
}
