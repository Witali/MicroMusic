// Derived from the user's Audio Codec Lab v11 experiment.
const clamp=(v,lo,hi)=>Math.min(hi,Math.max(lo,v));
const progress=()=>{}; const status=()=>{}; const tick=async()=>{};
const LPC_CHIRP=new Float64Array([0.2415,0.2415,0.2415,0.2415,-0.2760,-0.2760,-0.2760,0.2415,-0.2760,-0.2760,0.2415,0.2415,-0.2760,0.2415,-0.2760]);const LPC_K_BITS=[5,5,4,4,4,4,4,3,3,3],LPC_PITCH_MIN=55,LPC_PITCH_MAX=420;
function lpcGainQ(g){const floor=-60;if(!(g>10**(floor/20)))return 0;const db=clamp(20*Math.log10(g),floor,0);return 1+Math.round((db-floor)/-floor*30)}
function qLpcGain(q){if(!q)return 0;return 10**((-60+(q-1)/30*60)/20)}
function lpcPitchQ(period,sr){const f=clamp(sr/period,LPC_PITCH_MIN,LPC_PITCH_MAX);return clamp(Math.round(Math.log(f/LPC_PITCH_MIN)/Math.log(LPC_PITCH_MAX/LPC_PITCH_MIN)*127),0,127)}
function qLpcPitch(q,sr){const f=LPC_PITCH_MIN*(LPC_PITCH_MAX/LPC_PITCH_MIN)**(q/127);return sr/f}
function quantReflection(k,bits){const n=(1<<bits)-1;return clamp(Math.round((clamp(k,-.98,.98)+.98)/1.96*n),0,n)}
function unquantReflection(q,bits){const n=(1<<bits)-1;return q/n*1.96-.98}
function levinsonDurbin(r,order){
  let a=new Float64Array(order+1);a[0]=1;const k=new Float64Array(order);let err=Math.max(r[0],1e-10);
  for(let m=1;m<=order;m++){
    let acc=r[m];for(let j=1;j<m;j++)acc+=a[j]*r[m-j];
    const km=clamp(-acc/Math.max(err,1e-12),-.98,.98),next=new Float64Array(order+1);next[0]=1;
    for(let j=1;j<m;j++)next[j]=a[j]+km*a[m-j];next[m]=km;a=next;k[m-1]=km;err*=Math.max(1e-4,1-km*km);
  }
  return{k,error:Math.max(err,1e-12)};
}
function estimatePitch(x,start,H,sr,threshold){
  const from=Math.max(0,start-(H>>1)),len=Math.min(x.length-from,Math.max(H*2,Math.round(sr*.04)));
  if(len<Math.round(sr*.012))return{voiced:false,period:0,corr:0};
  let mean=0;for(let i=0;i<len;i++)mean+=x[from+i];mean/=len;let peak=0;const y=new Float64Array(len);
  for(let i=0;i<len;i++){y[i]=x[from+i]-mean;peak=Math.max(peak,Math.abs(y[i]))}
  if(peak<1e-4)return{voiced:false,period:0,corr:0};const clip=peak*.28;
  for(let i=0;i<len;i++){const v=y[i];y[i]=v>clip?v-clip:v<-clip?v+clip:0}
  const lo=Math.max(2,Math.floor(sr/LPC_PITCH_MAX)),hi=Math.min(len-8,Math.ceil(sr/LPC_PITCH_MIN));let best=0,bestLag=0;
  for(let lag=lo;lag<=hi;lag++){
    let c=0,e0=0,e1=0;for(let i=lag;i<len;i++){const a=y[i],b=y[i-lag];c+=a*b;e0+=a*a;e1+=b*b}
    const q=c/Math.sqrt(Math.max(1e-12,e0*e1));if(q>best){best=q;bestLag=lag}
  }
  return{voiced:best>=threshold,period:bestLag,corr:best};
}
async function encodeLPC(x,sr,c){
  const order=10,H=Math.max(order+4,Math.round(sr*c.frameMs/1000)),F=Math.ceil(x.length/H),pre=new Float32Array(x.length);let prev=0;
  for(let i=0;i<x.length;i++){const v=x[i];pre[i]=v-c.pre*prev;prev=v}
  const frames=[],window=new Float64Array(H);for(let i=0;i<H;i++)window[i]=.54-.46*Math.cos(2*Math.PI*i/Math.max(1,H-1));let previous=null,voicedCount=0,repeatCount=0,silenceCount=0,pitchSum=0;
  for(let f=0;f<F;f++){
    const st=f*H,buf=new Float64Array(H);let mean=0;for(let i=0;i<H;i++)mean+=pre[st+i]||0;mean/=H;
    for(let i=0;i<H;i++)buf[i]=((pre[st+i]||0)-mean)*window[i];
    const r=new Float64Array(order+1);for(let lag=0;lag<=order;lag++){let z=0;for(let i=lag;i<H;i++)z+=buf[i]*buf[i-lag];r[lag]=z}
    const ld=levinsonDurbin(r,order),gain=Math.sqrt(ld.error/H),energy=lpcGainQ(gain),pitch=estimatePitch(x,st,H,sr,c.voicing);
    let voiced=energy>0&&pitch.voiced,pitchCode=voiced?lpcPitchQ(pitch.period,sr):0,kq=LPC_K_BITS.map((bits,i)=>quantReflection(i<(voiced?10:4)?ld.k[i]:0,bits)),repeat=false;
    if(!energy){voiced=false;pitchCode=0;kq=LPC_K_BITS.map((bits,i)=>quantReflection(0,bits));silenceCount++}
    if(previous&&energy&&previous.energy&&previous.voiced===voiced){const count=voiced?10:4;let d=0;for(let i=0;i<count;i++)d+=Math.abs(kq[i]-previous.kq[i])/((1<<LPC_K_BITS[i])-1);d/=count;if(d<=c.repeat){repeat=true;kq=previous.kq.slice();repeatCount++}}
    const frame={energy,voiced,pitch:pitchCode,repeat,kq};frames.push(frame);previous=frame;
    if(voiced){voicedCount++;pitchSum+=sr/qLpcPitch(pitchCode,sr)}
    if(!(f&31)){progress(f/F*.78);status(`LPC-анализ: ${f+1} / ${F}`);await tick()}
  }
  return{meta:{codec:"lpc1",ver:1,sr,H,order,samples:x.length,frameCount:F,pre:c.pre,voicing:c.voicing},frames,analysis:{voicedCount,repeatCount,silenceCount,avgPitch:voicedCount?pitchSum/voicedCount:0}};
}

