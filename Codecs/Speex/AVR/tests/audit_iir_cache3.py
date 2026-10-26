#!/usr/bin/env python3
"""Bind third-LPC-cache measurements to binaries, frozen sources and PCM/PWM."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
import build
import build_wb
from verify_nb_players import source_hashes as nb_hashes
from verify_wb_players import source_hashes as wb_hashes


def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc')
    parser.add_argument('--rebuild',action='store_true',help='Rebuild representative images byte-identically')
    args=parser.parse_args()
    if args.rebuild and not args.avr_gcc:parser.error('--rebuild requires --avr-gcc')
    build.verify_sources();report_dir=ROOT/'reports';images=[];reports={}
    baseline_kernel=subprocess.check_output(['git','show','61a51e6:Codecs/Speex/AVR/src/iir_kernel.inc'],cwd=ROOT)
    assert (ROOT/'build/cache3-unit-baseline/src/iir_kernel.inc').read_bytes()==baseline_kernel
    for p in (ROOT/'src').iterdir():
        if p.is_file() and p.name!='iir_kernel.inc':
            assert p.read_bytes()==(ROOT/'build/cache3-unit-baseline/src'/p.name).read_bytes()
    def retain(name,path):
        data=read(path);shutil.copyfile(path,report_dir/('iir-cache3-'+name+'.json'))
        reports[name]=data;return data
    before=read(ROOT/'build/cache3-unit-baseline/build/iir/cursor-verification.json')
    after=retain('unit',ROOT/'build/iir/cursor-verification.json')
    assert before['calls']==after['calls']==16384 and after['baseLowValues']==256
    for key in ['exact','calleeSavedRegistersPreserved','zeroRegisterRestored','guardsIntact',
                'inputsAndCoefficientsPreserved','pageCrossingsCovered']:
        assert before[key] and after[key]
    assert len(before['rows'])==len(after['rows'])==512
    for a,b in zip(before['rows'],after['rows']):
        assert (a['inPlace'],a['baseLow'])==(b['inPlace'],b['baseLow'])
        assert a['minCycles']-b['minCycles']==a['maxCycles']-b['maxCycles']==111
        assert a['totalCycles']-b['totalCycles']==32*111
    wide=retain('wide-unit',ROOT/'build/iir/verification.json')
    assert wide['exact'] and wide['samples']==327680 and wide['bufferGuardsIntact']
    kernels=retain('wb-kernels',ROOT/'build/wb-kernels/verification.json')
    assert len(kernels['streams'])==8 and all(r['pcmExact'] and r['guards'] for r in kernels['streams'])
    retain('backend-selection',ROOT/'build/backend-selection.json')
    portable=retain('portable',ROOT/'build/portable-library.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert read(ROOT/'build/cache3-oracle-before.json')==read(ROOT/'build/cache3-corpus/manifest.json')
    manifest=read(ROOT/'build/cache3-corpus/manifest.json')
    assert manifest['frames']==9100 and len(manifest['streams'])==31
    for row in manifest['streams']:
        assert digest(ROOT/'build/cache3-corpus/streams'/row['stream'])==row['inputSha256']
        assert digest(ROOT/'build/cache3-corpus/oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    old_rows={r['stream']:r for n in ['fixtures','speech']
              for r in read(report_dir/('long40-asm-'+n+'.json'))['streams']}
    full=retain('nb-corpus',ROOT/'build/cache3-full/avr-verification.json')
    assert full['frames']==9100 and set(old_rows)=={r['stream'] for r in full['streams']}
    pairs=[(old_rows[r['stream']],r) for r in full['streams']]
    for name in ['pitch','zero','lsp']:
        current=retain('nb-'+name,ROOT/('build/cache3-'+name+'/avr-verification.json'))
        old={r['stream']:r for r in read(report_dir/('long40-asm-'+name+'.json'))['streams']}
        pairs += [(old[r['stream']],r) for r in current['streams']]
        assert current['binarySha256']==full['binarySha256']
    assert sum(b['frames'] for a,b in pairs)==14278
    for a,b in pairs:
        assert a['frames']==b['frames'] and b['resetVerified']
        assert all(a[k]-b[k]==444 for k in ['minCycles','meanCycles','maxCycles'])
        assert (a['stackBytes'],a['freeSramAtPeak'])==(b['stackBytes'],b['freeSramAtPeak'])
    decoder=ROOT/'build/cache3-decoder/speex-test.bin'
    assert digest(decoder)==full['binarySha256']
    c_digest=digest(ROOT/'build/cache3-c-decoder/speex-test.bin')
    assert c_digest=='46a3f066f72a32de1496f9969bc27c8f182d83abacb4c4b275cfd3f9bce55faa'
    c_wb_digest=digest(ROOT/'build/cache3-wb-c/wb.bin')
    assert c_wb_digest==read(report_dir/'wb2-c.json')['binarySha256']
    wb=retain('wb-decoder',ROOT/'build/cache3-wb-decoder/verification.json')
    old=read(report_dir/'wb2-asm.json')
    assert wb['frames']==old['frames']==10563
    for a,b in zip(old['streams'],wb['streams']):
        assert a['name']==b['name'] and b['pcmExact'] and b['reset']
        assert a['minCycles']-b['minCycles']==a['maxCycles']-b['maxCycles']==916
    assert old['meanCycles']-wb['meanCycles']==916
    assert digest(ROOT/'build/cache3-wb-decoder/wb.bin')==wb['binarySha256']
    repeats=retain('wb-repeats',ROOT/'build/cache3-wb-repeats/verification.json')
    assert repeats['frames']==744 and repeats['binarySha256']==wb['binarySha256']
    retain('wb-repeats-native',ROOT/'build/wb-speed-repeats/verification.json')
    old_oracle=read(report_dir/'wb2-native.json')
    fresh=retain('fresh-wb-oracle',ROOT/'build/cache3-wb-oracle-proof/native-verification.json')
    assert old_oracle['streams']==fresh['streams']
    for family,matrices in [('nb',['normal','load40']),('wb',['normal','load5'])]:
        for mode in matrices:
            folder=ROOT/'build'/('cache3-'+family+'-'+mode)
            assert read(folder/'source-sha256.json')==(nb_hashes() if family=='nb' else wb_hashes())
            matrix=retain(family+'-'+mode,folder/'player-all.json')
            assert matrix['frames']==(9100 if family=='nb' else 6467 if mode=='normal' else 808)
            assert matrix['underruns']==0 and matrix['includesInterrupts']
            assert matrix['extraCpuCyclesPerFrame']==(128000 if mode=='load40' else 16000 if mode=='load5' else 0)
            for row in matrix['streams']:
                name=Path(row['input']['file']);image=folder/name.stem
                binary=image/('speex-player.bin' if family=='nb' else 'wb.bin')
                pcm_root=ROOT/'build'/('cache3-corpus' if family=='nb' else 'wb-corpus')
                assert digest(pcm_root/'streams'/name)==row['input']['sha256']
                assert digest(binary)==row['binarySha256']
                expected=bytes(b^128 for b in (pcm_root/'oracle'/(name.stem+'.pcm')).read_bytes()[1::2])
                assert (image/'player-pwm.u8').read_bytes()==expected
                assert hashlib.sha256(expected).hexdigest()==row['pwmSha256']
                assert row['staticSramBytes']+row['peakStackBytes']+row['freeSramAtPeak']==2048
                assert row['underruns']==0 and row['minQueuedSamplesBeforeOutput']>0
                if mode!='normal':assert row['measuredExtraLoadCount']==row['frames']
                images.append(dict(image=binary.relative_to(ROOT).as_posix(),sha256=row['binarySha256']))
    rebuilt=[]
    if args.rebuild:
        out=ROOT/'build/cache3-rebuild';out.mkdir(exist_ok=True)
        build.avr(args.avr_gcc,backend='asm')
        assert digest(ROOT/'build/profile/speex-test.bin')==full['binarySha256']
        for family in ['nb','wb']:
            for mode in ['normal','loaded']:
                name='speech_ru' if family=='nb' else 'ru_pushkin_a'
                load=(128000 if family=='nb' else 16000) if mode=='loaded' else 0
                stream=ROOT/'build'/('cache3-corpus' if family=='nb' else 'wb-corpus')/'streams'/(name+'.spxraw')
                folder=ROOT/'build'/('cache3-'+family+'-'+('normal' if mode=='normal' else 'load40' if family=='nb' else 'load5'))/name
                if family=='nb':
                    build.avr(args.avr_gcc,stream,load,'asm');new=ROOT/'build/player/speex-player.bin'
                    expected=folder/'speex-player.bin'
                else:
                    fresh=build_wb.avr(args.avr_gcc,'asm',stream,load,out/(family+'-'+mode))
                    new=fresh/'wb.bin';expected=folder/'wb.bin'
                assert digest(new)==digest(expected);rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(new)))
        fresh=build_wb.avr(args.avr_gcc,'asm',destination=out/'wb-decoder')
        assert digest(fresh/'wb.bin')==wb['binarySha256']
    mean_before=sum(a['frames']*a['meanCycles'] for a,b in pairs[:31])/9100
    mean_after=sum(b['frames']*b['meanCycles'] for a,b in pairs[:31])/9100
    result=dict(scope='ATmega328P; exact NB3 and compact WB PCM; ISA simulation, not physical board',
        nbFrames=14278,wbDecoderFrames=10563,nbSavedCyclesPerFrame=444,
        iirOrder10SavedCyclesPerBlock=111,iirOrder8SavedCyclesPerBlock=118,
        beforeMeanCycles=mean_before,afterMeanCycles=mean_after,
        meanCyclesSavedPercent=100*(1-mean_after/mean_before),
        beforeMaxCycles=122066,afterMaxCycles=full['maxCycles'],
        flashBytes=full['flashBytes'],staticSramBytes=full['staticSramBytes'],
        unchangedCDecoderSha256=c_digest,all512AddressModePairsSave111Cycles=True,
        unchangedWbCDecoderSha256=c_wb_digest,
        frozenPlayerImages=images,representativeImagesRebuilt=rebuilt,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),physicalBoardTested=False,
        beforeUnitBinarySha256=before['binarySha256'],afterUnitBinarySha256=after['binarySha256'])
    result['baselineKernelGitCommit']='61a51e6'
    result['beforeKernelSourceSha256']=hashlib.sha256(baseline_kernel).hexdigest()
    result['afterKernelSourceSha256']=digest(ROOT/'src/iir_kernel.inc')
    (report_dir/'iir-cache3-admission.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(images),'frozen player images; NB saved 444 cycles/frame; unchanged C image')


if __name__=='__main__':main()
