"""Compile UM88 data and one invariant portable engine for all retained songs."""
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
BASE=2560
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

def compile_song(song,cpu_hz=8000000):
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
    return encode_score(document,cpu_hz)

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

def encode_score(score,cpu_hz):
    validate_score(score)
    raw=score['commands'];contexts=score['contexts'];models=score['envelopes'];pitches=score['pitches']
    stream,rules,depth=codec.grammar(raw)
    encoded=[]
    for symbol in stream:
        if symbol<128:encoded.append(symbol)
        else:encoded.extend((128|(symbol>>8),symbol&255))
    decoded=[]
    for symbol in stream:
        pending=[symbol]
        while pending:
            code=pending.pop()
            if code<256:decoded.append(code)
            else:a,b=rules[code-256];pending.extend((b,a))
    if decoded!=raw:raise ValueError('Grammar changed musical commands')
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
    rule_ptr=add(b''.join(u16(x) for row in rules for x in row));stream_ptr=add(bytes(encoded))
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
    return data,dict(schema='UM88',version=1,variant=score['name'],source=score.get('source',{}),controlTicks=score['controlTicks'],
                     voices=score['voices'],channels=score['channels'],contexts=contexts,envelopeModels=models,
                     commands=len(raw),grammarRules=len(rules),grammarDepth=depth,dataBytes=len(data),
                     grammarBytes=len(encoded)+len(rules)*4,rawSymbolBytes=sum(1 if x<128 else 2 for x in raw),
                     packing='minimum byte cost across three bounded Re-Pair searches and their prefixes',
                     decodedCommandsSha256=digest(bytes(raw)),allControlFramesVerified=score.get('importedControlFramesVerified',False))

