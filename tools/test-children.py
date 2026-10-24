"""Verify native Children against the complete retained source-event grid."""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'ATtiny13A/Music/variants/children'
SOURCE=ROOT/'ATtiny13A/Music/reference/children/source-events.json'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


reader=module('children_test_reader',ROOT/'tools/midi-reader.py')
bank=module('children_test_bank',ROOT/'tools/instrument-bank.py')
assembler=module('children_test_assembler',ROOT/'tools/assemble-avr.py')
notes,ppqn,bpm=reader.read_midi(SOURCE)
score=json.loads((FOLDER/'score.json').read_text(encoding='utf-8'))
report=json.loads((FOLDER/'build-report.json').read_text(encoding='utf-8'))
native=report['native'];meta=native['metadata'];labels=report['labels']
rom=(FOLDER/'synth.bin').read_bytes();ep=(FOLDER/'eeprom.bin').read_bytes()
assert score['engine']==report['engine']=='children-native'
assert score['active_primary_voices']==report['activePrimaryVoices']==4
assert score['release_tail_slots']==report['releaseChannels']['tailSlots']==2
assert report['releaseChannels']['voiceAddresses']==[97,102,107,112,117,122]
assert score['arrangement']['sourceQuarterBeats']==560 and score['arrangement']['firstSourceQuarterBeat']==0
assert score['arrangement']['totalQuarterBeats']==564
assert score['source_midi']['sha256']==hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert score['tempo_bpm']==bpm==140
assert len(rom)==report['flashBytes']<=1024
assert report['flashSha256']==hashlib.sha256(rom).hexdigest()
rebuilt,rebuilt_labels=assembler.assemble(FOLDER/'synth.S')
assert rebuilt==rom and rebuilt_labels==labels,'Saved AVR source reproduces every byte and address'
assert labels['code_end']==report['codeBytes']
assert report['score']['compression']['verifiedLossless']
assert report['score']['compression']['packedBytes']<report['score']['compression']['sourceLayoutBytes']

# Independent retained-source grid, preserving every real NoteOn identity.
melody=sorted((n for n in notes if n[0]==1),key=lambda n:(n[3],n[2]))
quantized=[(n[2],round(n[3]*4/ppqn),max(round(n[3]*4/ppqn)+1,round(n[4]*4/ppqn)),identity)
           for identity,n in enumerate(melody)]
source_grid=[]
for unit in range(1712):
    active=[n for n in quantized if n[1]<=unit<n[2]]
    source_grid.append(max(active,key=lambda n:(n[0],n[1])) if active else None)
expected_attacks=[(unit,note[0]) for unit,note in enumerate(source_grid)
                  if note and (unit==0 or source_grid[unit-1] is None or source_grid[unit-1][3]!=note[3])]
assert len(expected_attacks)==len(melody)==256
assert expected_attacks[:4]==[(0,77),(24,80),(28,79),(30,75)]
durations=[1,2,3,4,6,8,16];actual_grid=[];actual_attacks=[];current=None
raw=bytes(native['sourceStream']);expanded=[]
for index in range(labels['PLAYLIST_LEN']):
    address=labels['melody_data']+rom[labels['playlist']+index]
    while rom[address]!=255:expanded.append(rom[address]);address+=1
assert bytes(expanded)==raw,'Dictionary/playlist decoding is byte-for-byte lossless'
for token in raw:
    if token>=151:continue
    pitch=token>>3
    if pitch==17:current=None
    elif pitch!=18:
        current=meta['pitches'][pitch];actual_attacks.append((len(actual_grid),current))
    actual_grid.extend([current]*durations[token&7])
assert actual_grid[:1712]==[note[0] if note else None for note in source_grid]
assert actual_attacks==expected_attacks+[(2240,65)]
assert len(actual_grid)==2256 and actual_grid[2244:]==[None]*12
assert actual_grid[1712:2240]==[None]*528,'The native continuation shares the idle primary slot'
continuation=sorted((round(n[3]*4/ppqn),round(n[4]*4/ppqn)) for n in notes
                    if n[0]==15 and n[2]==77 and n[3]>=448*ppqn)
assert continuation==[(unit,unit+1) for unit in range(1792,2240)]
assert meta['continuation']['noteOns']==len(continuation)==448
assert meta['continuation']['program']==50 and meta['continuation']['pitch']==77

# Reconstruct every bass glyph independently; four-quarter and whole-bar gates
# must reproduce all345 retained source notes, including8-quarter holds.
bass=sorted((n for n in notes if n[0]==4 and n[2]!=41),key=lambda n:n[3])
expected_bass=[(round(n[3]*4/ppqn),n[2],round(n[4]*4/ppqn)) for n in bass]
actual_bass=[]
for bar,glyph in enumerate(meta['bassGlyphs']):
    if glyph==3:continue
    pitch=[37,34,29][glyph&3]
    for offset in ([0,4,8,12] if glyph&4 else [0]):actual_bass.append((bar*16+offset,pitch))
assert len(actual_bass)==458
assert actual_bass==[(unit,pitch) for unit,pitch,off in expected_bass]
for index,(unit,pitch,off) in enumerate(expected_bass):
    assert off==(actual_bass[index+1][0] if index+1<len(actual_bass) else 2176)

assert bank.verify_sources()
assert ep==bank.build_eeprom(score['instruments']) and len(ep)==64
assert report['instrumentBankSha256']==hashlib.sha256(bank.BANK_PATH.read_bytes()).hexdigest()
profiles=bank.load_bank()['instruments']
assert report['instrumentAssignments']==bank.describe_assignments(score['instruments'])
assert profiles['synth-strings-1']['gmProgram']==50
assert profiles['synth-strings-1']['envelope']['attackMask']==1
assert profiles['synth-strings-1']['envelope']['releaseMask']==7
assert score['primary_voice_assignments'][0]['level']==15
assert score['primary_voice_assignments'][1]['level']==7
for index,pitch in enumerate(meta['pitches']):
    address=labels['note_steps']+index*2
    actual=rom[address]|(rom[address+1]&127)<<8
    assert actual==round(440*2**((pitch-69)/12)*65536/18750)
    assert bool(rom[address+1]&128)==(pitch>=75),'Original high-register piano decay is retained'
for check in meta['pageLocalProof']['removedCarries']:
    assert labels[check['table']]%256+check['length']<=256
print(f'Children:256 piano notes,458 source bass notes/gates,448 GM50 continuation notes,2256 grid cells,4 main voices+2 tails; '
      f'{len(rom)} Flash bytes; measured GM0/35/50 EEPROM and lossless phrase packing verified.')
