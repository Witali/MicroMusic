"""Rebuild final native sources, compare retained PCM and switch packet modes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args):subprocess.run([str(a) for a in args],check=True,capture_output=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);args=p.parse_args()
    out=ROOT/'build/higher-native-final';out.mkdir(exist_ok=True)
    build.host(args.cc,'profile',enable_nb4=True);shutil.copyfile(ROOT/'build/profile/decode.exe',out/'nb.exe')
    build_wb.host(args.cc,enable_nb4=True);shutil.copyfile(ROOT/'build/wb-native/decode.exe',out/'wb.exe')
    manifest=json.loads((ROOT/'build/higher-corpus/manifest.json').read_text(encoding='utf-8'));rows=[]
    for row in manifest['streams']:
        folder=ROOT/'build/higher-corpus'/row['family'];stream=folder/'streams'/row['stream']
        oracle=folder/'oracle'/(stream.stem+'.pcm');assert digest(stream)==row['inputSha256'] and digest(oracle)==row['pcmSha256']
        actual=out/'actual.pcm';run([out/('nb.exe' if row['family']=='nb4' else 'wb.exe'),stream,actual,row['packetBytes']])
        assert actual.read_bytes()==oracle.read_bytes();rows.append(dict(row,finalSourcePcmExact=True))
    # The opt-in build must still decode both old profiles, not only mode 4.
    legacy=[]
    for wb,streams,oracle_dir,width in [(False,ROOT/'build/real-speech/streams',None,20),(True,ROOT/'build/wb-corpus/streams',ROOT/'build/wb-corpus/oracle',25)]:
        for stream in sorted(streams.glob('*.spxraw')):
            actual=out/'actual.pcm';run([out/('wb.exe' if wb else 'nb.exe'),stream,actual,width])
            oracle=oracle_dir/(stream.stem+'.pcm') if wb else out/'oracle.pcm'
            if not wb:run([ROOT/'build/reference/decode.exe',stream,oracle,width])
            assert actual.read_bytes()==oracle.read_bytes();legacy.append(dict(wb=wb,stream=stream.name,frames=actual.stat().st_size//(640 if wb else 320)))
    source=build_wb.prepare()
    production=out/'mixed.exe';run([args.cc,*build_wb.flags(source,'c'),'-O2',*build_wb.sources(source),ROOT/'tests/decode_mixed.c','-o',production])
    reference=ROOT/'build/wb-reference/source';units=build.SOURCES+['modes_wb','sb_celp','high_lsp_tables','hexc_table','hexc_10_32_table']
    oracle=out/'mixed-reference.exe';defs=[d for d in build.DEFINES if d!='DISABLE_WIDEBAND']
    run([args.cc,'-O2','-fwrapv','-fno-strict-aliasing','-DTEST_REFERENCE',*['-D'+d for d in defs],
        '-I'+str(reference/'include'),'-I'+str(reference/'libspeex'),'-I'+str(ROOT/'tests'),
        *[reference/'libspeex'/(s+'.c') for s in units],ROOT/'tests/wb_oracle_qmf.c',ROOT/'tests/decode_mixed.c','-o',oracle])
    mixed=[]
    for wb,family,width,oldwidth,oldfolder in [(0,'nb4',28,20,ROOT/'build/real-speech/streams'),(1,'wb128',32,25,ROOT/'build/wb-corpus/streams')]:
        for clip in ['ru_pushkin_a','en_letter_a']:
            old=(oldfolder/(clip+'.spxraw')).read_bytes();new=(ROOT/'build/higher-corpus'/family/'streams'/(clip+'.spxraw')).read_bytes()
            data=bytearray();modes=[]
            for i in range(256):
                # Alternate individual frames and longer runs; history never resets.
                high=(i%2==0) if i<128 else (i//7)%2==0
                n=width if high else oldwidth;raw=new if high else old
                data.append(n);data+=raw[i*n:(i+1)*n];modes.append(n)
            path=out/(family+'-'+clip+'.mixed');path.write_bytes(data)
            expected=path.with_suffix('.oracle.pcm');actual=path.with_suffix('.pcm')
            run([oracle,wb,path,expected]);run([production,wb,path,actual]);assert actual.read_bytes()==expected.read_bytes()
            run([production,wb,path,out/'reset.pcm']);assert (out/'reset.pcm').read_bytes()==actual.read_bytes()
            mixed.append(dict(stream=path.name,sha256=digest(path),pcmSha256=digest(actual),frames=256,
                transitions=sum(a!=b for a,b in zip(modes,modes[1:])),invalidCallsBeforeEveryFrame=True,resetReplayExact=True))
    report=dict(higherStreams=rows,legacyStreams=legacy,mixedStreams=mixed,
        sourceSha256={f.relative_to(ROOT).as_posix():digest(f) for f in sorted((ROOT/'src').iterdir()) if f.is_file()},
        physicalBoardTested=False,scope='Native final sources; original Xiph NB/HB with independent compact QMF')
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS: final sources,',sum(r['frames'] for r in rows),'higher frames,',len(legacy),'legacy streams, 1024 mixed frames with rejection/state/reset checks')
if __name__=='__main__':main()
