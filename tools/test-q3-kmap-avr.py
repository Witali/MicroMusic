"""Real AVR K1/K2 maps, music-derived unrolling, arithmetic, EEPROM and budgets."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream,unpack_stream
from q3_kmap import legacy_tables,pack_eeprom,SCHEMA
from q3_pulsebook import render as old_render

spec = importlib.util.spec_from_file_location('kmap_avr_builder',ROOT/'tools/build-q3-kmap.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def maximum_fixture(capacity):
    count,remaining = divmod(capacity,6)
    if remaining in (1,3):
        count -= 1
        remaining += 6
    frames = [[40,1 | ((i%4)<<4),*([0x79 if i%2 else 0x97]*4)] for i in range(count)]
    durations = [64]*count
    if remaining in (7,9):
        frames.append([90,1,0x88,0x88,0x88,0x88])
        durations.append(192)
        if remaining == 9:
            frames.append([40,1,0x88,0x88,0x88,0x88])
            durations.append(64)
    elif remaining == 5:
        frames.append([90,1,0x88,0x88,*frames[-1][4:]])
        durations.append(192)
    else:
        raise AssertionError('Unexpected Kmap capacity residue')
    return np.array(frames,np.uint8),np.array(durations,np.uint16)


class KmapAvrTests(unittest.TestCase):
    images = {}

    def tools(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE',ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the repository toolchains')
        return avr,node

    def execute(self,name,frames,durations,table,rounded=False,unrolled=False):
        avr,node = self.tools()
        output = ROOT/'build/q3-kmap-validation'/name
        output.mkdir(parents=True,exist_ok=True)
        stream,table_path = output/'source.hq',output/'table.json'
        stream.write_bytes(pack_stream(frames,durations))
        table_path.write_text(json.dumps(dict(schema=SCHEMA,pulsebook=table[:4].tolist(),
                                             coefficient_maps=table[4:].tolist())))
        report = builder.build(stream,table_path,output/'avr',avr,node,rounded=rounded,
                               unrolled=unrolled,expected_samples=int(durations.sum()))
        self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
        self.assertEqual(report['codeBytes'],builder.layout(rounded,unrolled))
        self.assertEqual(report['eepromUsedBytes'],64)
        self.assertEqual(report['verification']['verifiedSamples'],int(durations.sum())*3)
        self.assertEqual(report['verification']['engines'],['reference','wasm','wasm-unoptimized'])
        self.assertEqual(report['verification']['mismatches'],0)
        self.assertEqual(report['verification']['lostOverflows'],0)
        self.assertEqual(report['verification']['missedSamples'],0)
        self.assertGreater(report['verification']['foregroundTiming']['minimumSlackCycles'],0)
        self.assertEqual(report['verification']['eepromSha256'],builder.sha(pack_eeprom(table)))
        return report,output/'avr'

    def edge_image(self,rounded,unrolled):
        key = rounded,unrolled
        if key not in self.images:
            table = legacy_tables()
            table[:4] = ((np.arange(64).reshape(4,16)%15)-7).astype(np.int8)
            table[4] = np.array([-127,-113,-97,-81,-65,-49,-33,-17,0,19,35,51,67,83,99,115],np.int8)
            table[5] = np.array([-115,-99,-83,-67,-51,-35,-19,0,17,33,49,65,81,97,113,127],np.int8)
            frames = np.array([[40,1,0xf0,0x79,0x97,0x79],
                [126,0x11,0x8f,0x97,0x79,0x97], [40,0x21,0x00,0x97,0x79,0x97],
                [0,0x31,0x00,0x97,0x79,0x97], [63,2,0xf0,0x79,0x97,0x79],
                [64,0x12,0xf0,0x79,0x79,0x97], [1,0x22,0xf0,0x79,0x79,0x97],
                [2,0x32,0xf0,0x79,0x79,0x97], [3,1,0x88,0x79,0x79,0x97],
                [4,0x11,0x88,0x79,0x79,0x97], [0,0,0x88,0x79,0x79,0x97]],np.uint8)
            durations = np.array([64,192,128,256,64,192,64,128,256,192,64],np.uint16)
            self.images[key] = self.execute('edges-'+str(key),frames,durations,table,rounded,unrolled)
        return self.images[key]

    def test_mapped_extremes_index0_eeprom63_partial_updates_and_both_arithmetic_profiles(self):
        for rounded in (False,True):
            for unrolled in (False,True):
                self.edge_image(rounded,unrolled)
            a,_ = self.edge_image(rounded,False)
            b,_ = self.edge_image(rounded,True)
            self.assertEqual(a['phrasePcmSha256'],b['phrasePcmSha256'])
            self.assertEqual(a['intermediateWraps'],b['intermediateWraps'])

    def test_exhaustive_actual_signed_q7_products_and_stage_selected_q3_products(self):
        _,node = self.tools()
        images = []
        for rounded in (False,True):
            for unrolled in (False,True):
                report,folder = self.edge_image(rounded,unrolled)
                images.append(dict(image=str(folder/'firmware.bin'),rounded=rounded,unrolled=unrolled,
                    entry=report['symbols']['mul_q7' if unrolled else 'mul_lattice']))
        script = ROOT/'build/q3-kmap-validation/scalar-products.mjs'
        script.write_text('''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '''+json.dumps((ROOT/'web-player/lib/avr-reference.js').as_uri())+''';
import {AVRCore as Wasm} from '''+json.dumps((ROOT/'web-player/lib/avr-core.js').as_uri())+''';
const images='''+json.dumps(images)+''';let checked=0;
for(const image of images){
 const bytes=readFileSync(image.image),engines=[new Reference(bytes),new Wasm(bytes),new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})];
 for(const cpu of engines){
  function check(value,coefficient,stage,scale){
   const adjusted=coefficient<0?(((-value+128)&255)-128):value;
   const expected=Math.floor((adjusted*Math.abs(coefficient)+(image.rounded?scale/2:0))/scale);
   cpu.pc=image.entry/2;cpu.sp=0x9f;cpu.sreg=0x35;cpu.r[21]=value&255;cpu.r[23]=coefficient&255;
   cpu.r[19]=stage;cpu.r[20]=0x5a;cpu.r[27]=0;cpu.pushPC(511);
   let steps=0;while(cpu.pc!==511&&steps++<200)cpu.step();
   assert.equal(cpu.pc,511);assert.equal(cpu.r[24],expected&255,JSON.stringify({value,coefficient,stage,scale,image}));
   assert.equal(cpu.r[23],coefficient&255);assert.equal(cpu.r[19],stage);assert.equal(cpu.r[20],0x5a);
   assert.equal(cpu.r[27],0);assert.equal(cpu.sp,0x9f);checked++;
  }
  for(let value=-128;value<128;value++)for(let coefficient=-127;coefficient<128;coefficient++)check(value,coefficient,1+(coefficient&1),128);
  if(!image.unrolled)for(const stage of [3,8])for(let value=-128;value<128;value++)for(let coefficient=-7;coefficient<=7;coefficient++)check(value,coefficient,stage,8);
 }
}assert.equal(checked,829440);console.log(JSON.stringify({checked}));
''',encoding='utf-8',newline='\n')
        self.assertEqual(json.loads(builder.run([node,script],ROOT).stdout)['checked'],829440)

    def test_packed_wave_selection_survives_real_irq_between_lag_lsr_and_branch(self):
        _,node = self.tools()
        images = []
        for rounded in (False,True):
            for unrolled in (False,True):
                report,folder = self.edge_image(rounded,unrolled)
                images.append(dict(image=str(folder/'firmware.bin'),eeprom=str(folder/'eeprom.bin'),
                    table=report['pulsebook'],lookup=report['symbols']['pulse_lookup'],filter=report['symbols']['filter']))
        script = ROOT/'build/q3-kmap-validation/irq-lookups.mjs'
        script.write_text('''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '''+json.dumps((ROOT/'web-player/lib/avr-reference.js').as_uri())+''';
import {AVRCore as Wasm} from '''+json.dumps((ROOT/'web-player/lib/avr-core.js').as_uri())+''';
const images='''+json.dumps(images)+''';let checked=0;
for(const image of images){
 const bytes=readFileSync(image.image),ee=readFileSync(image.eeprom);
 const engines=[new Reference(bytes,ee),new Wasm(bytes,ee),new Wasm(bytes,ee,{fastIdle:false,fastBlocks:false})];
 for(const cpu of engines)for(let mode=0;mode<4;mode++)for(let lag=0;lag<16;lag++)for(const interrupt of [false,true]){
  const gain=1+(lag+mode)%15;
  cpu.pc=image.lookup/2;cpu.sp=0x9f;cpu.r[18]=lag;cpu.r[22]=mode*16;cpu.r[3]=gain;cpu.r[27]=0;
  cpu.r[9]=1;cpu.r[8]=0;cpu.sreg=0;cpu.io[0x39]=2;cpu.pending=false;cpu.irqDelay=0;
  for(let i=0;i<4;i++)cpu.step();assert.equal(cpu.c,lag&1);
  const beforeIrqs=cpu.irqCount;
  if(interrupt){cpu.i=1;cpu.pending=true;cpu.interrupt();}
  let steps=0;while(cpu.pc!==image.filter/2&&steps++<250)cpu.step();
  assert.equal(cpu.pc,image.filter/2);assert.equal(cpu.r[18],(image.table[mode][lag]*gain)&255);
  assert.equal(cpu.sp,0x9f);assert.equal(cpu.r[27],0);assert.equal(cpu.irqCount-beforeIrqs,interrupt?1:0);checked++;
 }
}assert.equal(checked,1536);console.log(JSON.stringify({checked}));
''',encoding='utf-8',newline='\n')
        self.assertEqual(json.loads(builder.run([node,script],ROOT).stdout)['checked'],1536)

    def test_uniform_maps_reproduce_legacy_source_phase_noise_lattice_and_wrap_counts(self):
        table = legacy_tables()
        frames = np.array([[period,1+((i%4)<<4),(15-i)<<4 | (i+1),0x79,0x97,0x79]
                           for i,period in enumerate([0,1,2,3,4,16,40,63,64,90,126,0,40,64,1])],np.uint8)
        durations = np.array(([64,128,192,256]*4)[:len(frames)],np.uint16)
        for rounded in (False,True):
            pcm,counts = old_render(frames,durations,table[:4],1,rounded)
            for unrolled in (False,True):
                report,folder = self.execute('legacy-'+str((rounded,unrolled)),frames,durations,table,rounded,unrolled)
                self.assertEqual(report['phrasePcmSha256'],builder.sha(pcm.tobytes()))
                self.assertEqual((folder/'actual.raw').read_bytes()[:len(pcm)],pcm.tobytes())
                np.testing.assert_array_equal(report['intermediateWraps'],counts)

    def test_all_four_real_maximum_images_fit1024_flash_and64_eeprom(self):
        table = legacy_tables()
        table[:4] = 0
        for rounded in (False,True):
            for unrolled in (False,True):
                capacity = 1024-builder.layout(rounded,unrolled)-1
                frames,durations = maximum_fixture(capacity)
                self.assertEqual(len(pack_stream(frames,durations)),capacity)
                report,folder = self.execute('maximum-'+str((rounded,unrolled)),frames,durations,table,rounded,unrolled)
                self.assertEqual(report['flashBytes'],1024)
                self.assertEqual(report['maximumStreamBytes'],capacity)
                excessive = folder.parent/'excessive.hq'
                excessive.write_bytes(pack_stream(frames,durations)+b'\0')
                with self.assertRaisesRegex(ValueError,'stream bytes'):
                    builder.load_stream(excessive,table,rounded=rounded,unrolled=unrolled)

    def test_independent_layout_and_reject_old_tag_invalid_maps_or_fixed_nibble0(self):
        folder = ROOT/'build/q3-kmap-validation/invalid'
        folder.mkdir(parents=True,exist_ok=True)
        table = legacy_tables()
        raw = builder.pack_table(table)
        self.assertEqual(raw,pack_eeprom(table))
        source = folder/'table.bin'
        source.write_bytes(raw)
        np.testing.assert_array_equal(builder.load_table(source),table)
        for bad in (raw[:63],raw+b'\0',bytes([0])+raw[1:],raw[:63]+b'\x80'):
            source.write_bytes(bad)
            with self.assertRaises(ValueError):builder.load_table(source)
        model = folder/'model.json'
        for bad in (dict(schema='hq4-q3-pulsebook-v1',pulsebook=table[:4].tolist(),coefficient_maps=table[4:].tolist()),
                    dict(schema=SCHEMA,pulsebook=table[:4].tolist(),coefficient_maps=table[4:].astype(float).tolist())):
            model.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):builder.load_table(model)
        stream = folder/'speech.hq'
        stream.write_bytes(pack_stream(np.array([[40,1,0x00,0x88,0x88,0x88]],np.uint8),np.array([256],np.uint16)))
        builder.load_stream(stream,table,expected_samples=256)
        with self.assertRaisesRegex(ValueError,'complete requested'):
            builder.load_stream(stream,table,expected_samples=192)
        stream.write_bytes(pack_stream(np.array([[40,1,0x88,0x80,0x88,0x88]],np.uint8),np.array([256],np.uint16)))
        with self.assertRaisesRegex(ValueError,'Only mapped K1/K2'):
            builder.load_stream(stream,table)


if __name__ == '__main__':
    unittest.main()
