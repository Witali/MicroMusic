"""Bind D3/D9 gallery, GPIO, long SPI and compile-only C routing checks."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
CODEC=ROOT/'Codecs/Speex/AVR'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def main():
    gallery=ROOT/'build/speex-nano'
    before=read(CODEC/'reports/nano-d9-output-baseline.json')
    d3=read(gallery/'pwm-3/manifest.json');d9=read(gallery/'pwm-9/manifest.json')
    assert len(before['variants'])==len(d3['variants'])==len(d9['variants'])==9
    comparisons=[]
    for old,a,b in zip(before['variants'],d3['variants'],d9['variants']):
        assert old['id']==a['id']==b['id']
        for key in ['streamSha256','audioSha256','pwmSha256']:
            assert old[key]==a[key]==b[key],(a['id'],key)
        reports=[]
        for pin,row in [(3,a),(9,b)]:
            folder=gallery/f'pwm-{pin}'/row['clipId']/row['profile']/'player'
            report=read(folder/'player-verification.json')
            assert report['passed'] and report['input']['pwmPin']==pin
            assert report['underruns']==0 and report['includesInterrupts']
            assert report['pwmSha256']==row['pwmSha256']
            assert report['freeSramAtPeak']>0
            reports.append(report)
        assert reports[1]['binarySha256']==old['binarySha256'],a['id']
        comparisons.append(dict(id=a['id'],streamSha256=a['streamSha256'],pwmSha256=a['pwmSha256'],
            d9BinaryUnchanged=True,d3=reports[0],d9=reports[1]))
    for name,h in d3['sourceSha256'].items():assert sha(ROOT/name)==h,name
    assert read(ROOT/'web-player/firmware-speex-atmega328p.json')==d3
    gpio=read(CODEC/'build/audio-output/verification.json');assert gpio['passed']
    for name,h in gpio['sourceSha256'].items():assert sha(CODEC/name)==h,name
    fallback=read(ROOT/'build/speex-output/c-link.json')
    assert {(r['pin'],r['profile']) for r in fallback}=={(p,s) for p in [3,9] for s in ['nb215','wb395']}
    assert all(r['compiledAndLinked'] and r['executed'] is False and r['backend']['backend']=='c' for r in fallback)
    spi=[]
    for profile,frames in [('nb215',6000),('wb395',3600)]:
        report=read(ROOT/'build/speex-output'/('spi-d3-'+profile)/'verification.json')
        assert report['passed'] and report['input']['pwmPin']==3 and report['input']['backend']=='asm'
        assert report['frames']==frames and report['underruns']==0 and report['pwmExact']
        assert report['includesInterrupts'] and report['freeSramAtPeak']>0
        assert report['input']['streamBytes']>32768 and report['fullHistoryWithoutReset']
        spi.append(dict(profile=profile,verification=report))
    report=dict(passed=True,scope='Selectable PWM routing; arithmetic pinned to prepared-admission.json',
        decoderAdmissionSha256=d3['decoderAdmissionSha256'],sourceSha256=d3['sourceSha256'],
        baselineSha256=sha(CODEC/'reports/nano-d9-output-baseline.json'),
        arithmeticSourceChanges=False,hardwareChangesFromAdmission=d3['hardwareChangesFromAdmission'],
        galleryComparisons=comparisons,gpio=gpio,cFallbackLinkOnly=fallback,spi=spi,
        physicalBoardTested=False,fullCDecoderExecuted=False)
    path=CODEC/'reports/nano-output-routing.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('PASS 18 IRQ gallery images, 9 unchanged D9 binaries, exact D3/D9 PWM, 9600 SPI frames, four C compile/link checks')


if __name__=='__main__':main()
