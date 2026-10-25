"""Produce standalone LPX3 JavaScript decoder from the original LPC2 v2 LSF math.
Reuses the exact formant maths from our earlier implementation.
"""
from pathlib import Path
import re
P=Path(__file__).resolve().parent
source=(P/'lpc2_v2_reference.html').read_text()

def extract(name,typ='function'):
    s=source
    m=re.search(r'\b'+typ+r' '+name+r'(?:\(|\s*\{)',s)
    if not m:raise ValueError(f'not found {name}')
    st=m.start(); start=s.find('{',m.start()); level=1; i=start+1
    # These individual functions have no braces inside text literals except those in simple error messages.
    while level:
        if s[i]=='{':level+=1
        if s[i]=='}':level-=1
        i+=1
    return s[st:i]

header='''"use strict";
/* LPX3 v1: an LPC2 Voice v2 descriptor plus 2/3/4-bit voiced excitation.
 * Legacy LPC2 v2 bitstream is preserved byte for byte in the header.
 * Generated from existing LPC2 v2 formant conversion functions.
 */
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const LPC2_LSF_BITS10=[5,5,4,4,4,4,4,3,3,3], LPC2_LSF_BITS4=[5,5,4,4];
let LPC2_PITCH_MIN=65,LPC2_PITCH_MAX=850;
'''
funcs=['qLpc2Pitch','polyMul','stabilizeLsf','lpcToLsf','lsfToLpc','lsfRange','quantLsf','unquantLsf','defaultLsf','expandLsf4','unpackLPC2','decodeLpc2FrameLsf']
out=header+'\n\n'.join(extract(n) for n in funcs)+'\n'+extract('BitReader',typ='class')+'\n'
out+='''
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
'''
(P/'lpx3_decoder.js').write_text(out)
print('Saved',P/'lpx3_decoder.js',len(out.encode('utf8')))
