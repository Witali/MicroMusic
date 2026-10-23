"""Compaction preserves real PCM; freed bytes are measured with full AVR builds."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream


def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('compact_pulsebook_builder',ROOT/'tools/build-q3-pulsebook-compact.py')
old_builders = {pole:module('old_compact_baseline_'+str(pole),ROOT/'tools'/
    ('build-q3-pulsebook-pole.py' if pole else 'build-q3-pulsebook.py')) for pole in (False,True)}


def mixed_fixture(pole):
    k = 0x80 if pole else 0x79
    frames = np.array([[40,1,0x88,0x88,0x88,0x88],
        [126,0x11,k,0x97,0x88,0x88], [40,0x21,k,0x97,0x79,k],
        [0,0x31,k,0x97,0x79,k], [63,2,0x97,k,0x97,k],
        [64,0x12,k,0x79,k,0x97], [1,0x22,k,0x79,k,0x97],
        [2,0x32,k,0x79,0x88,k], [3,1,0x88,k,0x88,k],
        [4,0x11,k,0x88,k,0x79], [0,0,k,0x88,k,0x79]],np.uint8)
    return frames,np.array([64,192,128,256,64,192,64,128,256,192,64],np.uint16)


def maximum_fixture(capacity,pole):
    count,remaining = divmod(capacity,6)
    if remaining in (1,3):
        count -= 1
        remaining += 6
    frames = [[40,1 | ((i%4)<<4),*([0x90 if pole and i%2 else 0x79 if i%2 else 0x97]*4)] for i in range(count)]
    durations = [64]*count
    if remaining in (7,9):
        alternate = 0x88
        frames.append([90,1,*([alternate]*4)])
        durations.append(192)
        if remaining == 9:
            frames.append([40,1,*frames[-1][2:]])
            durations.append(64)
    elif remaining == 5:
        frames.append([90,1,0x88,0x88,*frames[-1][4:]])
        durations.append(192)
    else:
        raise AssertionError('Unexpected compact-profile capacity residue')
    return np.array(frames,np.uint8),np.array(durations,np.uint16)


class CompactPulsebookTests(unittest.TestCase):
    pairs = {}

    def tools(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE',ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the repository toolchains')
        return avr,node

    def pair(self,pole,rounded):
        key = pole,rounded
        if key in self.pairs:
            return self.pairs[key]
        avr,node = self.tools()
        frames,durations = mixed_fixture(pole)
        output = ROOT/'build/q3-pulsebook-compact-validation'/('pole-' if pole else 'base-')/str(rounded)
        output.mkdir(parents=True,exist_ok=True)
        source,table_path = output/'source.hq',output/'table.bin'
        payload = pack_stream(frames,durations)
        source.write_bytes(payload)
        table = ((np.arange(64).reshape(4,16)%15)-7).astype(np.int8)
        table_path.write_bytes(table.tobytes())
        before = old_builders[pole].build(source,table_path,output/'before',avr,node,
                                          rounded=rounded,expected_samples=int(durations.sum()))
        after = builder.build(source,table_path,output/'after',avr,node,
                               rounded=rounded,pole=pole,expected_samples=int(durations.sum()))
        for report in (before,after):
            self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
            self.assertEqual(report['verification']['mismatches'],0)
            self.assertEqual(report['verification']['missedSamples'],0)
            self.assertEqual(report['verification']['lostOverflows'],0)
            self.assertEqual(report['verification']['verifiedSamples'],4800)
            self.assertGreater(report['verification']['foregroundTiming']['minimumSlackCycles'],0)
        self.assertEqual(before['phrasePcmSha256'],after['phrasePcmSha256'])
        self.assertEqual(before['expectedPcmSha256'],after['expectedPcmSha256'])
        self.assertEqual(before['eepromSha256'],after['eepromSha256'])
        self.assertEqual(before['streamSha256'],after['streamSha256'])
        self.assertEqual((output/'before/actual.raw').read_bytes(),(output/'after/actual.raw').read_bytes())
        comparison = dict(pole=pole,rounded=rounded,code_before=before['codeBytes'],code_after=after['codeBytes'],
            flash_before=before['flashBytes'],flash_after=after['flashBytes'],saved_code_bytes=before['codeBytes']-after['codeBytes'],
            pcm_exact=True,eeprom_exact=True,stream_exact=True,verified_samples_each=4800,
            before_minimum_slack_cycles=before['verification']['foregroundTiming']['minimumSlackCycles'],
            after_minimum_slack_cycles=after['verification']['foregroundTiming']['minimumSlackCycles'],
            before_source_hashes=before['normalizedSourceSha256'],after_source_hashes=after['normalizedSourceSha256'])
        (output/'core-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n',encoding='utf-8')
        self.pairs[key] = before,after,output
        return self.pairs[key]

    def test_before_after_pcm_and_16_actual_code_bytes_saved_in_all_profiles(self):
        for pole in (False,True):
            for rounded in (False,True):
                before,after,_ = self.pair(pole,rounded)
                self.assertEqual(before['codeBytes']-after['codeBytes'],16)
                self.assertEqual(before['flashBytes']-after['flashBytes'],16)
                self.assertEqual(after['eepromUsedBytes'],64)
                self.assertEqual(after['codeBytes'],builder.layout(rounded,pole)[0])
                self.assertEqual(after['maximumStreamBytes'],builder.layout(rounded,pole)[1])

    def test_every_actual_multiplier_input_including_extreme_pole_unchanged(self):
        _,node = self.tools()
        images = []
        for pole in (False,True):
            for rounded in (False,True):
                _,after,output = self.pair(pole,rounded)
                images.append(dict(image=str(output/'after/firmware.bin'),entry=after['symbols']['mul_q3'],pole=pole,rounded=rounded))
        script = ROOT/'build/q3-pulsebook-compact-validation/scalar-products.mjs'
        script.write_text('''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '''+json.dumps((ROOT/'web-player/lib/avr-reference.js').as_uri())+''';
import {AVRCore as Wasm} from '''+json.dumps((ROOT/'web-player/lib/avr-core.js').as_uri())+''';
const images='''+json.dumps(images)+''';let checked=0;
for(const image of images){
 const bytes=readFileSync(image.image),engines=[new Reference(bytes),new Wasm(bytes),new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})];
 for(const cpu of engines)for(let value=-128;value<128;value++)for(let coefficient=-8;coefficient<8;coefficient++){
  let expected;
  if(image.pole&&coefficient===-8)expected=Math.floor((-15*value+(image.rounded?8:0))/16);
  else{const adjusted=coefficient<0?(((-value+128)&255)-128):value;expected=Math.floor((adjusted*Math.abs(coefficient)+(image.rounded?4:0))/8);}
  cpu.pc=image.entry/2;cpu.sp=0x9f;cpu.sreg=0x35;cpu.r[21]=value&255;cpu.r[23]=coefficient&255;cpu.r[27]=0;cpu.pushPC(511);
  let steps=0;while(cpu.pc!==511&&steps++<200)cpu.step();
  assert.equal(cpu.pc,511);assert.equal(cpu.r[24],expected&255,JSON.stringify({value,coefficient,pole:image.pole,rounded:image.rounded}));
  assert.equal(cpu.r[27],0);assert.equal(cpu.sp,0x9f);checked++;
 }
}assert.equal(checked,49152);console.log(JSON.stringify({checked}));
''',encoding='utf-8',newline='\n')
        self.assertEqual(json.loads(builder.run([node,script],ROOT).stdout)['checked'],49152)

    def test_all_four_expanded_stream_budgets_really_fill_1024_flash(self):
        avr,node = self.tools()
        output = ROOT/'build/q3-pulsebook-compact-validation/maximum'
        output.mkdir(parents=True,exist_ok=True)
        table = output/'table.bin'
        table.write_bytes(np.zeros((4,16),np.int8).tobytes())
        for pole in (False,True):
            for rounded in (False,True):
                _,capacity,_ = builder.layout(rounded,pole)
                frames,durations = maximum_fixture(capacity,pole)
                payload = pack_stream(frames,durations)
                self.assertEqual(len(payload),capacity)
                source = output/(str(pole)+'-'+str(rounded)+'.hq')
                source.write_bytes(payload)
                report = builder.build(source,table,output/(source.stem+'-avr'),avr,node,
                                       rounded=rounded,pole=pole,expected_samples=int(durations.sum()))
                self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
                self.assertEqual(report['flashBytes'],1024)
                self.assertEqual(report['eepromUsedBytes'],64)
                self.assertEqual(report['verification']['mismatches'],0)
                self.assertEqual(report['verification']['missedSamples'],0)
                source.write_bytes(payload+b'\0')
                with self.assertRaisesRegex(ValueError,'stream bytes'):
                    builder.load_stream(source,np.zeros((4,16),np.int8),rounded=rounded,pole=pole)

    def test_profile_mapping_and_changed_duration_cannot_silently_cross_formats(self):
        output = ROOT/'build/q3-pulsebook-compact-validation/invalid'
        output.mkdir(parents=True,exist_ok=True)
        source = output/'source.hq'
        source.write_bytes(pack_stream(np.array([[40,1,0x80,0x88,0x88,0x88]],np.uint8),np.array([256],np.uint16)))
        table = np.zeros((4,16),np.int8)
        with self.assertRaisesRegex(ValueError,'Ordinary Q3 excludes'):
            builder.load_stream(source,table,pole=False)
        builder.load_stream(source,table,expected_samples=256,pole=True)
        with self.assertRaisesRegex(ValueError,'complete requested'):
            builder.load_stream(source,table,expected_samples=192,pole=True)


if __name__ == '__main__':
    unittest.main()
