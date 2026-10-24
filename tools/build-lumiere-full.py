"""Build Lumiere with a complete chord quality and five independent tonal DDS voices.

The saved lead-sheet adaptation is the source, not an orchestral transcription.
Three piano tones plus the guitar realize each named chord. The two former
release slots now play actual chord tones; every oscillator keeps its phase.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def replace(source,old,new):
    assert source.count(old)==1,(old,source.count(old))
    return source.replace(old,new)


VOICINGS={
    'Bm':['B3','D4','F#4','F#3'],
    'Gmaj7':['G3','B3','F#4','D3'],
    'Em':['E3','G3','B3','B2'],
    'F#m':['F#3','A3','C#4','C#3'],
    'F#':['F#3','A#3','C#4','C#3'],
    'C#m7b5':['C#3','E3','B3','G2'],
}


def specialize(data,common):
    assignments=common.bank.describe_assignments(data['instruments'])
    base,_=common.engine.specialize(data,assignments)
    base=common.percussion.compile_source(base,'natural-kit',attenuation_shift=0)
    source=common.release_engine.specialize(data,base)
    source=replace(source,'  sbrc r26, 4\n  asr r17\n','')
    source=replace(source,'  lsr r16\n  cpi r26, 111\n  brne note_off_loop',
        '  cpi r26, 101\n  breq off_shift\n  cpi r26, 116\n  brcs off_same_piano\noff_shift:\n  lsr r16\noff_same_piano:\n  cpi r26, 121\n  brne note_off_loop')
    source=replace(source,'  lsl r16\n  lsl r16\n  ldi r30, lo8(chord_steps)',
        '  lsl r16\n  lsl r16\n  lsl r16\n  ldi r30, lo8(chord_steps)')
    source=replace(source,'  ldi r26, 106\n  ldi r25, 175\n  rcall initialize_voice',
        '  ldi r26, 106\n  rcall initialize_voice\n  ldi r26, 111\n  rcall initialize_voice\n  ldi r26, 116\n  ldi r25, 175\n  rcall initialize_voice')
    source=replace(source,'  ldi r26, 101\n  ldi r25, 223\n  rcall initialize_voice\n  ldi r26, 106\n  rcall initialize_voice\n  ldi r26, 111\n  rcall initialize_voice\n  ldi r26, 116\n',
        '  ldi r26, 101\n  ldi r25, 223\npiano_chord_loop:\n  rcall initialize_voice\n  cpi r26, 116\n  brne piano_chord_loop\n')
    source=replace(source,'  cpi r26, 106\n  brne piano_attack_done',
        '  sbrs r0, 4\n  rjmp piano_attack_done')
    source=replace(source,'piano_attack_done:\n',
        'piano_attack_done:\n  /* Balance three simultaneous piano tones against the solo and guitar. */\n  sbrc r0, 4\n  lsr r25\n')
    source=replace(source,'  rcall capture_ram_tail\n',
        '  ld r16, X+\n  andi r16, 15\n')
    start=source.index('capture_ram_tail:\n')
    source=source[:start]+'.include "score.inc"\n'
    return source,assignments


def stereo_source(source):
    # Eight paired frames in the same 16-byte ring. Every publish appends
    # midpoint L/R and next L/R; the ISR consumes exactly one paired frame.
    source=replace(source,'  mov r23, r18\n','  mov r23, r18\n  mov r9, r18\n  mov r8, r18\n')
    source=replace(source,'  ldi r22, 142\n','  ldi r22, 140\n')
    source=replace(source,'  cpi r16, 13\n','  cpi r16, 11\n')
    source=replace(source,'  sbi 23, 1\n  out 41, r18\n  ldi r16, 35\n',
        '  sbi 23, 0\n  sbi 23, 1\n  out 42, r18\n  out 41, r18\n  ldi r16, 163\n')
    source=replace(source,'  clr r21\n','  clr r21\n  clr r10\n')
    source=replace(source,'primary_gain:\n  add r21, r17\n',
        'primary_gain:\n  mov r16, r17\n  cpi r26, 101\n  brne right_gain_ready\n  asr r16\nright_gain_ready:\n  add r10, r16\n  cpi r26, 121\n  brne left_gain_ready\n  asr r17\nleft_gain_ready:\n  add r21, r17\n')
    source=replace(source,'  add r21, r17\nwrite_pwm:',
        '  add r21, r17\n  add r10, r17\nwrite_pwm:')
    source=replace(source,'write_pwm:\n  subi r21, 128\n',
        'write_pwm:\n  mov r17, r10\n  subi r17, 128\n  subi r21, 128\n')
    source=replace(source,'  st X+, r16\n  st X+, r21\n  mov r22, r26\n',
        '  st X+, r16\n  mov r25, r9\n  add r25, r17\n  ror r25\n  st X+, r25\n  st X+, r21\n  st X+, r17\n  mov r9, r17\n  mov r22, r26\n')
    source=replace(source,'pwm_irq:\n  out 41, r18\nring_read:\n  ld r18, Y+\n',
        'pwm_irq:\n  out 42, r18\n  out 41, r8\nring_read:\n  ld r18, Y+\n  ld r8, Y+\n')
    # Noise-only snare leaves the bass drum oscillator and hi-hat unchanged.
    # Sharing the two noise instruments makes room for the second output.
    start=source.index('  mov r25, r15\n')
    end=source.index('.L2ae:\n',start)
    source=source[:start]+source[end:]
    source=replace(source,'  asr r17\n  sbrc r19, 1\n  asr r17\n  sbrc r19, 1\n  rjmp .L2ae\n  asr r17\n.L2ae:',
        '  asr r17\n  asr r17\n.L2ae:')
    # Three-bit amplitude multiplication recovers the stereo CPU margin.
    # DDS phases/pitches and all five musical voices retain full precision.
    start=source.index('.L25c:\n')
    end=source.index('voice_silent:\n',start)
    source=source[:start]+'''.L25c:
  lsr r25
  mov r0, r17
  sbrs r25, 2
  clr r17
  lsl r17
  sbrc r25, 1
  add r17, r0
  lsl r17
  sbrc r25, 0
  add r17, r0
  rjmp envelope_return
'''+source[end:]
    return source


def build(folder,stereo=False):
    common=module('lumiere_common','build-rhythmic.py')
    data=json.loads((folder/'score.json').read_text(encoding='utf-8'))
    if stereo:
        mono=json.loads((ROOT/'ATtiny13A/Music/variants/rhythmic/score.json').read_text(encoding='utf-8'))
        data={**mono,**data}
        assert {k:(data['panorama'][k]['left'],data['panorama'][k]['right']) for k in ('lead','keys','pluck','drums')}==dict(lead=(1,.5),keys=(1,1),pluck=(.5,1),drums=(1,1)),'Update the stereo mixer and tests with panorama changes'
    data.update(engine='lumiere-chords',chord_voicings=VOICINGS,release_tail_slots=0,
        title='Lumière — five tonal voices'+(' stereo' if stereo else ''),
        player_description='Скрипка, трёхголосное пианино, гитара и ударные; все 3:42 сохранённой аранжировки.',
        arrangement_note='Full saved lead-sheet arrangement. Piano triads and guitar realize the named chords; this is not the original orchestral score. Two former tail slots now carry two added piano chord tones. Gmaj7 and C#m7b5 include their seventh in the piano and fifth in the guitar. F# major is distinct from F#m.')
    source,assignments=specialize(data,common)
    if stereo:source=stereo_source(source)
    inc,meta=common.compiler.to_inc(data)
    step=round(data['tempo_bpm']*4/60/(37500/512)*65536)
    settings=dict(REST_INDEX=meta['rest_index'],HOLD_INDEX=meta['hold_index'],PLAYLIST_LEN=len(meta['playlist']),
        FIRST_PLAYLIST_INDEX=int(len(meta['playlist'])>1),GRID_STEP_LOW=step&255,GRID_STEP_HIGH=step>>8,
        GRID_INITIAL_HIGH=-(-(65536-step)//256))
    common.save_text(folder/'config.inc',''.join(f'.set {k}, {v}\n' for k,v in settings.items()))
    common.save_text(folder/'score.inc',inc)
    common.save_text(folder/'synth.S',source)
    rom,labels=common.release_engine.assemble_relaxed(folder/'synth.S')
    assert len(rom)<=1024,len(rom)
    ep=common.bank.build_eeprom(data['instruments'])
    for name,raw in [('synth',rom),('eeprom',ep)]:
        (folder/(name+'.bin')).write_bytes(raw)
        common.save_text(folder/(name+'.hex'),common.ihex(raw))
    common.save_text(folder/'score.json',json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    report=dict(engine='lumiere-chords',activePrimaryVoices=6,flashBytes=len(rom),codeBytes=labels['playlist'],tableBytes=len(rom)-labels['playlist'],
        eepromBytes=len(ep),flashSha256=hashlib.sha256(rom).hexdigest(),eepromSha256=hashlib.sha256(ep).hexdigest(),
        labels=labels,score=meta,instrumentAssignments=assignments,audioChannels=2 if stereo else 1,
        channels=dict(tonalVoices=5,parts=4,percussionGenerators=1,tailSlots=0,
            roles=['violin','piano root','piano third','piano fifth or seventh','nylon guitar'],
            voiceAddresses=[96,101,106,111,116],voiceStateBytes=25,pwmRingBytes=16),
        timing=dict(tempoBpm=data['tempo_bpm'],actualTempoBpm=step/65536*(37500/512)*60/4,
            phaseStep=step,phaseBits=16,envelopeTickCycles=131072,synthesisHz=18750,pwmHz=37500))
    report['amplitudeLevels']=8 if stereo else 16
    if stereo:report.update(outputs=data['outputs'],panorama=data['panorama'])
    common.save_text(folder/'build-report.json',json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    core=(ROOT/'web-player/lib/avr-reference.js').read_text(encoding='utf-8').replace('export class AVRCore','class AVRCore')
    core+='\n'+(ROOT/'web-player/lib/hex.js').read_text(encoding='utf-8').replace('export function','function')
    core+='\nAVRCore.fromHex=(flash,eeprom)=>new AVRCore(parseHex(flash),eeprom?parseHex(eeprom,64):null);\n'
    core+="\nif(typeof module!=='undefined' && module.exports)module.exports={AVRCore};\n"
    common.save_text(folder/'avr_core.js',core)
    html=(ROOT/'tools'/('stereo-player-template.html' if stereo else 'player-template.html')).read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),('FIRMWARE_HEX',common.ihex(rom)),('EEPROM_HEX',common.ihex(ep))]:
        html=html.replace('/*'+key+'*/',value)
    if stereo:
        html=html.replace('/*HEX_PARSER*/','')
        html=html.replace('/*RENDERER*/','\n'.join(line for line in (ROOT/'web-player/lib/renderer-js.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export class','class'))
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — '+data['title'])
    html=html.replace('ATtiny13A: четырёхголосный плеер — эмулятор HEX','ATtiny13A — '+data['title'])
    html=html.replace('мелодия, пианино, гитара и ударные.',data['player_description'])
    common.save_text(folder/'player.html',html)
    print(f'{folder.name}: {len(rom)} Flash; {labels["playlist"]} code; {meta["total_data_bytes"]} tables')
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stereo',action='store_true')
    args=ap.parse_args()
    build(ROOT/'ATtiny13A/Music/variants'/('lumiere-stereo' if args.stereo else 'rhythmic'),args.stereo)
