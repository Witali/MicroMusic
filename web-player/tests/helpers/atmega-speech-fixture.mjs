// Original synthetic machine-code fixture, never a speech codec output.
// ATmega328P AVR5 instructions and data-space addresses follow avr-libc's
// iom328p.h. Two independent timers run concurrently with a live sample ISR.
const ldi=(r,k)=>0xe000|((r-16)<<4)|(k&15)|((k&240)<<4);
const rr=(op,d,s)=>op|(d<<4)|(s&15)|((s&16)<<5);
const sts=(address,r)=>[0x9200|(r<<4),address];
const set=(address,value)=>[ldi(16,value),...sts(address,16)];
function hex(bytes){
  let result='';
  for(let at=0;at<bytes.length;at+=16){
    const data=[Math.min(16,bytes.length-at),at>>8,at&255,0,...bytes.slice(at,at+16)];
    data.push((-data.reduce((a,b)=>a+b,0))&255);
    result+=':'+data.map(x=>x.toString(16).padStart(2,'0')).join('').toUpperCase()+'\n';
  }
  return result+':00000001FF\n';
}
export function timerProgram(pwmOutput='OC2B'){
  const words=new Uint16Array(256).fill(0xffff),main=64,isr=128;
  const write=(at,code)=>words.set(code,at);
  write(0,[0xc000|(main-1)]);
  const vector=pwmOutput==='OC2B'?0x16:0x0e;
  write(vector,[0xc000|(isr-vector-1)]);
  const pwm=pwmOutput==='OC2B'?0xb4:0x88;
  const setup=pwmOutput==='OC2B'
    ?[...set(0x2a,8),...set(0xb4,128),...set(0xb0,0x23),...set(0xb1,1),
      ...set(0x89,7),...set(0x88,207),...set(0x6f,2),...set(0x81,9)]
    :[...set(0x24,2),...set(0x89,0),...set(0x88,128),...set(0x80,0x81),...set(0x81,9),
      ...set(0xb3,249),...set(0xb0,2),...set(0x70,2),...set(0xb1,2)];
  write(main,[ldi(16,17),ldi(17,19),rr(0x9c00,16,17),...sts(0x100,0),...sts(0x101,1),
    rr(0x2400,1,1),ldi(18,0),...setup,0x9478,0,0xcfff]);
  write(isr,[rr(0x0c00,18,17),...sts(pwm,18),0x9518]);
  return new Uint8Array(words.buffer);
}
export function speechEntry(pwmOutput='OC2B'){
  const bytes=timerProgram(pwmOutput);
  return {id:pwmOutput==='OC2B'?'lpx-fixture-arduino':'speex-fixture-arduino',order:'01',
    title:'Synthetic timer fixture',description:'Original test program; not encoded speech.',
    device:'atmega328p',board:'arduino-16mhz',executionEngine:'avr8js',supportedEngines:['avr8js'],
    cpuHz:16000000,sampleHz:8000,pwmHz:62500,kind:'speech',codec:pwmOutput==='OC2B'?'lpx-v5':'speex-nb',
    audioChannels:1,playOnce:true,phraseSamples:80,playbackCycles:200000,
    flashHex:hex(bytes),source:'firmware/atmega328p/test.hex',flashBytes:bytes.length,
    flashSha256:'0'.repeat(64),eepromBytes:0,pwmOutput,outputPin:pwmOutput==='OC2B'?'D3':'D9',
    programFlashBytes:496,encodedBytes:16,bitrateBps:12800,originalAudioUrl:'audio/lpx-bread/original.wav'};
}
export const arduinoCatalog=()=>{
  const entries=[speechEntry(),{...speechEntry('OC1A'),order:'02'}];
  return {schemaVersion:1,defaultId:entries[0].id,entries};
};
