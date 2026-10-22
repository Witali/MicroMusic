// Run using Node. Offline encoder from the restored Audio Codec Lab.
const fs=require('fs'),vm=require('vm'),path=require('path');
const n=fs.readFileSync(path.join(__dirname,'input_8k.s16le'));
const x=new Float32Array(n.length/2);for(let i=0;i<x.length;i++)x[i]=n.readInt16LE(i*2)/32768;
const code=fs.readFileSync(path.join(__dirname,'lpc_math.js'),'utf8');
const ctx={Float32Array,Float64Array,Uint8Array,DataView,ArrayBuffer,Math,console};vm.createContext(ctx);
(async()=>{
  vm.runInContext(code,ctx);
  const result=await vm.runInContext('encodeLPC(x,8000,{frameMs:20,pre:.85,voicing:.34,repeat:.055})',Object.assign(ctx,{x}));
  const packed=vm.runInContext('packLPC(result.meta,result.frames,result.analysis)',Object.assign(ctx,{result}));
  const pcm=await vm.runInContext('synthLPC(result.meta,result.frames)',ctx);
  fs.writeFileSync(path.join(__dirname,'phrase_lpc1.lpc'),Buffer.from(packed.buffer));
  const wav=new Int16Array(pcm.length);for(let i=0;i<pcm.length;i++)wav[i]=Math.round(Math.max(-1,Math.min(1,pcm[i]*.2))*32767);
  fs.writeFileSync(path.join(__dirname,'phrase_lpc1.s16le'),Buffer.from(wav.buffer));
  console.log('LPC1:',packed.stats, 'max',Math.max(...pcm));
  const cfg={frameMs:20,pre:.85,voicing:.36,windowMs:32,postfilter:.35,pitchSmooth:.65,repeat:.055};
  const res2=await vm.runInContext('encodeLPC2(x,8000,c)',Object.assign(ctx,{x,c:cfg}));
  const packed2=vm.runInContext('packLPC2(res2.meta,res2.frames,res2.analysis)',Object.assign(ctx,{res2}));
  const pcm2=await vm.runInContext('synthLPC2(res2.meta,res2.frames,.35)',ctx);
  fs.writeFileSync(path.join(__dirname,'phrase_lpc2.lp2'),Buffer.from(packed2.buffer));
  const wav2=new Int16Array(pcm2.length);for(let i=0;i<pcm2.length;i++)wav2[i]=Math.round(Math.max(-1,Math.min(1,pcm2[i]*.15))*32767);
  fs.writeFileSync(path.join(__dirname,'phrase_lpc2.s16le'),Buffer.from(wav2.buffer));
  console.log('LPC2:',packed2.stats);
})().catch(e=>{console.error(e);process.exit(1)});
