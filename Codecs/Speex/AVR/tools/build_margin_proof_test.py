#!/usr/bin/env python3
"""Check affine certificates against every original Xiph NB3 dequantization."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build
import prove_nb3_margins
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);args=p.parse_args()
    build.verify_sources();proof=prove_nb3_margins.prove()
    assert proof==json.loads((build.ROOT/'reports/margin-proof.json').read_text())
    out=build.ROOT/'build/margin-proof-unit';out.mkdir(parents=True,exist_ok=True)
    reference=out/'reference';shutil.copytree(build.VENDOR,reference,dirs_exist_ok=True)
    (reference/'include/speex/speex_config_types.h').write_text('#include <stdint.h>\n'
        'typedef int16_t spx_int16_t;typedef uint16_t spx_uint16_t;\n'
        'typedef int32_t spx_int32_t;typedef uint32_t spx_uint32_t;\n')
    forms=proof['certificates']
    header='#define MARGIN_CERTIFICATES '+str(len(forms))+'\n'
    header+='static const struct {int16_t weights[10];int32_t constant,maximum;} margin_certificates[]={\n'
    header+=',\n'.join('{{'+','.join(map(str,x['weights']))+'},'+str(x['constant'])+','+str(x['maximum'])+'}' for x in forms)+'\n};\n'
    (out/'margin-certificates.h').write_text(header)
    flags=['-std=c11','-O2','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',
        *['-D'+d for d in build.DEFINES],'-I'+str(reference/'include'),'-I'+str(reference/'libspeex'),'-I'+str(out)]
    objects=[]
    for name in ['quant_lsp','bits','lsp_tables_nb']:
        obj=out/(name+'.o');objects.append(obj)
        build.run([args.cc,*flags,'-Dlsp_unquant_lbr=proof_unquant','-c',reference/'libspeex'/(name+'.c'),'-o',obj])
    exe=out/'proof.exe'
    build.run([args.cc,*flags,*objects,build.ROOT/'tests/margin_proof.c','-o',exe])
    report=json.loads(subprocess.check_output([exe],text=True))
    report.update(binarySha256=digest(exe),proofSha256=prove_nb3_margins.canonical_hash(build.ROOT/'reports/margin-proof.json'),
        oracle='Untouched Xiph quant_lsp.c, bits.c and lsp_tables_nb.c, separate non-LTO objects',
        compiler=subprocess.check_output([args.cc,'--version'],text=True).splitlines()[0],
        sourceSha256={p:prove_nb3_margins.canonical_hash(build.ROOT/p) for p in
            ['tools/prove_nb3_margins.py','tools/build_margin_proof_test.py','tests/margin_proof.c']})
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
