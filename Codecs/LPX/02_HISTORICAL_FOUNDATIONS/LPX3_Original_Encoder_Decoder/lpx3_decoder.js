"use strict";
/* LPX3 v1: an LPC2 Voice v2 descriptor plus 2/3/4-bit voiced excitation.
 * Legacy LPC2 v2 bitstream is preserved byte for byte in the header.
 * Generated from existing LPC2 v2 formant conversion functions.
 */
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const LPC2_LSF_BITS10=[5,5,4,4,4,4,4,3,3,3], LPC2_LSF_BITS4=[5,5,4,4];
let LPC2_PITCH_MIN=65,LPC2_PITCH_MAX=850;
function qLpc2Pitch(q,sr,minHz=LPC2_PITCH_MIN,maxHz=LPC2_PITCH_MAX){const f=minHz*(maxHz/minHz)**(q/63);return sr/f}

function polyMul(a,b){const o=new Float64Array(a.length+b.length-1);for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++)o[i+j]+=a[i]*b[j];return o}

function stabilizeLsf(input,order){
  const x=Array.from(input).sort((a,b)=>a-b),sep=Math.PI*(order===10?.012:.025),lo=sep,hi=Math.PI-sep;
  for(let i=0;i<order;i++)x[i]=clamp(x[i]??Math.PI*(i+1)/(order+1),lo,hi);
  for(let i=1;i<order;i++)x[i]=Math.max(x[i],x[i-1]+sep);
  if(x[order-1]>hi){x[order-1]=hi;for(let i=order-2;i>=0;i--)x[i]=Math.min(x[i],x[i+1]-sep)}
  if(x[0]<lo){x[0]=lo;for(let i=1;i<order;i++)x[i]=Math.max(x[i],x[i-1]+sep)}
  return new Float64Array(x)
}

function lpcToLsf(a){
  const p=a.length-1,steps=p===10?640:320,rr=[],ri=[];
  function bi(w){let ar=0,ai=0;for(let k=0;k<=p;k++){ar+=a[k]*Math.cos(w*k);ai-=a[k]*Math.sin(w*k)}const ph=w*(p+1)/2,c=Math.cos(ph),s=Math.sin(ph);return[ar*c-ai*s,ar*s+ai*c]}
  function root(lo,hi,which,flo){for(let z=0;z<24;z++){const mid=(lo+hi)/2,v=bi(mid)[which];if(flo*v<=0)hi=mid;else{lo=mid;flo=v}}return(lo+hi)/2}
  let pw=1e-6,[pr,pi]=bi(pw);
  for(let n=1;n<=steps;n++){
    const w=Math.PI*n/(steps+1),v=bi(w),cr=v[0],ci=v[1];
    if(pr===0||cr===0||pr*cr<0){const q=root(pw,w,0,pr);if(q>1e-4&&q<Math.PI-1e-4&&(!rr.length||Math.abs(q-rr[rr.length-1])>1e-4))rr.push(q)}
    if(pi===0||ci===0||pi*ci<0){const q=root(pw,w,1,pi);if(q>1e-4&&q<Math.PI-1e-4&&(!ri.length||Math.abs(q-ri[ri.length-1])>1e-4))ri.push(q)}
    pw=w;pr=cr;pi=ci
  }
  const roots=[...rr.map(x=>[x,0]),...ri.map(x=>[x,1])].sort((a,b)=>a[0]-b[0]);
  if(roots.length!==p)return null;
  return stabilizeLsf(roots.map(x=>x[0]),p)
}

function lsfToLpc(lsf){
  const x=stabilizeLsf(lsf,lsf.length),r=[],i=[];
  for(let n=0;n<x.length;n++)(n&1?i:r).push(x[n]);
  let P=new Float64Array([1,1]),Q=new Float64Array([1,-1]);
  for(const w of r)P=polyMul(P,new Float64Array([1,-2*Math.cos(w),1]));
  for(const w of i)Q=polyMul(Q,new Float64Array([1,-2*Math.cos(w),1]));
  const a=new Float64Array(x.length+1);
  for(let n=0;n<a.length;n++)a[n]=.5*((P[n]||0)+(Q[n]||0));
  a[0]=1;return a
}

