"""Audit exact cosine/entry-layout admission and optionally rebuild 15 images.

Source/report text hashes use LF; firmware hashes cover raw bytes. Rebuilds
confirm executable identity, not a fresh execution of the retained PWM tests.
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',help='Also rebuild eight decoder, three cosine, two paired-stage and two streaming-test images');args=p.parse_args()
    build.verify_sources();reports=ROOT/'reports';admission=read(reports/'angle-admission.json')
    assert admission['textHashNormalization']=='CRLF to LF; firmware images remain raw bytes'
    for name,sha in admission['sourceSha256'].items():assert text_digest(ROOT/name)==sha,name
    for name,sha in admission['reportSha256'].items():assert text_digest(reports/name)==sha,name
    base=admission['baselineGitCommit'];changed={'compact_lsp.c.inc','lsp_pair.S','lsp_angle.S','nb3_lsp_angle.h'}
    old_names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {f.name for f in (ROOT/'src').iterdir() if f.is_file()}==old_names|changed
    for name in old_names-changed:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert old.replace(b'\r\n',b'\n')==(ROOT/'src'/name).read_bytes().replace(b'\r\n',b'\n'),name
    for backend in ['asm','c']:
        unit=read(reports/('angle-unit-'+backend+'.json'))
        assert unit['cases']==65536 and unit['calls']==196608 and unit['fullSigned16Domain']
        assert unit['selectedForcedCAndUntouchedXiphExact'] and unit['independentBigIntOracle'] and unit['calleeSavedRegistersAndR1AtRet']
        if backend=='asm':
            assert unit['ownStackBytes']==0 and unit['ramReadsInsideAsm']==0 and unit['ramWritesInsideAsm']==0
            assert unit['primitiveCyclesIncludingRet']==[{'cycles':123,'calls':45636},{'cycles':131,'calls':19900}]
    irq=read(reports/'angle-irq.json')
    assert irq['injections']==1533 and irq['isrMulInstructions']==1533 and irq['nonzeroR1Interrupts']==737
    assert irq['t0Interrupts']>0 and irq['t1Interrupts']>0
    for key in ['all32RegistersAndSregRestoredAtReti','interruptReturnPcAndSpExact','everyInstructionBoundaryPreempted']:assert irq[key]
    pair=read(reports/'angle-pair-unit.json');pair_irq=read(reports/'angle-pair-irq.json')
    assert pair['cases']==257790 and pair['outputsPerPath']==2062320 and pair['primitiveCyclesIncludingRet']=={'2':[460],'3':[634],'4':[804]}
    assert pair_irq['injections']==30828 and pair_irq['everyInstructionBoundaryIncludingInternalRetPreempted']
    for row in read(reports/'angle-unit-bindings.json'):
        expected=read(reports/('angle-irq.json' if row['mode']=='irq' else 'angle-unit-'+row['mode']+'.json'))
        assert row['byteIdentical'] and row['binarySha256']==expected['binarySha256']
    host=read(reports/'angle-host.json')
    assert host['inputsPerConfiguration']==65536 and len(host['configurations'])==3 and host['selectedAndExplicitCExactToUntouchedXiph']
    assert host['headerSha256']==text_digest(ROOT/'src/nb3_lsp_angle.h')
    identity=read(reports/'angle-c-player-identity.json');assert len(identity['images'])==identity['imagesByteIdentical']==62
    previous={load:{Path(r['input']['file']).stem:r['binarySha256'] for r in read(reports/name)['streams']}
        for load,name in [(0,'first-nb-c-normal.json'),(32000,'first-nb-c-load10.json')]}
    for row in identity['images']:assert row['byteIdentical'] and row['sha256']==previous[row['load']][row['name']]
    for row in admission['decoderImages']:
        if row['backend']=='c':assert row['cBaselineIdentical']
    frames=0
    for name,count in [('nb8',9100),('nb8-pitch',4096),('nb8-zero',1024),('nb8-lsp',58),('nb11',11587),('wb98',10563),('wb98-repeats',744),('wb128',10563)]:
        data=read(reports/('angle-'+name+'-asm.json'));assert data['frames']==count;frames+=count
    assert frames==47735
    for corpus in admission['decoderCorpora'].values():
        for row in corpus:
            for path,key in [(row['stream'],'inputSha256'),(row['oracle'],'pcmSha256')]:
                if (ROOT/path).exists():assert digest(ROOT/path)==row[key],path
    images=0
    for name,count in admission['pwmImageCounts'].items():
        pwm=read(reports/('angle-pwm-'+name+'.json'));assert len(pwm['streams'])==count and pwm['includesInterrupts']
        for row in pwm['streams']:assert row['passed'] and not row['underruns'] and row['freeSramAtPeak']>0
        images+=count
    assert images==admission['freshPwmImages']
    for name in ['wb98-load8','wb128-load8']:
        pwm=read(reports/('angle-pwm-'+name+'.json'));assert pwm['frames']==6467 and pwm['extraCpuCyclesPerFrame']==25600
    for mode,width in [('wb98',25),('wb128',32)]:
        streaming=read(reports/('angle-stream-'+mode+'.json'))
        assert streaming['packetBytes']==width and streaming['frames']==10563 and streaming['includesInterrupts']
        assert streaming['extraCpuCyclesPerFrame']==25600 and streaming['underruns']==0
        assert streaming['freeSramAtPeak']>0 and streaming['minQueuedSamplesBeforeOutput']>0
        corpus={Path(row['stream']).name:row for row in admission['decoderCorpora'][mode]}
        assert len(streaming['streams'])==len(corpus)==17
        for row in streaming['streams']:
            reference=corpus.pop(row['stream'])
            assert row['fullHistoryWithoutChunkReset'] and row['s16AndPwmExact'] and row['underruns']==0
            assert row['frames']==row['measuredLoads']==reference['frames']
            assert row['inputSha256']==reference['inputSha256'] and row['pcmSha256']==reference['pcmSha256']
            assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
        assert not corpus
    geometry=read(reports/'angle-geometry.json');legacy=read(reports/'angle-legacy.json')
    assert geometry['calls']==6208 and geometry['fusedAndSeparateExactAgainstUntouchedXiph']
    assert legacy['boundedCalls']==49680 and legacy['overlappingLpcOutputs']==12288 and legacy['exactAgainstUntouchedXiphOnAvr']
    portable=read(reports/'angle-portable.json');assert portable['testedStaticArchives']==2 and portable['higherProfiles']['frames']==22150
    replay=read(reports/'angle-replay.json');assert replay['pinnedRuntimeSourcesExact']
    expected_replay={r['sha256'] for r in admission['decoderImages'] if r['backend']=='asm' and r['mode'] in ['nb8','wb128']}
    assert {r['binarySha256'] for r in replay['reconstructedDecoderImages']}==expected_replay
    assert all(r['byteIdentical'] for r in replay['reconstructedDecoderImages'])
    if args.avr_gcc:
        out=ROOT/'build/angle-audit-rebuild';out.mkdir(parents=True,exist_ok=True)
        for row in admission['decoderImages']:
            if row['mode'].startswith('nb'):
                build.avr(args.avr_gcc,backend=row['backend'],packet_bytes=20 if row['mode']=='nb8' else 28);image=ROOT/'build/profile/speex-test.bin'
            else:
                folder=build_wb.avr(args.avr_gcc,row['backend'],packet_bytes=25 if row['mode']=='wb98' else 32,destination=out/'wb');image=folder/'wb.bin'
            assert digest(image)==row['sha256'],row
        for mode in ['asm','c','irq']:
            directory=out/('scalar-'+mode)
            subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build_lsp_angle_test.py'),'--avr-gcc',args.avr_gcc,'--out',str(directory),
                *(['--irq'] if mode=='irq' else ['--backend',mode])],check=True)
            expected=read(reports/('angle-irq.json' if mode=='irq' else 'angle-unit-'+mode+'.json'))
            assert digest(directory/'unit.bin')==expected['binarySha256']
        for mode in ['unit','irq']:
            directory=out/('pair-'+mode)
            subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build_lsp_pair_test.py'),'--avr-gcc',args.avr_gcc,'--out',str(directory),
                *(['--irq'] if mode=='irq' else [])],check=True)
            assert digest(directory/'unit.bin')==read(reports/('angle-pair-'+mode+'.json'))['binarySha256']
        for mode,width in [('wb98',25),('wb128',32)]:
            directory=out/('stream-'+mode)
            subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build_wb_stream_test.py'),'--avr-gcc',args.avr_gcc,
                '--packet-bytes',str(width),'--out',str(directory)],check=True)
            assert digest(directory/'wb.bin')==read(reports/('angle-stream-'+mode+'.json'))['binarySha256']
    print('PASS: exact cosine/layout source, C/ASM/IRQ/PCM/PWM admission'+('; fifteen firmware rebuilds identical' if args.avr_gcc else ''))
if __name__=='__main__':main()
