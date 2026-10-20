"""Build the canonical, self-contained firmware and its embedded HTML player."""
from pathlib import Path
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

def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        b=bytes([len(raw[i:i+16]),i>>8,i&255,0])+raw[i:i+16]
        rows.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])

def build(folder):
    data=json.loads((folder/'score.json').read_text(encoding='utf-8'))
    assignments=None
    if 'instruments' in data:
        assignments=bank.describe_assignments(data['instruments'])
        if data.get('engine')=='instrument-bank':
            source,metadata=engine.specialize(data,assignments)
            data.update(metadata)
            (folder/'synth.S').write_text(source,encoding='utf-8',newline='\n')
            (folder/'score.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
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
    (folder/'score.inc').write_text(score,encoding='utf-8',newline='\n')
    (folder/'config.inc').write_text(''.join(f'.set {k}, {v}\n' for k,v in settings.items()),encoding='utf-8',newline='\n')
    rom,labels=assembler.assemble(folder/'synth.S');assert len(rom)<=1024,len(rom)
    ep=(folder/'eeprom.bin').read_bytes();assert len(ep)==64
    (folder/'synth.bin').write_bytes(rom)
    (folder/'synth.hex').write_text(ihex(rom),encoding='utf-8',newline='\n')
    (folder/'eeprom.hex').write_text(ihex(ep),encoding='utf-8',newline='\n')
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),('FIRMWARE_HEX',ihex(rom)),('EEPROM_HEX',ihex(ep))]:
        html=html.replace('/*'+key+'*/',value)
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — '+data['title'])
    (folder/'player.html').write_text(html,encoding='utf-8',newline='\n')
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
    (folder/'build-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(folder.name+':',len(rom),'Flash;',labels['playlist'],'code;',len(meta['holds']),'unique hold commands; phase step',step)

if __name__=='__main__':
    build(ROOT/(sys.argv[1] if len(sys.argv)>1 else 'ATtiny13A/Music/variants/rhythmic'))
