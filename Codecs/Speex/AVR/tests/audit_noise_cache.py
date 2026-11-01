#!/usr/bin/env python3
"""Audit source-bound exact cache lifetime, mixed PCM and active-output evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,help='Optional lower-profile corpus for input/oracle hash checks')
    p.add_argument('--avr-gcc',help='Optionally rebuild five final decoder/IRQ/SPI images')
    p.add_argument('--spi-stream',type=Path)
    p.add_argument('--higher-stream',type=Path)
    args=p.parse_args();admission=read('noise-cache-admission.json')
    base=read('noise-speed-admission.json')
    assert sha(ROOT/'reports/noise-speed-admission.json')==admission['baselineAdmissionSha256']
    changed=sorted(name for name,value in base['sourceSha256'].items() if sha(ROOT/name)!=value)
    assert changed==sorted(['src/lowrate_excitation.h','src/lowrate_noise.c','src/lowrate_noise.h',
                            'src/speex_avr.c','src/speex_wb1.c','src/wb_internal.h']),changed
    for name,value in admission['sourceSha256'].items():assert sha(ROOT/name)==value,name
    for name,value in admission['reportSha256'].items():assert sha(ROOT/'reports'/name)==value,name
    for name,value in read('spi-input-admission.json')['sourceSha256'].items():
        assert sha(ROOT.parents[2]/name)==value,name
    pipeline=read('noise-cache-pipeline.json')
    assert pipeline['frames']==1024 and pipeline['cacheFrames']==205 and pipeline['expandedBlocks']==820
    assert pipeline['calls']==dict(vocoder=205,values5=205,indices40=820,cached40=820)
    assert pipeline['cacheBytes']==170 and pipeline['firstDelayedInputByte']==210 and pipeline['nextHistorySourceByte']==320
    assert pipeline['guardBytes']==40 and pipeline['seedAdvancesOnce'] and pipeline['resetClearsCache']
    assert pipeline['cacheAndDelayedHistoryPreserved'] and pipeline['pcmExact']
    after,before=read('noise-cache-wb395.json'),read('noise-speed-wb395.json')
    assert after['frames']==before['frames']==10627 and len(after['streams'])==18
    assert after['meanCycles']<before['meanCycles'] and after['maxCycles']<before['maxCycles']
    assert after['staticSramBytes']==before['staticSramBytes']-4
    assert after['peakStack']==before['peakStack']-11
    assert after['flashBytes']==before['flashBytes']-78
    for a,b in zip(after['streams'],before['streams']):
        assert a['name']==b['name'] and a['frames']==b['frames'] and a['reset'] and a['pcmExact']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile']!='wb395':continue
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:
                path=args.corpus/'wb395'/folder/(Path(row['stream']).stem+suffix)
                assert sha(path,False)==row[key],path
    for label,load in [('normal',0),('load8',25600)]:
        irq=read('noise-cache-irq-'+label+'.json')
        assert irq['frames']==10627 and len(irq['streams'])==18
        assert irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==load and irq['underruns']==0
        for row in irq['streams']:
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
            assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
    for mode,count,byte_count in [('wb395',3600,36000),('wb128',2200,70400)]:
        spi=read('noise-cache-spi-'+mode+'.json')
        assert spi['passed'] and spi['frames']==count and spi['input']['streamBytes']==byte_count
        assert spi['pwmExact'] and spi['includesInterrupts'] and spi['underruns']==0
        assert spi['fullHistoryWithoutReset'] and spi['freeSramAtPeak']>0
        stats=spi['modelStats'];assert stats['readBytes']==byte_count
        assert stats['transferCalls']==stats['selectedBytes']==byte_count+5
        assert stats['unsupportedCommands']==0 and stats['commandBytes']==stats['dummyBytes']==1
        reference='noise-speed-spi.json' if mode=='wb395' else 'spi-input-wb128.json'
        assert spi['pwmSha256']==read(reference)['pwmSha256']
        if mode=='wb128':assert spi['s16Exact']
    for mode,rejects in [('nb',6144),('wb',7168)]:
        api=read('noise-cache-api-'+mode+'.json')
        assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
    identity=read('noise-cache-identities.json')
    assert identity['nbOnly']['byteIdentical'] and not identity['nbOnly']['freshDecoderRun']
    assert identity['nbOnly']['retainedFrames']==10627
    assert len(identity['minimalAsm'])==4 and all(row['byteIdentical'] for row in identity['minimalAsm'])
    assert identity['cDecoderExecuted'] is False and len(identity['cImages'])==2
    export=read('noise-cache-export.json');assert not export['handwrittenAssembly'] and not export['duplicateSources']
    if args.avr_gcc:
        if not args.spi_stream or not args.higher_stream:p.error('Rebuild requires --spi-stream and --higher-stream')
        sys.path.insert(0,str(ROOT/'tools'));import build_wb
        out=ROOT/'build/cache-rebuild'
        build_wb.avr(args.avr_gcc,'asm',packet_bytes=10,enable_nb4=True,low_rates=7,destination=out/'decoder')
        targets=[('decoder/wb.bin',after['binarySha256'])]
        for label,load in [('normal',0),('load8',25600)]:
            subprocess.run([sys.executable,ROOT/'tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,
                '--packet-bytes','10','--low-rates','7','--enable-nb4','--frame-load-cycles',str(load),
                '--out',out/label],check=True)
            targets.append((label+'/wb.bin',read('noise-cache-irq-'+label+'.json')['binarySha256']))
        for mode,stream in [('wb395',args.spi_stream),('wb128',args.higher_stream)]:
            command=[sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
                '--backend','asm','--wideband','--enable-nb4','--stream',stream,'--out',out/mode]
            if mode=='wb128':command.append('--capture-pcm')
            subprocess.run(command,check=True)
            targets.append((mode+'/player.bin',read('noise-cache-spi-'+mode+'.json')['input']['binarySha256']))
        for name,value in targets:assert sha(out/name,False)==value,name
    print('PASS: exact 170-byte cache, 10627 WB / 21254 IRQ / 5800 SPI frames, mixed modes and preserved C fallback'
          +('; five images rebuilt identically' if args.avr_gcc else ''))


if __name__=='__main__':main()
