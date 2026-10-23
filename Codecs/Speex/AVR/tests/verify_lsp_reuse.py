"""Compare repeated LSP envelopes with independently changing excitation.

Build the original host decoder, profile host decoder and AVR mailbox first.
Generated streams exercise A->B->A transitions and explicit AVR state reset.
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
    args=parser.parse_args()
    output=build.ROOT/'build/lsp-reuse'
    streams=output/'streams'
    oracle=output/'oracle'
    streams.mkdir(parents=True,exist_ok=True)
    oracle.mkdir(parents=True,exist_ok=True)
    seed=0x2439e715
    def rnd(n):
        global seed
        seed^=seed<<13;seed&=0xffffffff
        seed^=seed>>17;seed^=seed<<5;seed&=0xffffffff
        return seed&((1<<n)-1)
    suffix='.exe' if sys.platform=='win32' else ''
    for index in range(2):
        codes=[tuple(rnd(6) for _ in range(3)) for _ in range(3)]
        sequence=[0]*12+[1]*3+[0]*4+[2]*4+[1]+[0]*5
        data=bytearray()
        for envelope in sequence:
            fields=[(0,1),(3,4)]+[(v,6) for v in codes[envelope]]+[(rnd(5),5)]
            for sub in range(4):
                fields += [(rnd(7),7),(rnd(5),5),(rnd(1),1)]
                fields += [(rnd(5),5) for _ in range(4)]
            assert sum(n for _,n in fields)==160
            packet=0
            for value,n in fields: packet=(packet<<n)|value
            data+=packet.to_bytes(20,'big')
        raw=streams/f'repeated_lsp_{index}.spxraw'
        raw.write_bytes(data)
        expected=oracle/(raw.stem+'.pcm')
        actual=output/(raw.stem+'-profile.pcm')
        subprocess.run([build.ROOT/f'build/reference/decode{suffix}',raw,expected],check=True)
        subprocess.run([build.ROOT/f'build/profile/decode{suffix}',raw,actual],check=True)
        assert actual.read_bytes()==expected.read_bytes()
    subprocess.run([args.node,build.ROOT/'tests/verify_avr.mjs','--streams',streams,
                    '--oracle',oracle,'--out',output,'--verify-reset'],check=True)
    report=json.loads((output/'avr-verification.json').read_text())
    assert all(r['resetVerified'] and r['lspCacheHits']>=r['frames']*2 for r in report['streams'])
    print('PASS: repeated envelopes, independent excitation, changes and explicit AVR reset')
