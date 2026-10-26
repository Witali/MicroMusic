"""Host proof only: exact small representations of the retained LPX tables.

Original project derivation; no decoder modification or AVR speed claim.
Run from any directory. Only the Python standard library is required.
"""
import hashlib,json,re
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[3]/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'
MANTISSAS=(4194,4380,4573,4776,4987,5208,5439,5680,
           5931,6194,6468,6754,7053,7366,7692,8032)


def read_table(name):
    text='\n'.join(line for line in (SOURCE/name).read_text().splitlines()
                   if not line.lstrip().startswith('//'))
    return [int(x) for x in re.findall(r'-?\d+',text)]


def scale_step(index):
    if not 0<=index<=255:raise ValueError('Expected uint8 index')
    # On AVR every intermediate fits uint16 and each shift is 0..15.
    return ((MANTISSAS[index&15]>>(15-(index>>4)))+1)>>1


def prove():
    steps=read_table('scale_table.inc');cos=read_table('cos_table.inc')
    assert len(steps)==256 and len(cos)==257 and max(MANTISSAS)+1<65536
    assert [scale_step(i) for i in range(256)]==steps
    # Independently derive a feasible doubled mantissa by intersecting the
    # integer intervals imposed by all sixteen octave-related entries.
    for residue in range(16):
        low,high=0,65535
        for group in range(16):
            value=steps[residue+16*group];shift=16-group
            low=max(low,(2*value-1)*(1<<(shift-1)))
            high=min(high,(2*value+1)*(1<<(shift-1))-1)
        assert low<=MANTISSAS[residue]<=high and low==MANTISSAS[residue]
    half=cos[:129]
    def folded(i):return half[i] if i<=128 else -half[256-i]
    assert [folded(i) for i in range(257)]==cos
    for norm in range(4096):
        index,fraction=norm>>4,norm&15
        original=cos[index]+((cos[index+1]-cos[index])*fraction>>4)
        compact=folded(index)+((folded(index+1)-folded(index))*fraction>>4)
        assert original==compact
    return {'scope':'Host integer identity; AVR code/Flash/SRAM/cycles unmeasured.',
        'scale_values_exact':256,'cos_values_exact':257,'interpolated_cos_values_exact':4096,
        'table_bytes_before':512+514,'table_bytes_after':32+258,'raw_table_bytes_saved':736,
        'mantissas_u16':MANTISSAS,
        'source_sha256':{name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
                         for name in ('scale_table.inc','cos_table.inc')}}


if __name__=='__main__':print(json.dumps(prove(),indent=2))
