"""Build the canonical, self-contained firmware and its embedded HTML player."""
from pathlib import Path
from html import escape
import importlib.util
import hashlib
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

assembler=module('assembler',ROOT/'tools/assemble-avr.py')
compiler=module('score_format',ROOT/'tools/score-format.py')
bank=module('instrument_bank',ROOT/'tools/instrument-bank.py')
engine=module('instrument_engine',ROOT/'tools/build-instrument-engine.py')
percussion=module('percussion_bank',ROOT/'tools/percussion-bank.py')
release_engine=module('release_engine',ROOT/'tools/build-release-engine.py')

def save_text(path,text):
    # Avoid rewriting identical generated sources while previews/editors read
    # them; a metadata-only rebuild need not touch every firmware artifact.
    if not path.exists() or path.read_text(encoding='utf-8')!=text:
        path.write_text(text,encoding='utf-8',newline='\n')

def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        b=bytes([len(raw[i:i+16]),i>>8,i&255,0])+raw[i:i+16]
        rows.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])

def build(folder):
    data=json.loads((folder/'score.json').read_text(encoding='utf-8'))
    if data.get('engine')=='alicia-native':
        native=module('alicia_native',ROOT/'tools/arrange-alicia-multi.py')
        return native.build(folder,candidates=data.get('packing_candidates',4096),production=True)
    if data.get('engine')=='children-native':
        native=module('children_native',ROOT/'tools/arrange-children-four.py')
        return native.build(folder,candidates=data.get('packing_candidates',4096),production=True)
    assignments=None;percussion_profile=None
    if 'instruments' in data:
        assignments=bank.describe_assignments(data['instruments'])
        if data.get('engine')=='instrument-bank':
            source,metadata=engine.specialize(data,assignments)
            if assignments.get('percussion',{}).get('enabled',False):
                kit=data.get('percussion_kit','natural-kit')
                # Noise gain is shift-only; level is quantized to 1, 1/2,
                # 1/4 or 1/8. Level zero removes the whole generator above.
                shift=min(3,max(0,round(math.log2(15/assignments['percussion']['level']))))
                source=percussion.compile_source(source,kit,attenuation_shift=shift)
                percussion_profile=dict(kit=kit,attenuationShift=shift,hits=percussion.select_kit(kit,shift),
                    bankSha256=hashlib.sha256(percussion.BANK_PATH.read_bytes()).hexdigest())
            data.update(metadata)
            slots=data.get('release_tail_slots',0)
            if slots not in (0,2):raise ValueError('release_tail_slots must be 0 or 2')
            if slots==2:source=release_engine.specialize(data,source)
            save_text(folder/'synth.S',source)
            save_text(folder/'score.json',json.dumps(data,indent=2,ensure_ascii=False)+'\n')
        (folder/'eeprom.bin').write_bytes(bank.build_eeprom(data['instruments']))
    # The bytecode is meter-independent; Greensleeves uses dotted-quarter
    # companion boundaries and its written pickup/closing bars.
    original_pack_bar=compiler.pack_bar
    if data.get('meter')=='6/8':
        meter=module('meter_6_8',ROOT/'tools/arrange-greensleeves.py')
        compiler.pack_bar=lambda *args,**kwargs:meter.pack_bar_6_8(compiler,*args,**kwargs)
    try:score,meta=compiler.to_inc(data)
    finally:compiler.pack_bar=original_pack_bar
    step=round(data['tempo_bpm']*4/60/(37500/512)*65536)
    assert 0<step<65536
    initial=math.ceil((65536-step)/256)
    assert len(meta['playlist'])<=255,'Playlist index is one byte'
    settings=dict(REST_INDEX=meta['rest_index'],HOLD_INDEX=meta['hold_index'],PLAYLIST_LEN=len(meta['playlist']),FIRST_PLAYLIST_INDEX=int(len(meta['playlist'])>1),
                  GRID_STEP_LOW=step&255,GRID_STEP_HIGH=step>>8,GRID_INITIAL_HIGH=initial)
    save_text(folder/'score.inc',score)
    save_text(folder/'config.inc',''.join(f'.set {k}, {v}\n' for k,v in settings.items()))
    rom,labels=(release_engine.assemble_relaxed(folder/'synth.S') if data.get('release_tail_slots')==2 else assembler.assemble(folder/'synth.S'));assert len(rom)<=1024,len(rom)
    ep=(folder/'eeprom.bin').read_bytes();assert len(ep)==64
    (folder/'synth.bin').write_bytes(rom)
    save_text(folder/'synth.hex',ihex(rom))
    save_text(folder/'eeprom.hex',ihex(ep))
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),('FIRMWARE_HEX',ihex(rom)),('EEPROM_HEX',ihex(ep))]:
        html=html.replace('/*'+key+'*/',value)
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — '+data['title'])
    if data.get('player_description'):
        html=html.replace('ATtiny13A: четырёхголосный плеер — эмулятор HEX','ATtiny13A — '+escape(data['title']))
        html=html.replace('мелодия, пианино, гитара и ударные.',escape(data['player_description']))
    save_text(folder/'player.html',html)
    report=dict(flashBytes=len(rom),codeBytes=labels['playlist'],tableBytes=len(rom)-labels['playlist'],eepromBytes=64,
                flashSha256=hashlib.sha256(rom).hexdigest(),eepromSha256=hashlib.sha256(ep).hexdigest(),labels=labels,score=meta,
                timing=dict(phaseStep=step,phaseBits=16,envelopeTickCycles=131072,tempoBpm=data['tempo_bpm'],actualTempoBpm=step/65536*(37500/512)*60/4,
                            sharedGrid='One sixteenth grid drives score and half-beat percussion',initialHighPhase=initial),
                articulation=dict(holdIndex=meta['hold_index'],holds=meta['holds'],
                                  attack=data.get('lead_envelope_model','bowed'),
                                  retrigger=data.get('lead_retrigger','half'),phaseContinuous=True))
    if assignments is not None:
        report['instrumentAssignments']=assignments
        report['instrumentBankSha256']=hashlib.sha256(bank.BANK_PATH.read_bytes()).hexdigest()
    if percussion_profile is not None:report['percussionProfile']=percussion_profile
    if data.get('release_tail_slots')==2:
        report['releaseChannels']=dict(primaryVoices=3,tailSlots=2,voiceAddresses=[96,101,106,111,116],
            voiceStateBytes=25,pwmRingBytes=16,tailGain=.5,stealing='Quietest of two release levels',
            phaseContinuous=True,isrCycles=15,requiredFuses=dict(low='0x7A',high='0xFF'))
    save_text(folder/'build-report.json',json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(folder.name+':',len(rom),'Flash;',labels['playlist'],'code;',len(meta['holds']),'unique hold commands; phase step',step)

if __name__=='__main__':
    build(ROOT/(sys.argv[1] if len(sys.argv)>1 else 'ATtiny13A/Music/variants/rhythmic'))
