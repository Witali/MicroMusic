#!/usr/bin/env python3
"""Freeze the native oracle's rare one-ULP cosine differences on reachable angles."""
import json,os,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/lpc-math'

def main():
    BUILD.mkdir(parents=True,exist_ok=True);exe=BUILD/('math-reference.exe' if os.name=='nt' else 'math-reference');source=front.VENDOR/'src'
    front.run(['clang','-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_LPC_NATIVE_COMPAT=0','-DCODEC2_LPC_MATH_CHECKS=1','-I'+str(ROOT/'src'),'-I'+str(source),ROOT/'src/lpc_math.c',ROOT/'tests/lpc_math.c','-o',exe,*([] if os.name=='nt' else ['-lm'])])
    result=json.loads(front.run([exe,BUILD/'patches.bin'],capture_output=True,text=True).stdout);pairs=sorted(set(struct.iter_unpack('<II',(BUILD/'patches.bin').read_bytes())))
    assert result['maximum_ulp']<=1 and len({a for a,b in pairs})==len(pairs)
    body='/* Native Clang/Windows CRT cosine compatibility at reachable Codec2 angles.\n * Generated data, not a mathematical accuracy correction; see lpc-math-compat.json. */\n'
    body+=f'#define LPC_COSINE_COMPAT_COUNT {len(pairs)}\nstatic const uint32_t lpc_cosine_compat[{2*len(pairs)}] CODEC2_TABLE_STORAGE = {{\n'
    for a,b in pairs:body+=f'    UINT32_C(0x{a:08x}), UINT32_C(0x{b:08x}),\n'
    body+='};\n';destination=ROOT/'src/lpc_math_compat.inc';destination.write_text(body,encoding='ascii',newline='\n')
    report={'test':result,'unique_corrections':len(pairs),'pairs_hex':[[f'{a:08x}',f'{b:08x}'] for a,b in pairs],'table_sha256':front.digest(destination),'reference_binary_sha256':front.digest(exe),'compiler':front.run(['clang','--version'],capture_output=True,text=True).stdout.splitlines()[0],'scope':'Matches the frozen native upstream oracle cosine on all 393 grid angles, 393^2 midpoints and 10*393 startup midpoints. Optional compatibility mode, mathematical mode remains available. No AVR qualification.'}
    names=['src/lpc_math.c','src/lpc_math.h','src/lpc_math_tables.inc','src/lpc_math_compat.inc','tests/lpc_math.c','tools/generate_lpc_math.py','tools/generate_lpc_compat.py']
    report['sources']={n:front.digest(ROOT/n) for n in names};front.dump(ROOT/'reports/lpc-math-compat.json',report);print(json.dumps(result|{'unique_corrections':len(pairs)}))
if __name__=='__main__':main()
