"""Audit paired LSP admission; optionally rebuild decoder and direct-test images.

Text hashes normalize CRLF to LF. Firmware hashes always cover raw bytes.
Rebuilds confirm retained executable identity; they are not fresh simulations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text_digest(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',help='Rebuild eight decoders and four direct-test images');args=p.parse_args()
    build.verify_sources();reports=ROOT/'reports';admission=read(reports/'twin-admission.json')
    assert admission['textHashNormalization']=='CRLF to LF; firmware images remain raw bytes'
    for name,sha in admission['sourceSha256'].items():assert text_digest(ROOT/name)==sha,name
    for name,sha in admission['reportSha256'].items():assert text_digest(reports/name)==sha,name
    changed={'compact_lsp.c.inc','lsp_stage.S','lsp_stage_macros.S','lsp_pair.S','nb3_lsp_pair.h'}
    base=admission['baselineGitCommit'];old_names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {f.name for f in (ROOT/'src').iterdir() if f.is_file()}==old_names|changed
    for name in old_names-changed:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert old.replace(b'\r\n',b'\n')==(ROOT/'src'/name).read_bytes().replace(b'\r\n',b'\n'),name
    for backend in ['asm','c']:
        unit=read(reports/('twin-unit-'+backend+'.json'))
        assert unit['cases']==257790 and unit['outputsPerPath']==2062320 and unit['addressCases']==3840
        assert unit['all65536Signed16RootsAtBothInputs'] and unit['selectedAndForcedCExact']
        assert unit['independentBigIntProductOracle'] and unit['calleeSavedRegistersAndR1AtRet']
        if backend=='asm':
            assert unit['readBytes']==6186960 and unit['writtenBytes']==8249280 and unit['stackBytesInsideAsm']==18
            assert unit['initialTStates']==[0,1] and unit['primitiveCyclesIncludingRet']=={'2':[456],'3':[634],'4':[812]}
    irq=read(reports/'twin-irq.json')
    assert irq['injections']==30870 and irq['irqVectors']==63 and irq['isrMulInstructions']==30870
    assert irq['nonzeroR1Interrupts']>0 and irq['t0Interrupts']>0 and irq['t1Interrupts']>0
    for key in ['everyInstructionBoundaryIncludingInternalRetPreempted','all32RegistersAndSregRestoredAtReti','interruptReturnPcAndSpExact']:assert irq[key]
    assert read(reports/'twin-single-identity.json')['singleStageUnitByteIdentical']
    identity=read(reports/'twin-c-player-identity.json');assert identity['imagesByteIdentical']==62 and len(identity['images'])==62
    previous={load:{Path(r['input']['file']).stem:r['binarySha256'] for r in read(reports/name)['streams']}
        for load,name in [(0,'first-nb-c-normal.json'),(32000,'first-nb-c-load10.json')]}
    for row in identity['images']:assert row['byteIdentical'] and row['sha256']==previous[row['load']][row['name']]
    for row in admission['decoderImages']:
        if row['backend']=='c':assert row['cBaselineIdentical']
    frames=0
    for name,count in [('nb8',9100),('nb8-pitch',4096),('nb8-zero',1024),('nb8-lsp',58),('nb11',11587),('wb98',10563),('wb98-repeats',744),('wb128',10563)]:
        data=read(reports/('twin-'+name+'-asm.json'));assert data['frames']==count;frames+=count
        assert not data['includesInterrupts']
    assert frames==47735
    for corpus in admission['decoderCorpora'].values():
        for row in corpus:
            for path,key in [(row['stream'],'inputSha256'),(row['oracle'],'pcmSha256')]:
                if (ROOT/path).exists():assert digest(ROOT/path)==row[key],path
    image_count=0
    for name,count in admission['pwmImageCounts'].items():
        pwm=read(reports/('twin-pwm-'+name+'.json'));assert len(pwm['streams'])==count and pwm['includesInterrupts']
        for row in pwm['streams']:assert row['passed'] and not row['underruns'] and row['freeSramAtPeak']>0
        image_count+=count
    assert image_count==134
    geometry=read(reports/'twin-geometry.json');legacy=read(reports/'twin-legacy.json')
    assert geometry['calls']==6208 and geometry['selectorAndForcedCExact'] and geometry['fusedAndSeparateExactAgainstUntouchedXiph']
    assert legacy['boundedCalls']==49680 and legacy['overlappingLpcOutputs']==12288 and legacy['exactAgainstUntouchedXiphOnAvr']
    portable=read(reports/'twin-portable.json');assert portable['testedStaticArchives']==2 and portable['higherProfiles']['frames']==22150
    replay=read(reports/'twin-replay.json');assert replay['runtimeSourcesCanonicalExact'] and replay['nb8BinaryExact']
    assert replay['binarySha256']==next(r['sha256'] for r in admission['decoderImages'] if r['mode']=='nb8' and r['backend']=='asm')
    if args.avr_gcc:
        out=ROOT/'build/twin-audit-rebuild';out.mkdir(parents=True,exist_ok=True)
        for row in admission['decoderImages']:
            if row['mode'].startswith('nb'):
                build.avr(args.avr_gcc,backend=row['backend'],packet_bytes=20 if row['mode']=='nb8' else 28)
                image=ROOT/'build/profile/speex-test.bin'
            else:
                folder=build_wb.avr(args.avr_gcc,row['backend'],packet_bytes=25 if row['mode']=='wb98' else 32,destination=out/'wb')
                image=folder/'wb.bin'
            assert digest(image)==row['sha256'],row
        for backend in ['asm','c','irq']:
            directory=out/backend
            subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build_lsp_pair_test.py'),'--avr-gcc',args.avr_gcc,'--out',str(directory),
                *(['--irq'] if backend=='irq' else ['--backend',backend])],check=True)
            report=read(reports/('twin-irq.json' if backend=='irq' else 'twin-unit-'+backend+'.json'))
            assert digest(directory/'unit.bin')==report['binarySha256']
        subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build_lsp_stage_test.py'),'--avr-gcc',args.avr_gcc,'--backend','asm','--out',str(out/'single')],check=True)
        assert digest(out/'single/stage.bin')==read(reports/'twin-single-identity.json')['binarySha256']
    print('PASS: paired LSP source/ABI/IRQ/PCM/PWM/C-package admission'+('; twelve firmware rebuilds identical' if args.avr_gcc else ''))
if __name__=='__main__':main()