const LPC2_LSF_BITS10=[5,5,4,4,4,4,4,3,3,3],LPC2_LSF_BITS4=[5,5,4,4],LPC2_PITCH_MIN=55,LPC2_PITCH_MAX=420;
function lpc2PitchQ(period,sr){const f=clamp(sr/period,LPC2_PITCH_MIN,LPC2_PITCH_MAX);return clamp(Math.round(Math.log(f/LPC2_PITCH_MIN)/Math.log(LPC2_PITCH_MAX/LPC2_PITCH_MIN)*63),0,63)}
function qLpc2Pitch(q,sr){const f=LPC2_PITCH_MIN*(LPC2_PITCH_MAX/LPC2_PITCH_MIN)**(q/63);return sr/f}
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
function pitchCandidateSet(x,center,W,sr){
  const len=Math.max(W,Math.round(sr*.042)),from=Math.max(0,Math.round(center-len/2)),n=Math.min(len,x.length-from);
  if(n<Math.round(sr*.014))return{candidates:[],maxCorr:0,zcr:0};
  let mean=0;for(let i=0;i<n;i++)mean+=x[from+i];mean/=n;
  const y=new Float64Array(n);let peak=0,zcr=0,last=0;
  for(let i=0;i<n;i++){const v=x[from+i]-mean;y[i]=v;peak=Math.max(peak,Math.abs(v));if(i&&((v>=0)!==(last>=0)))zcr++;last=v}
  if(peak<1e-5)return{candidates:[],maxCorr:0,zcr:zcr/n};
  const clip=peak*.25;for(let i=0;i<n;i++){const v=y[i];y[i]=v>clip?v-clip:v<-clip?v+clip:0}
  const lo=Math.max(2,Math.floor(sr/LPC2_PITCH_MAX)),hi=Math.min(n-8,Math.ceil(sr/LPC2_PITCH_MIN)),corr=new Float64Array(hi+1);
  for(let lag=lo;lag<=hi;lag++){let c=0,e0=0,e1=0;for(let i=lag;i<n;i++){const a=y[i],b=y[i-lag];c+=a*b;e0+=a*a;e1+=b*b}corr[lag]=c/Math.sqrt(Math.max(1e-12,e0*e1))}
  const peaks=[];for(let lag=lo+1;lag<hi;lag++)if(corr[lag]>=corr[lag-1]&&corr[lag]>=corr[lag+1]){const den=corr[lag-1]-2*corr[lag]+corr[lag+1],d=den?clamp(.5*(corr[lag-1]-corr[lag+1])/den,-.5,.5):0;peaks.push({period:lag+d,corr:corr[lag]})}
  peaks.sort((a,b)=>b.corr-a.corr);const out=[];for(const p of peaks){if(out.some(q=>Math.abs(Math.log2(p.period/q.period))<.035))continue;out.push(p);if(out.length===5)break}
  return{candidates:out,maxCorr:out.length?out[0].corr:0,zcr:zcr/n}
}
function trackPitchViterbi(records,threshold,smooth){
  const back=[],costs=[];
  for(let f=0;f<records.length;f++){
    const r=records[f],states=[{period:0,corr:0},...r.pitch.candidates],cur=new Float64Array(states.length),bp=new Int16Array(states.length);
    for(let j=0;j<states.length;j++){
      const s=states[j],em=s.period?Math.max(0,threshold-s.corr)*7-s.corr*1.2:Math.max(0,r.pitch.maxCorr-threshold)*5;
      if(f===0){cur[j]=em;bp[j]=-1;continue}
      const prevStates=back[f-1].states,pc=costs[f-1];let best=Infinity,bi=0;
      for(let k=0;k<prevStates.length;k++){
        const p=prevStates[k];let tr=0;
        if(!p.period&&!s.period)tr=0;
        else if(!p.period||!s.period)tr=.55+smooth*.35;
        else{const jump=Math.abs(Math.log2((r.sr/s.period)/(r.sr/p.period)));tr=smooth*(2.4*jump+(jump>.55?3:0))}
        const z=pc[k]+tr;if(z<best){best=z;bi=k}
      }
      cur[j]=best+em;bp[j]=bi
    }
    back.push({states,bp});costs.push(cur)
  }
  if(!records.length)return[];
  let idx=0,last=costs[costs.length-1];for(let i=1;i<last.length;i++)if(last[i]<last[idx])idx=i;
  const path=new Array(records.length);for(let f=records.length-1;f>=0;f--){path[f]=back[f].states[idx];idx=back[f].bp[idx]}
  return path
}
function analyzeLpcWindow(pre,start,W,order){
  const buf=new Float64Array(W);let mean=0;for(let i=0;i<W;i++)mean+=pre[start+i]||0;mean/=W;
  for(let i=0;i<W;i++){const w=.54-.46*Math.cos(2*Math.PI*i/Math.max(1,W-1));buf[i]=((pre[start+i]||0)-mean)*w}
  const r=new Float64Array(order+1);for(let lag=0;lag<=order;lag++){let z=0;for(let i=lag;i<W;i++)z+=buf[i]*buf[i-lag];r[lag]=z}
  return levinsonDurbin(r,order)
}
async function encodeLPC2(x,sr,c){
  const H=Math.max(16,Math.round(sr*c.frameMs/1000)),W=Math.max(H,Math.round(sr*c.windowMs/1000)),F=Math.ceil(x.length/H),pre=new Float32Array(x.length);
  let pv=0;for(let i=0;i<x.length;i++){pre[i]=x[i]-c.pre*pv;pv=x[i]}
  const rec=[];
  for(let f=0;f<F;f++){
    const center=f*H+H/2,start=Math.round(center-W/2),ld10=analyzeLpcWindow(pre,start,W,10),ld4=analyzeLpcWindow(pre,start,W,4),gain=Math.sqrt(ld10.error/W),energy=lpcGainQ(gain),a10=reflectionToLpc(ld10.k),a4=reflectionToLpc(ld4.k),lsf10=lpcToLsf(a10)||defaultLsf(10),lsf4=lpcToLsf(a4)||defaultLsf(4),pitch=pitchCandidateSet(x,center,W,sr);
    rec.push({sr,energy,gain,lsf10,lsf4,pitch});
    if(!(f&15)){progress(f/F*.55);status(`LPC2: LSF и кандидаты F0 ${f+1} / ${F}`);await tick()}
  }
  const path=trackPitchViterbi(rec,c.voicing,c.pitchSmooth),frames=[];let previous=null,voicedCount=0,mixedCount=0,transientCount=0,repeatCount=0,silenceCount=0,pitchSum=0,prevGain=0;
  for(let f=0;f<F;f++){
    const r=rec[f],sel=path[f],rise=20*Math.log10((r.gain+1e-8)/(prevGain+1e-8));let mode=0;
    if(!r.energy){mode=0;silenceCount++}
    else if(sel&&sel.period){mode=sel.corr>=c.voicing+.15?2:1}
    else if(rise>6||r.pitch.zcr>.24)mode=3;
    const voiced=mode===1||mode===2,pitch=voiced?lpc2PitchQ(sel.period,sr):0,bits=voiced?LPC2_LSF_BITS10:LPC2_LSF_BITS4,lsf=voiced?r.lsf10:r.lsf4;
    let lsfq=quantLsf(lsf,bits),repeat=false;
    if(previous&&r.energy&&previous.energy&&((previous.mode===1||previous.mode===2)===voiced)){
      let d=0;for(let i=0;i<lsfq.length;i++)d+=Math.abs(lsfq[i]-previous.lsfq[i])/((1<<bits[i])-1);d/=lsfq.length;
      if(d<=c.repeat){repeat=true;lsfq=previous.lsfq.slice();repeatCount++}
    }
    const frame={energy:r.energy,mode,pitch,repeat,lsfq};frames.push(frame);previous=frame;prevGain=r.gain;
    if(mode===2)voicedCount++;if(mode===1)mixedCount++;if(mode===3)transientCount++;if(voiced)pitchSum+=sr/qLpc2Pitch(pitch,sr);
    if(!(f&31)){progress(.56+f/F*.20);status(`LPC2: выбор режимов ${f+1} / ${F}`);await tick()}
  }
  return{meta:{codec:"lpc2",ver:1,sr,H,W,order:10,samples:x.length,frameCount:F,pre:c.pre,voicing:c.voicing},frames,analysis:{voicedCount,mixedCount,transientCount,repeatCount,silenceCount,avgPitch:(voicedCount+mixedCount)?pitchSum/(voicedCount+mixedCount):0}}
}
function packLPC2(m,F,analysis=null){
  const bw=new BitWriter();
  for(const f of F){
    bw.write(f.energy,5);if(!f.energy)continue;bw.write(f.mode,2);bw.write(f.repeat?1:0,1);
    const voiced=f.mode===1||f.mode===2;if(voiced)bw.write(f.pitch,6);
    if(!f.repeat){const bits=voiced?LPC2_LSF_BITS10:LPC2_LSF_BITS4;for(let i=0;i<bits.length;i++)bw.write(f.lsfq[i],bits[i])}
  }
  const payload=bw.finish(),b=new ArrayBuffer(36+payload.length),v=new DataView(b);
  for(let i=0;i<4;i++)v.setUint8(i,"LPC2".charCodeAt(i));v.setUint8(4,1);v.setUint8(5,m.order);v.setUint16(6,m.sr,true);v.setUint16(8,m.H,true);v.setUint16(10,m.W,true);v.setUint32(12,F.length,true);v.setUint32(16,m.samples,true);v.setUint32(20,bw.total,true);v.setFloat32(24,m.pre,true);v.setFloat32(28,m.voicing,true);v.setUint32(32,0,true);new Uint8Array(b,36).set(payload);
  const A=analysis||{};
  return{buffer:b,stats:{version:1,codec:"lpc2",frames:F.length,payloadBits:bw.total,payloadBytes:payload.length,voiced:A.voicedCount??F.filter(x=>x.mode===2).length,mixed:A.mixedCount??F.filter(x=>x.mode===1).length,transient:A.transientCount??F.filter(x=>x.mode===3).length,repeatFrames:A.repeatCount??F.filter(x=>x.repeat).length,silence:A.silenceCount??F.filter(x=>!x.energy).length,avgPitch:A.avgPitch||0,actualBytes:b.byteLength}}
}
function unpackLPC2(b){
  const v=new DataView(b);if(b.byteLength<36||String.fromCharCode(v.getUint8(0),v.getUint8(1),v.getUint8(2),v.getUint8(3))!=="LPC2"||v.getUint8(4)!==1)throw Error("Это не поддерживаемый поток LPC2");
  const m={codec:"lpc2",ver:1,order:v.getUint8(5),sr:v.getUint16(6,true),H:v.getUint16(8,true),W:v.getUint16(10,true),frameCount:v.getUint32(12,true),samples:v.getUint32(16,true),payloadBits:v.getUint32(20,true),pre:v.getFloat32(24,true),voicing:v.getFloat32(28,true)};
  if(m.order!==10||36+Math.ceil(m.payloadBits/8)>b.byteLength)throw Error("Повреждён или не поддерживается LPC2");
  const br=new BitReader(v,36,m.payloadBits),frames=[];let previous=null,voiced=0,mixed=0,transient=0,repeats=0,silence=0,pitchSum=0;
  for(let n=0;n<m.frameCount;n++){
    const energy=br.read(5);
    if(!energy){const f={energy:0,mode:0,pitch:0,repeat:false,lsfq:quantLsf(defaultLsf(4),LPC2_LSF_BITS4)};frames.push(f);previous=f;silence++;continue}
    const mode=br.read(2),repeat=!!br.read(1),isVoiced=mode===1||mode===2,pitch=isVoiced?br.read(6):0,bits=isVoiced?LPC2_LSF_BITS10:LPC2_LSF_BITS4;let lsfq;
    if(repeat){if(!previous||((previous.mode===1||previous.mode===2)!==isVoiced))throw Error("Некорректный повтор LSF");lsfq=previous.lsfq.slice();repeats++}
    else{lsfq=[];for(let i=0;i<bits.length;i++)lsfq.push(br.read(bits[i]))}
    const f={energy,mode,pitch,repeat,lsfq};frames.push(f);previous=f;if(mode===2)voiced++;if(mode===1)mixed++;if(mode===3)transient++;if(isVoiced)pitchSum+=m.sr/qLpc2Pitch(pitch,m.sr)
  }
  return{meta:m,frames,stats:{version:1,codec:"lpc2",frames:m.frameCount,payloadBits:m.payloadBits,payloadBytes:Math.ceil(m.payloadBits/8),voiced,mixed,transient,repeatFrames:repeats,silence,avgPitch:(voiced+mixed)?pitchSum/(voiced+mixed):0,actualBytes:b.byteLength}}
}
function decodeLpc2FrameLsf(f){const voiced=f.mode===1||f.mode===2;if(voiced)return unquantLsf(f.lsfq,LPC2_LSF_BITS10);return expandLsf4(unquantLsf(f.lsfq,LPC2_LSF_BITS4))}
async function synthLPC2(m,F,postStrength=.35){
  const out=new Float32Array(m.samples),hist=new Float64Array(10),pfIn=new Float64Array(10),pfOut=new Float64Array(10),subCount=8;
  let seed=0x51f15e3d,de=0,pitchCounter=0,chirpIndex=LPC_CHIRP.length,noisePrev=0;
  const decoded=F.map(decodeLpc2FrameLsf),first=F[0]||{energy:0,mode:0,pitch:0};
  let prevLsf=decoded[0]||defaultLsf(10),prevGain=qLpcGain(first.energy),prevPitch=(first.mode===1||first.mode===2)?qLpc2Pitch(first.pitch,m.sr):m.sr/120,prevMode=first.mode||0;
  for(let fi=0;fi<F.length;fi++){
    const cur=F[fi],curLsf=decoded[fi],curGain=qLpcGain(cur.energy),isPitch=cur.mode===1||cur.mode===2,curPitch=isPitch?qLpc2Pitch(cur.pitch,m.sr):prevPitch,frameStart=fi*m.H;
    for(let sub=0;sub<subCount;sub++){
      const s0=Math.floor(sub*m.H/subCount),s1=Math.floor((sub+1)*m.H/subCount),t0=(sub+.5)/subCount,t=cur.mode===3&&curGain>prevGain?Math.min(1,t0*2):t0;
      const lsf=stabilizeLsf(curLsf.map((v,i)=>prevLsf[i]+(v-prevLsf[i])*t),10),a=lsfToLpc(lsf),lg0=Math.log(prevGain+1e-8),lg1=Math.log(curGain+1e-8),gain=Math.exp(lg0+(lg1-lg0)*t),period=Math.max(2,prevPitch+(curPitch-prevPitch)*t),mode=t<.5?prevMode:cur.mode,sf=clamp(postStrength,0,.7),gn=.96-.38*sf,gd=.985-.20*sf,bn=new Float64Array(11),bd=new Float64Array(11);
      for(let i=1;i<=10;i++){bn[i]=a[i]*gn**i;bd[i]=a[i]*gd**i}
      for(let s=s0;s<s1;s++){
        const pos=frameStart+s;if(pos>=out.length)break;
        seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;
        const noise=(((seed>>>0)/4294967296)*2-1)*Math.sqrt(3),hpNoise=noise-.82*noisePrev;noisePrev=noise;
        if(pitchCounter<=0){pitchCounter+=period;chirpIndex=0}pitchCounter--;
        const pulse=chirpIndex<LPC_CHIRP.length?LPC_CHIRP[chirpIndex++]*Math.sqrt(period):0;
        let src;if(mode===2)src=.94*pulse+.12*noise;else if(mode===1)src=.58*pulse+.62*hpNoise;else if(mode===3){const edge=1-s/Math.max(1,m.H);src=hpNoise*(1+.8*edge)}else src=noise;
        const excitation=gain*src;let y=excitation;for(let i=1;i<=10;i++)y-=a[i]*hist[i-1];y=clamp(y,-8,8);for(let i=9;i>0;i--)hist[i]=hist[i-1];hist[0]=y;
        let z=y;if(sf>0){for(let i=1;i<=10;i++)z+=bn[i]*pfIn[i-1]-bd[i]*pfOut[i-1];z=clamp(z,-8,8);for(let i=9;i>0;i--){pfIn[i]=pfIn[i-1];pfOut[i]=pfOut[i-1]}pfIn[0]=y;pfOut[0]=z}
        const d=clamp(z+m.pre*de,-8,8);de=d;out[pos]=d
      }
    }
    prevLsf=curLsf;prevGain=curGain;prevPitch=curPitch;prevMode=cur.mode;
    if(!(fi&63)){progress(.78+.20*fi/Math.max(1,F.length));status(`LPC2-синтез: ${fi+1} / ${F.length}`);await tick()}
  }
  return out
}
class BitWriter{constructor(){this.a=[];this.acc=0;this.n=0;this.total=0}write(v,b){for(let i=0;i<b;i++){this.acc|=((v>>>i)&1)<<this.n;if(++this.n===8){this.a.push(this.acc);this.acc=0;this.n=0}this.total++}}finish(){if(this.n)this.a.push(this.acc);return new Uint8Array(this.a)}}
class BitReader{constructor(v,o,bits){this.v=v;this.o=o;this.bit=0;this.left=bits}read(n){if(this.left<n)throw Error("Обрезан LPC-битовый поток");let q=0;for(let i=0;i<n;i++){q|=((this.v.getUint8(this.o+(this.bit>>3))>>(this.bit&7))&1)<<i;this.bit++;this.left--}return q}}
function packLPC(m,F,analysis=null){
  const bw=new BitWriter();for(const f of F){bw.write(f.energy,5);if(!f.energy)continue;bw.write(f.voiced?1:0,1);bw.write(f.repeat?1:0,1);if(f.voiced)bw.write(f.pitch,7);if(!f.repeat){const count=f.voiced?10:4;for(let i=0;i<count;i++)bw.write(f.kq[i],LPC_K_BITS[i])}}
  const payload=bw.finish(),b=new ArrayBuffer(32+payload.length),v=new DataView(b);for(let i=0;i<4;i++)v.setUint8(i,"LPC1".charCodeAt(i));v.setUint8(4,1);v.setUint8(5,0);v.setUint16(6,m.sr,true);v.setUint16(8,m.H,true);v.setUint8(10,m.order);v.setUint8(11,0);v.setUint32(12,F.length,true);v.setUint32(16,m.samples,true);v.setUint32(20,bw.total,true);v.setFloat32(24,m.pre,true);v.setFloat32(28,m.voicing,true);new Uint8Array(b,32).set(payload);
  const voiced=analysis?analysis.voicedCount:F.filter(x=>x.voiced).length,repeats=analysis?analysis.repeatCount:F.filter(x=>x.repeat).length,silence=analysis?analysis.silenceCount:F.filter(x=>!x.energy).length;
  return{buffer:b,stats:{version:1,codec:"lpc1",frames:F.length,payloadBits:bw.total,payloadBytes:payload.length,voiced,repeatFrames:repeats,silence,avgPitch:analysis?analysis.avgPitch:0,actualBytes:b.byteLength}};
}
function unpackLPC(b){
  const v=new DataView(b);if(b.byteLength<32||String.fromCharCode(v.getUint8(0),v.getUint8(1),v.getUint8(2),v.getUint8(3))!=="LPC1"||v.getUint8(4)!==1)throw Error("Это не поддерживаемый поток LPC1");
  const m={codec:"lpc1",ver:1,sr:v.getUint16(6,true),H:v.getUint16(8,true),order:v.getUint8(10),frameCount:v.getUint32(12,true),samples:v.getUint32(16,true),payloadBits:v.getUint32(20,true),pre:v.getFloat32(24,true),voicing:v.getFloat32(28,true)};
  if(m.order!==10||32+Math.ceil(m.payloadBits/8)>b.byteLength)throw Error("Повреждён или не поддерживается LPC1");const br=new BitReader(v,32,m.payloadBits),frames=[];let previous=null,voiced=0,repeats=0,silence=0,pitchSum=0;
  for(let n=0;n<m.frameCount;n++){
    const energy=br.read(5);if(!energy){const kq=LPC_K_BITS.map((bits,i)=>quantReflection(0,bits)),f={energy:0,voiced:false,pitch:0,repeat:false,kq};frames.push(f);previous=f;silence++;continue}
    const isVoiced=!!br.read(1),repeat=!!br.read(1),pitch=isVoiced?br.read(7):0;let kq;
    if(repeat){if(!previous||previous.voiced!==isVoiced)throw Error("Некорректный повтор LPC-коэффициентов");kq=previous.kq.slice();repeats++}else{kq=LPC_K_BITS.map((bits,i)=>quantReflection(0,bits));const count=isVoiced?10:4;for(let i=0;i<count;i++)kq[i]=br.read(LPC_K_BITS[i])}
    const f={energy,voiced:isVoiced,pitch,repeat,kq};frames.push(f);previous=f;if(isVoiced){voiced++;pitchSum+=m.sr/qLpcPitch(pitch,m.sr)}
  }
  return{meta:m,frames,stats:{version:1,codec:"lpc1",frames:m.frameCount,payloadBits:m.payloadBits,payloadBytes:Math.ceil(m.payloadBits/8),voiced,repeatFrames:repeats,silence,avgPitch:voiced?pitchSum/voiced:0,actualBytes:b.byteLength}};
}
function reflectionToLpc(k){let a=new Float64Array(1);a[0]=1;for(let m=1;m<=k.length;m++){const next=new Float64Array(m+1);next[0]=1;next[m]=k[m-1];for(let i=1;i<m;i++)next[i]=a[i]+k[m-1]*a[m-i];a=next}return a}
async function synthLPC(m,F){
  const out=new Float32Array(m.samples),hist=new Float64Array(10),subCount=8;let seed=0x6d2b79f5,de=0,pitchCounter=0,chirpIndex=LPC_CHIRP.length,previous=F[0]||{energy:0,voiced:false,pitch:0,kq:LPC_K_BITS.map((b,i)=>quantReflection(0,b))};
  const decodeK=f=>f.kq.map((q,i)=>unquantReflection(q,LPC_K_BITS[i]));let prevK=decodeK(previous),prevGain=qLpcGain(previous.energy),prevPitch=previous.voiced?qLpcPitch(previous.pitch,m.sr):m.sr/120,prevVoice=previous.voiced?1:0;
  for(let fi=0;fi<F.length;fi++){
    const cur=F[fi],curK=decodeK(cur),curGain=qLpcGain(cur.energy),curPitch=cur.voiced?qLpcPitch(cur.pitch,m.sr):prevPitch,curVoice=cur.voiced?1:0,frameStart=fi*m.H;
    for(let sub=0;sub<subCount;sub++){
      const s0=Math.floor(sub*m.H/subCount),s1=Math.floor((sub+1)*m.H/subCount),t=(sub+.5)/subCount,k=curK.map((v,i)=>prevK[i]+(v-prevK[i])*t),a=reflectionToLpc(k),gain=prevGain+(curGain-prevGain)*t,period=Math.max(2,prevPitch+(curPitch-prevPitch)*t),voice=clamp(prevVoice+(curVoice-prevVoice)*t,0,1);
      for(let s=s0;s<s1;s++){
        const pos=frameStart+s;if(pos>=out.length)break;seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;const noise=(((seed>>>0)/4294967296)*2-1)*Math.sqrt(3);if(pitchCounter<=0){pitchCounter+=period;chirpIndex=0}pitchCounter--;const pulse=chirpIndex<LPC_CHIRP.length?LPC_CHIRP[chirpIndex++]*Math.sqrt(period):0;
        const excitation=gain*(voice*pulse+(1-voice)*noise),y0=excitation;let y=y0;for(let i=1;i<=10;i++)y-=a[i]*hist[i-1];y=clamp(y,-6,6);for(let i=9;i>0;i--)hist[i]=hist[i-1];hist[0]=y;const z=clamp(y+m.pre*de,-6,6);de=z;out[pos]=z;
      }
    }
    previous=cur;prevK=curK;prevGain=curGain;prevPitch=curPitch;prevVoice=curVoice;if(!(fi&63)){progress(.80+.18*fi/Math.max(1,F.length));status(`LPC-синтез: ${fi+1} / ${F.length}`);await tick()}
  }
  return out;
}

