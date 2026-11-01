#!/usr/bin/env python3
"""Build matched one-tap NB3.95/WB5.75 images and continuous output controls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
from build_forced_zero_admission import prepare_data
PROFILES={'nb395':(10,False),'wb575':(15,True)}


def capture_layout(compiler,out):
    objdump=str(Path(compiler).with_name('avr-objdump'+('.exe' if str(compiler).endswith('.exe') else '')))
    rows=[]
    for epoch in ['before','after']:
        folder=out/epoch/'wb575';text=subprocess.check_output([objdump,'-d',folder/'wb.elf'],text=True)
        body=re.search(r'<speex_nb3_interpolate_lpc>:(.*?)(?=\n[0-9a-f]+ <)',text,re.S)[1]
        calls=[]
        for n in [2,3,4]:
            line=next(s for s in body.splitlines() if '<speex_avr_lsp_pair'+str(n)+'>' in s)
            opcode=re.search(r'\b(rcall|call)\b',line)[1];calls.append(dict(target='speex_avr_lsp_pair'+str(n),opcode=opcode))
        rows.append(dict(epoch=epoch,binarySha256=hashlib.sha256((folder/'wb.bin').read_bytes()).hexdigest(),calls=calls))
    (out/'layout.json').write_bytes((json.dumps(dict(scope='Three call relaxations in NB LPC conversion, WB5.75 image',images=rows),indent=2)+'\n').encode())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    for n in ['baseline-root','low-corpus','spi-corpus']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--baseline-images',type=Path,help='Reuse source/hash-verified parent admission images and traces')
    args=p.parse_args();out=ROOT/'build/forced-final';out.mkdir(parents=True,exist_ok=True)
    admission=ROOT/'reports/forced-zero-admission.json';base=json.loads(admission.read_text())
    for n,v in base['sourceSha256'].items():
        assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==v,n
    (out/'baseline-source.json').write_bytes((json.dumps(dict(sourceTreeVerified=True,sourceFiles=len(base['sourceSha256']),
        admissionSha256=hashlib.sha256(admission.read_bytes().replace(b'\r\n',b'\n')).hexdigest()),indent=2)+'\n').encode())
    prepare_data(args.low_corpus)

    def run(script,*options):
        subprocess.run([sys.executable,ROOT/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    for label,(width,wb) in PROFILES.items():
        filename='wb.bin' if wb else 'speex-test.bin';report='verification.json' if wb else 'avr-verification.json'
        if args.baseline_images:
            parent=args.baseline_images/label;expected=json.loads((ROOT/'reports'/('forced-zero-after-'+label+'.json')).read_text())
            assert hashlib.sha256((parent/filename).read_bytes()).hexdigest()==expected['binarySha256']
            assert json.loads((parent/report).read_text())==expected
            trace=json.loads((parent/'forced-zero-timing.json').read_text());assert trace['binarySha256']==expected['binarySha256'] and trace['frames']==10627
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
    run('tools/build_wb_stream_test.py','--packet-bytes',15,'--low-rates',7,'--enable-nb4',
        '--frame-load-cycles',9600,'--out',out/'irq/wb575')
    run('tests/build_low_api.py','--out',out/'api')
    for label,width in [('nb8',20),('nb11',28),('wb98',25),('wb128',32)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            cmd=[sys.executable,source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py'),
                '--avr-gcc',args.avr_gcc,'--backend','asm','--packet-bytes',str(width),'--low-rates','0','--out',out/'identities'/epoch/label]
            if label=='nb11':cmd.append('--enable-nb4')
            subprocess.run(cmd,check=True)
    capture_layout(args.avr_gcc,out)
    print('Built one-tap admission; all C decoder images compile/link only')


if __name__=='__main__':main()
