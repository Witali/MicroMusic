"""Frozen experimental LPX v9 Rice0 transcoder (stdlib only).

Provenance: tools/speech_v9.py at95346ea9. The parser duplication is
intentional: production source bindings and default tooling remain frozen.
This module can read/propose v9 flag64; current production firmware has NOT
admitted that extension. Its separate experimental reader still requires
Flash, timing, IRQ, stack and exact-output validation before adoption.

Opt-in optimization keeps every recording parameter/sample exact and sets64
only for a strictly smaller complete six-bit-profile file. Legacy5/8 output
clears64; P4's original delta-k0 syntax is unchanged.
"""
import argparse
from pathlib import Path
import struct


class Bits:
    def __init__(self, data=b''):
        self.data=data
        self.at=0
        self.output=bytearray()

    def get(self, count):
        if self.at+count>len(self.data)*8:
            raise ValueError('Truncated LPX packet')
        value=0
        for bit in range(count):
            value|=((self.data[self.at>>3]>>(self.at&7))&1)<<bit
            self.at+=1
        return value

    def put(self, value, count):
        for bit in range(count):
            if not self.at&7:self.output.append(0)
            self.output[-1]|=((value>>bit)&1)<<(self.at&7)
            self.at+=1


def pulse_pair(first, second):
    if not (0<=first<20 and 0<=second<20):
        raise ValueError('Invalid pulse positions')
    return (first&3)|((second&3)<<2)|(((first>>2)+5*(second>>2))<<4)


