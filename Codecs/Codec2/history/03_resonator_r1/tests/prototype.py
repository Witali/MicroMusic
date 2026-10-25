import math, numpy as np, sys, wave, struct
from pathlib import Path
from codec2_test_common import fields
ROOT=Path(__file__).parents[1]
FS=8000
COEF=[min(250,round(256*math.sin(math.pi*100*i/8000))) for i in range(31)]
def sat8(v): return max(-128,min(127,int(v)))
def arshift(v,k):return v>>k

def render(frames,voiced_drive=10,noise_drive=1,leak=4):
    pos=[0]*3; vel=[0]*3; phase=0; result=[]; measures={'clips':0,'maxstate':0,'pulses':0}
    for fr in frames:
        v0,v1,p,e,ls=fields(fr)
        f0=50+(350*p)/128
        step=round(f0*65536/FS)
        k=[]; pp=0
        for j in range(6):
            d=ls[j]+1 if j not in [3,4,5] or ls[j]<8 else 2*ls[j]-6
            pp+=d
            if j%2==0:st=pp
            else:
                f=(st+pp)*12.5
                k.append(COEF[min(30,round(f/100))])
        for i in range(160):
            vv=v0 if i<80 else v1
            t=phase+step; pulse=t>65535;phase=t&65535
            if vv:
                exc=(max(0,e-8)//2+3) if pulse else 0
                measures['pulses']+=bool(pulse)
            else:
                exc=(((i*7187+phase*3353+i*i*12973)%65537)>>15)%3-1
                exc*=max(0,e-8)//5+1
            y=[]
            for j in range(3):
                v=vel[j] - ((pos[j]*k[j])>>7) - (vel[j]>>leak) + exc
                x=pos[j] + ((v*k[j])>>7)
                if abs(v)>127 or abs(x)>127:measures['clips']+=1
                vel[j]=sat8(v);pos[j]=sat8(x)
                measures['maxstate']=max(measures['maxstate'],abs(v),abs(x))
                y.append(pos[j])
            output=max(0,min(255,128+y[0]+y[1]+(y[2]>>1)))
            result.append(output)
    return np.array(result),measures
if __name__=='__main__':
  for fname in ['speech.c2zx','codec2_3200_8byte_frames.bin']:
    b=(ROOT/'tests'/fname).read_bytes();frames=[b[i:i+8] for i in range(0,len(b),8)]
    for leak in [3,4,5]:
      x,metrics=render(frames,leak=leak)
      print(fname,leak,metrics,'rms',round(np.sqrt(np.mean((x.astype(float)-128)**2)),2),'clips output',(x==0).sum()+(x==255).sum())
    x,metrics=render(frames,leak=4)
    with wave.open(str(ROOT/'audio'/f'{fname}.resonator_python.wav'),'wb') as w:
      w.setnchannels(1);w.setsampwidth(2);w.setframerate(FS);w.writeframes(struct.pack('<'+'h'*len(x),*((x.astype(np.int16)-128)*256)))
  print(COEF)
