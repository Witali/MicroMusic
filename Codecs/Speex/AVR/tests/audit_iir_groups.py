"""Audit grouped IIR/warm-cache/cosine admission; optionally rebuild 17 images.

Text hashes normalize CRLF to LF. Firmware hashes use raw bytes. Rebuilding
checks identity with executed images, not a fresh PWM simulation.
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc');args=p.parse_args()
    build.verify_sources();reports=ROOT/'reports';admission=read(reports/'group4-admission.json');base=admission['baselineGitCommit']
    assert base=='f80752a2b2bad896ad1a4fe3bf6c955dc7b8dfbe'
    assert admission['textHashNormalization']=='CRLF to LF; firmware images remain raw bytes'
    for name,sha in admission['sourceSha256'].items():assert text_digest(ROOT/name)==sha,name
    for name,sha in admission['reportSha256'].items():assert text_digest(reports/name)==sha,name
    before=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert before=={p.name for p in (ROOT/'src').iterdir() if p.is_file()}
    for name in before-{'iir_kernel.inc','lsp_angle.S'}:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert old.replace(b'\r\n',b'\n')==(ROOT/'src'/name).read_bytes().replace(b'\r\n',b'\n'),name
    assert set(admission['candidates'])=={'baseline','warm','groups3','groups4','direct','cosine','grouped','production'}
    for replacements in admission['candidates'].values():
        assert set(replacements)<={'src/iir_kernel.inc','src/lsp_angle.S'}
        for sha in replacements.values():assert hashlib.sha256(admission['sourceText'][sha].encode()).hexdigest()==sha
    for backend in ['asm','c']:
        unit=read(reports/('group4-iir-unit-'+backend+'.json'))
        assert unit['cases']==7374 and unit['calls']==14748 and unit['samplesPerPath']==294960
        assert unit['orders']==[8,10] and unit['statePageLowBytes']==256
        for key in ['selectedAndExplicitProductionCExact','independentBigIntOracle','fullSigned16InputNegationSweep','inPlaceAndSeparate','wholeWorkArenaAndGuardsExact']:assert unit[key]
        if backend=='asm':
            assert unit['calleeSavedAndR1AtRet']==7374 and unit['ownAsmStackBytes']==20
            assert unit['privateAsmCalls']==unit['privateAsmReturns']==25809 and unit['privateReturnsWithNonzeroR1']>0
    irq=read(reports/'group4-iir-irq.json')
    assert irq['injections']==irq['isrMulInstructions']==75479 and irq['nonzeroR1Interrupts']==50102
    assert irq['ownAsmStackBytes']==20 and irq['privateAsmCalls']==irq['privateAsmReturns']==56
    for key in ['everyExecutedBoundaryPreempted','all32RegistersAndSregRestoredAtReti','interruptPcAndSpRestored','traceUnchanged']:assert irq[key]
    angle=read(reports/'group4-angle-unit-asm.json');assert angle['cases']==65536 and angle['calls']==196608 and angle['fullSigned16Domain']
    assert angle['selectedForcedCAndUntouchedXiphExact'] and angle['independentBigIntOracle'] and angle['ownStackBytes']==0
    assert angle['primitiveCyclesIncludingRet']==[{'cycles':123,'calls':45636},{'cycles':130,'calls':19900}]
    airq=read(reports/'group4-angle-irq.json');assert airq['injections']==1533 and airq['nonzeroR1Interrupts']==737
    assert airq['all32RegistersAndSregRestoredAtReti'] and airq['interruptReturnPcAndSpExact']
    for row in read(reports/'group4-unit-bindings.json'):
        name='group4-'+row['family']+('-irq.json' if row['mode']=='irq' else '-unit-'+row['mode']+'.json')
        assert row['byteIdentical'] and row['binarySha256']==read(reports/name)['binarySha256']
    old=read(reports/'group4-iir-cursor-before.json');new=read(reports/'group4-iir-cursor.json')
    assert new['calls']==16384 and new['samples']==655360 and len(new['rows'])==len(old['rows'])==512
    for key in ['exact','calleeSavedRegistersPreserved','zeroRegisterRestored','guardsIntact','inputsAndCoefficientsPreserved']:assert new[key]
    for a,b in zip(old['rows'],new['rows']):
        assert (a['inPlace'],a['baseLow'],a['blocks'])==(b['inPlace'],b['baseLow'],b['blocks'])
        assert a['minCycles']-b['minCycles']==a['maxCycles']-b['maxCycles']==247 and a['totalCycles']-b['totalCycles']==32*247
    wide=read(reports/'group4-iir-wide.json');assert wide['samples']==327680 and wide['exact'] and wide['bufferGuardsIntact']
    total=0
    for name,frames in [('nb8',9100),('nb8-pitch',4096),('nb8-zero',1024),('nb8-lsp',58),('nb11',11587),('wb98',10563),('wb98-repeats',744),('wb128',10563)]:
        current=read(reports/('group4-'+name+'-asm.json'));previous=read(reports/('seed-'+name+'-asm.json'))
        assert current['frames']==previous['frames']==frames;total+=frames
        saved,extra=(988,40) if name.startswith('nb') else (1940,72)
        assert len(current['streams'])==len(previous['streams']) and current['staticSramBytes']==previous['staticSramBytes']
        for a,b in zip(previous['streams'],current['streams']):
            assert a.get('stream',a.get('name'))==b.get('stream',b.get('name')) and a['frames']==b['frames']
            for key in ['minCycles','maxCycles','meanCycles']:assert saved<=a[key]-b[key]<=saved+extra,(name,key)
    assert total==47735
    for rows in admission['decoderCorpora'].values():
        for row in rows:
            for path,key in [(row['stream'],'inputSha256'),(row['oracle'],'pcmSha256')]:
                if (ROOT/path).exists():assert digest(ROOT/path)==row[key],path
    counts={'nb8-normal':31,'nb8-load40':31,'nb11-normal':2,'nb11-load40':2,'wb98-normal':16,'wb98-load5':2,'wb128-normal':48,'wb128-load5':2,'wb98-load8':16,'wb128-load8':48}
    assert admission['pwmImageCounts']==counts and admission['freshPwmImages']==198
    for name,count in counts.items():
        data=read(reports/('group4-pwm-'+name+'.json'));assert data['includesInterrupts'] and len(data['streams'])==count
        for row in data['streams']:assert row['passed'] and row['underruns']==0 and row['freeSramAtPeak']>0
    for mode,width in [('wb98',25),('wb128',32)]:
        data=read(reports/('group4-stream-'+mode+'.json'));assert data['packetBytes']==width and data['frames']==10563
        assert data['includesInterrupts'] and data['extraCpuCyclesPerFrame']==25600 and data['underruns']==0
        corpus={Path(r['stream']).name:r for r in admission['decoderCorpora'][mode]};assert len(data['streams'])==len(corpus)==17
        for row in data['streams']:
            other=corpus.pop(row['stream']);assert row['fullHistoryWithoutChunkReset'] and row['s16AndPwmExact'] and row['underruns']==0
            assert row['frames']==row['measuredLoads']==other['frames']
            assert (row['inputSha256'],row['pcmSha256'])==(other['inputSha256'],other['pcmSha256'])
            assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
    identity=read(reports/'group4-c-player-identity.json');assert identity['imagesByteIdentical']==len(identity['images'])==62
    previous={load:{Path(r['input']['file']).stem:r['binarySha256'] for r in read(reports/name)['streams']}
        for load,name in [(0,'first-nb-c-normal.json'),(32000,'first-nb-c-load10.json')]}
    for row in identity['images']:assert row['byteIdentical'] and row['sha256']==previous[row['load']][row['name']]
    old_admission=json.loads(subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/reports/seed-admission.json'],cwd=ROOT))
    old_images={(r['mode'],r['backend']):r['sha256'] for r in old_admission['decoderImages']}
    assert len(admission['decoderImages'])==8 and {(r['mode'],r['backend']) for r in admission['decoderImages']}==set(old_images)
    for image in admission['decoderImages']:
        if image['backend']=='c':assert image['cBaselineIdentical'] and image['sha256']==old_images[image['mode'],'c']
    replay=read(reports/'group4-replay.json');assert replay['pinnedRuntimeSourcesExact']
    expected={r['sha256'] for r in admission['decoderImages'] if r['backend']=='asm' and r['mode'] in ['nb8','wb128']}
    assert {r['binarySha256'] for r in replay['reconstructedDecoderImages']}==expected and all(r['byteIdentical'] for r in replay['reconstructedDecoderImages'])
    if args.avr_gcc:
        out=ROOT/'build/group4-audit-rebuild';out.mkdir(parents=True,exist_ok=True)
        for row in admission['decoderImages']:
            if row['mode'].startswith('nb'):
                build.avr(args.avr_gcc,backend=row['backend'],packet_bytes=20 if row['mode']=='nb8' else 28);image=ROOT/'build/profile/speex-test.bin'
            else:
                directory=build_wb.avr(args.avr_gcc,row['backend'],packet_bytes=25 if row['mode']=='wb98' else 32,destination=out/'wb');image=directory/'wb.bin'
            assert digest(image)==row['sha256'],row
        for family in ['iir','angle']:
            for mode in ['asm','c','irq']:
                directory=out/(family+'-'+mode);tool='build_iir_block_test.py' if family=='iir' else 'build_lsp_angle_test.py'
                subprocess.run([sys.executable,'-X','utf8',ROOT/'tools'/tool,'--avr-gcc',args.avr_gcc,'--out',directory,*(['--irq'] if mode=='irq' else ['--backend',mode])],check=True)
                assert digest(directory/'unit.bin')==read(reports/('group4-'+family+('-irq.json' if mode=='irq' else '-unit-'+mode+'.json')))['binarySha256']
        for mode,width in [('wb98',25),('wb128',32)]:
            directory=out/('stream-'+mode)
            subprocess.run([sys.executable,'-X','utf8',ROOT/'tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,'--packet-bytes',str(width),'--out',directory],check=True)
            assert digest(directory/'wb.bin')==read(reports/('group4-stream-'+mode+'.json'))['binarySha256']
        subprocess.run([sys.executable,'-X','utf8',ROOT/'tools/build_iir_test.py','--avr-gcc',args.avr_gcc],check=True)
        assert digest(ROOT/'build/iir/iir.bin')==new['binarySha256']
    print('PASS: grouped IIR/cosine source, C/ASM/IRQ/corpus/PWM admission'+('; seventeen firmware rebuilds identical' if args.avr_gcc else ''))
if __name__=='__main__':main()
