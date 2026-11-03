"""Lossless LPX v5 <-> v9 repacking without audio analysis or dependencies.

V9 preserves every output sample. Its 13-byte header omits fixed geometry
and narrows the already bounded sample count. Zero-gain lag fields and
unplayed final subframes are omitted. P6 pulse
positions use a 5x5 high-coordinate index plus four low bits, still nine bits.
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


def repack(blob, version=9):
    """Return a strictly validated equivalent stream and bit/size statistics."""
    if version not in (5,9) or len(blob)<13:
        raise ValueError('Expected LPX v5 or v9')
    source=9 if blob[:2]==b'L9' else 5 if blob[:5]==b'L4HY\x05' else 0
    if source==5 and len(blob)>=22:
        _,_,flags,rate,n,pre,bright,frame,block,payload=struct.unpack('<4sBBHIHHHHH',blob[:22])
        if (frame,block)!=(320,160):raise ValueError('Invalid packet geometry')
        header=22
    elif source==9:
        _,flags,rate,n,pre,bright,payload=struct.unpack('<2sBHHHHH',blob[:13])
        header=13
    else:raise ValueError('Expected LPX v5 or v9')
    if (flags&127) not in (4,6) or rate!=8000:
        raise ValueError('Unsupported LPX profile or sample rate')
    if not 1<=n<=64000 or pre>16384 or bright>11469:
        raise ValueError('Invalid LPX metadata')
    if len(blob)>65535 or len(blob)!=header+payload:
        raise ValueError('Invalid bounded payload length')
    r=Bits(blob[header:]);w=Bits()
    bits=5 if flags&127==4 else 6
    old=None

    def copy(count):
        value=r.get(count);w.put(value,count);return value

    def rice(k,width):
        high=0
        while high<8 and not copy(1):high+=1
        return copy(width) if high==8 else (high<<k)|copy(k)

    for fi in range((n+319)//320):
        if copy(1):
            delta=copy(1)
            if delta and old is None:raise ValueError('Initial delta spectrum')
            vec=[]
            for i in range(10):
                z=rice(bits-4-delta,bits+delta)
                value=(old[i]+(z//2 if not z&1 else -(z//2)-1)) if delta else ((vec[-1]+1 if vec else 0)+z)
                if not 0<=value<(1<<bits) or vec and value<=vec[-1]:
                    raise ValueError('Invalid spectrum')
                vec.append(value)
            old=vec
        elif old is None:raise ValueError('Initial repeated spectrum')
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
    if source==5 and version==9:assert w.at<=used
    payload=len(w.output)
    if version==5:
        result=struct.pack('<4sBBHIHHHHH',b'L4HY',5,flags,rate,n,pre,bright,320,160,payload)
    else:result=struct.pack('<2sBHHHHH',b'L9',flags,rate,n,pre,bright,payload)
    result+=w.output
    if len(result)>65535:raise ValueError('Stream exceeds bounded ROM API')
    return bytes(result),dict(source_version=source,version=version,samples=n,
        input_bytes=len(blob),file_bytes=len(result),input_payload_bits=used,payload_bits=w.at,payload_bytes=payload)


def main():
    import json
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--version',type=int,choices=(5,9),default=9)
    args=parser.parse_args();protect_outputs([args.input],[args.output])
    blob,stats=repack(args.input.read_bytes(),args.version)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(blob);print(json.dumps(stats))


if __name__=='__main__':main()
