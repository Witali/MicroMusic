import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';

const [input,output]=process.argv.slice(2),spec=JSON.parse(readFileSync(input,'utf8'));
const bytes=readFileSync(spec.image),results=[];
const word=value=>((value+32768)&65535)-32768;
function multiply(value,k,bits){
 if(k<0)value=word(-value);
 const p=value*Math.abs(k),half=1<<(bits-1),scale=1<<bits;
 return word(p<0?-Math.floor((-p+half)/scale):Math.floor((p+half)/scale));
}
for(const [engine,create] of [['reference',b=>new Reference(b)],['wasm',b=>new Wasm(b)],
 ['wasm-unoptimized',b=>new Wasm(b,undefined,{fastIdle:false,fastBlocks:false})]]){
 for(const fixture of spec.cases){
  const cpu=create(bytes),frames=JSON.parse(readFileSync(fixture.input)),expected=readFileSync(fixture.expected);
  cpu.data.fill(0,0x60,0x72);const actual=new Uint8Array(frames.length);
  let minimum=Infinity,maximum=0,irqChecked=0,maximumStack=0,previous=0,stateChecks=0;
  const states=new Int32Array(8);
  for(let n=0;n<frames.length;n++){
   const [value,...coefficients]=frames[n];
   (spec.coefficientMemory==='ram'?cpu.data:cpu.rom).set(coefficients.map(k=>k&255),spec.symbols.coefficient_data);
   const interrupt=n%257===0;
   cpu.pc=spec.symbols.filter_word_q4/2;cpu.sp=0x9f;cpu.sreg=interrupt?0xc1:0x41;
   cpu.io[0x39]=interrupt?2:0;cpu.pending=false;cpu.irqDelay=0;cpu.r[27]=0;
   cpu.r[14]=value&255;cpu.r[15]=(value>>8)&255;
   cpu.r[28]=0x60;cpu.r[29]=0;cpu.r[30]=(spec.symbols.coefficient_data+7)&255;cpu.r[31]=(spec.symbols.coefficient_data+7)>>8;
   cpu.pushPC(511);const before=cpu.cyc,irqs=cpu.irqCount;let steps=0,injected=false;
   while(cpu.pc!==511&&steps++<2000){
    if(interrupt&&!injected&&cpu.pc===spec.symbols.word_mul_round/2){cpu.pending=true;cpu.interrupt();injected=true;}
    cpu.step();maximumStack=Math.max(maximumStack,0x9f-cpu.sp);
   }
   assert.equal(cpu.pc,511);assert.equal(cpu.sp,0x9f);assert.equal(cpu.r[27],0);assert.equal(cpu.sreg&0xc0,interrupt?0xc0:0x40);
   actual[n]=cpu.r[24];assert.equal(actual[n],expected[n],`${engine} ${fixture.name} sample ${n}`);
   let ex=value;
   for(let j=7;j>=0;j--){const old=states[j],k=coefficients[j];ex=word(ex-multiply(old,k,spec.coefficientBits));if(j<7)states[j+1]=word(old+multiply(ex,k,spec.coefficientBits));}
   states[0]=ex;previous=word(ex+previous-(previous>>1));
   const stateWords=[...states,previous];
   for(let j=0;j<stateWords.length;j++){
    assert.equal(cpu.data[0x60+2*j]|(cpu.data[0x61+2*j]<<8),stateWords[j]&65535,`${engine} sample ${n} state ${j}`);stateChecks++;
   }
   if(interrupt){assert.ok(injected);assert.equal(cpu.irqCount-irqs,1);irqChecked++;}
   else{minimum=Math.min(minimum,cpu.cyc-before);maximum=Math.max(maximum,cpu.cyc-before);}
  }
  assert.deepEqual(Buffer.from(actual),expected);
  results.push({engine,case:fixture.name,samples:actual.length,minimumCycles:minimum,maximumCycles:maximum,maximumStack,
   pcm_sha256:createHash('sha256').update(actual).digest('hex'),model_sha256:fixture.model_sha256,irqChecked,stateChecks});
 }
}
const report={pass:true,stateBits:spec.stateBits,coefficientBits:spec.coefficientBits,filterBytes:spec.filterBytes,multiplyBytes:spec.multiplyBytes,
 arithmeticBytes:spec.filterBytes+spec.multiplyBytes,stateBytes:18,coefficientMemory:spec.coefficientMemory,
 coefficientBytes:spec.coefficientMemory==='ram'?8:0,results,
 samples:results.reduce((n,r)=>n+r.samples,0),stateChecks:results.reduce((n,r)=>n+r.stateChecks,0),irqChecked:results.reduce((n,r)=>n+r.irqChecked,0),
 scope:`Actual assembled 8-stage uniform Q${spec.coefficientBits} word filter on full phrases; host supplies excitation and promoted coefficients; cycles include internal calls and RET, exclude outer RCALL`,
 fullDecoderImplemented:false,hardwareTested:false};
writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
