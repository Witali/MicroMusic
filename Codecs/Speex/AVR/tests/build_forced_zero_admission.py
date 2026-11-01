#!/usr/bin/env python3
"""Build matched zero-coefficient NB3.95/WB5.75 and real output controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
PROFILES={'nb395':(10,False),'wb575':(15,True)}


def prepare_data(corpus):
    out=ROOT/'build/forced-zero-screen-data';rows=[];counts=[]
    for label,(width,wb) in PROFILES.items():
        total=zero=speech=speech_zero=0
        for path in sorted((corpus/label/'streams').glob('*.spxraw')):
            data=path.read_bytes();assert len(data)%width==0
            n=len(data)//width;z=sum((((data[p+3]&3)<<2)|(data[p+4]>>6))==0 for p in range(0,len(data),width))
            total+=n;zero+=z
            if path.name.startswith(('en_','ru_')):speech+=n;speech_zero+=z
        counts.append(dict(profile=label,frames=total,zeroCoefficientFrames=zero,speechFrames=speech,speechZeroCoefficientFrames=speech_zero))
        for name in ['coverage4096','en_letter_a','ru_slutskaya_a']:
            row=dict(profile=label,stream=name,frames=128)
            for folder,suffix,size,key in [('streams','.spxraw',width,'input'),('oracle','.pcm',640 if wb else 320,'pcm')]:
                data=(corpus/label/folder/(name+suffix)).read_bytes();part=data[:128*size];assert len(part)==128*size
                path=out/label/folder/(name+suffix);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(part)
                row[key+'Sha256']=hashlib.sha256(part).hexdigest();row['source'+key.title()+'Sha256']=hashlib.sha256(data).hexdigest()
            rows.append(row)
    (out/'manifest.json').write_bytes((json.dumps(dict(streams=rows,counts=counts),indent=2)+'\n').encode())


def check_baseline(root):
    path=ROOT/'reports/low-fusion-admission.json';data=path.read_bytes().replace(b'\r\n',b'\n');base=json.loads(data)
    for n,v in base['sourceSha256'].items():assert hashlib.sha256((root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==v,n
    return dict(admissionSha256=hashlib.sha256(data).hexdigest(),sourceFiles=len(base['sourceSha256']),sourceTreeVerified=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--after-only',action='store_true',help='Keep already built immutable before images')
    for name in ['baseline-root','low-corpus','spi-corpus']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();out=ROOT/'build/forced-zero-final';out.mkdir(parents=True,exist_ok=True)
    (out/'baseline-source.json').write_bytes((json.dumps(check_baseline(args.baseline_root),indent=2)+'\n').encode())
    prepare_data(args.low_corpus)

    def run(script,*options):
        subprocess.run([sys.executable,ROOT/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    for label,(width,wb) in PROFILES.items():
        if not args.after_only:
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
    run('tools/build_wb_stream_test.py','--packet-bytes',15,'--low-rates',7,'--enable-nb4',
        '--frame-load-cycles',9600,'--out',out/'irq/wb575')
    run('tests/build_low_api.py','--out',out/'api')
    run('tests/build_zero20.py','--baseline-root',args.baseline_root)
    for label,width in [('nb8',20),('nb11',28),('wb98',25),('wb128',32)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            if args.after_only and epoch=='before':continue
            command=[sys.executable,source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py'),
                '--avr-gcc',args.avr_gcc,'--backend','asm','--packet-bytes',str(width),'--low-rates','0',
                '--out',out/'identities'/epoch/label]
            if label=='nb11':command.append('--enable-nb4')
            subprocess.run(command,check=True)
    print('Built forced-zero admission; C decoder controls compile/link only')


if __name__=='__main__':main()
