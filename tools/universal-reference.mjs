// Independent UM88 command interpreter and exact integer audio oracle.
// Reads the uncompressed score, never firmware tables or the binary grammar.
import assert from 'node:assert/strict';

const word=(a,p)=>a[p]|a[p+1]<<8;
const roundEven=x=>{const a=Math.floor(x),f=x-a;return f===.5?a+(a&1):Math.round(x);};
export class UniversalReference {
 constructor(score,cpuHz,{pwmChannels=2,pwmFrames=192/pwmChannels,pwmReserveFrames=4/pwmChannels}={}){
  assert.equal(score.schema,'micromusic-um88-score');assert.equal(score.version,1);
  assert.ok(score.voices>=1&&score.voices<=8);assert.ok(cpuHz>=75000&&cpuHz<=16000000);
  this.score=score;this.cpuHz=cpuHz;this.pwmChannels=pwmChannels;
  this.steps=score.pitches.map(n=>n===null?0:roundEven(440*2**((n-69)/12)*65536/(cpuHz/1024)));
  this.voices=Array.from({length:score.voices},()=>({phase:0,step:0,level:0,context:0}));
  this.clock=0;this.fraction=0;this.samples=0;this.totalTicks=0;this.loops=-1;
  this.previous=[128,128];this.ring=new Uint8Array(pwmFrames*pwmChannels).fill(128);this.write=this.ring.length-pwmReserveFrames*pwmChannels;
  this.clippedSamples=0;this.peakMix=0;this.square=0;this.sum=0;this.commandCount=0;
  this.reset();this.events();
 }
 reset(){
  for(const v of this.voices){v.phase=0;v.step=0;v.level=0;}
  this.at=0;this.tick=0;this.wait=0;this.drumMode=0;this.drumPhase=0;this.noiseHigh=1;this.loops++;
 }
 events(){
  let budget=this.score.commands.length;
  const take=()=>{assert.ok(this.at<this.score.commands.length,'Truncated score');return this.score.commands[this.at++];};
  while(budget--){
   const op=take(),i=op&7;this.commandCount++;
   if(op===0){this.reset();continue;}
   if(op<64){this.wait=op;return;}
   if(op<72)this.voices[i].context=take();
   else if(op<80)this.voices[i].step=this.steps[take()];
   else if(op<88)this.voices[i].phase=0;
   else if(op<96)this.voices[i].phase=this.voices[take()].phase;
   else if(op===96)this.drumMode=take();
   else if(op===97)this.drumPhase=take();
   else if(op===98)this.noiseHigh=take();
   else if(op>=128)this.voices[(op>>4)&7].level=op&15;
   else throw Error('Reserved score opcode');
  }
  throw Error('A command cycle must reach WAIT');
 }
 advanceControl(){
  this.tick++;this.totalTicks++;
  for(const v of this.voices){
   const model=this.score.contexts[v.context][0],rows=this.score.envelopes[model],at=v.level*3;
   if(word(rows,at+1)&(1<<(this.tick&15)))v.level=rows[at];
  }
  if(!--this.wait)this.events();
 }
 wave(v,p){
  const [,base,gain]=this.score.contexts[v.context];
  const bank=base|((gain&64)&&v.level>=14?48:0);
  const packed=this.score.waves[bank+(p>>1)],q=((p&1?packed>>4:packed)&15)-8;
  let level=v.level;if(gain&128)level>>=1;if(gain&16)level>>=1;
  return Math.floor(((gain&32)?q:q*level)/2**(gain&7))||0;
 }
 beginSample(){
  this.clock+=75000;
  if(this.clock>=this.cpuHz){this.clock-=this.cpuHz;this.advanceControl();}
  this.beforePhases=this.voices.map(v=>v.phase);
  let l=0,r=0,group=0;
  for(const v of this.voices){
   v.phase=(v.phase+v.step)&65535;group+=this.wave(v,v.phase>>12);
   const mix=this.score.contexts[v.context][3];
   if(mix&128){
    let value=(mix&32)?Math.floor(Math.floor(group*v.level/8)/2**(mix&1)):Math.floor(group/2**(mix&7));
    group=0;l+=(mix&8)?Math.floor(value/2):value;r+=(mix&16)?Math.floor(value/2):value;
   }
  }
  this.mix=[l,r];this.peakMix=Math.max(this.peakMix,Math.abs(l),Math.abs(r));
  return ((l&65535)|((r&65535)<<16))>>>0;
 }
 percussion(){
  let advance=Math.floor(19200000/this.cpuHz);
  this.fraction+=19200000%this.cpuHz;
  if(this.fraction>=this.cpuHz){this.fraction-=this.cpuHz;advance++;}
  const mode=this.drumMode;if(!(mode&128))return 0;
  let q;
  if((mode&3)===0){
   this.drumPhase=(this.drumPhase+advance)&255;
   const phase=(this.drumPhase&128)?255-this.drumPhase:this.drumPhase;
   q=(phase-61)>>2;
  }else{
   let noise=this.drumPhase|(this.noiseHigh<<8),carry=noise>>15;
   noise=(noise<<1)&65535;if(carry)noise^=45;
   this.drumPhase=noise&255;this.noiseHigh=noise>>8;
   const low=noise&255;
   q=((mode&3)===1)?((low>>1)&63)-(low&63):((low>>1)&63)-32;q>>=2;
  }
  q>>=(mode>>2)&3;if(mode&16)q=(q+4)>>3;return q;
 }
 output(value){
  if(this.score.normalizer.length){
   const index=value-this.score.normalizerMinimum;
   assert.ok(index>=0&&index<this.score.normalizer.length,'Normalizer index leaves its table');
   return this.score.normalizer[index];
  }
  const raw=value*2**this.score.masterShift+128;
  if(raw<0||raw>255)this.clippedSamples++;
  return Math.max(0,Math.min(255,raw));
 }
 finishSample(){
  const drum=this.percussion(),target=this.mix.map(x=>this.output(x+drum));
  const mid=target.map((x,i)=>(this.previous[i]+x)>>1);
  const frames=[mid.map((x,i)=>(this.previous[i]+x)>>1),mid,target.map((x,i)=>(mid[i]+x)>>1),target];
  for(const frame of frames){
   for(let i=0;i<this.pwmChannels;i++)this.ring[this.write++]=frame[i];
   if(this.write===this.ring.length)this.write=0;
  }
  this.previous=target;this.samples++;
  const x=target[0]-128;this.square+=x*x;this.sum+=x;
 }
}
