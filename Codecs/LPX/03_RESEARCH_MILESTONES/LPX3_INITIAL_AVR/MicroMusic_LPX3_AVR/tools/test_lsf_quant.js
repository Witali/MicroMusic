'use strict';
const fs=require('fs'),vm=require('vm');
const src=fs.readFileSync(__dirname+'/../reference/lpx3_decoder.js','utf8');
const ctx={Float64Array,Float32Array,Uint8Array,DataView,Array,Math};vm.createContext(ctx);vm.runInContext(src,ctx);
ctx.raw=fs.readFileSync(process.argv[2]);ctx.bits=+process.argv[3];
vm.runInContext(`
 const a=new Uint8Array(raw),h=new DataView(a.buffer),base=a.slice(24,24+h.getUint32(12,true));
 const p=unpackLPC2(base.buffer), lsf=p.frames.map(decodeLpc2FrameLsf);
 const n=(1<<bits)-1,prev0=lsf[0];let prev=prev0,cf=[];
 for(let fi=0;fi<lsf.length;fi++){
  const cur=lsf[fi];
  const qc=stabilizeLsf(cur.map(v=>Math.round(v/Math.PI*n)/n*Math.PI),10);
  const qp=stabilizeLsf(prev.map(v=>Math.round(v/Math.PI*n)/n*Math.PI),10);
  let sub=[];for(let s=0;s<8;s++){
   const t=(s+.5)/8;
   sub.push(Array.from(lsfToLpc(stabilizeLsf(qc.map((v,i)=>qp[i]+(v-qp[i])*t),10))).slice(1));
  }cf.push(sub);prev=cur;
 }
 globalThis.cf=cf;
`,ctx);
fs.writeFileSync(process.argv[4],JSON.stringify(ctx.cf));
