#!/usr/bin/env python3
"""Build prepared-dispatch admission against the verified zero-synthesis parent."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from audit_nb1_gain import sha
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--avr-gcc',required=True);parser.add_argument('--clang',required=True)
    parser.add_argument('--baseline-root',type=Path,required=True);parser.add_argument('--spi-corpus',type=Path,required=True);args=parser.parse_args()
    out=ROOT/'build/prepared-final';out.mkdir(parents=True,exist_ok=True)
    base=json.loads((ROOT/'reports/zero-synthesis-admission.json').read_text())
    for n,h in base['sourceSha256'].items():assert sha(args.baseline_root/n)==h,n
    (out/'baseline-source.json').write_bytes((json.dumps(dict(sourceTreeVerified=True,sourceFiles=len(base['sourceSha256']),
        admissionSha256=sha(ROOT/'reports/zero-synthesis-admission.json')),indent=2)+'\n').encode())
    parent=args.baseline_root/'build/zero-synthesis-final/after'
    for relative,binary,report,name in [('wb395','wb.bin','verification.json','raw'),('irq8','wb.bin','verification.json','irq8'),
        ('irq11','wb.bin','verification.json','irq11'),('spi/wb395','player.bin','verification.json','spi'),
        ('api/nb','api.bin','verification.json','after-api-nb'),('api/wb','api.bin','verification.json','after-api-wb')]:
        folder=parent/relative;expected=json.loads((ROOT/'reports'/('zero-synthesis-'+name+'.json')).read_text())
        assert json.loads((folder/report).read_text())==expected
        assert sha(folder/binary,False)==expected.get('binarySha256',expected.get('input',{}).get('binarySha256'))
        shutil.copytree(folder,out/'before'/relative,dirs_exist_ok=True)

    def run(script,*options):subprocess.run([sys.executable,ROOT/script,*map(str,options)],check=True)

    folder=out/'after/wb395';existing=json.loads((folder/'verification.json').read_text()) if (folder/'verification.json').exists() else None
    build_wb.avr(args.avr_gcc,backend='asm',packet_bytes=10,enable_nb4=True,low_rates=7,destination=folder)
    if existing:assert sha(folder/'wb.bin',False)==existing['binarySha256'],'Changed rebuild requires fresh raw verification'
    identities=[]
    build.avr(args.avr_gcc,backend='asm',packet_bytes=6,enable_nb4=True,low_rates=7,destination=out/'identities/nb215')
    identities.append(dict(profile='nb215',binarySha256=sha(out/'identities/nb215/speex-test.bin',False),byteIdentical=True))
    assert identities[-1]['binarySha256']==json.loads((ROOT/'reports/nb1-zero-after-nb215.json').read_text())['binarySha256']
    for label,width,mask in [('nb8',20,0),('nb11',28,0),('wb98',25,0),('wb128',32,0),('nb395',10,2),('wb575',15,2)]:
        folder=out/'identities'/label
        (build_wb.avr if label.startswith('wb') else build.avr)(args.avr_gcc,backend='asm',packet_bytes=width,
            enable_nb4=label in ('nb11','wb128'),low_rates=mask,destination=folder)
        expected=next(r for r in json.loads((ROOT/'reports/nb1-zero-controls.json').read_text())['images'] if r['profile']==label)
        binary=folder/('wb.bin' if label.startswith('wb') else 'speex-test.bin');assert sha(binary,False)==expected['binarySha256'],label
        identities.append(dict(profile=label,binarySha256=sha(binary,False),byteIdentical=True))
    for backend in ['asm','c']:build_wb.avr(args.avr_gcc,backend=backend,packet_bytes=10,low_rates=4,destination=out/'features'/backend)
    for name,load in [('irq8',25600),('irq11',35200)]:
        run('tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,'--packet-bytes',10,'--low-rates',7,'--enable-nb4',
            '--frame-load-cycles',load,'--out',out/'after'/name)
    for backend in ['asm','c']:
        run('tools/build_spi_player.py','--avr-gcc',args.avr_gcc,'--backend',backend,'--wideband','--low-rates',7,'--enable-nb4',
            '--stream',args.spi_corpus/'wb395/long.spxraw','--out',out/('after/spi/wb395' if backend=='asm' else 'c/wb395'),
            *(['--capture-pcm'] if backend=='asm' else []))
    run('tools/build_spi_player.py','--avr-gcc',args.avr_gcc,'--backend','asm','--low-rates',7,'--enable-nb4','--capture-pcm',
        '--stream',args.spi_corpus/'nb215/long.spxraw','--out',out/'identities/spi-nb215')
    binary=out/'identities/spi-nb215/player.bin';assert sha(binary,False)==json.loads((ROOT/'reports/nb1-zero-after-spi-nb215.json').read_text())['input']['binarySha256']
    identities.append(dict(profile='spi-nb215',binarySha256=sha(binary,False),byteIdentical=True))
    (out/'identities.json').write_bytes((json.dumps(dict(images=identities),indent=2)+'\n').encode())
    run('tests/build_low_api.py','--avr-gcc',args.avr_gcc,'--out',out/'after/api')
    run('tests/build_noise_cache.py','--avr-gcc',args.avr_gcc)
    run('tools/build_wb.py','--export-c',ROOT/'build/prepared-export','--low-rates',7,'--enable-nb4')
    run('tests/check_refill_c_export.py','--clang',args.clang,'--export',ROOT/'build/prepared-export')
    print('Built prepared dispatch; full C controls/export compile/link only')


if __name__=='__main__':main()
