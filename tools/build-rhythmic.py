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

def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        b=bytes([len(raw[i:i+16]),i>>8,i&255,0])+raw[i:i+16]
        rows.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])

def build(folder):
    data=json.loads((folder/'score.json').read_text(encoding='utf-8'))
    score,meta=compiler.to_inc(data)
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
                articulation=dict(holdIndex=meta['hold_index'],holds=meta['holds'],attack='Four envelope levels per tick, saturated at 15',
                                  retrigger='Half current amplitude, same oscillator phase; explicit holds skip retrigger'))
    (folder/'build-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(folder.name+':',len(rom),'Flash;',labels['playlist'],'code;',len(meta['holds']),'unique hold commands; phase step',step)

if __name__=='__main__':
    build(ROOT/(sys.argv[1] if len(sys.argv)>1 else 'ATtiny13A/Music/variants/rhythmic'))
