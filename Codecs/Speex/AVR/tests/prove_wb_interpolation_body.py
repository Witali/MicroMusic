#!/usr/bin/env python3
"""Exhaust actual HB interpolation bodies against an independent Xiph model.

Only extracted scalar functions execute. No complete decoder is compiled,
linked or run. Requires a host C compiler; GCC/Clang on POSIX is supported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from check_wb_interpolation import ROOT, TABLE, endpoints


def sha(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def body(text):
    marker = 'static SPEEX_NB3_NOINLINE void wb_interpolate('
    start = text.index(marker)
    end = text.index('\n}', start) + 2
    assert text.count(marker) == 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='gcc')
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--baseline-file', type=Path,
        help='Optional exported baseline file for hosts that cannot read a Windows worktree Git path')
    args = parser.parse_args()
    original = (args.baseline_file.read_bytes() if args.baseline_file else
        subprocess.check_output(['git', 'show', '1da660ea:Codecs/Speex/AVR/src/speex_wb1.c'], cwd=ROOT))
    admitted = json.loads((ROOT / 'reports/wb-size-full.json').read_text())
    assert sha(original) == admitted['sourceSha256']['src/speex_wb1.c']
    current = (ROOT / 'src/speex_wb1.c').read_bytes()
    before, after = [body(data.decode('utf-8').replace('\r\n', '\n')) for data in [original, current]]
    values = endpoints()
    assert len(values) == 4096 and all(len(row) == 8 for row in values)
    out = ROOT / 'build/interpolation-body-proof'
    out.mkdir(parents=True, exist_ok=True)
    program = '''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SPEEX_NB3_NOINLINE __attribute__((noinline))
static struct {int16_t old_lsp[8],lsp[8];uint8_t sub;} wb;
static const int16_t endpoints[4096][8]={
''' + ',\n'.join('{' + ','.join(map(str, row)) + '}' for row in values) + '};\n'
    program += before.replace('wb_interpolate(', 'wb_interpolate_before(') + '\n' + after + '\n'
    program += '''
static void reference(int16_t *out) {
    int32_t fraction=4096*(wb.sub+1);
    for(unsigned i=0;i<8;i++)out[i]=((wb.old_lsp[i]*(16384-fraction)+8192)>>14)+((wb.lsp[i]*fraction+8192)>>14);
    if(out[0]<410)out[0]=410;
    if(out[7]>25326)out[7]=25326;
    for(unsigned i=1;i<7;i++) {
        if(out[i]<out[i-1]+410)out[i]=out[i-1]+410;
        if(out[i]>out[i+1]-410)out[i]=(out[i]>>1)+((out[i+1]-410)>>1);
    }
}
int main(void) {
    uint64_t cases=0;
    for(unsigned old=0;old<4096;old++) {
        memcpy(wb.old_lsp,endpoints[old],16);
        for(unsigned next=0;next<4096;next++) {
            memcpy(wb.lsp,endpoints[next],16);
            for(unsigned sub=0;sub<4;sub++) {
                int16_t a[10],b[10],r[8];
                a[0]=b[0]=0x55aa;a[9]=b[9]=0x33cc;wb.sub=sub;
                wb_interpolate_before(a+1);wb_interpolate(b+1);reference(r);
                if(memcmp(a,b,20)||memcmp(b+1,r,16)||a[0]!=0x55aa||a[9]!=0x33cc) {
                    fprintf(stderr,"Mismatch %u,%u quarter%u\\n",old,next,sub+1);return 2;
                }
                ++cases;
            }
        }
    }
    printf("%llu\\n",(unsigned long long)cases);return 0;
}
'''
    source = out / 'proof.c'
    source.write_text(program, encoding='utf-8')
    executable = out / 'proof'
    flags = ['-std=c11', '-O3', '-fwrapv', '-fno-strict-aliasing']
    subprocess.run([args.cc, *flags, source, '-o', executable], check=True)
    count = int(subprocess.check_output([executable], text=True).strip())
    assert count == 67108864
    result = dict(scope='Complete actual scalar interpolation bodies versus independent separately-rounded Xiph formula',
        baselineRevision='1da660ea', endpointVectors=4096, oldNewPairs=4096**2, quarterCases=count,
        compiler=subprocess.check_output([args.cc, '--version'], text=True).splitlines()[0], flags=flags,
        sourceHashMode='UTF-8 text normalized to LF',
        sourceSha256={name: sha((ROOT / name).read_bytes()) for name in
            ['src/speex_wb1.c', 'src/speex_platform.h', 'tests/prove_wb_interpolation_body.py',
             'tests/check_wb_interpolation.py', str(TABLE.relative_to(ROOT)).replace('\\', '/')]},
        baselineBodySha256=sha(before.encode()), currentBodySha256=sha(after.encode()),
        generatedProofSha256=sha(source.read_bytes()), exact=True, outputGuards=True,
        cDecoderExecuted=False, includesInterrupts=False, physicalBoardTested=False,
        limitations=['Host scalar proof; actual AVR integer/range behavior and timing need target gates.'])
    target = ROOT / 'reports/wb-interpolation-mask-domain.json'
    if args.record:
        target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    else:
        assert json.loads(target.read_text()) == result
    print('PASS actual interpolation bodies and Xiph model on all 67108864 quarter cases')


if __name__ == '__main__':
    main()
