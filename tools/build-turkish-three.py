"""Use former release memory for a third real source-derived piano voice."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import shutil

ROOT=Path(__file__).resolve().parents[1]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


standalone = module('avr_standalone', ROOT/'tools/avr-standalone.py')


def specialize(score,common):
    assignments=common.bank.describe_assignments(score['instruments'])
    source,metadata=common.engine.specialize(score,assignments);score.update(metadata)
    # Extend only this native specialization to three identical piano roles.
    # The shared legacy generator deliberately accepts fewer combinations.
    release_path=ROOT/'tools/build-release-engine.py'
    release_text=release_path.read_text(encoding='utf-8')
    release_text=release_text.replace("('piano','piano','off'),", "('piano','piano','off'),('piano','piano','piano'),")
    release_text=release_text.replace("    if data.get('keys_rest_check') or data.get('pluck_rest_check'):", "    if False:")
    release_text=release_text.replace("        else:raise ValueError('Unsupported piano transient roles')", "        elif piano==[0,1,2]:gate=''\n        else:raise ValueError('Unsupported piano transient roles')")
    namespace=dict(__file__=str(release_path),__name__='turkish_piano_specialization')
    exec(compile(release_text,str(release_path),'exec'),namespace)
    source=namespace['specialize'](score,source)
    source=source.replace('  sbrc r26, 4\n  asr r17\n','')
    source=source.replace('cpi r26, 121','cpi r26, 111')
    source=source.replace('  rcall capture_ram_tail\n','  ld r16, X+\n  andi r16, 15\n')
    source=source[:source.index('capture_ram_tail:\n')]+'.include "score.inc"\n'
    # An absent second source chord tone must be exact silence, including its
    # envelope, while preserving the ordinary zero-frequency table entry.
    source=source.replace('voice_initialized:\n', '''voice_initialized:
  /* All selected nonzero DDS words are >=256. */
  tst r16
  brne voice_initialized_return
  subi r26, 5
  st X+, r29
  subi r26, 252
voice_initialized_return:
''')
    return source,assignments


def build(folder,score=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    score=json.loads((folder/'score.json').read_text(encoding='utf-8')) if score is None else score
    common=module('turkish_common','build-rhythmic.py')
    source,assignments=specialize(score,common)
    inc,meta=common.compiler.to_inc(score)
    (folder/'score.inc').write_text(inc,encoding='utf-8',newline='\n')
    step=round(score['tempo_bpm']*4/60/(37500/512)*65536)
    settings=dict(REST_INDEX=meta['rest_index'],HOLD_INDEX=meta['hold_index'],PLAYLIST_LEN=len(meta['playlist']),
        FIRST_PLAYLIST_INDEX=int(len(meta['playlist'])>1),GRID_STEP_LOW=step&255,GRID_STEP_HIGH=step>>8,
        GRID_INITIAL_HIGH=math.ceil((65536-step)/256))
    (folder/'config.inc').write_text(''.join(f'.set {k}, {v}\n' for k,v in settings.items()),encoding='ascii',newline='\n')
    (folder/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    rom,labels=common.release_engine.assemble_relaxed(folder/'synth.S')
    assert len(rom)<=1024,len(rom)
    ep=common.bank.build_eeprom(score['instruments'])
    for name,raw in [('synth',rom),('eeprom',ep)]:
        (folder/(name+'.bin')).write_bytes(raw);(folder/(name+'.hex')).write_text(common.ihex(raw),encoding='ascii',newline='\n')
    standalone.save_core(folder)
    shutil.copyfile(ROOT/'ATtiny13A/Music/instruments/FluidR3-MIT.txt',folder/'FluidR3-MIT.txt')
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),('FIRMWARE_HEX',common.ihex(rom)),('EEPROM_HEX',common.ihex(ep))]:html=html.replace('/*'+key+'*/',value)
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки',score['title']).replace('мелодия, пианино, гитара и ударные.',score['player_description'])
    (folder/'player.html').write_text(html,encoding='utf-8',newline='\n')
    report=dict(engine='turkish-three',flashBytes=len(rom),codeBytes=labels['playlist'],tableBytes=len(rom)-labels['playlist'],
        eepromBytes=64,flashSha256=hashlib.sha256(rom).hexdigest(),eepromSha256=hashlib.sha256(ep).hexdigest(),labels=labels,score=meta,
        instrumentAssignments=assignments,instrumentBankSha256=hashlib.sha256(common.bank.BANK_PATH.read_bytes()).hexdigest(),
        timing=dict(phaseStep=step,phaseBits=16,envelopeTickCycles=131072,tempoBpm=score['tempo_bpm'],actualTempoBpm=step/65536*(37500/512)*60/4,initialHighPhase=settings['GRID_INITIAL_HIGH']),
        channels=dict(tonalVoices=3,parts=2,tailSlots=0,voiceAddresses=[96,101,106],pwmRingBytes=16,roles=['right-hand melody','left-hand bass','left-hand chord tone']),
        articulation=dict(holdIndex=meta['hold_index'],phaseContinuous=True,attack='piano',release='linear'),
        outputNormalization=None)
    standalone.record_sources(report)
    for name,obj in [('score.json',score),('build-report.json',report),('waveforms.json',assignments)]:
        (folder/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report