function lsfRange(index,order){const sep=order===10?.012:.025,center=(index+1)/(order+1),half=order===10?.235:.30;return[Math.max((index+1)*sep,center-half),Math.min(1-(order-index)*sep,center+half)]}

function quantLsf(lsf,bits){const order=bits.length,x=stabilizeLsf(lsf,order),q=[];for(let i=0;i<order;i++){const [lo,hi]=lsfRange(i,order),n=(1<<bits[i])-1,u=clamp(x[i]/Math.PI,lo,hi);q.push(clamp(Math.round((u-lo)/(hi-lo)*n),0,n))}return q}

function unquantLsf(q,bits){const order=bits.length,x=[];for(let i=0;i<order;i++){const [lo,hi]=lsfRange(i,order),n=(1<<bits[i])-1;x.push((lo+(q[i]/n)*(hi-lo))*Math.PI)}return stabilizeLsf(x,order)}

function defaultLsf(order){return new Float64Array(Array.from({length:order},(_,i)=>Math.PI*(i+1)/(order+1)))}

function expandLsf4(lsf4){const a4=lsfToLpc(lsf4),a10=new Float64Array(11);a10.set(a4);return lpcToLsf(a10)||defaultLsf(10)}

function unpackLPC2(b){
  const v=new DataView(b);if(b.byteLength<36||String.fromCharCode(v.getUint8(0),v.getUint8(1),v.getUint8(2),v.getUint8(3))!=="LPC2"||![1,2].includes(v.getUint8(4)))throw Error("Это не поддерживаемый поток LPC2");
  const m={codec:"lpc2",ver:v.getUint8(4),pitchMin:v.getUint8(4)===2?v.getUint16(32,true):55,pitchMax:v.getUint8(4)===2?v.getUint16(34,true):420,order:v.getUint8(5),sr:v.getUint16(6,true),H:v.getUint16(8,true),W:v.getUint16(10,true),frameCount:v.getUint32(12,true),samples:v.getUint32(16,true),payloadBits:v.getUint32(20,true),pre:v.getFloat32(24,true),voicing:v.getFloat32(28,true)};
  if(m.order!==10||m.pitchMin<20||m.pitchMax>2500||m.pitchMax<=m.pitchMin||36+Math.ceil(m.payloadBits/8)>b.byteLength)throw Error("Повреждён или не поддерживается LPC2");
  const br=new BitReader(v,36,m.payloadBits),frames=[];let previous=null,voiced=0,mixed=0,transient=0,repeats=0,silence=0,pitchSum=0;
  for(let n=0;n<m.frameCount;n++){
    const energy=br.read(5);
    if(!energy){const f={energy:0,mode:0,pitch:0,repeat:false,lsfq:quantLsf(defaultLsf(4),LPC2_LSF_BITS4)};frames.push(f);previous=f;silence++;continue}
    const mode=br.read(2),repeat=!!br.read(1),isVoiced=mode===1||mode===2,pitch=isVoiced?br.read(6):0,bits=isVoiced?LPC2_LSF_BITS10:LPC2_LSF_BITS4;let lsfq;
    if(repeat){if(!previous||((previous.mode===1||previous.mode===2)!==isVoiced))throw Error("Некорректный повтор LSF");lsfq=previous.lsfq.slice();repeats++}
    else{lsfq=[];for(let i=0;i<bits.length;i++)lsfq.push(br.read(bits[i]))}
    const f={energy,mode,pitch,repeat,lsfq};frames.push(f);previous=f;if(mode===2)voiced++;if(mode===1)mixed++;if(mode===3)transient++;if(isVoiced)pitchSum+=m.sr/qLpc2Pitch(pitch,m.sr,m.pitchMin,m.pitchMax)
  }
  return{meta:m,frames,stats:{version:m.ver,codec:"lpc2",frames:m.frameCount,payloadBits:m.payloadBits,payloadBytes:Math.ceil(m.payloadBits/8),voiced,mixed,transient,repeatFrames:repeats,silence,avgPitch:(voiced+mixed)?pitchSum/(voiced+mixed):0,actualBytes:b.byteLength}}
}

