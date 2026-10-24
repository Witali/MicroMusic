"""Measure literal music-style Q3 Horner and matched full-phrase Q7 unrolling.

This creates benchmark sources under build; it never edits a frozen profile.
The deterministic coalesced phrase is a performance fixture, not a quality fit.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kmap_music_builder',ROOT/'tools/build-q3-kmap.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
from hq4_core import pack_stream,unpack_stream

LOOP = '''mul_q3_loop:
 add r24,r21
 adc r16,r17
 dec r25
 brne mul_q3_loop
'''
HORNER = '''/* Literal16-bit adaptation of the music routine's3-bit Horner form. */
 sbrc r25,2
 add r24,r21
 sbrc r25,2
 adc r16,r17
 lsl r24
 rol r16
 sbrc r25,1
 add r24,r21
 sbrc r25,1
 adc r16,r17
 lsl r24
 rol r16
 sbrc r25,0
 add r24,r21
 sbrc r25,0
 adc r16,r17
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'build/q3-kmap-music-unroll')
    p.add_argument('--avr-bin',type=Path,required=True)
    p.add_argument('--node',required=True)
    p.add_argument('--retain',type=Path)
    a = p.parse_args()
    output = a.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    suffix = '.exe' if os.name == 'nt' else ''
    def avr(name):return a.avr_bin/(name+suffix)
    images = []
    for rounded in (False,True):
        path = ROOT/'ATtiny13A/Sound/codec/q3-kmap'/('hq4-rounded.S' if rounded else 'hq4-floor.S')
        original = path.read_text(encoding='utf-8')
        if original.count(LOOP) != 1:
            raise ValueError('Frozen Q3 product changed; review the extraction')
        original_core = builder.layout(rounded)
        for horner in (False,True):
            name = ('horner-' if horner else 'loop-')+('nearest' if rounded else 'floor')
            folder = output/name
            folder.mkdir(exist_ok=True)
            source = original.replace(LOOP,HORNER) if horner else original
            expected_core = original_core+(24 if horner else 0)
            source = source.replace('.set VOICE_ADDR,'+str(original_core),'.set VOICE_ADDR,'+str(expected_core))
            (folder/'firmware.S').write_text(source,encoding='utf-8',newline='\n')
            (folder/'speech.hq').write_bytes(bytes([40,1,0x88,0x88,0x88,0x88]))
            builder.run([avr('avr-gcc'),'-mmcu=attiny13','-nostdlib','-x','assembler','-c','firmware.S','-o','firmware.o'],folder)
            symbols = builder.parse_symbols(builder.run([avr('avr-nm'),'-n','firmware.o'],folder).stdout)
            if symbols['code_end'] != expected_core or symbols['voice_data'] != expected_core:
                raise ValueError('Measured literalHorner core is not the expected size')
            builder.run([avr('avr-gcc'),'-mmcu=attiny13','-nostdlib','-Wl,-Ttext=0','-x','assembler','firmware.S','-o','firmware.elf'],folder)
            builder.run([avr('avr-objcopy'),'-O','binary','firmware.elf','firmware.bin'],folder)
            images.append(dict(name=name,image=str(folder/'firmware.bin'),entry=symbols['mul_lattice'],
                rounded=rounded,horner=horner,code_bytes=symbols['code_end'],
                generated_asm_sha256=builder.sha(source.encode()),base_source=path.relative_to(ROOT).as_posix(),
                base_source_sha256=builder.sha(original.encode()),image_sha256=builder.sha((folder/'firmware.bin').read_bytes())))
    script = output/'products.mjs'
    script.write_text('''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '''+json.dumps((ROOT/'web-player/lib/avr-reference.js').as_uri())+''';
import {AVRCore as Wasm} from '''+json.dumps((ROOT/'web-player/lib/avr-core.js').as_uri())+''';
const images='''+json.dumps(images)+''';let checked=0;const timing=[];
for(const image of images){
 const bytes=readFileSync(image.image),ranges=Array.from({length:8},()=>({minimum:Infinity,maximum:0}));
 const engines=[new Reference(bytes),new Wasm(bytes),new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})];
 for(const cpu of engines)for(const stage of [3,8])for(let value=-128;value<128;value++)for(let coefficient=-7;coefficient<=7;coefficient++){
  const adjusted=coefficient<0?(((-value+128)&255)-128):value;
  const expected=Math.floor((adjusted*Math.abs(coefficient)+(image.rounded?4:0))/8);
  cpu.pc=image.entry/2;cpu.sp=0x9f;cpu.sreg=0x35;cpu.r[21]=value&255;cpu.r[23]=coefficient&255;
  cpu.r[19]=stage;cpu.r[20]=0x5a;cpu.r[27]=0;cpu.pushPC(511);const start=cpu.cyc;
  let steps=0;while(cpu.pc!==511&&steps++<200)cpu.step();
  assert.equal(cpu.pc,511);assert.equal(cpu.r[24],expected&255,JSON.stringify({value,coefficient,stage,image}));
  assert.equal(cpu.sp,0x9f);assert.equal(cpu.r[23],coefficient&255);assert.equal(cpu.r[19],stage);
  assert.equal(cpu.r[27],0);assert.equal(cpu.r[20],0x5a);
  const range=ranges[Math.abs(coefficient)],cycles=cpu.cyc-start;
  range.minimum=Math.min(range.minimum,cycles);range.maximum=Math.max(range.maximum,cycles);checked++;
 }
 timing.push({name:image.name,body_cycles_including_ret_by_coefficient_magnitude:ranges,rcall_cycles:3});
}assert.equal(checked,92160);console.log(JSON.stringify({checked,timing,pass:true}));
''',encoding='utf-8',newline='\n')
    scalar = json.loads(builder.run([a.node,script],ROOT).stdout)
    # Both complete-player profiles receive the exact same speech bytes/table.
    source = ROOT/'ATtiny13A/Sound/research/q3-kmap-generic-timing'
    frames,durations = unpack_stream((source/'speech.hq').read_bytes())
    frames = frames.copy()
    capacity = 1024-builder.layout(False,True)-1
    payload = pack_stream(frames,durations)
    coalesced = 0
    for i in range(len(frames)-1,0,-1):
        if len(payload) <= capacity:break
        frames[i:,2:] = frames[i-1,2:]
        payload = pack_stream(frames,durations)
        coalesced += 1
    paired = output/'matched-phrase'
    paired.mkdir(exist_ok=True)
    stream = paired/'speech.hq'
    stream.write_bytes(payload)
    reports = []
    for unrolled in (False,True):
        r = builder.build(stream,source/'table.json',paired/('unrolled' if unrolled else 'stage'),a.avr_bin,a.node,
                          unrolled=unrolled,expected_samples=int(durations.sum()))
        if r['status'] != 'verified':raise ValueError('Matched full-phrase performance fixture failed')
        t = r['verification']['foregroundTiming']
        reports.append(dict(profile=r['multiplyProfile'],code_bytes=r['codeBytes'],flash_bytes=r['flashBytes'],
            eeprom_bytes=r['eepromUsedBytes'],stream_bytes=r['streamBytes'],image_sha256=r['imageSha256'],
            phrase_pcm_sha256=r['phrasePcmSha256'],verified_samples=r['verification']['verifiedSamples'],
            maximum_completion_cycles=t['maximumCompletionCycles'],minimum_slack_cycles=t['minimumSlackCycles'],
            normalized_source_sha256=r['normalizedSourceSha256']))
    if reports[0]['phrase_pcm_sha256'] != reports[1]['phrase_pcm_sha256']:
        raise ValueError('Matched profiles changed output PCM')
    report = dict(schema='micromusic-q3-kmap-music-unroll-benchmark-v1',hardware_tested=False,
        literal_q3_horner=dict(images=images,verification=scalar,
            limits='Arithmetic and assembled core-size test; no complete-player timing claim for the literalQ3 Horner profile'),
        matched_full_phrase=dict(samples=int(durations.sum()),stream_bytes=len(payload),stream_sha256=builder.sha(payload),
            source_stream_sha256=builder.sha((source/'speech.hq').read_bytes()),source_table_sha256=builder.sha((source/'table.json').read_bytes()),
            coalesced_tail_frames=coalesced,pcm_equal=True,quality_assessed=False,reports=reports),
        probe_source_sha256=builder.sha(Path(__file__).read_text(encoding='utf-8').encode()))
    data = json.dumps(report,indent=2)+'\n'
    (output/'report.json').write_text(data,encoding='utf-8',newline='\n')
    if a.retain:
        a.retain.parent.mkdir(parents=True,exist_ok=True)
        a.retain.write_text(data,encoding='utf-8',newline='\n')
    print(json.dumps(dict(scalar_checks=scalar['checked'],matched_stream_bytes=len(payload),
        matched_profiles=[{k:r[k] for k in ('profile','code_bytes','flash_bytes','minimum_slack_cycles')} for r in reports]),indent=2))


if __name__ == '__main__':main()
