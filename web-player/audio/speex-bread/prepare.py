"""Prepare only the two fixed Speex derivatives of the already-public phrase."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import wave

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
CODEC=REPO/'Codecs/Speex/AVR'
sys.path.insert(0,str(CODEC/'tools'))
import build
from prepare_real_speech import packets


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def invoke(command,log):
    r=subprocess.run([str(x) for x in command],capture_output=True)
    log.write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('Preparation step failed; inspect ignored log')
    return r.stdout


def extract(ogg,raw,mode,width,nominal):
    """Discard Ogg headers/comments; retain every complete audio packet."""
    data=ogg.read_bytes()
    iterator=iter(packets(data))
    header=next(iterator)
    assert len(header)==80 and header[:8]==b'Speex   '
    version=header[8:28].rstrip(b'\0').decode('ascii')
    assert version=='1.2.1'
    assert struct.unpack_from('<9i',header,36)==(8000,0,4,1,nominal,160,0,1,0)
    next(iterator)  # Container comments are never copied to public streams.
    frames=list(iterator)
    assert len(frames)==121 and all(len(f)==width and f[0]>>3==mode for f in frames)
    raw.write_bytes(b''.join(frames))
    cursor=0
    pages=[]
    while cursor<len(data):
        count=data[cursor+26]
        size=27+count+sum(data[cursor+27:cursor+27+count])
        pages.append(dict(flags=data[cursor+5],granule=struct.unpack_from('<q',data,cursor+6)[0]))
        cursor+=size
    # FFmpeg's Ogg granule subtracts its40-sample encoder lookahead.
    # Raw packet decoding still returns121*160=19360 samples.
    assert pages[-1]['flags']&4 and pages[-1]['granule']==19360-40
    return dict(frames=len(frames),encoderLibraryVersion=version,finalGranule=pages[-1]['granule'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc',required=True)
    ap.add_argument('--ffmpeg',default='ffmpeg')
    ap.add_argument('--ffprobe',default='ffprobe')
    ap.add_argument('--build-dir',type=Path,required=True)
    ap.add_argument('--publish',action='store_true',help='Copy verified outputs only when public destinations are absent')
    a=ap.parse_args()
    out=a.build_dir.resolve()
    if out.exists() or REPO/'build' not in out.parents:
        raise ValueError('Use a fresh directory under repository build/')
    out.mkdir(parents=True)
    original=REPO/'web-player/audio/lpx-bread/original.wav'
    original_digest=sha(original)
    with wave.open(str(original),'rb') as w:
        assert (w.getnchannels(),w.getframerate(),w.getsampwidth(),w.getnframes())==(1,8000,2,19200)
        pcm=w.readframes(19200)
    assert len(pcm)==38400
    (out/'input-padded.pcm').write_bytes(pcm+bytes(320))
    # Existing builders verify upstream/import provenance before creating
    # their ordinary ignored source copies. No downloads or codec edits.
    _,reference=build.prepare('reference')
    _,project=build.prepare('profile')
    native_files=[p for folder in (reference,project,CODEC/'src') for p in folder.rglob('*') if p.is_file()]
    frozen={str(p.resolve()):sha(p) for p in native_files}
    recipe_files=[HERE/'bread_native.c',Path(__file__),CODEC/'tools/build.py',
                  CODEC/'tools/apply_profile.py',CODEC/'tools/prepare_real_speech.py',
                  *sorted((CODEC/'handoff/upstream/tools').glob('*.py'))]
    frozen.update({str(p.resolve()):sha(p) for p in recipe_files})
    flags=['-x','c','-std=c11','-O2','-fwrapv','-fno-strict-aliasing',
           '-Wno-pointer-to-int-cast','-D_CRT_SECURE_NO_WARNINGS']
    defs=build.DEFINES
    sources=build.SOURCES
    oracle=out/('oracle.exe' if sys.platform=='win32' else 'oracle')
    command=[a.cc,*flags,*['-D'+d for d in defs],'-I'+str(reference/'include'),
             '-I'+str(reference/'libspeex'),*[reference/'libspeex'/(s+'.c') for s in sources],
             HERE/'bread_native.c','-o',oracle]
    if sys.platform!='win32':command.append('-lm')
    invoke(command,out/'oracle-build-private.log')
    production=out/('project.exe' if sys.platform=='win32' else 'project')
    defs=build.DEFINES+['SPEEX_AVR_COMPACT_LSP','SPEEX_AVR_TIGHT_EXC','SPEEX_AVR_PROFILE',
                       'SPEEX_ENABLE_NB1=1','SPEEX_NB3_ENABLE_ASM=0','BREAD_PROJECT']
    command=[a.cc,*flags,*['-D'+d for d in defs],'-I'+str(project/'include'),
             '-I'+str(project/'libspeex'),'-I'+str(CODEC/'src'),
             *[project/'libspeex'/(s+'.c') for s in build.PROFILE_SOURCES],
             *[CODEC/'src'/s for s in ('speex_avr.c','bits.c','lowrate_noise.c')],
             HERE/'bread_native.c','-o',production]
    if sys.platform!='win32':command.append('-lm')
    invoke(command,out/'project-build-private.log')
    manifest=dict(schemaVersion=1,codec='Speex NB',title='«И того, и другого, и можно без хлеба»',
                  sampleRate=8000,samples=19200,durationSeconds=2.4,previewKind='native-pwm8',
                  decoderTarget='atmega328p',reference=dict(audio='audio/lpx-bread/original.wav',
                  label='Исходник · 8 кГц, моно'),variants=[])
    rows=[]
    for name,mode,width,nominal,label in (('compact',1,6,2150,'Компактный'),
                                         ('quality',3,20,8000,'Повышенное качество')):
        raw=out/(name+'.spxraw')
        ogg=out/(name+'.ogg')
        encoder_command=[a.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
                         '-f','s16le','-ar','8000','-ac','1','-i',out/'input-padded.pcm',
                         '-c:a','libspeex','-b:a',nominal,'-abr','0','-vad','0','-dtx','0',
                         '-frames_per_packet','1','-compression_level','3','-f','ogg',ogg]
        invoke(encoder_command,out/(name+'-encode-private.log'))
        encoded=extract(ogg,raw,mode,width,nominal)
        probe=json.loads(invoke([a.ffprobe,'-v','error','-show_entries',
              'packet=pts,duration,size','-of','json',ogg],out/(name+'-ffprobe-private.json')))
        packet_rows=probe['packets']
        assert len(packet_rows)==121 and all(p['duration']==160 and int(p['size'])==width for p in packet_rows)
        encoder_lookahead=-packet_rows[0]['pts']
        assert encoder_lookahead==40 and packet_rows[-1]['pts']==19160
        expected_path=out/(name+'-oracle.pcm')
        reference_row=json.loads(invoke([oracle,'decode',mode,raw,expected_path,19200],out/(name+'-reference-private.log')))
        actual_path=out/(name+'-project.pcm')
        actual_row=json.loads(invoke([production,'decode',mode,raw,actual_path,19200],out/(name+'-project-private.log')))
        expected,actual=expected_path.read_bytes(),actual_path.read_bytes()
        assert expected==actual and len(actual)==encoded['frames']*320
        decoder_lookahead=reference_row['decoderLookahead']
        delay=encoder_lookahead+decoder_lookahead
        assert decoder_lookahead==40 and delay==80
        assert encoded['frames']==121 and raw.stat().st_size==width*encoded['frames']
        assert reference_row['frames']==actual_row['frames']==encoded['frames']
        signal=struct.unpack('<'+'h'*(len(actual)//2),actual)
        aligned=signal[delay:delay+19200]
        assert len(aligned)==19200
        duty=bytes((s>>8)+128 for s in aligned)
        pwm16=b''.join(struct.pack('<h',(v-128)*256) for v in duty)
        wav=out/(name+'.wav')
        with wave.open(str(wav),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(pwm16)
        assert wav.stat().st_size==38444
        with wave.open(str(wav),'rb') as w:
            assert w.getnframes()==19200 and w.getframerate()==8000 and w.readframes(19200)==pwm16
        # Exact44-byte PCM header followed only by data: no metadata chunks.
        assert wav.read_bytes()[12:16]==b'fmt ' and wav.read_bytes()[36:40]==b'data'
        row=dict(id=name,label=label,mode=mode,nominalBitrateBps=nominal,packetBytes=width,
                 packets=encoded['frames'],decodedSamples=len(signal),trimStartSamples=delay,
                 trimEndSamples=len(signal)-delay-19200,audio='audio/speex-bread/'+name+'.wav',
                 stream='audio/speex-bread/'+name+'.spxraw',bytes=raw.stat().st_size,
                 bitrateBps=raw.stat().st_size*8/2.4)
        assert row['decodedSamples']-row['trimStartSamples']-row['trimEndSamples']==19200
        manifest['variants'].append(row)
        rows.append(dict(**row,encoderLookaheadSamples=encoder_lookahead,
                         decoderLookaheadSamples=decoder_lookahead,
                         encoderLibraryVersion=encoded['encoderLibraryVersion'],finalOggGranule=encoded['finalGranule'],
                         meaningfulBitsPerPacket=43 if mode==1 else 160,bytePaddingBitsPerPacket=5 if mode==1 else 0,
                         sourceSamples=19200,encoderInputFrames=121,finalZeroPaddingInputSamples=160,
                         nativeProjectUpstreamPcmExact=True,previewProjectPwmExact=True,
                         previewWavBytes=wav.stat().st_size))
    assert sha(original)==original_digest
    assert all(sha(Path(p))==h for p,h in frozen.items())
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    artifact_names=['manifest.json',*[row['id']+suffix for row in rows for suffix in ('.spxraw','.wav')]]
    comparisons={name:sha(out/name)==sha(HERE/name) for name in artifact_names if (HERE/name).exists()}
    if a.publish:
        if any((HERE/name).exists() for name in artifact_names):
            raise ValueError('Do not overwrite published artifacts')
        for name in artifact_names:
            shutil.copyfile(out/name,HERE/name)
    proof=dict(status='PASS',sourceInput=str(original.resolve()),sourceSha256=sha(original),
               nativeSources=frozen,compiler=a.cc,compilerVersion=subprocess.check_output([a.cc,'--version'],text=True).splitlines()[0],
               binaries={p.name:sha(p) for p in (oracle,production)},variants=rows,
               encoder='FFmpeg libspeex1.2.1, mode1/3 CBR, complexity3, VBR/VAD/DTX off, default encoder highpass',
               ffmpegVersion=subprocess.check_output([a.ffmpeg,'-version'],text=True).splitlines()[0],
               encoderInput='Original PCM16 followed by160 zero samples; no rate, level, or timing change',
               decoder='project native C, enh/highpass off; exact independent upstream fixed point',
               existingPublicArtifactsMatch=comparisons,published=a.publish,
               physicalTargetMeasured=False,noFlashOrTiny88Claim=True)
    (out/'proof-private.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',variants=rows)),flush=True)


if __name__=='__main__':main()
