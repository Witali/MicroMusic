"""Build IRQ-verified Nano dialogue profiles; retain only images fitting 30 KiB."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'Codecs/Speex/AVR'
sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from pcm16_wav import write_pcm16_wav
from dialogue_source import prepare_clips,assemble_dialogue
from pwm_output_level import apply_gain,choose_gain,describe_level
spec=importlib.util.spec_from_file_location('speex_gallery',ROOT/'tools/build-speex-nano-catalog.py')
gallery=importlib.util.module_from_spec(spec);spec.loader.exec_module(gallery)


def sha(path,text=False):
    data=path.read_bytes();return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True);p.add_argument('--node',required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--publish',action='store_true');args=p.parse_args()
    out=ROOT/'build/speex-dialogue';out.mkdir(parents=True,exist_ok=True)
    if out.is_symlink() or any(p.is_symlink() or p.is_junction() for p in out.parents):raise ValueError('Output alias')
    recipe_path=ROOT/'ATmega328/Sound/lpx-dialogue/recipe.json'
    recipe=json.loads(recipe_path.read_text(encoding='utf-8'))
    if recipe['schemaVersion']!=1 or recipe['sampleHz']!=8000:raise ValueError('Expected the public 8 kHz dialogue recipe')
    definitions=json.loads((ROOT/'web-player/speech-examples.json').read_text(encoding='utf-8'))['examples']
    definitions={entry['id']:entry for entry in definitions}
    names=list(dict.fromkeys(item['clip'] for item in recipe['sequence'] if 'clip' in item))
    sources=[ROOT/'web-player'/definitions[name]['originalAudioUrl'] for name in names]
    if any(not p.resolve().is_relative_to(ROOT/'web-player') or sha(p)!=definitions[name]['originalSha256'] for name,p in zip(names,sources)):
        raise ValueError('Canonical public source changed')
    ffmpeg=shutil.which(args.ffmpeg)
    if not ffmpeg:raise ValueError('FFmpeg is required')
    prepared,target=prepare_clips(recipe,names,sources,out/'source',ffmpeg)
    pcm,segments=assemble_dialogue(recipe,prepared)
    source=out/'source.wav';write_pcm16_wav(source,pcm)
    base=json.loads((ROOT/'web-player/firmware-speex-atmega328p.json').read_text(encoding='utf-8'))
    source_hashes=dict(base['sourceSha256'])
    for name,digest in source_hashes.items():
        if sha(ROOT/name,True)!=digest:raise ValueError('Speex source differs from its gallery admission: '+name)
    for path in (Path(__file__),ROOT/'tools/dialogue_source.py',recipe_path,ROOT/'web-player/speech-examples.json',ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/pcm16_wav.py'):
        source_hashes[path.relative_to(ROOT).as_posix()]=sha(path,True)
    manifest=dict(schema='micromusic-speex-dialogue-v1',title=recipe['title'],device='atmega328p',cpuHz=16000000,
        pwmHz=62500,pwmPin=3,pwmOutput='D3 / PD3 / OC2B',flashLimitBytes=30720,assemblyEnabled=True,
        physicalBoardMeasured=False,decoderAdmissionSha256=base['decoderAdmissionSha256'],
        sourceHashEncoding='text-lf',sourceSha256=source_hashes,sourceSamples=len(pcm),sourceSampleHz=8000,
        sourcePcmSha256=hashlib.sha256(pcm.astype('<i2').tobytes()).hexdigest(),segments=segments,
        sources=[dict(clipId=name,source=definitions[name]['originalAudioUrl'],sourceSha256=definitions[name]['originalSha256'],
                      gainDb=prepared[name][4],normalized=prepared[name][3]) for name in names],
        targetLufs=target,paddingSeconds=.08,variants=[])

    def invoke(command,log):
        with log.open('w',encoding='utf-8') as f:subprocess.run(list(map(str,command)),stdout=f,stderr=subprocess.STDOUT,check=True)

    retained=[]
    for profile in gallery.PROFILES:
        ident='speex-nano-dialogue-'+profile['id'];folder=out/profile['id'];folder.mkdir(exist_ok=True)
        hz=profile['hz'];wb=profile['band']=='WB';decoder=folder/'decoder'
        (gallery.build_wb.avr if wb else gallery.build.avr)(args.avr_gcc,backend='asm',packet_bytes=profile['width'],
            low_rates=profile['mask'],enable_nb4=False,destination=decoder)
        resampled=folder/'input.wav'
        invoke([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',source,'-ac','1','-ar',hz,
                '-c:a','pcm_s16le','-map_metadata','-1',resampled],folder/'resample.log')
        with wave.open(str(resampled),'rb') as f:
            assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,hz)
            input_samples=f.getnframes();raw_pcm=f.readframes(input_samples)
        assert abs(input_samples/hz-len(pcm)/8000)<=1/hz
        padded=folder/'input.pcm';padded.write_bytes(raw_pcm+bytes(round(hz*.08)*2))
        ogg=folder/'encoded.ogg'
        invoke([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-f','s16le','-ar',hz,'-ac','1','-i',padded,
                '-c:a','libspeex','-b:a',profile['nominal'],'-abr','0','-vad','0','-dtx','0','-frames_per_packet','1',
                '-compression_level','10','-f','ogg',ogg],folder/'encode.log')
        encoded=list(gallery.packets(ogg.read_bytes()));header=encoded[0];frames=encoded[2:]
        assert len(header)==80 and header[:8]==b'Speex   '
        assert struct.unpack_from('<9i',header,36)==(hz,int(wb),4,1,profile['nominal'],hz//50,0,1,0)
        assert frames and all(len(frame)==profile['width'] and frame[0]>>3==profile['mode'] for frame in frames)
        raw=folder/(profile['id']+'.spxraw');raw.write_bytes(b''.join(frames))
        reference=folder/'decoder.pcm'
        invoke([args.node,CODEC/'tools/capture_examples.mjs',decoder,raw,reference,*(['--wideband'] if wb else [])],folder/'capture.log')
        raw_pwm=bytes(value^128 for value in reference.read_bytes()[1::2])
        gain=choose_gain(raw_pwm);level=describe_level(raw_pwm,gain);player=folder/'player'
        if wb:gallery.build_wb.avr(args.avr_gcc,backend='asm',stream=raw,packet_bytes=profile['width'],low_rates=profile['mask'],enable_nb4=False,destination=player,pwm_pin=3,output_gain=gain)
        else:gallery.build.avr(args.avr_gcc,backend='asm',packet_file=raw,packet_bytes=profile['width'],low_rates=profile['mask'],enable_nb4=False,destination=player,pwm_pin=3,output_gain=gain)
        binary=player/('wb.bin' if wb else 'speex-player.bin');hexfile=binary.with_suffix('.hex')
        size=binary.stat().st_size;samples=len(frames)*(hz//50)
        row=dict(id=ident,profile=profile['id'],label=f'Speex {profile["band"]} · {str(profile["nominal"]/1000).replace(".",",")} кбит/с',
            band=profile['band'],sampleHz=hz,nominalBitrateBps=profile['nominal'],packetBytes=profile['width'],
            frames=len(frames),samples=samples,inputSamples=input_samples,streamBytes=raw.stat().st_size,
            flashBytes=size,programFlashBytes=size-raw.stat().st_size,outputLevel=level,available=size<=30720)
        if size>30720:
            row['unavailableReason']='Не помещается во Flash Arduino Nano'
            manifest['variants'].append(row);print(ident,'disabled:',size,'bytes',flush=True);continue
        command=[args.node,CODEC/'tests/verify_wb_player.mjs',raw,player,reference] if wb else [args.node,CODEC/'tests/verify_player.mjs',raw,'--firmware',player,'--oracle',reference]
        invoke(command,folder/'player.log')
        report=json.loads((player/'player-verification.json').read_text(encoding='utf-8'));pwm=(player/'player-pwm.u8').read_bytes()
        assert report['passed'] and report['includesInterrupts'] and report['underruns']==0 and len(pwm)==samples
        assert pwm==apply_gain(raw_pwm,gain) and samples>=input_samples+round(hz*.08) and report['freeSramAtPeak']>0
        wav=folder/(profile['id']+'.wav')
        with wave.open(str(wav),'wb') as f:
            f.setparams((1,2,hz,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',(v-128)*256) for v in pwm))
        row.update(source='firmware/arduino-nano/'+ident+'.hex',audio='audio/speex-speech/dialogue/'+wav.name,
            stream='audio/speex-speech/dialogue/'+raw.name,streamSha256=sha(raw),audioSha256=sha(wav),
            pwmSha256=hashlib.sha256(pwm).hexdigest(),hexSha256=sha(hexfile,True),staticSramBytes=report['staticSramBytes'],
            peakStackBytes=report['peakStackBytes'],freeSramAtPeak=report['freeSramAtPeak'],
            timing={key:report[key] for key in ('samples','underruns','includesInterrupts','timerIntervalMinCycles','timerIntervalMaxCycles','minQueuedSamplesBeforeOutput')})
        manifest['variants'].append(row)
        retained.extend([(raw,ROOT/'web-player'/row['stream']),(wav,ROOT/'web-player'/row['audio']),(hexfile,ROOT/'web-player'/row['source'])])
        print('Verified',ident,'Flash',size,'free SRAM',row['freeSramAtPeak'],flush=True)
    for name,digest in source_hashes.items():
        if sha(ROOT/name,True)!=digest:raise ValueError('Sources changed during dialogue build: '+name)
    output=out/'manifest.json';output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    if args.publish:
        for source,dest in retained:
            dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.is_symlink() or dest.exists() and dest.stat().st_nlink>1:raise ValueError('Retained output alias')
            dest.write_bytes(source.read_bytes().replace(b'\r\n',b'\n') if dest.suffix=='.hex' else source.read_bytes())
        shutil.copyfile(output,ROOT/'web-player/firmware-speex-dialogue-atmega328p.json')
    print('PASS dialogue profiles:',sum(v['available'] for v in manifest['variants']),'available,',sum(not v['available'] for v in manifest['variants']),'disabled')


if __name__=='__main__':main()