def main():
    global BASE
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--avr-bin');parser.add_argument('--no-import',action='store_true',help=argparse.SUPPRESS);parser.add_argument('--backend',choices=('c','avr-asm'),default='c');parser.add_argument('--cpu-hz',type=int);parser.add_argument('--buffer-frames',type=int);parser.add_argument('--platform-header',type=Path);parser.add_argument('--score',type=Path);parser.add_argument('--reimport',action='store_true');parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();tools=legacy.toolchain(args.avr_bin)
    if args.backend=='c' and args.output_dir is None:args.output_dir=ROOT/'build/universal/c'
    if args.reimport or not args.score and not (ROOT/'ATtiny88/Music/universal/songs/rhythmic/score.json').exists():
        legacy.run('node','tools/import-universal-music.mjs')
    source=ROOT/'ATtiny88/Music/universal';scratch_root=ROOT/'build/universal';scratch_root.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(prefix='compile-',dir=scratch_root)
    scratch=Path(temporary.name)
    elf=scratch/'engine.elf'
    defines=['-DUM_REQUESTED_CPU_HZ='+str(args.cpu_hz)+'UL'] if args.cpu_hz is not None else []
    if args.buffer_frames is not None:defines+=['-DUM_REQUESTED_BUFFER_FRAMES='+str(args.buffer_frames)]
    if args.platform_header:defines+=['-include',str(args.platform_header.resolve())]
    # Read the compiler's evaluated constant, including expressions and UL suffixes.
    probe=scratch/'clock-probe.c';probe_obj=scratch/'clock-probe.o';probe_bin=scratch/'clock-probe.bin'
    legacy.save(probe,'#include <avr/io.h>\n#include <stdint.h>\n#include "clock.h"\n#include "audio-buffer.h"\nconst uint32_t um_clock[2] __attribute__((section(".umclock")))={F_CPU,UM_PWM_BUFFER_FRAMES};\n')
    legacy.run(tools['avr-gcc'],'-mmcu=attiny88','-I'+str(source),'-I'+str(source/'vendor/ATtiny_DFP/3.4.278/include'),*defines,'-c',probe,'-o',probe_obj)
    legacy.run(tools['avr-objcopy'],'-O','binary','-j','.umclock',probe_obj,probe_bin)
    clock_config=probe_bin.read_bytes();assert len(clock_config)==8
    cpu_hz=int.from_bytes(clock_config[:4],'little');assert 75000<=cpu_hz<=12000000
    buffer_frames=int.from_bytes(clock_config[4:],'little')
    defines+=['-DUM_ENABLE_AVR_ASM='+('1' if args.backend=='avr-asm' else '0')]
    for attempt in range(3):
        legacy.run(tools['avr-gcc'],'-mmcu=attiny88','-Os','-fno-jump-tables','-ffunction-sections','-fdata-sections',
                   '-I'+str(source/'vendor/ATtiny_DFP/3.4.278/include'),*defines,'-DUM_SONG_ADDRESS='+str(BASE),
                   '-Wl,--gc-sections',source/'engine.c',source/'platform.c',source/'render-avr.S',source/'irq-avr.S','-o',elf)
        legacy.run(tools['avr-objcopy'],'-O','binary','-j','.text',elf,scratch/'engine.bin')
        engine=(scratch/'engine.bin').read_bytes();needed=(len(engine)+31)//32*32
        if needed<=BASE:break
        BASE=needed
    else:raise ValueError('Cannot place the song block after the compiled engine')
    assert len(engine)<=BASE,(len(engine),BASE)
    symbols=legacy.run(tools['avr-nm'],'-n',elf)
    labels={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-fA-F]+)\s+([tTbBdD])\s+(\S+)$',symbols,re.M)}
    assert labels['um_ring']-0x800000+buffer_frames+48<=768,'Need 48 bytes of stack above the FIFO'
    legacy.save(scratch/'disassembly.txt',legacy.run(tools['avr-objdump'],'-d',elf))
    common=dict(engine='UM88',backend=args.backend,pwmBufferLayout='mono',pwmBufferFrames=buffer_frames,engineBytes=len(engine),songAddress=BASE,engineSha256=digest(engine),labels=labels,
                cpuHz=cpu_hz,synthesisHz=cpu_hz/1024,pwmHz=cpu_hz/256,controlHz=18750/256,
                toolchainVersion=legacy.run(tools['avr-gcc'],'--version').splitlines()[0])
    (scratch_root/('engine-'+args.backend+'.bin')).write_bytes(engine)
    legacy.save(scratch_root/('engine-'+args.backend+'.json'),json.dumps(common,indent=2)+'\n')
    names=[json.loads(args.score.read_text(encoding='utf-8'))['name']] if args.score else NAMES
    for name in names:
        score_path=args.score or source/'songs'/name/'score.json'
        if score_path.exists() and not args.reimport:
            score=json.loads(score_path.read_text(encoding='utf-8'))
            data,report=encode_score(score,cpu_hz)
        else:
            song=json.loads((scratch_root/(name+'.tape.json')).read_text(encoding='utf-8'));data,report=compile_song(song,cpu_hz)
            score=json.loads((source/'songs'/name/'score.json').read_text(encoding='utf-8'))
        if score['channels']!=1:
            if args.score:raise ValueError('The current PWM driver is mono; stereo firmware remains archived')
            print(name+': archived stereo firmware retained; mono driver not applied');continue
        binary=engine+bytes([255])*(BASE-len(engine))+data
        assert len(binary)<=8192,(name,len(binary))
        folder=(args.output_dir or source/'songs')/name;folder.mkdir(parents=True,exist_ok=True)
        if score_path.resolve()!=(folder/'score.json').resolve():
            legacy.save(folder/'score.json',json.dumps(score,ensure_ascii=False,indent=2)+'\n')
        (folder/'synth.bin').write_bytes(binary);legacy.save(folder/'synth.hex',legacy.ihex(binary))
        ep=bytes(score['waves']);(folder/'eeprom.bin').write_bytes(ep);legacy.save(folder/'eeprom.hex',legacy.ihex(ep))
        report.update(common,flashBytes=len(binary),flashSha256=digest(binary),eepromSha256=digest(ep))
        legacy.save(folder/'build-report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(f'{name}: engine {len(engine)}, data {len(data)}, Flash {len(binary)}/8192; {report["controlTicks"]} control ticks; playback audit is separate')
    legacy.save((args.output_dir or source)/'build-report.json',json.dumps(common,indent=2)+'\n')
    temporary.cleanup()
if __name__=='__main__':main()
