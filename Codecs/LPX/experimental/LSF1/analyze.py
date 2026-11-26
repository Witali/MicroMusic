"""Count exact LSF group costs against native V9 Rice, including every tag."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import struct

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]


def rice(value,k,width):
    return 8+width if value>>k>=8 else (value>>k)+1+k


def zigzag(value):
    return 2*value if value>=0 else -2*value-1


def native(vector,old,bits):
    if vector==old:
        return 1,'repeat'
    gaps=[vector[0]]+[b-a-1 for a,b in zip(vector,vector[1:])]
    gap=2+sum(rice(v,bits-4,bits) for v in gaps)
    delta=2+sum(rice(zigzag(a-b),bits-5,bits+1) for a,b in zip(vector,old)) if old is not None else 10**9
    return (delta,'delta') if delta<gap else (gap,'gap')


def group(values,signed):
    common=0
    for value in values:
        common|=abs(value)
    if not common:
        return dict(bits=3,width=0,exponent=0,length=len(values))
    e=(common&-common).bit_length()-1
    mantissas=[v>>e for v in values]
    width=(1+max((v if v>=0 else ~v).bit_length() for v in mantissas)) if signed else max(mantissas).bit_length()
    if not 1<=width<=7 or e>6:
        raise ValueError('LSF group exceeds proposed format domain')
    return dict(bits=6+len(values)*width,width=width,exponent=e,length=len(values))


def plans(values,signed):
    result=[]
    for code,size in enumerate((10,5,2)):
        groups=[group(values[i:i+size],signed) for i in range(0,10,size)]
        result.append(dict(plan=code,bits=2+sum(g['bits'] for g in groups),groups=groups))
    costs=[0]*11
    selected=[None]*10
    for begin in range(9,-1,-1):
        options=[]
        for length in range(1,11-begin):
            g=group(values[begin:begin+length],signed)
            options.append((4+g['bits']+costs[begin+length],-length,g))
        cost,_,chosen=min(options,key=lambda v:v[:2]);costs[begin]=cost;selected[begin]=chosen
    groups=[];begin=0
    while begin<10:
        g=selected[begin];groups.append(g);begin+=g['length']
    result.append(dict(plan=3,bits=2+costs[0],groups=groups))
    return result


def grouped(vector,old,bits):
    marker=(1<<bits)-9
    prefix=2+rice(marker,bits-4,bits)+1  # changed/absolute + marker + residual kind
    gaps=[vector[0]]+[b-a-1 for a,b in zip(vector,vector[1:])]
    candidates=[]
    for kind,values in ((0,gaps),(1,[a-b for a,b in zip(vector,old)] if old is not None else None)):
        if values is None:continue
        for p in plans(values,bool(kind)):
            candidates.append(dict(p,kind=kind,bits=prefix+p['bits']))
    return min(candidates,key=lambda p:(p['bits'],p['kind'],p['plan']))


def read_model(path):
    values=list(map(int,path.read_text().split()))
    if len(values)<4:raise ValueError('Missing model header')
    n,profile,pre,bright=values[:4]
    if not 1<=n<=64000 or profile not in (4,6) or not 0<=pre<=16384 or not 0<=bright<=11469:
        raise ValueError('Invalid bounded model header')
    at=4;frames=(n+319)//320
    if len(values)!=4+64*frames:raise ValueError('Invalid complete model token count')
    def rows(count,width):
        nonlocal at
        out=[values[at+i*width:at+(i+1)*width] for i in range(count)];at+=count*width;return out
    spectra=rows(frames,10);params=rows(frames*2,3);pulses=rows(frames*16,2);extras=rows(frames*8,2)
    if at!=len(values):raise ValueError('Invalid complete model length')
    alphabet=32 if profile==4 else 64
    for vector in spectra:
        if any(not 0<=v<alphabet for v in vector) or any(a>=b for a,b in zip(vector,vector[1:])):raise ValueError('Invalid ordered model spectrum')
    for scale,lag,gain in params:
        if not 0<=scale<=31 or not 18<=lag<=145 or not 0<=gain<=14 or gain&1:raise ValueError('Invalid model scale or pitch')
    for position,amplitude in pulses:
        if not 0<=position<20 or not -8<=amplitude<=(8 if profile==4 else 7):raise ValueError('Invalid model pulse')
        if profile==4:
            code=position-(position+2)//5
            if code+(code+2)//4!=position or amplitude not in (-8,8):raise ValueError('Invalid model P4 pulse')
    for position,amplitude in extras:
        if not -8<=amplitude<=7 or amplitude and not 0<=position<40:raise ValueError('Invalid extra pulse')
    return dict(n=n,profile=profile,pre=pre,bright=bright,spectra=spectra,params=params,pulses=pulses,extras=extras)


class NativeWriter:
    def __init__(self):self.output=bytearray();self.count=0
    def put(self,value,width):
        if not 0<=value<1<<width:raise ValueError('Native field does not fit')
        for bit in range(width):
            if not self.count&7:self.output.append(0)
            self.output[-1]|=((value>>bit)&1)<<(self.count&7);self.count+=1
    def rice(self,value,k,width):
        if value>>k>=8:self.put(0,8);self.put(value,width)
        else:self.put(0,value>>k);self.put(1,1);self.put(value&((1<<k)-1),k)


def serialize_native(model,flags):
    """Independent V9 reserialization, including useful bits and zero padding."""
    writer=NativeWriter();old=None;bits=5 if model['profile']==4 else 6
    for frame,vector in enumerate(model['spectra']):
        _,mode=native(vector,old,bits);writer.put(int(mode!='repeat'),1)
        if mode!='repeat':
            delta=mode=='delta';writer.put(int(delta),1)
            values=[zigzag(a-b) for a,b in zip(vector,old)] if delta else [vector[0]]+[b-a-1 for a,b in zip(vector,vector[1:])]
            for value in values:writer.rice(value,bits-4-delta,bits+delta)
        old=vector
        for half in range(2):
            base=frame*320+half*160
            if base>=model['n']:break
            scale,lag,gain=model['params'][frame*2+half];writer.put(scale,5);writer.put(gain//2,3)
            if gain:writer.put(lag-18,7)
            for group in range(4):
                at=base+group*40
                if at>=model['n']:break
                first,second=model['pulses'][at//20:at//20+2]
                if model['profile']==4:
                    for position,amplitude in (first,second):writer.put(position-(position+2)//5,4);writer.put(int(amplitude>0),1)
                else:
                    writer.put((first[0]&3)|((second[0]&3)<<2),4)
                    writer.put((first[0]>>2)+5*(second[0]>>2),5)
                    writer.put(first[1]&15,4);writer.put(second[1]&15,4)
                if flags&128:
                    position,amplitude=model['extras'][at//40];writer.put(int(amplitude!=0),1)
                    if amplitude:writer.put(position,6);writer.put(amplitude&15,4)
    return writer


def verify_native(model,blob):
    if len(blob)<13:raise ValueError('Truncated native V9 header')
    magic,flags,rate,n,pre,bright,payload=struct.unpack('<2sBHHHHH',blob[:13])
    if magic!=b'L9' or flags not in (model['profile'],model['profile']|128) or rate!=8000 or len(blob)!=13+payload:
        raise ValueError('Invalid bounded native V9 header')
    if (n,pre,bright)!=(model['n'],model['pre'],model['bright']):raise ValueError('Native/model header identity mismatch')
    if bool(flags&128)!=any(e[1] for e in model['extras']):raise ValueError('Native/model extra-pulse flag mismatch')
    encoded=serialize_native(model,flags)
    if bytes(encoded.output)!=blob[13:]:raise AssertionError('Native model reserialization differs, including padding')
    return encoded


def measure(prefix):
    model=read_model(prefix.with_suffix('.model'));blob=prefix.with_suffix('.lpx').read_bytes()
    encoded=verify_native(model,blob)
    bits=5 if model['profile']==4 else 6;old=None;native_bits=forced_bits=adaptive_bits=0
    modes=Counter();forced_plans=Counter();forced_kinds=Counter();forced_e=Counter();adaptive_e=Counter();selected=0;changed=Counter()
    for vector in model['spectra']:
        cost,mode=native(vector,old,bits);native_bits+=cost;modes[mode]+=1
        if old is not None:changed[sum(a!=b for a,b in zip(vector,old))]+=1
        if vector==old:forced_bits+=1;adaptive_bits+=1
        else:
            g=grouped(vector,old,bits);forced_bits+=g['bits'];adaptive_bits+=min(cost,g['bits'])
            forced_plans[g['plan']]+=1;forced_kinds[g['kind']]+=1
            for item in g['groups']:
                if item['width']:forced_e[item['exponent']]+=1
            if g['bits']<cost:
                selected+=1
                for item in g['groups']:
                    if item['width']:adaptive_e[item['exponent']]+=1
        old=vector
    other=encoded.count-native_bits
    if other<0 or 13+(encoded.count+7)//8!=len(blob):raise AssertionError('Native useful-bit count differs')
    return dict(name=prefix.name,bytes=len(blob),model_sha256=hashlib.sha256(prefix.with_suffix('.model').read_bytes()).hexdigest(),
        lpx_sha256=hashlib.sha256(blob).hexdigest(),frames=len(model['spectra']),native_spectral_bits=native_bits,
        forced_group_spectral_bits=forced_bits,adaptive_spectral_bits=adaptive_bits,
        forced_group_file_bytes=13+(forced_bits+other+7)//8,adaptive_file_bytes=13+(adaptive_bits+other+7)//8,
        selected_adaptive_group_packets=selected,native_modes=dict(modes),changed_indices_histogram=dict(sorted(changed.items())),
        forced_plan_histogram=dict(forced_plans),forced_kind_histogram=dict(forced_kinds),
        forced_exponent_histogram=dict(sorted(forced_e.items())),adaptive_exponent_histogram=dict(sorted(adaptive_e.items())),
        native_useful_payload_bits=encoded.count,native_reserialization_byte_exact=True)


def validation_selftest(prefix):
    text=prefix.with_suffix('.model').read_text();tokens=text.split();model=read_model(prefix.with_suffix('.model'));blob=prefix.with_suffix('.lpx').read_bytes()
    class Text:
        def __init__(self,value):self.value=value
        def read_text(self):return self.value
    invalid=[[],tokens[:-1]]
    for index,value in ((0,'0'),(1,'5'),(2,'16385'),(3,'11470'),(5,tokens[4]),(4,'-1')):
        changed=tokens.copy();changed[index]=value;invalid.append(changed)
    rejected=0
    for values in invalid:
        try:read_model(Text(' '.join(values)))
        except ValueError:rejected+=1
        else:raise AssertionError('Malformed model was accepted')
    variants=[b'',b'XX'+blob[2:],blob[:-1]]
    changed=bytearray(blob);changed[5]^=1;variants.append(bytes(changed))
    changed=bytearray(blob);changed[13]^=1;variants.append(bytes(changed))
    used=verify_native(model,blob).count
    if used%8:
        changed=bytearray(blob);changed[-1]|=1<<(used%8);variants.append(bytes(changed))
    rejected_native=0
    for changed in variants:
        try:verify_native(model,changed)
        except (ValueError,AssertionError):rejected_native+=1
        else:raise AssertionError('Mismatched native header/payload was accepted')
    return dict(invalid_models_rejected=rejected,invalid_native_files_rejected=rejected_native,
                native_payload_and_padding_byte_exact=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',type=Path,default=REPO/'build/lsf1-common/baselines')
    parser.add_argument('--output',type=Path,default=REPO/'build/lsf1-encoder/analysis.json')
    args=parser.parse_args()
    rows=[measure(args.models/f'{clip}-p{profile}') for clip in ('chego','otvechaesh','vinni','bread') for profile in (4,6)]
    totals={key:sum(row[key] for row in rows) for key in ('bytes','frames','native_spectral_bits','forced_group_spectral_bits','adaptive_spectral_bits','forced_group_file_bytes','adaptive_file_bytes','selected_adaptive_group_packets')}
    result=dict(schema='lsf1-exact-cost-analysis-v1',method='Actual current calls=4 models; native Rice competitor and complete escaped group bits, one-bit repeat retained, 13-byte header unchanged. Native reserialization matches every payload byte and final zero padding.',
                width_codes='0=zero,1..7=mantissa bits',exponent_bits=3,escape_marker='2**grid_bits-9',rows=rows,totals=totals,
                selftest=validation_selftest(args.models/'chego-p4'),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(totals,indent=2))


if __name__=='__main__':main()