function decodeLpc2FrameLsf(f){const voiced=f.mode===1||f.mode===2;if(voiced)return unquantLsf(f.lsfq,LPC2_LSF_BITS10);return expandLsf4(unquantLsf(f.lsfq,LPC2_LSF_BITS4))}
class BitReader{constructor(v,o,bits){this.v=v;this.o=o;this.bit=0;this.left=bits}read(n){if(this.left<n)throw Error("Обрезан LPC-битовый поток");let q=0;for(let i=0;i<n;i++){q|=((this.v.getUint8(this.o+(this.bit>>3))>>(this.bit&7))&1)<<i;this.bit++;this.left--}return q}}

function unpackLPX3Codes(raw,bits,n){
  const out=new Uint8Array(n), mask=(1<<bits)-1;
  let acc=0,nb=0,j=0;
  for(let i=0;i<raw.length;i++){
    acc|=raw[i]<<nb;nb+=8;
    while(nb>=bits && j<n){out[j++]=acc&mask;acc>>>=bits;nb-=bits;}
  }
  if(j!==n)throw Error('Обрезанные данные LPX3');
  return out;
}
function decodeLPX3(input){
  const bytes=input instanceof Uint8Array ? input : new Uint8Array(input);
  if(bytes.length<24)throw Error('Короткий LPX3');
  const h=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(String.fromCharCode(...bytes.subarray(0,4))!=='LPX3' || h.getUint8(4)!==1)
    throw Error('Неверная сигнатура или версия LPX3');
  const bits=h.getUint8(5),sr=h.getUint16(6,true),n=h.getUint32(8,true),blen=h.getUint32(12,true);
  const blocksize=h.getUint16(16,true),bright=h.getUint16(18,true),nb=h.getUint32(20,true);
  if(![2,3,4].includes(bits)||sr<4000||sr>96000||n>sr*3600||blocksize<20||blocksize>2048||bright>700||
     nb!==Math.ceil(n/blocksize)||24+blen+nb>bytes.length)
    throw Error('Неверные параметры LPX3');
  const base=bytes.slice(24,24+blen),levels=bytes.subarray(24+blen,24+blen+nb);
  const qs=unpackLPX3Codes(bytes.subarray(24+blen+nb),bits,n);
  const {meta:m,frames:F}=unpackLPC2(base.buffer);
  if(m.sr!==sr || m.samples!==n)throw Error('Несовпадение LPC2/LPX3');
  const decoded=F.map(decodeLpc2FrameLsf),hist=new Float64Array(10),out=new Float32Array(n);
  let prev=decoded[0]||defaultLsf(10),last=0,pos=0;
  let co=new Float64Array(11),coUntil=0;
  for(let fi=0;fi<F.length;fi++){
    const cur=decoded[fi];
    for(let sub=0;sub<8;sub++){
      const start=fi*m.H+Math.floor(sub*m.H/8), end=Math.min(n,fi*m.H+Math.floor((sub+1)*m.H/8));
      if(start>=n)break;
      const t=(sub+.5)/8;
      co=lsfToLpc(stabilizeLsf(cur.map((v,i)=>prev[i]+(v-prev[i])*t),10));
      for(let i=start;i<end;i++){
        let acc=0;
        for(let k=1;k<=10;k++)acc+=co[k]*hist[k-1];
        const b=Math.floor(i/blocksize), step=.001*Math.pow(2,(levels[b]-128)/16);
        let pre=(qs[i]-(1<<(bits-1)))*step-acc;
        pre=clamp(pre,-2,2);
        for(let k=9;k>0;k--)hist[k]=hist[k-1];hist[0]=pre;
        const x=pre+m.pre*last;last=clamp(x,-2,2);
        out[i]=clamp(x,-1,1);
      }
    }
    prev=cur;
  }
  if(bright){
    const alpha=bright/1000;let prevSample=out[0];
    for(let i=1;i<out.length;i++){
      const orig=out[i];out[i]=clamp(orig-alpha*prevSample,-1,1);
      prevSample=orig;
    }
  }
  return {pcm:out,sampleRate:sr,info:{bits, samples:n, bytes:bytes.length,brightness:bright/1000, baseBytes:blen}};
}
