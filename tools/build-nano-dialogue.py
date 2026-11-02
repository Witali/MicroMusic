"""Normalize public speech clips, encode a dialogue and verify one Nano HEX.

All build media and detailed receipts stay in ignored build/. --retain copies
only the verified HEX, exact PWM WAV, compressed segments and path-free receipt.
The existing reset-chain player shares one decoder across speech and silence.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0,str(CODEC/'tools'))
from output_paths import protect_outputs
from profile_avr import linux_path
from pwm_output_level import apply_gain,choose_gain,describe_level
from dialogue_source import loudness,prepare_clips

NATIVE=r'''
#include <stdint.h>
#include <stdio.h>
#include <vector>
#include <fstream>
#include <iterator>
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
 if(argc!=3)return 2;
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> b((std::istreambuf_iterator<char>(f)),{});
 Lpx4HybridCore d;if(b.size()>65535||!d.begin(b.data(),b.size()))return 3;
 FILE* out=fopen(argv[2],"wb");if(!out)return 4;
 int16_t sample;unsigned count=0;
 while(d.nextS16(sample)){
  fputc((uint16_t)sample&255,out);fputc((uint16_t)sample>>8,out);++count;
 }
 fclose(out);return d.error()||!d.finished()||count!=d.samples()?5:0;
}
'''


def sha(data):return hashlib.sha256(data).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


class NativeReference:
    def __init__(self,folder,*,wsl=None,compact=False):
        self.folder=folder;self.wsl=wsl;self.serial=0
        folder.mkdir(parents=True,exist_ok=True)
        source=folder/'decode.cpp';source.write_text(NATIVE,encoding='utf-8',newline='\n')
        self.binary=folder/('decode.exe' if sys.platform=='win32' and not wsl else 'decode')
        flags=['-O2','-std=c++11','-DLPX4_ENABLE_ASM=0','-DLPX4_ENABLE_SPEECH=1',
               '-DLPX4_ENABLE_SPEECH_COMPACT=1','-I'+self.path(CODEC/'src')]
        if compact:flags+=['-DLPX4_COMPACT_ONLY=1']
        self.run('g++',*flags,self.path(source),self.path(CODEC/'src/Lpx4HybridCore.cpp'),'-o',self.path(self.binary))

    def path(self,p):return linux_path(p) if self.wsl else str(p)

    def run(self,*args):
        result=subprocess.run([*(['wsl','-d',self.wsl,'--'] if self.wsl else []),*args],capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout

    def decode_one_s16(self,blob,n):
        import numpy as np
        self.serial+=1;source=self.folder/(str(self.serial)+'.lpx');output=source.with_suffix('.pcm16')
        source.write_bytes(blob);self.run(self.path(self.binary),self.path(source),self.path(output))
        samples=np.frombuffer(output.read_bytes(),dtype='<i2').copy()
        if len(samples)!=n:raise ValueError('Native decoder returned the wrong sample count')
        return samples


def pause_stream(samples):
    from speech_compact import pack
    frames=(samples+319)//320
    # Scale zero gives exact silence; all stored final-packet fields are present.
    return pack(samples,4,[[1+2*i for i in range(10)] for _ in range(frames)],
                [(0,18,0)]*(frames*2),[(0,-8),(1,8)]*(frames*8),pre=13926)[0]


def build(args):
    import numpy as np
    from speech_v4 import encode
    from speech_compact import repack,decode_model
    from standard_metrics import pwm_duties
    from pcm16_wav import write_pcm16_wav
    from build_release_player import simulate

    recipe_path=args.recipe.resolve();recipe=json.loads(recipe_path.read_text(encoding='utf-8'))
    if recipe['schemaVersion']!=1 or recipe['sampleHz']!=8000 or recipe['speechProfile']!=6:
        raise ValueError('Expected an 8 kHz LPX P6 dialogue recipe')
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'build') or output==ROOT/'build':raise ValueError('Use ignored build storage')
    if output.is_symlink() or any(p.is_symlink() or p.is_junction() for p in output.parents):
        raise ValueError('Output aliases are not allowed')
    output.mkdir(parents=True,exist_ok=True)
    definitions=json.loads((ROOT/'web-player/speech-examples.json').read_text(encoding='utf-8'))['examples']
    definitions={entry['id']:entry for entry in definitions}
    sequence=recipe['sequence']
    if not 1<=len(sequence)<=255:raise ValueError('Expected 1..255 dialogue segments')
    names=list(dict.fromkeys(item['clip'] for item in sequence if 'clip' in item))
    if not names or any(name not in definitions for name in names):raise ValueError('Unknown public phrase')
    ffmpeg=shutil.which(args.ffmpeg)
    if not ffmpeg:raise ValueError('FFmpeg is required to measure perceived loudness')
    source_files=[ROOT/'web-player'/definitions[name]['originalAudioUrl'] for name in names]
    if any(ROOT/'web-player' not in p.resolve().parents for p in source_files):raise ValueError('Source escapes public assets')
    if any(sha(p.read_bytes())!=definitions[name]['originalSha256'] for name,p in zip(names,source_files)):
        raise ValueError('Canonical public source changed')
    targets=[output/'dialogue.wav',output/'manifest.json',output/'lpx-nano-dialogue-quality.hex']
    protect_outputs([*source_files,recipe_path,Path(__file__)],targets)
    if any(p.is_symlink() or p.exists() and p.stat().st_nlink>1 for p in targets):raise ValueError('Output alias')
    common=NativeReference(output/'native-common',wsl=args.wsl)
    compact=NativeReference(output/'native-v5',wsl=args.wsl,compact=True)
    prepared,target=prepare_clips(recipe,names,source_files,output,ffmpeg)
    clips={}
    for name in names:
        adjusted,folder,initial,before_encoding,gain_db=prepared[name];pcm=adjusted
        seed,decoded,_=encode(adjusted.astype(np.int16),6,common,pre=13926,bandwidth=.97)
        stream,_=repack(seed);model=decode_model(stream)
        if not np.array_equal(decoded,model) or not np.array_equal(decoded,compact.decode_one_s16(stream,len(pcm))):
            raise ValueError('Model and current native C disagree')
        pwm=pwm_duties(decoded).tobytes();preview=folder/'decoded.wav'
        write_pcm16_wav(preview,(np.frombuffer(pwm,dtype=np.uint8).astype(np.int16)-128)*256)
        after_encoding=loudness(preview,ffmpeg)
        if after_encoding['truePeakDb']>recipe['truePeakLimitDb']+.1:raise ValueError('Decoded true peak exceeds the ceiling')
        (folder/'speech.lpx').write_bytes(stream)
        clips[name]=dict(stream=stream,pwm=pwm,title=definitions[name]['title'],gainDb=gain_db,
                         source=definitions[name]['originalAudioUrl'],sourceSha256=definitions[name]['originalSha256'],
                         original=initial,normalized=before_encoding,decoded=after_encoding)
        print(json.dumps(dict(clip=name,sourceLufs=initial['lufs'],normalizedLufs=before_encoding['lufs'],
                              decodedLufs=after_encoding['lufs'],gainDb=gain_db),ensure_ascii=False),flush=True)
    normalized_spread=max(c['normalized']['lufs'] for c in clips.values())-min(c['normalized']['lufs'] for c in clips.values())
    decoded_spread=max(c['decoded']['lufs'] for c in clips.values())-min(c['decoded']['lufs'] for c in clips.values())
    if normalized_spread>.2 or decoded_spread>recipe['maxDecodedSpreadLu']:raise ValueError('Dialogue loudness is not sufficiently matched')
    streams=[];expected=[];segments=[];at=0
    for item in sequence:
        if set(item)=={'clip'}:
            name=item['clip'];clip=clips[name];stream,pwm=clip['stream'],clip['pwm']
            info={k:v for k,v in clip.items() if k not in ('stream','pwm')};info.update(kind='speech',clipId=name)
        elif set(item)=={'silenceSeconds'}:
            count=round(float(item['silenceSeconds'])*8000)
            if not 1<=count<=64000:raise ValueError('Pause must be 1..64000 samples')
            stream=pause_stream(count);pwm=bytes([128])*count
            if pwm_duties(decode_model(stream)).tobytes()!=pwm:raise ValueError('Pause model is not exact silence')
            if pwm_duties(compact.decode_one_s16(stream,count)).tobytes()!=pwm:raise ValueError('Native pause is not exact silence')
            info=dict(kind='silence',title='Пауза',seconds=count/8000)
        else:raise ValueError('Each segment must select a phrase or a pause')
        streams.append(stream);expected.append(pwm)
        segments.append(dict(**info,startSample=at,samples=len(pwm),streamBytes=len(stream),streamSha256=sha(stream)))
        at+=len(pwm)
    expected=b''.join(expected)
    gain=choose_gain(expected);level=describe_level(expected,gain);expected=apply_gain(expected,gain)
    result=simulate(streams,output/'avr',args.avr_bin,args.observer,wsl=args.wsl,lib=args.lib,
                    assembly=args.enable_asm,expected_pwm=expected,output_gain=gain)
    cost,report=result['cost'],result['report']
    if cost['flash_bytes']>30720 or cost['static_sram_bytes']>=2048:raise ValueError('Image exceeds classic Nano budget')
    if report.get('irq_entry_cycles')!=4 or report.get('irq_reti_complete') is not True:raise ValueError('Expected calibrated full-IRQ timing')
    for info,(start,end) in zip(segments,cost['embedded_segment_ranges']):info.update(romOffset=start,romEnd=end)
    image=(output/'avr/player.hex').read_bytes();(output/'lpx-nano-dialogue-quality.hex').write_bytes(image)
    actual=(output/'avr/valid.pcm8').read_bytes()
    if actual!=expected:raise ValueError('Actual firmware output differs from the complete dialogue')
    write_pcm16_wav(output/'dialogue.wav',(np.frombuffer(actual,dtype=np.uint8).astype(np.int16)-128)*256)
    sources=[recipe_path,Path(__file__),ROOT/'tools/dialogue_source.py',ROOT/'Codecs/common/pwm_gain.h',ROOT/'tools/pwm_output_level.py',*sorted((CODEC/'src').glob('*')),CODEC/'examples/AVR_V5_PLAYER/player.cpp',
             CODEC/'examples/AVR_V5_PLAYER/player_config.h',CODEC/'tools/build_release_player.py',
             CODEC/'tools/speech_v4.py',CODEC/'tools/speech_compact.py',CODEC/'tools/pcm16_wav.py',
             CODEC.parent/'validation/atmega328p/sim_player.c']
    manifest=dict(schema='micromusic-nano-dialogue-v1',title=recipe['title'],device='atmega328p',cpuHz=16000000,
                  sampleHz=8000,samples=len(actual),durationSeconds=len(actual)/8000,pwmOutput='D3 / PD3 / OC2B',
                  playback='once-after-reset',assemblyEnabled=args.enable_asm,physicalBoardMeasured=False,
                  compiler=cost['environment']['compiler'],
                  ffmpegVersion=subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0].split('Copyright')[0].strip(),
                  flashBytes=cost['flash_bytes'],programFlashBytes=cost['program_flash_bytes'],streamBytes=cost['stream_bytes'],
                  staticSramBytes=cost['static_sram_bytes'],hexSha256=sha(image),wavSha256=sha((output/'dialogue.wav').read_bytes()),
                  outputLevel=level,normalization=dict(method='EBU R128 integrated loudness, constant source gain before encoding',
                                     targetLufs=target,sourceSpreadLu=normalized_spread,decodedSpreadLu=decoded_spread,
                                     truePeakLimitDb=recipe['truePeakLimitDb']),segments=segments,
                  timing={key:report[key] for key in ('played','underruns','timer_ticks','timer_events','queued_at_stop',
                         'tick_interval_min_cycles','tick_interval_max_cycles','pwm_interval_min_cycles','pwm_interval_max_cycles',
                         'irq_cycles_max','irq_entry_cycles','irq_reti_complete','stack_margin_all_bytes')},
                  sourceHashEncoding='text-lf',sourceSha256={p.resolve().relative_to(ROOT).as_posix():sha(p.read_bytes().replace(b'\r\n',b'\n')) for p in sources if p.is_file()})
    save(output/'manifest.json',manifest)
    if args.retain:
        media=ROOT/'web-player/audio/lpx-dialogue';media.mkdir(parents=True,exist_ok=True)
        firmware=ROOT/'web-player/firmware/arduino-nano/lpx-nano-dialogue-quality.hex'
        files=[media/'dialogue.wav',media/'manifest.json',firmware]
        files += [media/(str(i).zfill(2)+'.lpx') for i in range(len(streams))]
        protect_outputs([*source_files,recipe_path,Path(__file__)],files)
        if any(not p.resolve().is_relative_to(ROOT) or p.is_symlink() or p.exists() and p.stat().st_nlink>1 for p in files):
            raise ValueError('Retained output alias')
        shutil.copyfile(output/'dialogue.wav',media/'dialogue.wav');firmware.write_bytes(image)
        for i,(info,stream) in enumerate(zip(segments,streams)):
            info['stream']='audio/lpx-dialogue/'+str(i).zfill(2)+'.lpx';(media/(str(i).zfill(2)+'.lpx')).write_bytes(stream)
        manifest.update(audio='audio/lpx-dialogue/dialogue.wav',firmware='firmware/arduino-nano/lpx-nano-dialogue-quality.hex')
        save(media/'manifest.json',manifest)
    print(json.dumps(dict(samples=len(actual),seconds=len(actual)/8000,flashKiB=cost['flash_bytes']/1024,
                          staticSramBytes=cost['static_sram_bytes'],underruns=report['underruns'],decodedSpreadLu=decoded_spread)),flush=True)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',type=Path,default=ROOT/'ATmega328/Sound/lpx-dialogue/recipe.json')
    parser.add_argument('--output',type=Path,default=ROOT/'build/nano-dialogue/release')
    parser.add_argument('--avr-bin',type=Path,required=True);parser.add_argument('--observer',type=Path,required=True)
    parser.add_argument('--lib',type=Path);parser.add_argument('--wsl');parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--enable-asm',action='store_true');parser.add_argument('--retain',action='store_true')
    build(parser.parse_args())
