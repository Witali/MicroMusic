#!/usr/bin/env python3
"""Three Intel 8080 table-free CRC-16 implementations: reference + emulator tests.

Usage: python3 test_crc16_8080_v3.py
No third-party dependencies. Full-ROM simulation is slow (~seconds per run).
"""
from pathlib import Path
import random

from crc8080_tools import assemble, crc, emulate, patch_rom

ROOT = Path(__file__).resolve().parent
PROFILES = {
    'strong': ('crc16_8080_fast39', 0x002D, 39, 8785713, 65535),
    'fastest': ('crc16_8080_fast33z_poly0009', 0x0009, 33, 6164278, 57337),
    'balanced': ('crc16_8080_fast38_poly001B', 0x001B, 38, 8130353, 59055),
    'speed': ('crc16_8080_fast37_poly000F', 0x000F, 37, 7474993, 57337),
}


def polynomial_period(poly):
    val=1
    seen=set()
    for k in range(1, 65536):
        assert val != 0
        assert val not in seen, (poly, k)
        seen.add(val)
        val = ((val << 1) ^ (poly if val & 0x8000 else 0)) & 0xFFFF
        if val == 1:
            return k
    raise AssertionError('Unexpected period')


def byte_transform(old_crc, value, poly):
    """Independent 8-round bit-serial CRC reference."""
    c = old_crc ^ (value << 8)
    for _ in range(8):
        c = ((c << 1) ^ (poly if c & 0x8000 else 0)) & 0xFFFF
    return c


def test_case(profile, rng):
    name,poly,nbytes,ncycles,period = PROFILES[profile]
    program,labels = assemble((ROOT/(name+'.asm')).read_text())
    assert program == (ROOT/(name+'.bin')).read_bytes()
    assert len(program)==nbytes and labels['NEXT']==(6 if profile=='fastest' else 5)
    assert polynomial_period(poly) == period
    # A zero image with a random firmware header and repaired footer.
    rom = bytearray(patch_rom(program, poly=poly))
    assert len(rom) == 65536 and crc(rom,poly)==0
    assert rom[-2:]==crc(rom[:-2],poly).to_bytes(2,'big')

    good=emulate(rom,init=rng.randrange(256),crc_layout='HC',trace_addresses=True)
    assert good['CRC']==0 and good['INTE'] and good['DE']==0
    assert good['rom_reads']==65536 and good['unique_rom_reads']==65536
    assert good['cycles']==ncycles, (profile,good['cycles'])

    # Isolated faults, including address boundary, data area, and footer.
    for address,mask in ((0x0100,0x80),(0x8000,0x04),(0xfffe,0x80),(0xffff,1)):
        altered=bytearray(rom);altered[address]^=mask
        reference=crc(altered,poly)
        assert reference != 0
        failed=emulate(altered,init=rng.randrange(256),crc_layout='HC')
        assert failed['CRC']==reference and not failed['INTE'] and failed['rom_reads']==65536

    # Confirm a precisely chosen two-bit undetectable pattern for this CRC.
    first=0x2000
    offset=period//8
    rem=period%8
    second=first+offset
    altered=bytearray(rom)
    altered[first]^=0x80                    # bit 7 (MSB) at first address
    altered[second]^=(0x80>>rem)          # bit 7-rem at second address
    assert crc(altered,poly)==0,(profile,first,second,rem)
    coll=emulate(altered,init=rng.randrange(256),crc_layout='HC')
    assert coll['INTE'] and coll['CRC']==0

    # A random ROM body rather than only erased 0xFF bytes.
    random_rom=bytearray(rom)
    random_rom[len(program):-2] = rng.randbytes(65534-len(program))
    random_rom[-2:]=crc(random_rom[:-2],poly).to_bytes(2,'big')
    check=emulate(random_rom,init=rng.randrange(256),crc_layout='HC')
    assert check['INTE'] and check['CRC']==0 and check['rom_reads']==65536

    # Compare the closed-form GF(2) byte update with the independent
    # bit-at-a-time reference for arbitrary CRC states, not only init=0.
    factors={0x002D:(2,3), 0x001B:(1,3), 0x000F:(1,2)}
    for _ in range(30000):
        s=rng.randrange(65536)
        x=rng.randrange(256)
        actual=byte_transform(s,x,poly)
        t=x^(s>>8)
        if poly in factors:
            a,b=factors[poly]
            u=t^(t<<a)
            result=(((s&255)<<8)^u^(u<<b))&65535
        else:
            assert poly==0x0009
            result=(((s&255)<<8)^t^(t<<3))&65535
        assert actual==result, (profile,s,x,actual,result)
    print(f'{profile:8} {nbytes:2} bytes  poly=0x{poly:04X}  '
          f'{ncycles:,} T  {ncycles/65536:.3f} T/B  '
          f'double-bit period {period:5} bits  PASS',flush=True)


def main():
    rng=random.Random(0x808080)
    for profile in PROFILES:
        test_case(profile,rng)
    # Independent analytical test of every possible one-bit error syndrome
    for profile,(_,poly,_,_,_) in PROFILES.items():
        syndrome=poly
        for bit in range(524288):
            assert syndrome != 0,(profile,bit)
            syndrome=((syndrome<<1)^(poly if syndrome&0x8000 else 0))&0xffff
        print(profile,'all 524288 one-bit error positions detected (syndrome test)')
    print('PASS: CRC-16 v3 regression suite')


if __name__=='__main__':
    main()
