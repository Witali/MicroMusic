"""Compile UM88 scores with a shared portable engine for each mono/stereo profile."""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import importlib.util
import json
import math
import re
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BASE=0
NAMES=('rhythmic','lumiere-stereo','alicia','children','turkish-march','greensleeves',
       'cancion-del-mariachi','cancion-del-mariachi-polyphonic','cancion-del-mariachi-sparse')
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
codec=module('um88_codec','universal-music.py')
legacy=module('um88_tools','build-attiny88-music.py')
def key(i,v):return i,v['envelope']>>4,int(bool(v['step']&32768)),int((v['step']&32767)>=1229)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def u16(n):return bytes((n&255,n>>8))
def context_settings(song,k):
    i,flags,fast,high=k;name=song['name'];count=len(song['frames'][0]['voices'])
    bank=(flags&3)*16;gain=1;mix=128
    if name=='greensleeves':bank=i*16;gain=3
    elif song['poly']:
        split=3 if name.endswith('-sparse') else 2
        bank=0 if i<split else 16;gain=32
        mix=(160|(0 if i<split else 1)) if i in (split-1,count-1) else 0
    elif name=='rhythmic':gain=1|(128 if flags&1 else 0)|(64 if flags&1 else 0)
    elif name=='lumiere-stereo':
        gain=129|(80 if flags&1 else 0)
        if i==0:mix|=16
        if i==count-1:mix|=8
    elif name in ('alicia','children'):
        gain=(3 if i>=2 else 2)|(64 if (name=='alicia' and i==0 or name=='children' and i<2) else 0)
    elif name=='turkish-march':gain=1|64
    elif name=='cancion-del-mariachi':gain=2 if i>=3 else 1
    return bank|(8 if high else 0),gain,mix

