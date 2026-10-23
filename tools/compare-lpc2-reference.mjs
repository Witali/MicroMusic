// Execute the retained reference codec offline on supplied float32 PCM.
// This is a codec benchmark, independent of the browser UI and audio device.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import vm from 'node:vm';

const [input,output,rate='7500']=process.argv.slice(2);
if(!input||!output)throw new Error('Usage: node tools/compare-lpc2-reference.mjs input.f32 output.f32 [sample-rate]');
const path=new URL('../ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html',import.meta.url);
const html=readFileSync(path,'utf8');
const code=html.slice(html.indexOf('const LPC_CHIRP='),html.indexOf('async function synthLFA('));
const bytes=readFileSync(resolve(input));
if(bytes.length%4)throw new Error('Expected little-endian float32 mono PCM');
const x=new Float32Array(bytes.length/4);
for(let i=0;i<x.length;i++)x[i]=bytes.readFloatLE(i*4);
const context=vm.createContext({x,sr:Number(rate),
  clamp:(v,lo,hi)=>Math.max(lo,Math.min(hi,v)),tick:async()=>{},progress:()=>{},status:()=>{}});
vm.runInContext(code,context,{filename:path.pathname});
const {packed,pcm}=await vm.runInContext(`(async()=>{
  const c={frameMs:20,windowMs:32,pre:.85,voicing:.38,repeat:.05,pitchSmooth:.65};
  const a=await encodeLPC2(x,sr,c),p=packLPC2(a.meta,a.frames,a.analysis),r=unpackLPC2(p.buffer);
  return {packed:{bytes:p.buffer.byteLength,meta:r.meta,stats:r.stats},pcm:await synthLPC2(r.meta,r.frames,.35)};
})()`,context);
const result=Buffer.alloc(pcm.length*4);
for(let i=0;i<pcm.length;i++)result.writeFloatLE(pcm[i],i*4);
writeFileSync(resolve(output),result);
console.log(JSON.stringify({source:'ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html',
  sourceSha256:createHash('sha256').update(html.replaceAll('\r\n','\n')).digest('hex'),...packed},null,2));
