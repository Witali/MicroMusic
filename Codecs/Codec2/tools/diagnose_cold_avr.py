#!/usr/bin/env python3
"""Locate cold-packet divergence in the frozen full float reference on AVR."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/cold-diagnostic'

def main():
    BUILD.mkdir(parents=True,exist_ok=True);source=front.VENDOR/'src';suffix='.exe' if os.name=='nt' else ''
    inputs=ROOT.parents[1]/'build/codec2/adaptive/conditioning.bin';assert inputs.stat().st_size==24*8
    sources=[ROOT/'src/decoder_float.c',ROOT/'src/parameters.c',source/'lsp.c',source/'kiss_fft.c',source/'kiss_fftr.c']
    includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source)]
    program=BUILD/('decode'+suffix)
    front.run(['clang','-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_DECODER_TRACE',*includes,*sources,ROOT/'tests/decode.c','-o',program,*([] if os.name=='nt' else ['-lm'])])
    front.run([program,inputs,BUILD/'native.pcm',BUILD/'native.trace'])
    memory=device_memory('avr-gcc','atmega1284p')
    front.run(['avr-gcc','-mmcu=atmega1284p','-Os','-std=c99','-fno-strict-aliasing','-DCODEC2_DECODER_TRACE',*includes,*sources,ROOT/'tests/avr_decoder.c','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',BUILD/'decoder.elf','-lm'])
    front.run(['avr-objcopy','-O','binary',BUILD/'decoder.elf',BUILD/'decoder.bin'])
    with (BUILD/'symbols.txt').open('wb') as f:front.run(['avr-nm','-n',BUILD/'decoder.elf'],stdout=f)
    names=['src/decoder_float.c','src/parameters.c','tests/decode.c','tests/avr_decoder.c','tests/diagnose_cold_avr.mjs','tools/diagnose_cold_avr.py']
    report={'memory':memory,'packet_path':str(inputs),'packet_sha256':front.digest(inputs),'binary_sha256':front.digest(BUILD/'decoder.bin'),'native_trace_sha256':front.digest(BUILD/'native.trace'),'sources':{n:front.digest(ROOT/n) for n in names}}
    front.dump(BUILD/'build.json',report);front.run(['node',ROOT/'tests/diagnose_cold_avr.mjs'])
if __name__=='__main__':main()
