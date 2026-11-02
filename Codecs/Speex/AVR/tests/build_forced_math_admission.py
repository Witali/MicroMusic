#!/usr/bin/env python3
"""Build combined bounded-math decoding, output, feature and C link controls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
from build_forced_zero_admission import prepare_data
PROFILES={'nb395':(10,False),'wb575':(15,True)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    for name in ['baseline-root','low-corpus','spi-corpus']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline-images',type=Path,help='Reuse source/hash-verified complete before images/reports/traces')
    args=p.parse_args();out=ROOT/'build/forced-math-final';out.mkdir(parents=True,exist_ok=True)
    admission=ROOT/'reports/forced-one-admission.json';base=json.loads(admission.read_text())
    for n,h in base['sourceSha256'].items():assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    (out/'baseline-source.json').write_bytes((json.dumps(dict(sourceTreeVerified=True,sourceFiles=len(base['sourceSha256']),
        admissionSha256=hashlib.sha256(admission.read_bytes().replace(b'\r\n',b'\n')).hexdigest()),indent=2)+'\n').encode())
    prepare_data(args.low_corpus)

    def run(script,*options):subprocess.run([sys.executable,ROOT/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    for label,(width,wb) in PROFILES.items():
        filename='wb.bin' if wb else 'speex-test.bin';report='verification.json' if wb else 'avr-verification.json'
        if args.baseline_images:
            parent=args.baseline_images/label;expected=json.loads((ROOT/'reports'/('forced-one-after-'+label+'.json')).read_text())
            assert hashlib.sha256((parent/filename).read_bytes()).hexdigest()==expected['binarySha256']
            assert json.loads((parent/report).read_text())==expected
            t=json.loads((parent/'forced-zero-timing.json').read_text());assert t['binarySha256']==expected['binarySha256'] and t['frames']==10627
            shutil.copytree(parent,out/'before'/label,dirs_exist_ok=True)
        else:
            subprocess.run([sys.executable,args.baseline_root/'tools'/('build_wb.py' if wb else 'build.py'),
                '--avr-gcc',args.avr_gcc,'--backend','asm','--packet-bytes',str(width),'--low-rates','7','--enable-nb4',
                '--out',out/'before'/label],check=True)
        builder=build_wb.avr if wb else build.avr
        builder(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=out/'after'/label)
        stream=args.spi_corpus/label/'long.spxraw' if wb else args.low_corpus/label/'streams/coverage4096.spxraw'
        for backend in ['asm','c']:
            options=['--backend',backend,'--enable-nb4','--stream',stream,'--out',out/('spi' if backend=='asm' else 'c')/label]
            if wb:options.append('--wideband')
            if backend=='asm':options.append('--capture-pcm')
            run('tools/build_spi_player.py',*options)
            builder(args.avr_gcc,backend=backend,packet_bytes=width,enable_nb4=False,low_rates=2,destination=out/'features'/backend/label)
    run('tools/build_wb_stream_test.py','--packet-bytes',15,'--low-rates',7,'--enable-nb4','--frame-load-cycles',9600,'--out',out/'irq/wb575')
    run('tests/build_low_api.py','--out',out/'api')
    for label,width in [('nb8',20),('nb11',28),('wb98',25),('wb128',32)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            cmd=[sys.executable,source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py'),
                '--avr-gcc',args.avr_gcc,'--backend','asm','--packet-bytes',str(width),'--low-rates','0','--out',out/'identities'/epoch/label]
            if label=='nb11':cmd.append('--enable-nb4')
            subprocess.run(cmd,check=True)
    print('Built combined bounded-math admission; C decoder controls compile/link only')


if __name__=='__main__':main()
