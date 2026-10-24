"""Cover every NB3 pitch/gain code with deterministic hostile packets on AVR.

Build the reference host decoder and AVR mailbox first. Generated packets and
oracles stay under ignored build/. This verifies decoding, not encoder quality.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node',default='node')
    parser.add_argument('--firmware',type=Path,help='Use a preserved firmware directory')
    parser.add_argument('--out',type=Path,default=build.ROOT/'build/pitch-cases')
    args=parser.parse_args()
    output=args.out
    streams=output/'streams'
    oracle=output/'oracle'
    streams.mkdir(parents=True,exist_ok=True)
    oracle.mkdir(parents=True,exist_ok=True)
    seed=0x5971bc31
    def random_bits(n):
        global seed
        seed^=seed<<13;seed&=0xffffffff
        seed^=seed>>17;seed^=seed<<5;seed&=0xffffffff
        return seed&((1<<n)-1)
    data=bytearray()
    for pitch in range(128):
        for gain in range(32):
            fields=[(0,1),(3,4)]+[(random_bits(6),6) for _ in range(3)]+[((pitch+gain)%32,5)]
            for sub in range(4):
                fields += [(pitch,7),(gain,5),((pitch+gain+sub)%2,1)]
                fields += [(random_bits(5),5) for _ in range(4)]
            packed=0
            assert sum(n for _,n in fields)==160
            for value,n in fields: packed=(packed<<n)|value
            data+=packed.to_bytes(20,'big')
    raw=streams/'all_pitch_gains.spxraw'
    raw.write_bytes(data)
    reference=build.ROOT/'build/reference/decode.exe'
    if sys.platform!='win32': reference=reference.with_suffix('')
    subprocess.run([reference,raw,oracle/'all_pitch_gains.pcm'],check=True)
    subprocess.run([args.node,build.ROOT/'tests/verify_avr.mjs','--streams',streams,
                    '--oracle',oracle,'--out',output,
                    *(['--firmware',args.firmware] if args.firmware else [])],check=True)
    report=json.loads((output/'avr-verification.json').read_text())
    report['coverage']={'pitchCodes':128,'pitchGainCodes':32,'pairs':4096,
                        'subframes':16384,'seed':'0x5971bc31'}
    (output/'avr-verification.json').write_text(json.dumps(report,indent=2)+'\n')
