// Test stimuli, not an arithmetic optimization/backend. Expectations follow
// Microchip DS40002198A; unchanged instruction-read overhead is calibrated.
export const coreProbeCases=Object.freeze([
  {id:'add-overflow',a:127,b:1,flags:0,asm:'add r16,r17',result:128,sreg:0x2c,cycles:1},
  {id:'adc-carry',a:255,b:0,flags:1,asm:'adc r16,r17',result:0,sreg:0x23,cycles:1},
  {id:'sub-borrow',a:0,b:1,flags:0,asm:'sub r16,r17',result:255,sreg:0x35,cycles:1},
  {id:'sbc-borrow',a:0,b:0,flags:3,asm:'sbc r16,r17',result:255,sreg:0x35,cycles:1},
  {id:'cpc-preserve',a:42,b:42,flags:0x42,asm:'cpc r16,r17',result:42,sreg:0x42,cycles:1},
  {id:'lsr-carry',a:1,b:0,flags:0,asm:'lsr r16',result:0,sreg:0x1b,cycles:1},
  {id:'asr-negative',a:128,b:0,flags:0,asm:'asr r16',result:192,sreg:0x0c,cycles:1},
  {id:'ror-carry-in',a:0,b:0,flags:1,asm:'ror r16',result:128,sreg:0x0c,cycles:1},
  {id:'adiw-overflow',a:0,b:0,flags:0,setup:'ldi r24,255\nldi r25,127',asm:'adiw r24,1\nmov r16,r25',result:128,sreg:0x0c,cycles:3},
  {id:'brne-taken',a:1,b:0,flags:0,asm:'brne 1f\nldi r16,238\n1: inc r16',result:2,sreg:0,cycles:3},
  {id:'cpse-two-words',a:85,b:85,flags:0,asm:'cpse r16,r17\nlds r16,probe_packet\ninc r16',result:86,sreg:0,cycles:4},
  {id:'rcall-ret',a:1,b:0,flags:0,asm:'rcall probe_callee',result:2,sreg:0,cycles:8},
].map(Object.freeze));

export function crc16(bytes){
  let crc=0xffff;
  for(const byte of bytes){crc^=byte<<8;for(let n=0;n<8;n++)crc=((crc<<1)^((crc&0x8000)?0x1021:0))&0xffff;}
  return crc;
}
export function decodeCoreProbe(packet,descriptor){
  if(!(packet instanceof Uint8Array)||packet.length!==64)throw Error('Exactly 64 EEPROM bytes required');
  if(String.fromCharCode(...packet.subarray(0,4))!=='AVR1'||packet[4]!==1||packet[5]!==coreProbeCases.length)throw Error('Unsupported core probe record');
  if(packet[7]!==0xa5)throw Error('Probe record is incomplete');
  if(!descriptor?.buildId||descriptor.buildId.length!==4||descriptor.buildId.some((b,i)=>b!==packet[8+i]))throw Error('Probe build ID mismatch');
  const checked=packet.slice();checked[7]=0;
  if(crc16([...checked.subarray(0,14),...checked.subarray(16)])!==(packet[14]|packet[15]<<8))throw Error('Probe CRC mismatch');
  const overhead=packet[12]|packet[13]<<8;
  const cases=coreProbeCases.map((c,n)=>{const at=16+n*4,delta=packet[at+2]|packet[at+3]<<8,cycles=(delta-overhead)&65535;
    return {id:c.id,result:packet[at],sreg:packet[at+1],timerTicks:delta,cycles,
      expected:{result:c.result,sreg:c.sreg,cycles:c.cycles},passed:packet[at]===c.result&&packet[at+1]===c.sreg&&cycles===c.cycles};});
  const passedCases=cases.filter(c=>c.passed).length;
  if(packet[6]!==passedCases)throw Error('Firmware/host pass count mismatch');
  return {schema:'micromusic-avr-core-probe-result-v1',device:'ATtiny88',nominalCpuHz:16000000,
    buildId:descriptor.buildId,overheadTicks:overhead,passedCases,passed:passedCases===cases.length,cases};
}
