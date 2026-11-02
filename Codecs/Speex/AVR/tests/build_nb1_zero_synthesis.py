#!/usr/bin/env python3
"""Build the zero-vector admission; reuse only verified completed parent evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb


def digest(path,text=False):
    data=path.read_bytes();return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--avr-gcc',required=True);parser.add_argument('--clang',required=True)
    parser.add_argument('--baseline-root',type=Path,required=True);parser.add_argument('--spi-corpus',type=Path,required=True);args=parser.parse_args()
    out=ROOT/'build/zero-synthesis-final';out.mkdir(parents=True,exist_ok=True)
    base=json.loads((ROOT/'reports/nb1-zero-admission.json').read_text())
    for n,h in base['sourceSha256'].items():assert digest(args.baseline_root/n,True)==h,n
    (out/'baseline-source.json').write_bytes((json.dumps(dict(sourceTreeVerified=True,sourceFiles=len(base['sourceSha256']),
        admissionSha256=digest(ROOT/'reports/nb1-zero-admission.json',True)),indent=2)+'\n').encode())
    parent=args.baseline_root/'build/nb1-zero-final/after'

    def copy_verified(relative,binary,report):
        label=str(relative).replace('\\','-').replace('/','-')
        expected=json.loads((ROOT/'reports'/('nb1-zero-after-'+label+'.json')).read_text())
        folder=parent/relative;assert json.loads((folder/report).read_text())==expected
        assert digest(folder/binary)==expected.get('binarySha256',expected.get('input',{}).get('binarySha256'))
        shutil.copytree(folder,out/'before'/relative,dirs_exist_ok=True)

    copy_verified(Path('wb395'),'wb.bin','verification.json')
    for name in ['irq8','irq11']:copy_verified(Path(name),'wb.bin','verification.json')
    copy_verified(Path('spi/wb395'),'player.bin','verification.json')
    for name in ['nb','wb']:copy_verified(Path('api')/name,'api.bin','verification.json')

    def run(script,*options):subprocess.run([sys.executable,ROOT/script,*map(str,options)],check=True)

    folder=out/'after/wb395';existing=json.loads((folder/'verification.json').read_text()) if (folder/'verification.json').exists() else None
    build_wb.avr(args.avr_gcc,backend='asm',packet_bytes=10,enable_nb4=True,low_rates=7,destination=folder)
    if existing:assert digest(folder/'wb.bin')==existing['binarySha256'],'A new raw verification is required after a changed rebuild'
    identities=[]
    build.avr(args.avr_gcc,backend='asm',packet_bytes=6,enable_nb4=True,low_rates=7,destination=out/'identities/nb215')
    identities.append(dict(profile='nb215',binarySha256=digest(out/'identities/nb215/speex-test.bin'),byteIdentical=True))
    assert identities[-1]['binarySha256']==json.loads((ROOT/'reports/nb1-zero-after-nb215.json').read_text())['binarySha256']
    for label,width,mask in [('nb8',20,0),('nb11',28,0),('wb98',25,0),('wb128',32,0),('nb395',10,2),('wb575',15,2)]:
        folder=out/'identities'/label
        (build_wb.avr if label.startswith('wb') else build.avr)(args.avr_gcc,backend='asm',packet_bytes=width,
            enable_nb4=label in ('nb11','wb128'),low_rates=mask,destination=folder)
        expected=next(r for r in json.loads((ROOT/'reports/nb1-zero-controls.json').read_text())['images'] if r['profile']==label)
        binary=folder/('wb.bin' if label.startswith('wb') else 'speex-test.bin');assert digest(binary)==expected['binarySha256'],label
        identities.append(dict(profile=label,binarySha256=digest(binary),byteIdentical=True))
    for backend in ['asm','c']:
        build_wb.avr(args.avr_gcc,backend=backend,packet_bytes=10,low_rates=4,destination=out/'features'/backend)
    for name,load in [('irq8',25600),('irq11',35200)]:
        run('tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,'--packet-bytes',10,'--low-rates',7,'--enable-nb4',
            '--frame-load-cycles',load,'--out',out/'after'/name)
    for backend in ['asm','c']:
        run('tools/build_spi_player.py','--avr-gcc',args.avr_gcc,'--backend',backend,'--wideband','--low-rates',7,'--enable-nb4',
            '--stream',args.spi_corpus/'wb395/long.spxraw','--out',out/('after/spi/wb395' if backend=='asm' else 'c/wb395'),
            *(['--capture-pcm'] if backend=='asm' else []))
    run('tools/build_spi_player.py','--avr-gcc',args.avr_gcc,'--backend','asm','--low-rates',7,'--enable-nb4','--capture-pcm',
        '--stream',args.spi_corpus/'nb215/long.spxraw','--out',out/'identities/spi-nb215')
    binary=out/'identities/spi-nb215/player.bin';assert digest(binary)==json.loads((ROOT/'reports/nb1-zero-after-spi-nb215.json').read_text())['input']['binarySha256']
    identities.append(dict(profile='spi-nb215',binarySha256=digest(binary),byteIdentical=True))
    (out/'identities.json').write_bytes((json.dumps(dict(images=identities),indent=2)+'\n').encode())
    run('tests/build_low_api.py','--avr-gcc',args.avr_gcc,'--out',out/'after/api')
    run('tests/build_noise_cache.py','--avr-gcc',args.avr_gcc)
    run('tools/build_wb.py','--export-c',ROOT/'build/zero-synthesis-export','--low-rates',7,'--enable-nb4')
    run('tests/check_refill_c_export.py','--clang',args.clang,'--export',ROOT/'build/zero-synthesis-export')
    print('Built zero-vector admission; all full C controls/export compile/link only')


if __name__=='__main__':main()