def pulse_positions(code):
    high=code>>4
    if not (0<=code<512 and high<25):
        raise ValueError('Invalid pulse pair')
    return (code&3)+4*(high%5),((code>>2)&3)+4*(high//5)


def _put_rice(writer,value,k,width):
    high=value>>k
    if high>=8:writer.put(0,8);writer.put(value,width)
    else:writer.put(0,high);writer.put(1,1);writer.put(value&((1<<k)-1),k)


def _put_spectrum(writer,vector,old,bits,delta_k0):
    if vector==old:writer.put(0,1);return
    choices=[]
    for delta in (False,True):
        if delta and old is None:continue
        values=([2*(a-b) if a>=b else -2*(a-b)-1 for a,b in zip(vector,old)] if delta else
                [vector[0]]+[b-a-1 for a,b in zip(vector,vector[1:])])
        k=(0 if delta_k0 else bits-5) if delta else bits-4
        trial=Bits()
        for value in values:_put_rice(trial,value,k,bits+int(delta))
        choices.append((trial.at,delta,values,k))
    _,delta,values,k=min(choices,key=lambda choice:(choice[0],choice[1]))
    writer.put(1,1);writer.put(int(delta),1)
    for value in values:_put_rice(writer,value,k,bits+int(delta))


def _repack(blob,version,*,force_delta_k0=None,canonical_spectra=False):
    if version not in (5,8,9) or len(blob)<13:
        raise ValueError('Expected LPX v5, v8 or v9')
    source=9 if blob[:2]==b'L9' else blob[4] if blob[:4]==b'L4HY' and blob[4] in (5,8) else 0
    if source in (5,8) and len(blob)>=22:
        _,_,flags,rate,n,pre,bright,frame,block,payload=struct.unpack('<4sBBHIHHHHH',blob[:22])
        if (frame,block)!=(320,320 if source==8 else 160):raise ValueError('Invalid packet geometry')
        header=22
    elif source==9:
        _,flags,rate,n,pre,bright,payload=struct.unpack('<2sBHHHHH',blob[:13])
        header=13
    else:raise ValueError('Expected LPX v5, v8 or v9')
    base_flags=flags&~64 if source==9 else flags
    sparse80=base_flags==15
    legal=sparse80 if source==8 else (base_flags&127) in (4,6) or (source==9 and sparse80)
    if not legal or rate!=8000:
        raise ValueError('Unsupported LPX profile or sample rate')
    if not 1<=n<=64000 or pre>16384 or bright>11469:
        raise ValueError('Invalid LPX metadata')
    if len(blob)>65535 or len(blob)!=header+payload:
        raise ValueError('Invalid bounded payload length')
    if sparse80 and version==5 or not sparse80 and version==8:
        raise ValueError('Sparse80 uses legacy version8; P4/P6 use legacy version5')
    r=Bits(blob[header:]);w=Bits()
    bits=5 if base_flags&127==4 else 6
    input_delta_k0=source==9 and bool(flags&64)
    output_delta_k0=(input_delta_k0 if force_delta_k0 is None else force_delta_k0) if version==9 else False
    output_flags=(flags if source==9 and version==9 else base_flags)
    if version==9 and force_delta_k0 is not None:
        output_flags=base_flags|(64 if force_delta_k0 and bits==6 else 0)
    # P4 already uses delta-k0. A redundant input flag is accepted/preserved,
    # but newly optimized files never add that flag to a P4 stream.
    rewrite_spectra=canonical_spectra or bits==6 and input_delta_k0!=output_delta_k0
    old=None

    def copy(count):
        value=r.get(count);w.put(value,count);return value

    def spectral_get(count):
        return r.get(count) if rewrite_spectra else copy(count)

    def rice(k,width):
        high=0
        while high<8 and not spectral_get(1):high+=1
        return spectral_get(width) if high==8 else (high<<k)|spectral_get(k)

    for fi in range((n+319)//320):
        if spectral_get(1):
            delta=spectral_get(1)
            if delta and old is None:raise ValueError('Initial delta spectrum')
            vec=[]
            for i in range(10):
                k=0 if delta and input_delta_k0 else bits-4-delta
                z=rice(k,bits+delta)
                value=(old[i]+(z//2 if not z&1 else -(z//2)-1)) if delta else ((vec[-1]+1 if vec else 0)+z)
                if not 0<=value<(1<<bits) or vec and value<=vec[-1]:
                    raise ValueError('Invalid spectrum')
                vec.append(value)
        else:
            if old is None:raise ValueError('Initial repeated spectrum')
            vec=old
        if rewrite_spectra:_put_spectrum(w,vec,old,bits,output_delta_k0)
        old=vec
        if sparse80:
            scale=r.get(5)
            if source==8:lag,gain=r.get(7)+18,r.get(3)
            else:
                gain=r.get(3);lag=r.get(7)+18 if gain else 18
            w.put(scale,5)
            if version==8:w.put(lag-18,7);w.put(gain,3)
            else:
                w.put(gain,3)
                if gain:w.put(lag-18,7)
            for group in range(4):
                offset=fi*320+group*80
                raw=r.get(7) if source==8 or offset<n else 0
                if version==8 or offset<n:w.put(raw,7)
            continue
        for half in range(2):
            offset=fi*320+half*160
            stored=source==5 or offset<n
            emitted=version==5 or offset<n
            if stored:
                scale=r.get(5)
                if source==5:lag,gain=r.get(7)+18,r.get(3)
                else:
                    gain=r.get(3);lag=r.get(7)+18 if gain else 18
            else:scale,lag,gain=0,18,0
            if emitted:
                w.put(scale,5)
                if version==5:w.put(lag-18,7);w.put(gain,3)
                else:
                    w.put(gain,3)
                    if gain:w.put(lag-18,7)
            for si in range(4):
                present=source==5 or offset+si*40<n
                emit=version==5 or offset+si*40<n
                if bits==5:
                    raw=r.get(10) if present else 0
                    if emit:w.put(raw,10)
                else:
                    first=second=amps=0
                    if present:
                        code=r.get(9)
                        if source==5:
                            if code>=400:raise ValueError('Invalid pulse pair')
                            first,second=code%20,code//20
                        else:first,second=pulse_positions(code)
                        amps=r.get(8)
                    if emit:
                        w.put(first+20*second if version==5 else pulse_pair(first,second),9)
                        w.put(amps,8)
                if flags&128:
                    extra=r.get(1) if present else 0
                    if extra:
                        pos,amp=r.get(6),r.get(4)
                        if pos>=40:raise ValueError('Invalid extra pulse position')
                    if emit:
                        w.put(extra,1)
                        if extra:w.put(pos,6);w.put(amp,4)
    used=r.at
    if (used+7)//8!=payload or r.get(payload*8-used):
        raise ValueError('Unexpected trailing LPX data')
    if source in (5,8) and version==9 and not rewrite_spectra:assert w.at<=used
    payload=len(w.output)
    if version in (5,8):
        result=struct.pack('<4sBBHIHHHHH',b'L4HY',version,output_flags,rate,n,pre,bright,320,320 if sparse80 else 160,payload)
    else:result=struct.pack('<2sBHHHHH',b'L9',output_flags,rate,n,pre,bright,payload)
    result+=w.output
    if len(result)>65535:raise ValueError('Stream exceeds bounded ROM API')
    return bytes(result),dict(source_version=source,version=version,samples=n,
        input_bytes=len(blob),file_bytes=len(result),input_payload_bits=used,payload_bits=w.at,payload_bytes=payload)


def repack(blob,version=9,*,optimize_rice0=False):
    """Return an equivalent stream and exact bit/complete-file statistics.

    Flag64 requires the separate experimental reader. It is not admitted to
    the current production firmware; using this tool does not establish that.
    Default conversions retain their former bytes. V9 inputs may carry bit64,
    selecting delta Rice-k0 (P4 already uses k0); legacy5/8 output clears64 and
    restores the original width-dependent Rice syntax. For old syntax, the
    optional optimizer chooses shortest gap/delta encodings and sets64 only
    for a strictly smaller complete six-bit-profile file. Growth, byte ties
    and noncanonical original encodings retain the exact default v9 bytes.
    Existing bit64 inputs are left intact, making optimization idempotent.
    """
    if type(optimize_rice0) is not bool:raise ValueError('Rice0 optimization must be boolean')
    if optimize_rice0 and version!=9:raise ValueError('Rice0 optimization requires v9 output')
    baseline,stats=_repack(blob,version)
    if not optimize_rice0:return baseline,stats
    if baseline[2]&64:
        stats['rice0_optimization']=dict(decision='already-enabled',baseline_file_bytes=len(baseline),
            candidate_file_bytes=len(baseline),baseline_payload_bits=stats['payload_bits'],
            candidate_payload_bits=stats['payload_bits'],saved_bytes=0,saved_payload_bits=0,saved_padding_bits=0)
        return baseline,stats
    canonical,_=_repack(baseline,9,force_delta_k0=False,canonical_spectra=True)
    candidate,candidate_stats=_repack(baseline,9,force_delta_k0=True,canonical_spectra=True)
    restored,_=_repack(candidate,9,force_delta_k0=False,canonical_spectra=True)
    if restored!=canonical:raise AssertionError('Rice0 old-syntax roundtrip differs')
    if canonical!=baseline:decision='fallback-noncanonical-exact-roundtrip'
    elif len(candidate)<len(baseline):decision='k0'
    elif len(candidate)>len(baseline):decision='fallback-growth'
    else:decision='fallback-byte-tie'
    selected=candidate if decision=='k0' else baseline
    selected_bits=candidate_stats['payload_bits'] if decision=='k0' else stats['payload_bits']
    optimization=dict(decision=decision,baseline_file_bytes=len(baseline),candidate_file_bytes=len(candidate),
        baseline_payload_bits=stats['payload_bits'],candidate_payload_bits=candidate_stats['payload_bits'],
        saved_bytes=len(baseline)-len(selected),saved_payload_bits=stats['payload_bits']-selected_bits,
        saved_padding_bits=(len(baseline)-len(selected))*8-(stats['payload_bits']-selected_bits))
    stats.update(file_bytes=len(selected),payload_bits=selected_bits,payload_bytes=len(selected)-13,
                 rice0_optimization=optimization)
    return selected,stats


def main():
    import json
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--version',type=int,choices=(5,8,9),default=9)
    parser.add_argument('--optimize-rice0',action='store_true',
                        help='EXPERIMENTAL reader required: set64 only for a strictly smaller v9 file')
    args=parser.parse_args();protect_outputs([args.input],[args.output])
    blob,stats=repack(args.input.read_bytes(),args.version,optimize_rice0=args.optimize_rice0)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(blob);print(json.dumps(stats))


if __name__=='__main__':main()
