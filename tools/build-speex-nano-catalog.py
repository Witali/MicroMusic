#!/usr/bin/env python3
"""Encode three public phrases, capture AVR ASM PCM/PWM, retain verified Nano HEX."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import wave
ROOT=Path(__file__).resolve().parents[1];CODEC=ROOT/'Codecs/Speex/AVR'
sys.path.insert(0,str(CODEC/'tools'))
import build,build_wb
from prepare_real_speech import packets
PROFILES=[dict(id='nb215',band='NB',hz=8000,nominal=2150,width=6,mode=1,mask=4),
          dict(id='wb395',band='WB',hz=16000,nominal=3950,width=10,mode=1,mask=4),
          dict(id='wb98',band='WB',hz=16000,nominal=9800,width=25,mode=3,mask=0)]
CLIPS=['chego','otvechaesh','vinni']
# Arithmetic remains pinned to the core admission; only reviewed I/O routing,
# builders and their timer observers may differ. Those changes are recorded.
HARDWARE_PATHS=['src/player.c','src/wb_player.c','examples/spi_flash_player.c','tests/avr_wb_stream.c',
    'tools/build.py','tools/build_wb.py','tools/build_spi_player.py','tools/build_wb_stream_test.py',
    'tests/verify_player.mjs','tests/verify_wb_player.mjs','tests/verify_spi_player.mjs']


def sha(path,text=False):
    data=path.read_bytes();return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--node',required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--publish',action='store_true')
    p.add_argument('--pwm-pin',type=int,choices=[3,9],default=3,help='Gallery PWM output (default D3, shared with LPX)');args=p.parse_args()
    out=ROOT/'build/speex-nano'/('pwm-'+str(args.pwm_pin));out.mkdir(parents=True,exist_ok=True)
    definitions=json.loads((ROOT/'web-player/speech-examples.json').read_text(encoding='utf-8'))
    admission=CODEC/'reports/prepared-admission.json';baseline=json.loads(admission.read_text(encoding='utf-8'))
    changes={}
    for name,h in baseline['sourceSha256'].items():
        current=sha(CODEC/name,True)
        if current!=h:
            assert name in HARDWARE_PATHS,name
            changes[name]=dict(admittedSha256=h,currentSha256=current)
    sources={(CODEC/name).relative_to(ROOT).as_posix():sha(CODEC/name,True) for name in baseline['sourceSha256']}
    for path in [Path(__file__),CODEC/'tools/capture_examples.mjs',CODEC/'src/avr_audio_output.h',
                 *[CODEC/name for name in HARDWARE_PATHS]]:
        sources[path.relative_to(ROOT).as_posix()]=sha(path,True)
    version=subprocess.check_output([args.ffmpeg,'-version'],text=True).splitlines()[0].split()[2]
    manifest=dict(schema='micromusic-speex-avr-firmware-v1',device='atmega328p',cpuHz=16000000,pwmHz=62500,
        pwmPin=args.pwm_pin,pwmOutput={3:'D3 / PD3 / OC2B',9:'D9 / PB1 / OC1A'}[args.pwm_pin],assemblyEnabled=True,physicalBoardMeasured=False,sourceHashEncoding='text-lf',
        decoderAdmissionSha256=sha(admission,True),sourceSha256=sources,ffmpegVersion=version,encoderComplexity=10,
        hardwareChangesFromAdmission=changes,paddingSeconds=0.08,clips=[],variants=[])

    def invoke(command,log):
        with log.open('w',encoding='utf-8') as f:subprocess.run(list(map(str,command)),stdout=f,stderr=subprocess.STDOUT,check=True)

    decoders={}
    for profile in PROFILES:
        dest=out/'decoders'/profile['id'];wb=profile['band']=='WB'
        (build_wb.avr if wb else build.avr)(args.avr_gcc,backend='asm',packet_bytes=profile['width'],low_rates=profile['mask'],enable_nb4=False,destination=dest)
        decoders[profile['id']]=dest
    retained=[]
    for clip in CLIPS:
        definition=next(x for x in definitions['examples'] if x['id']==clip)
        original=ROOT/'web-player'/definition['originalAudioUrl'];assert sha(original)==definition['originalSha256']
        with wave.open(str(original),'rb') as f:
            assert f.getnchannels()==1 and f.getsampwidth()==2
            source_hz=f.getframerate();source_samples=f.getnframes()
        manifest['clips'].append(dict(id=clip,title=definition['title'],originalAudioUrl=definition['originalAudioUrl'],
            originalSha256=definition['originalSha256'],originalSampleHz=source_hz,originalSamples=source_samples,
            originalPlaybackUrl=f'audio/originals/playback/{clip}.wav'))
        for profile in PROFILES:
            hz=profile['hz'];wb=profile['band']=='WB';folder=out/clip/profile['id'];folder.mkdir(parents=True,exist_ok=True)
            resampled=folder/'input.wav'
            invoke([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',original,'-ac','1','-ar',hz,'-c:a','pcm_s16le','-map_metadata','-1',resampled],folder/'resample.log')
            with wave.open(str(resampled),'rb') as f:
                assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,hz)
                input_samples=f.getnframes();pcm=f.readframes(input_samples)
            assert abs(input_samples/hz-source_samples/source_hz)<=1/hz
            padded=folder/'input-padded.pcm';padded.write_bytes(pcm+bytes(round(hz*.08)*2))
            ogg=folder/'encoded.ogg'
            invoke([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-f','s16le','-ar',hz,'-ac','1','-i',padded,
                '-c:a','libspeex','-b:a',profile['nominal'],'-abr','0','-vad','0','-dtx','0','-frames_per_packet','1',
                '-compression_level','10','-f','ogg',ogg],folder/'encode.log')
            encoded=list(packets(ogg.read_bytes()));header=encoded[0];frames=encoded[2:]
            assert len(header)==80 and header[:8]==b'Speex   '
            h=struct.unpack_from('<9i',header,36)
            assert (h[0],h[1],h[2],h[3],h[4],h[5],h[6],h[7],h[8])==(hz,int(wb),4,1,profile['nominal'],hz//50,0,1,0),h
            assert frames and all(len(x)==profile['width'] and x[0]>>3==profile['mode'] for x in frames)
            raw=folder/(profile['id']+'.spxraw');raw.write_bytes(b''.join(frames))
            samples=len(frames)*(hz//50);assert samples>=input_samples+round(hz*.08)
            reference=folder/'decoder.pcm'
            invoke([args.node,CODEC/'tools/capture_examples.mjs',decoders[profile['id']],raw,reference,*(['--wideband'] if wb else [])],folder/'capture.log')
            player=folder/'player'
            if wb:build_wb.avr(args.avr_gcc,backend='asm',stream=raw,packet_bytes=profile['width'],low_rates=profile['mask'],enable_nb4=False,destination=player,pwm_pin=args.pwm_pin)
            else:build.avr(args.avr_gcc,backend='asm',packet_file=raw,packet_bytes=profile['width'],low_rates=profile['mask'],enable_nb4=False,destination=player,pwm_pin=args.pwm_pin)
            if wb:command=[args.node,CODEC/'tests/verify_wb_player.mjs',raw,player,reference]
            else:command=[args.node,CODEC/'tests/verify_player.mjs',raw,'--firmware',player,'--oracle',reference]
            invoke(command,folder/'player.log')
            report=json.loads((player/'player-verification.json').read_text(encoding='utf-8'));pwm=(player/'player-pwm.u8').read_bytes()
            assert report['passed'] and report['includesInterrupts'] and report['underruns']==0 and len(pwm)==samples
            assert report['samples']==samples and report['flashBytes']<=30720 and report['freeSramAtPeak']>0
            wav=folder/(profile['id']+'.wav')
            with wave.open(str(wav),'wb') as f:
                f.setparams((1,2,hz,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',(v-128)*256) for v in pwm))
            hexfile=player/('wb.hex' if wb else 'speex-player.hex')
            ident=f'speex-nano-{clip}-{profile["id"]}'
            label=f'Speex {profile["band"]} · {str(profile["nominal"]/1000).replace(".",",")} кбит/с'
            row=dict(id=ident,clipId=clip,profile=profile['id'],label=label,band=profile['band'],sampleHz=hz,
                nominalBitrateBps=profile['nominal'],packetBytes=profile['width'],frames=len(frames),samples=samples,
                inputSamples=input_samples,encoderLibraryVersion=header[8:28].rstrip(b'\0').decode('ascii'),
                stream=f'audio/speex-speech/{clip}/{profile["id"]}.spxraw',streamBytes=raw.stat().st_size,streamSha256=sha(raw),
                audio=f'audio/speex-speech/{clip}/{profile["id"]}.wav',audioSha256=sha(wav),pwmSha256=hashlib.sha256(pwm).hexdigest(),
                source=f'firmware/arduino-nano/{ident}.hex',hexSha256=sha(hexfile,True),flashBytes=report['flashBytes'],
                programFlashBytes=report['flashBytes']-raw.stat().st_size,staticSramBytes=report['staticSramBytes'],
                peakStackBytes=report['peakStackBytes'],freeSramAtPeak=report['freeSramAtPeak'],
                timing={k:report[k] for k in ['samples','underruns','includesInterrupts','timerIntervalMinCycles','timerIntervalMaxCycles','minQueuedSamplesBeforeOutput']})
            manifest['variants'].append(row);retained.extend([(raw,ROOT/'web-player'/row['stream']),(wav,ROOT/'web-player'/row['audio']),(hexfile,ROOT/'web-player'/row['source'])])
            print('Verified',ident,'Flash',row['flashBytes'],'free SRAM',row['freeSramAtPeak'],flush=True)
    for name,h in sources.items():assert sha(ROOT/name,True)==h,name
    output=out/'manifest.json';output.write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
    if args.publish:
        for src,dst in retained:
            dst.parent.mkdir(parents=True,exist_ok=True)
            if dst.suffix=='.hex':dst.write_bytes(src.read_bytes().replace(b'\r\n',b'\n'))
            else:shutil.copyfile(src,dst)
        shutil.copyfile(output,ROOT/'web-player/firmware-speex-atmega328p.json')
    print('PASS nine Speex examples: actual ASM decoder/PWM, complete phrases and no underruns; no C decoder execution')


if __name__=='__main__':main()
