#!/usr/bin/env python3
"""Build exact gain-zero preparation admission and preserve verified before evidence."""
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
    for name in ['baseline-root','baseline-images','low-corpus','spi-corpus']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();out=ROOT/'build/nb1-zero-final';out.mkdir(parents=True,exist_ok=True)
    path=ROOT/'reports/nb1-gain-admission.json';base=json.loads(path.read_text())
    for n,h in base['sourceSha256'].items():assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    (out/'baseline-source.json').write_bytes((json.dumps(dict(sourceTreeVerified=True,sourceFiles=len(base['sourceSha256']),
        admissionSha256=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()),indent=2)+'\n').encode())
    prepare_data(args.low_corpus)

    def copy_verified(name,relative,filename,reportname):
        parent=args.baseline_images/relative;expected=json.loads((ROOT/'reports'/name).read_text())
        assert json.loads((parent/reportname).read_text())==expected
        assert hashlib.sha256((parent/filename).read_bytes()).hexdigest()==expected.get('binarySha256',expected.get('input',{}).get('binarySha256'))
        shutil.copytree(parent,out/'before'/relative,dirs_exist_ok=True)

    for label,wb in [('nb215',False),('wb395',True)]:
        copy_verified('nb1-gain-after-'+label+'.json',Path(label),'wb.bin' if wb else 'speex-test.bin','verification.json' if wb else 'avr-verification.json')
        trace=json.loads((out/'before'/label/'packet-timing.json').read_text());assert trace['frames']==10627
        copy_verified('nb1-gain-after-spi-'+label+'.json',Path('spi')/label,'player.bin','verification.json')
    for name in ['irq8','irq11']:copy_verified('nb1-gain-after-'+name+'.json',Path(name),'wb.bin','verification.json')
    for label in ['nb','wb']:copy_verified('nb1-gain-after-api-'+label+'.json',Path('api')/label,'api.bin','verification.json')

    def run(script,*options):subprocess.run([sys.executable,ROOT/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    for label,(width,wb) in PROFILES.items():
        builder=build_wb.avr if wb else build.avr
        builder(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=out/'after'/label)
        for backend in ['asm','c']:
            builder(args.avr_gcc,backend=backend,packet_bytes=width,enable_nb4=False,low_rates=4,destination=out/'features'/backend/label)
        for backend in ['asm','c']:
            options=['--backend',backend,'--enable-nb4','--stream',args.spi_corpus/label/'long.spxraw','--out',out/('after/spi' if backend=='asm' else 'c')/label]
            if wb:options.append('--wideband')
            if backend=='asm':options.append('--capture-pcm')
            run('tools/build_spi_player.py',*options)
    for name,load in [('irq8',25600),('irq11',35200)]:
        run('tools/build_wb_stream_test.py','--packet-bytes',10,'--low-rates',7,'--enable-nb4','--frame-load-cycles',load,'--out',out/'after'/name)
    run('tests/build_low_api.py','--out',out/'after/api')
    run('tests/build_noise_cache.py')
    for label,width,mask in [('nb8',20,0),('nb11',28,0),('wb98',25,0),('wb128',32,0),('nb395',10,2),('wb575',15,2)]:
        filename='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        parent=args.baseline_root/'build/nb1-gain-final/identities/after'/label
        expected=next(r for r in json.loads((ROOT/'reports/nb1-gain-controls.json').read_text())['images'] if r['profile']==label)
        assert hashlib.sha256((parent/filename).read_bytes()).hexdigest()==expected['binarySha256']
        shutil.copytree(parent,out/'identities/before'/label,dirs_exist_ok=True)
        command=[sys.executable,ROOT/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py'),
            '--avr-gcc',args.avr_gcc,'--backend','asm','--packet-bytes',str(width),'--low-rates',str(mask),'--out',out/'identities/after'/label]
        if label=='nb11':command.append('--enable-nb4')
        subprocess.run(command,check=True)
    print('Built gain-zero admission; old completed evidence reused only after source/report/image verification')


if __name__=='__main__':main()
