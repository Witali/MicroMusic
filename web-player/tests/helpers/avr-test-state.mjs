import assert from 'node:assert/strict';
export const fields=['pc','cyc','irqDelay','timer','overflowAt','timerDivisor','prescalerAt',
  'irqStart','irqCount','lost','maxIRQ','writes','inIRQ','minSP','workLost','duty',
  'eempeUntil','clkprUntil'];
export function sameCPU(actual,expected,context=''){
  assert.deepEqual(actual.data,expected.data,context+' data/SREG/TCNT0/SPL');
  assert.deepEqual(actual.irqFrames,expected.irqFrames,context+' IRQ frames');
  for(const key of fields)assert.equal(actual[key],expected[key],context+' '+key);
}
export const snapshot=core=>({data:core.data.slice(),irqFrames:Array.from(core.irqFrames),
  fields:fields.map(key=>core[key])});
export const rr=(op,d,s)=>op|(d<<4)|(s&15)|((s&16)<<5);
export const immediate=(op,d,k)=>op|((d-16)<<4)|(k&15)|((k&240)<<4);
export const out=(address,d=8)=>0xb800|(d<<4)|(address&15)|((address&48)<<5);
export function put(rom,p,word){p=(p&511)*2;rom[p]=word;rom[p+1]=word>>8;}
export function program(Core,words,start=16,irq=false){
  const rom=new Uint8Array(1024).fill(255);
  words.forEach((word,i)=>put(rom,start+i,word));put(rom,start+words.length,out(0x29));
  if(irq){put(rom,3,out(0x29));put(rom,4,0x9518);}
  const c=new Core(rom,null,{fastIdle:false,fastBlocks:true});c.pc=start;return c;
}
export function advance(fast,reference,context='',onReferenceStep){
  let error;
  try{if(!fast.runBlock())fast.step();}catch(e){error=e.message;}
  if(error){
    assert.throws(()=>{onReferenceStep?.(reference);reference.step();},e=>e.message===error,context+' error');
    sameCPU(fast,reference,context);return error;
  }
  let steps=0;
  while(reference.cyc<fast.cyc){onReferenceStep?.(reference);reference.step();assert.ok(++steps<=65,'Reference cannot run indefinitely');}
  sameCPU(fast,reference,context);return null;
}
