'use strict';
/* Extracts LPC synthesis coefficients from original LPX3 v1, using the
 * ORIGINAL Lisp/LSF->LPC model. Only a host-PC packaging operation.
 * The AVR never evaluates trigonometric or polynomial functions.
 */
const fs=require('fs'),vm=require('vm'),path=require('path');
if(process.argv.length!==4){console.error('usage: node analyze_lpx3.js input.lpx3 output.json');process.exit(2)}
const dat=fs.readFileSync(process.argv[2]);
const src=fs.readFileSync(path.join(__dirname,'../reference/lpx3_decoder.js'),'utf8');
const context={Float64Array,Float32Array,Uint8Array,DataView,Array,Math};vm.createContext(context);
vm.runInContext(src,context);
context.rawBytes=dat;
vm.runInContext(`
  const raw=new Uint8Array(rawBytes);
  const v=new DataView(raw.buffer,raw.byteOffset,raw.byteLength);
  const base=raw.slice(24,24+v.getUint32(12,true));
  const parsed=unpackLPC2(base.buffer), m=parsed.meta,frames=parsed.frames;
  let prev=decodeLpc2FrameLsf(frames[0]);
  const coeffFrame=[], coeffExact=[], lsfFrame=[];
  for(let f=0;f<frames.length;f++){
    const cur=decodeLpc2FrameLsf(frames[f]);
    coeffFrame.push(Array.from(lsfToLpc(cur)).slice(1));
    lsfFrame.push(Array.from(cur).map(v=>v/Math.PI));
    let sub=[];
    for(let j=0;j<8;j++){
      const t=(j+0.5)/8;
      const c=lsfToLpc(stabilizeLsf(cur.map((x,i)=>prev[i]+(x-prev[i])*t),10));
      sub.push(Array.from(c).slice(1));
    }
    coeffExact.push(sub);prev=cur;
  }
  globalThis.out={meta:{version:m.ver,rate:m.sr,frameSamples:m.H,pre:m.pre,samples:m.samples},coeffFrame,coeffExact,lsfFrame};
`,context);
fs.writeFileSync(process.argv[3],JSON.stringify(context.out));
console.error('frames',context.out.coeffFrame.length,'samples',context.out.meta.samples);
