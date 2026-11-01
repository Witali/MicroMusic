#!/usr/bin/env python3
"""Build matched WB5.75/WB7.75 fusion, IRQ/SPI, feature and C controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_wb
PROFILES={'wb575':15,'wb775':20}


def prepare_screen(corpus):
    out=ROOT/'build/low-fuse-screen-data';rows=[]
    for label,width in PROFILES.items():
        for name in ['coverage4096','en_letter_a','ru_slutskaya_a']:
            row=dict(profile=label,stream=name,frames=128)
            for folder,suffix,size,key in [('streams','.spxraw',width,'input'),('oracle','.pcm',640,'pcm')]:
                source=(corpus/label/folder/(name+suffix)).read_bytes();part=source[:128*size]
                assert len(part)==128*size
                path=out/label/folder/(name+suffix);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(part)
                row[key+'Sha256']=hashlib.sha256(part).hexdigest();row['source'+key.title()+'Sha256']=hashlib.sha256(source).hexdigest()
            rows.append(row)
    (out/'manifest.json').write_bytes((json.dumps(dict(scope='First 128 frames of three existing streams per profile',streams=rows),indent=2)+'\n').encode())


def check_baseline(root):
    path=ROOT/'reports/noise-prefold-admission.json';raw=path.read_bytes().replace(b'\r\n',b'\n');manifest=json.loads(raw)
    for name,value in manifest['sourceSha256'].items():
        assert hashlib.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==value,name
    return dict(admissionSha256=hashlib.sha256(raw).hexdigest(),sourceFiles=len(manifest['sourceSha256']),sourceTreeVerified=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--spi-corpus',type=Path,required=True)
    p.add_argument('--low-corpus',type=Path,required=True)
    args=p.parse_args();out=ROOT/'build/low-fusion-final'
    out.mkdir(parents=True,exist_ok=True)
    (out/'baseline-source.json').write_bytes((json.dumps(check_baseline(args.baseline_root),indent=2)+'\n').encode())
    prepare_screen(args.low_corpus)

    def run(script,*options):
        subprocess.run([sys.executable,ROOT/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    for label,width in PROFILES.items():
        subprocess.run([sys.executable,args.baseline_root/'tools/build_wb.py','--avr-gcc',args.avr_gcc,
            '--backend','asm','--packet-bytes',str(width),'--low-rates','7','--enable-nb4','--out',out/'before'/label],check=True)
        build_wb.avr(args.avr_gcc,'asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=out/'after'/label)
        run('tools/build_wb_stream_test.py','--packet-bytes',width,'--low-rates',7,'--enable-nb4',
            '--frame-load-cycles',9600,'--out',out/'irq'/label)
        run('tools/build_spi_player.py','--backend','asm','--wideband','--enable-nb4','--capture-pcm',
            '--stream',args.spi_corpus/label/'long.spxraw','--out',out/'spi'/label)
        for backend in ['asm','c']:
            build_wb.avr(args.avr_gcc,backend,packet_bytes=width,enable_nb4=False,
                low_rates=2 if label=='wb575' else 1,destination=out/'features'/backend/label)
        run('tools/build_spi_player.py','--backend','c','--wideband','--enable-nb4',
            '--stream',args.spi_corpus/label/'long.spxraw','--out',out/'c'/label)
    run('tests/build_low_api.py','--out',out/'api')
    for label,width,mask in [('nb215',6,7),('nb8',20,0),('nb11',28,0),('wb98',25,0),('wb128',32,0)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            script=source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py')
            command=[sys.executable,script,'--avr-gcc',args.avr_gcc,'--backend','asm',
                '--packet-bytes',str(width),'--low-rates',str(mask),'--out',out/'identities'/epoch/label]
            if label in ['nb215','nb11']:command.append('--enable-nb4')
            subprocess.run(command,check=True)
    print('Built low-fusion admission; C decoder controls compile/link only')


if __name__=='__main__':main()