def compile_song(song,cpu_hz=8000000,packing='compact'):
    # Learn exactly the original per-tick envelope transition, before note events.
    observations=defaultdict(lambda:defaultdict(dict))
    frames=song['frames'][:-1]  # the last frame is the first legacy restart
    for tick,frame in enumerate(frames[1:],1):
        for i,(before,after) in enumerate(zip(frames[tick-1]['voices'],frame['envelopeResults'])):
            env=before['envelope'];assert (after>>4)==(env>>4),(song['name'],tick,i,env,after)
            states=observations[key(i,before)][env&15]
            phase=tick&15;level=after&15
            assert phase not in states or states[phase]==level
            states[phase]=level
    # Merge compatible partial observations before emitting envelope automata.
    # Unknown tick phases are constraints, not separate per-voice models.
    merged=[];model_for_key={}
    def compatible(a,b):
        for level in range(16):
            aa=a.get(level,{});bb=b.get(level,{})
            if any(p in aa and aa[p]!=v for p,v in bb.items()):return False
            if len({v for v in list(aa.values())+list(bb.values()) if v!=level})>1:return False
        return True
    for frame in frames:
        for i,v in enumerate(frame['voices']):
            k=key(i,v)
            if k in model_for_key:continue
            sample=observations[k]
            index=next((n for n,m in enumerate(merged) if compatible(m,sample)),len(merged))
            if index==len(merged):merged.append({})
            for level,states in sample.items():merged[index].setdefault(level,{}).update(states)
            model_for_key[k]=index
    models=[];contexts=[];keys={}
    for frame in frames:
        for i,v in enumerate(frame['voices']):
            k=key(i,v)
            if k in keys:continue
            rows=[]
            for level in range(16):
                states=merged[model_for_key[k]].get(level,{})
                changes={v for v in states.values() if v!=level}
                assert len(changes)<=1,(song['name'],k,level,changes)
                new=next(iter(changes),level)
                mask=sum(1<<p for p,v in states.items() if v!=level)
                rows.extend([new,mask&255,mask>>8])
            if rows not in models:models.append(rows)
            bank,gain,mix=context_settings(song,k)
            context=[models.index(rows),bank,gain,mix]
            if context not in contexts:contexts.append(context)
            keys[k]=contexts.index(context)
    assert len(contexts)<=256 and len(models)<=256
    pitches=sorted({v['step']&32767 for f in frames for v in f['voices']});assert len(pitches)<=256
    raw=[];wait=0;previous=[None]*len(frames[0]['voices']);drum_mode=None
    def flush():
        nonlocal wait
        while wait:amount=min(wait,63);raw.append(amount);wait-=amount
    for tick,frame in enumerate(frames):
        ops=[]
        for i,v in enumerate(frame['voices']):
            old=previous[i];env=v['envelope'];step=v['step']&32767;context=keys[key(i,v)]
            predicted=0 if old is None else frame['envelopeResults'][i]&15
            if old is None or context!=old[0]:ops.extend([64+i,context])
            if old is None or step!=old[1]:ops.extend([72+i,pitches.index(step)])
            if (env&15)!=predicted:ops.append(128+(i<<4)+(env&15))
            phase=frame.get('phaseOps',list(range(len(previous))))[i]
            if phase==-1:ops.append(80+i)
            elif phase!=i:ops.extend([88+i,phase])
            previous[i]=(context,step)
        if song['hasDrum']:
            d=frame['drum']
            if song['poly']:
                mode=(128|(1 if d&8 else 0)|((int(not(d&1))+int(not(d&2)))<<2)|16) if d&4 else 0
            else:
                kind=0 if frame['beat']<2 else (1 if frame['beat']&2 else 2)
                mode=(128|kind|(((d&1)+int(bool(d&2)))<<2)) if d<4 else 0
            if mode!=drum_mode:ops.extend([96,mode]);drum_mode=mode
            if 'drumReset' in frame:ops.extend([97,frame['drumReset']])
            if 'noiseReset' in frame:ops.extend([98,frame['noiseReset']])
        if ops:flush();raw.extend(ops)
        wait+=1
    flush();raw.append(0)
    stream,rules,depth=codec.grammar(raw)
    encoded=[]
    for symbol in stream:
        if symbol<128:encoded.append(symbol)
        else:encoded.extend((128|(symbol>>8),symbol&255))
    # Bounded grammar must restore every command and argument, in order.
    decoded=[]
    for symbol in stream:
        pending=[symbol]
        while pending:
            code=pending.pop()
            if code<256:decoded.append(code)
            else:a,b=rules[code-256];pending.extend((b,a))
    assert decoded==raw
    # Independent replay checks the predicted envelopes against every source tick.
    voices=[dict(level=0,context=0,step=0) for _ in previous];cursor=0;waiting=0
    for tick,frame in enumerate(frames):
        if tick:
            for v in voices:
                row=models[contexts[v['context']][0]][v['level']*3:v['level']*3+3]
                if (row[1]|row[2]<<8)&(1<<(tick&15)):v['level']=row[0]
            waiting-=1
        if not waiting:
            while True:
                op=raw[cursor];cursor+=1;i=op&7
                if 0<op<64:waiting=op;break
                assert op
                if op<72:voices[i]['context']=raw[cursor];cursor+=1
                elif op<80:voices[i]['step']=pitches[raw[cursor]];cursor+=1
                elif op<88:pass
                elif op<99:cursor+=1
                elif op>=128:voices[(op>>4)&7]['level']=op&15
            for v in voices:assert v['context']<len(contexts)
        for i,(v,expected) in enumerate(zip(voices,frame['voices'])):
            assert v==dict(level=expected['envelope']&15,context=keys[key(i,expected)],step=expected['step']&32767),(song['name'],tick,i,v,expected)
    normalizer=[]
    if song['name']=='greensleeves':
        folder=ROOT/'ATtiny88/Music/variants/greensleeves'
        meta=json.loads((folder/'build-report.json').read_text(encoding='utf-8'));rom=(folder/'synth.bin').read_bytes()
        at=meta['labels']['output_gain'];normalizer=list(rom[at:at+64])
    document=dict(schema='micromusic-um88-score',version=1,name=song['name'],voices=len(voices),
                  channels=song['channels'],waves=song['eeprom'],contexts=contexts,envelopes=models,
                  pitches=[None if not p else round(69+12*math.log2(p*15625/65536/440)) for p in pitches],
                  commands=raw,controlTicks=len(frames),groupGain=song['poly'],normalizer=normalizer,
                  normalizerMinimum=-33 if normalizer else 0,
                  masterShift=2 if song['name'].endswith('-sparse') else 0,
                  source=song['source'],importedControlFramesVerified=True)
    destination=ROOT/'ATtiny88/Music/universal/songs'/song['name']/'score.json'
    legacy.save(destination,json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    return encode_score(document,cpu_hz,packing)

def validate_score(score):
    if score.get('schema')!='micromusic-um88-score' or score.get('version')!=1:raise ValueError('Expected UM88 score v1')
    if not re.fullmatch('[a-z0-9-]+',score['name']):raise ValueError('Invalid song name')
    count=score['voices']
    if type(count) is not int or not 1<=count<=8:raise ValueError('UM88 supports 1..8 oscillators')
    if score['channels'] not in (1,2):raise ValueError('Channels must be 1 or 2')
    def octets(data):return all(type(x) is int and 0<=x<=255 for x in data)
    if len(score['waves'])!=64 or not octets(score['waves']):raise ValueError('Expected 64 packed wavetable bytes')
    models=score['envelopes'];contexts=score['contexts'];pitches=score['pitches'];raw=score['commands']
    if not 1<=len(models)<=256 or any(len(m)!=48 or not octets(m) or any(m[i]>15 for i in range(0,48,3)) for m in models):raise ValueError('Invalid envelope automata')
    if not 1<=len(contexts)<=256 or any(len(c)!=4 or not octets(c) or c[0]>=len(models) or c[1]>56 or c[1]%8 for c in contexts):raise ValueError('Invalid instrument context')
    mixes={0}|{128|pan for pan in (0,8,16,24)}|{160|pan|attenuation for pan in (0,8,16,24) for attenuation in (0,1)}
    if any(c[2]&8 or c[3] not in mixes for c in contexts):raise ValueError('Unsupported gain or panning flags')
    if any(bool(c[2]&32)!=(c[3]==0 or bool(c[3]&32)) for c in contexts):raise ValueError('Raw waveforms must use grouped mixing')
    if type(score['controlTicks']) is not int or not 1<=score['controlTicks']<=65535:raise ValueError('UM88 v1 supports 1..65535 control ticks per loop')
    if not 1<=len(pitches)<=256 or any(p is not None and (type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=127) for p in pitches):raise ValueError('Invalid pitch palette')
    if not raw or raw[-1]!=0 or not octets(raw):raise ValueError('Invalid command stream')
    cursor=0;duration=0;active_contexts=[0]*count
    def check_groups():
        pending=False
        for index in active_contexts:
            context=contexts[index]
            if context[2]&32:pending=not bool(context[3]&128)
            elif pending:raise ValueError('Close a raw group before an independent voice')
        if pending:raise ValueError('The final voice must close its raw group')
    while cursor<len(raw):
        op=raw[cursor];cursor+=1;voice=op&7
        if op==0:
            if cursor!=len(raw):raise ValueError('Trailing commands after LOOP')
        elif op<64:check_groups();duration+=op
        elif op<99:
            if op<96 and voice>=count:raise ValueError('Voice out of range')
            if op<80 or 88<=op<99:
                if cursor>=len(raw):raise ValueError('Truncated command')
                value=raw[cursor];cursor+=1
                if op<72 and value>=len(contexts):raise ValueError('Context out of range')
                if op<72:active_contexts[voice]=value
                if 72<=op<80 and value>=len(pitches):raise ValueError('Pitch out of range')
                if 88<=op<96 and value>=count:raise ValueError('Phase source out of range')
        elif op>=128:
            if ((op>>4)&7)>=count:raise ValueError('Level voice out of range')
        else:raise ValueError('Reserved opcode')
    if duration!=score['controlTicks'] or duration<1:raise ValueError('Declared duration differs from WAIT commands')
    if score['masterShift'] not in (0,1,2,3):raise ValueError('Invalid master gain')
    if score['normalizer'] and (len(score['normalizer'])>256 or not octets(score['normalizer'])):raise ValueError('Invalid normalizer')

def encode_score(score,cpu_hz,packing='compact'):
    validate_score(score)
    if packing not in ('compact','fast'):raise ValueError('Expected compact or fast dictionary packing')
    raw=score['commands'];contexts=score['contexts'];models=score['envelopes'];pitches=score['pitches']
    packed=codec.pack_grammar(raw) if packing=='compact' else codec.pack_fast_grammar(raw)
    if codec.unpack_grammar(packed)!=raw:raise ValueError('Grammar changed musical commands')
    data=bytearray(b'UM88'+bytes([score['voices'],score['channels'],score['masterShift'],score['normalizerMinimum']&255])+bytes(18))
    def add(payload):
        address=BASE+len(data);data.extend(payload);return address
    wave_ptr=add(bytes(score['waves']))
    ctx_ptr=add(bytes(x for row in contexts for x in row))
    rows=[];model_rows=[]
    for model in models:
        for i in range(0,48,3):
            row=model[i:i+3]
            if row not in rows:rows.append(row)
            model_rows.append(rows.index(row))
    if len(rows)>256:raise ValueError('More than 256 distinct envelope transitions')
    model_ptr=add(bytes(model_rows));rows_ptr=add(bytes(x for row in rows for x in row))
    add(bytes(packed['alphabet']))
    rule_ptr=add(packed['ruleData']);stream_ptr=add(packed['streamData'])
    values=[]
    for pitch in pitches:
        if pitch is None:values.append(0);continue
        frequency=440*2**((pitch-69)/12);rate=cpu_hz/1024
        if frequency>=rate/2:raise ValueError(f'F_CPU={cpu_hz}: MIDI pitch {pitch} reaches Nyquist at synthesis {rate}')
        values.append(round(frequency*65536/rate))
    pitch_ptr=add(b''.join(u16(value) for value in values))
    norm_ptr=add(bytes(score['normalizer'])) if score['normalizer'] else 0
    for offset,pointer in zip(range(8,22,2),(wave_ptr,ctx_ptr,model_ptr,rule_ptr,stream_ptr,rows_ptr,norm_ptr)):data[offset:offset+2]=u16(pointer)
    data[24:26]=u16(pitch_ptr)
    data[22]=packed['format'];data[23]=len(packed['alphabet'])&255
    return data,dict(schema='UM88',version=1,variant=score['name'],source=score.get('source',{}),controlTicks=score['controlTicks'],
                     voices=score['voices'],channels=score['channels'],contexts=contexts,envelopeModels=models,
                     commands=len(raw),grammarRules=len(packed['rules']),grammarDepth=packed['depth'],dataBytes=len(data),
                     grammarBytes=packed['grammarBytes'],grammarFormat=packed['format'],grammarAlphabetSize=len(packed['alphabet']) if packing=='compact' else 256,rawSymbolBytes=sum(1 if x<128 else 2 for x in raw),
                     packing='bounded Re-Pair with dense nine-bit symbols' if packing=='compact' else 'bounded Re-Pair with byte-aligned sixteen-bit rule pairs',
                     decodedCommandsSha256=digest(bytes(raw)),allControlFramesVerified=score.get('importedControlFramesVerified',False))


def channel_groups(scores,selection):
    """Keep source scores intact; only the emitted score's channels may change."""
    if selection not in ('auto','mono','stereo'):raise ValueError('Expected auto, mono or stereo channels')
    groups=defaultdict(list)
    for path,source_score in scores:
        source_channels=source_score['channels']
        if type(source_channels) is not int or source_channels not in (1,2):
            raise ValueError('Source channels must be 1 or 2')
        channels=source_channels if selection=='auto' else (1 if selection=='mono' else 2)
        score=dict(source_score,channels=channels)
        validate_score(score)
        groups[channels].append(dict(path=path,score=score,sourceChannels=source_channels))
    return groups


def main():
    global BASE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin')
    parser.add_argument('--no-import',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--backend',choices=('c','avr-asm'),default='c')
    parser.add_argument('--channels',choices=('auto','mono','stereo'),default='auto',
                        help='Compile only the selected output channels; auto follows each source score')
    parser.add_argument('--irq-scratch',choices=('stack','gpior'),default='stack',
                        help='ASM hardware driver: stack backup, or explicitly reserve GPIOR0/1/2 for faster IRQs')
    parser.add_argument('--board',choices=tuple(legacy.BOARDS),default='bare-8mhz')
    parser.add_argument('--cpu-hz',type=int)
    parser.add_argument('--buffer-frames',type=int,help='Legacy name: ring byte budget, shared by mono or stereo')
    parser.add_argument('--packing',choices=('auto','compact','fast'),default='auto',
                        help='Lossless dictionary layout: auto selects compact at 192 ring bytes, fast for smaller rings')
    parser.add_argument('--platform-header',type=Path)
    parser.add_argument('--score',type=Path)
    parser.add_argument('--reimport',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();tools=legacy.toolchain(args.avr_bin)
    usb=args.board=='mh-et-live-16mhz'
    flash_limit=legacy.BOARDS[args.board]['flashLimit']
    if usb:
        if args.cpu_hz not in (None,16000000):parser.error('MH-ET LIVE Micronucleus requires --cpu-hz 16000000')
        args.cpu_hz=16000000
    if args.output_dir is None and (args.backend=='c' or args.channels!='auto'):
        output_name=args.backend+('' if args.channels=='auto' else '-'+args.channels)+('-micronucleus' if usb else '')
        args.output_dir=ROOT/'build/universal'/output_name
    if args.reimport or not args.score and not (ROOT/'ATtiny88/Music/universal/songs/rhythmic/score.json').exists():
        legacy.run('node','tools/import-universal-music.mjs')
    source=ROOT/'ATtiny88/Music/universal';scratch_root=ROOT/'build/universal';scratch_root.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(prefix='compile-',dir=scratch_root)
    scratch=Path(temporary.name)
    defines=['-DUM_REQUESTED_CPU_HZ='+str(args.cpu_hz)+'UL'] if args.cpu_hz is not None else []
    defines+=['-DUM_REQUESTED_IRQ_GPIOR_SCRATCH='+('1' if args.irq_scratch=='gpior' else '0')]
    if usb:defines+=['-DUM_BOARD_MH_ET_LIVE_16MHZ=1']
    if args.buffer_frames is not None:defines+=['-DUM_REQUESTED_BUFFER_FRAMES='+str(args.buffer_frames)]
    if args.platform_header:defines+=['-include',str(args.platform_header.resolve())]
    # Read the compiler's evaluated constant, including expressions and UL suffixes.
    probe=scratch/'clock-probe.c';probe_obj=scratch/'clock-probe.o';probe_bin=scratch/'clock-probe.bin'
    legacy.save(probe,'#include <avr/io.h>\n#include <stdint.h>\n#include "clock.h"\n#include "audio-buffer.h"\n#include "audio-channels.h"\n#include "irq-scratch.h"\nconst uint32_t um_clock[2] __attribute__((section(".umclock")))={F_CPU,UM_PWM_BUFFER_FRAMES};\n')
    legacy.run(tools['avr-gcc'],'-mmcu=attiny88','-I'+str(source),'-I'+str(source/'vendor/ATtiny_DFP/3.4.278/include'),*defines,'-c',probe,'-o',probe_obj)
    legacy.run(tools['avr-objcopy'],'-O','binary','-j','.umclock',probe_obj,probe_bin)
    clock_config=probe_bin.read_bytes();assert len(clock_config)==8
    cpu_hz=int.from_bytes(clock_config[:4],'little')
    assert cpu_hz==16000000 if usb else 75000<=cpu_hz<=12000000
    buffer_bytes=int.from_bytes(clock_config[4:],'little')
    packing=('compact' if buffer_bytes==192 else 'fast') if args.packing=='auto' else args.packing
    defines+=['-DUM_ENABLE_AVR_ASM='+('1' if args.backend=='avr-asm' else '0'),
              '-DUM_COMPACT_SCORE_ONLY='+('1' if packing=='compact' else '0')]
    # Load and validate every score before compiling. A mixed catalog shares one
    # core per effective channel count, rather than linking runtime dispatch.
    names=[json.loads(args.score.read_text(encoding='utf-8'))['name']] if args.score else NAMES
    scores=[]
    for name in names:
        score_path=args.score or source/'songs'/name/'score.json'
        if not score_path.exists() or args.reimport:
            song=json.loads((scratch_root/(name+'.tape.json')).read_text(encoding='utf-8'))
            compile_song(song,cpu_hz,packing)
        scores.append((score_path,json.loads(score_path.read_text(encoding='utf-8'))))
    groups=channel_groups(scores,args.channels)
    for records in groups.values():
        for record in records:
            record['sourceSha256']=digest(record['path'].read_text(encoding='utf-8').encode())
    for channels in groups:
        if buffer_bytes<=4*channels:
            raise ValueError('Ring byte budget must leave a spare frame beyond four generated mono/stereo frames')
    retained_output=source/('songs-micronucleus' if usb else 'songs')
    for channels,records in groups.items():
        for record in records:
            destination=(args.output_dir or retained_output)/record['score']['name']/'score.json'
            if record['sourceChannels']!=channels and record['path'].resolve()==destination.resolve():
                raise ValueError('Channel conversion would overwrite its source score; choose a different --output-dir')
    # A platform may pin the channel count. Check every selected group before
    # the first core snapshot or song is written, so mixed auto builds fail
    # atomically on a mono/stereo header disagreement.
    if args.platform_header:
        for channels in sorted(groups):
            legacy.run(tools['avr-gcc'],'-mmcu=attiny88','-I'+str(source),
                       '-I'+str(source/'vendor/ATtiny_DFP/3.4.278/include'),*defines,
                       '-DUM_REQUESTED_OUTPUT_CHANNELS='+str(channels),
                       '-c',probe,'-o',scratch/('channel-check-'+str(channels)+'.o'))
    source_names=('engine.c','engine.h','platform.c','storage.h','clock.h','rational-clocks.h','audio-buffer.h','audio-channels.h','irq-scratch.h',
                  'render-avr.S','irq-avr.S','vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h')
    inputs=[source/name for name in source_names]+[Path(__file__),ROOT/'tools/universal-music.py']
    profiles=[]
    for channels,records in sorted(groups.items()):
        profile_name='mono' if channels==1 else 'stereo'
        profile_scratch=scratch/profile_name;profile_scratch.mkdir()
        elf=profile_scratch/'engine.elf'
        profile_defines=defines+['-DUM_REQUESTED_OUTPUT_CHANNELS='+str(channels)]
        # Flash data is byte-addressed; keep only word alignment after the code.
        # Start each profile independently, then converge on its own core size.
        BASE=0
        for attempt in range(8):
            legacy.run(tools['avr-gcc'],'-mmcu=attiny88','-Os','-fno-jump-tables','-ffunction-sections','-fdata-sections',
                       '-I'+str(source/'vendor/ATtiny_DFP/3.4.278/include'),*profile_defines,'-DUM_SONG_ADDRESS='+str(BASE),
                       '-Wl,--gc-sections',source/'engine.c',source/'platform.c',source/'render-avr.S',source/'irq-avr.S','-o',elf)
            legacy.run(tools['avr-objcopy'],'-O','binary','-j','.text',elf,profile_scratch/'engine.bin')
            engine=(profile_scratch/'engine.bin').read_bytes();needed=(len(engine)+1)&~1
            if needed<=BASE:break
            BASE=needed
        else:raise ValueError('Cannot place the song block after the compiled engine')
        assert len(engine)<=BASE,(len(engine),BASE)
        symbols=legacy.run(tools['avr-nm'],'-n',elf)
        labels={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-fA-F]+)\s+([tTbBdD])\s+(\S+)$',symbols,re.M)}
        assert labels['um_ring']-0x800000+buffer_bytes+48<=768,'Need 48 bytes of stack above the FIFO'
        legacy.save(profile_scratch/'disassembly.txt',legacy.run(tools['avr-objdump'],'-d',elf))
        common=dict(engine='UM88',backend=args.backend,packingMode=packing,packingPolicy=args.packing,
                    configuredChannels=channels,channelSelection=args.channels,
                    irqScratch=args.irq_scratch if args.backend=='avr-asm' else 'compiler',
                    irqScratchSelection=args.irq_scratch,
                    reservedIORegisters=['GPIOR0','GPIOR1','GPIOR2'] if args.backend=='avr-asm' and args.irq_scratch=='gpior' else [],
                    renderABI='mono-s16' if channels==1 else 'packed-stereo-u32',pwmBufferBytes=buffer_bytes,
                    engineBytes=len(engine),songAddress=BASE,songPaddingBytes=BASE-len(engine),engineSha256=digest(engine),labels=labels,
                    cpuHz=cpu_hz,synthesisHz=cpu_hz/1024,pwmHz=cpu_hz/256,controlHz=18750/256,
                    board=args.board,applicationFlashLimit=flash_limit,eepromRequired=False,
                    sourceInputs={str(file.relative_to(ROOT)).replace('\\','/'):digest(file.read_text(encoding='utf-8').encode()) for file in inputs},
                    deviceDefinitions=dict(pack='Microchip.ATtiny_DFP',version='3.4.278',
                        url='https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack',
                        sha256='41f09d5825abaa764c9000f4488f8ba3fab152afe6229b359de4a5efe9a21eda'),
                    toolchainVersion=legacy.run(tools['avr-gcc'],'--version').splitlines()[0])
        reset=int.from_bytes(engine[:2],'little');assert reset&0xf000==0xc000,'Expected Micronucleus-compatible RJMP reset vector'
        displacement=reset&4095;displacement-=4096 if displacement&2048 else 0
        common['resetVector']=dict(address=0,instruction='rjmp',target=(1+displacement)*2)
        if usb:
            common.update(uploadProtocol='micronucleus',requiredFuses=None,preserveFactoryFuses=True,
                          boardClockAboveRatedMaximum=True,bootloaderEntryInitialization='um_board_reset',
                          boardSource=dict(version='1.0.0',commit=legacy.MANUFACTURER_BOARD_COMMIT,url=legacy.MANUFACTURER_BOARD_URL))
            assert 'um_board_reset' in labels,'Early bootloader-entry initialization linked'
        profiles.append(dict(common,songs=[record['score']['name'] for record in records]))
        # The named snapshots prevent a mixed catalog's last core being mistaken
        # for every song's core. Keep the old convenience paths for older tools.
        for snapshot in (scratch_root/profile_name,scratch_root):
            snapshot.mkdir(parents=True,exist_ok=True)
            (snapshot/('engine-'+args.backend+'.bin')).write_bytes(engine)
            legacy.save(snapshot/('engine-'+args.backend+'.json'),json.dumps(common,indent=2)+'\n')
        for record in records:
            score_path=record['path'];score=record['score'];name=score['name']
            data,report=encode_score(score,cpu_hz,packing)
            binary=engine+bytes([255])*(BASE-len(engine))+data
            if len(binary)>flash_limit:
                raise ValueError(f'{name}: application {len(binary)} bytes exceeds {args.board} limit {flash_limit}')
            folder=(args.output_dir or retained_output)/name;folder.mkdir(parents=True,exist_ok=True)
            if score_path.resolve()!=(folder/'score.json').resolve():
                legacy.save(folder/'score.json',json.dumps(score,ensure_ascii=False,indent=2)+'\n')
            (folder/'synth.bin').write_bytes(binary);legacy.save(folder/'synth.hex',legacy.ihex(binary))
            ep=bytes(score['waves'])
            if not usb:
                (folder/'eeprom.bin').write_bytes(ep);legacy.save(folder/'eeprom.hex',legacy.ihex(ep))
            report.update(common,sourceChannels=record['sourceChannels'],
                          pwmBufferLayout='stereo-pairs' if channels==2 else 'mono',pwmBufferFrames=buffer_bytes//channels,
                          flashBytes=len(binary),flashSha256=digest(binary),
                          eepromBytes=0 if usb else len(ep),eepromSha256=None if usb else digest(ep),
                          scoreSource=dict(path=str(score_path.relative_to(ROOT)).replace('\\','/') if score_path.is_relative_to(ROOT) else score_path.name,
                                           sha256=record['sourceSha256']),
                          wavetableStorage=dict(space='flash',address=BASE+26,bytes=len(ep),sha256=digest(ep)))
            legacy.save(folder/'build-report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(f'{name}: {profile_name}, engine {len(engine)}, data {len(data)}, Flash {len(binary)}/{flash_limit}; {report["controlTicks"]} control ticks; playback audit is separate')
    summary=profiles[0] if len(profiles)==1 else dict(engine='UM88',backend=args.backend,channelSelection=args.channels,
                irqScratchSelection=args.irq_scratch,cpuHz=cpu_hz,board=args.board,applicationFlashLimit=flash_limit,profiles=profiles)
    legacy.save((args.output_dir or (retained_output if usb else source))/'build-report.json',json.dumps(summary,indent=2)+'\n')
    temporary.cleanup()
if __name__=='__main__':main()
