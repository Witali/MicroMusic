#!/usr/bin/env python3
"""Build current-parent and finite-gain NB1 decoding/output admission."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
from screen_nb1_gain import PROFILES,prepare_data


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    for name in ['baseline-root','low-corpus','spi-corpus']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();out=ROOT/'build/nb1-gain-final';out.mkdir(parents=True,exist_ok=True)
    path=ROOT/'reports/forced-math-admission.json';base=json.loads(path.read_text())
    for n,h in base['sourceSha256'].items():assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    (out/'baseline-source.json').write_bytes((json.dumps(dict(sourceTreeVerified=True,sourceFiles=len(base['sourceSha256']),
        admissionSha256=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()),indent=2)+'\n').encode())
    prepare_data(args.low_corpus)

    def run(source,script,*options):
        subprocess.run([sys.executable,source/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    screen=json.loads((ROOT/'build/nb1-gain-screen/summary.json').read_text())
    for label,(width,wb) in PROFILES.items():
        for epoch,variant in [('before','before'),('after','selected')]:
            parent=ROOT/'build/nb1-gain-screen'/variant/label;name='wb.bin' if wb else 'speex-test.bin'
            expected=next(r for r in screen['rows'] if r['profile']==label and r['variant']==variant)
            assert hashlib.sha256((parent/name).read_bytes()).hexdigest()==expected['binarySha256']
            shutil.copytree(parent,out/epoch/label,dirs_exist_ok=True)
    for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
        for label,load in [('irq8',25600),('irq11',35200)]:
            run(source,'tools/build_wb_stream_test.py','--packet-bytes',10,'--low-rates',7,'--enable-nb4',
                '--frame-load-cycles',load,'--out',out/epoch/label)
        for label,(width,wb) in PROFILES.items():
            options=['--backend','asm','--enable-nb4','--capture-pcm','--stream',args.spi_corpus/label/'long.spxraw','--out',out/epoch/'spi'/label]
            if wb:options.append('--wideband')
            run(source,'tools/build_spi_player.py',*options)
        run(source,'tests/build_low_api.py','--out',out/epoch/'api')
    for label,(width,wb) in PROFILES.items():
        builder=build_wb.avr if wb else build.avr
        for backend in ['asm','c']:
            builder(args.avr_gcc,backend=backend,packet_bytes=width,enable_nb4=False,low_rates=4,destination=out/'features'/backend/label)
        options=['--backend','c','--enable-nb4','--stream',args.spi_corpus/label/'long.spxraw','--out',out/'c'/label]
        if wb:options.append('--wideband')
        run(ROOT,'tools/build_spi_player.py',*options)
    for label,width,mask in [('nb8',20,0),('nb11',28,0),('wb98',25,0),('wb128',32,0),('nb395',10,2),('wb575',15,2)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            command=[sys.executable,source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py'),
                '--avr-gcc',args.avr_gcc,'--backend','asm','--packet-bytes',str(width),'--low-rates',str(mask),'--out',out/'identities'/epoch/label]
            if label=='nb11':command.append('--enable-nb4')
            subprocess.run(command,check=True)
    print('Built finite NB1 gain admission; full C decoder controls compile/link only')


if __name__=='__main__':main()
