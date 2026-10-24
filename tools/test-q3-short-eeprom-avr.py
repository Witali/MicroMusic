"""Real short-table AVR images, EEPROM/Flash seams, nibble carry and IRQ safety."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream
from q3_short_eeprom import code_bytes

spec = importlib.util.spec_from_file_location('short_eeprom_probe', ROOT/'tools/probe-q3-short-eeprom.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ShortEepromAvrTests(unittest.TestCase):
    images = {}

    def tools(self):
        avr = Path(os.environ.get('AVR_BIN', ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE', ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the repository toolchains')
        return avr, node

    def image(self, name, payload, book, packing='raw', prefix=None, width=4):
        if name not in self.images:
            avr, node = self.tools()
            output = ROOT/'build/q3-short-eeprom-validation'/name
            report = probe.build(payload, book, width, packing, prefix, output, avr, node)
            self.images[name] = report, output
        report, output = self.images[name]
        v = report['verification']
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(v['engines'], ['reference', 'wasm', 'wasm-unoptimized'])
        self.assertEqual(v['mismatches'], 0)
        self.assertEqual(v['missedSamples'], 0)
        self.assertEqual(v['lostOverflows'], 0)
        self.assertGreater(v['foregroundTiming']['minimumSlackCycles'], 0)
        self.assertEqual(v['verifiedSamples'], 3*report['phrase_samples'])
        self.assertEqual(v['silenceSamplesVerified'], 2*report['phrase_samples'])
        return report, output

    def mixed(self, packing='raw', prefix=None, width=4):
        frames, durations = probe.compaction.fixtures.mixed_fixture(False)
        book = np.zeros((4, 16), np.int8)
        book[:, :width] = ((np.arange(4*width).reshape(4, width)%15)-7)
        return self.image(f'mixed-{width}-{packing}-{prefix}', pack_stream(frames, durations), book, packing, prefix, width)

    def test_same_complete_vinni_pcm_at_972_and_976_actual_flash_bytes(self):
        payload, book = probe.load_model(ROOT/'ATtiny13A/Sound/research/q3-perceptual-fit/stronger32-start/before/model.json')
        for packing, code, flash, waves, prefix, capacity in (
                ('raw', 398, 972, 16, 48, 673), ('nibble', 410, 976, 8, 56, 669)):
            report, _ = self.image('vinni-'+packing, payload, book, packing)
            self.assertEqual((report['code_bytes'], report['flash_bytes']), (code, flash))
            self.assertEqual((report['waveform_bytes'], report['speech_prefix_bytes']), (waves, prefix))
            self.assertEqual(report['unused_eeprom_bytes'], 0)
            self.assertEqual(report['maximum_stream_bytes'], capacity)
            self.assertEqual(report['phrase_samples'], 22272)
            self.assertEqual(report['intermediate_wraps'], [0, 0, 0, 0])
            self.assertEqual(report['phrase_pcm_sha256'], '4155925af8a10464f0b3b7c26973ee2963adc514bb670ed6f93d9533ae7c4e12')

    def test_parser_modes_short_prefixes_and_complete_stream_inside_eeprom(self):
        for packing, prefix in (('raw', 0), ('raw', 1), ('nibble', 7), ('raw', None), ('nibble', None)):
            self.mixed(packing, prefix)
        frames = np.array([[40, 1, 0x88, 0x88, 0x88, 0x88]], np.uint8)
        payload = pack_stream(frames, np.array([64], np.uint16))
        report, _ = self.image('all-speech-in-eeprom', payload, np.zeros((4, 16), np.int8), 'nibble')
        self.assertEqual(report['speech_prefix_bytes'], len(payload))
        self.assertEqual(report['flash_speech_bytes'], 0)  # EOF alone stays in Flash.
        self.assertLess(report['prefix_end'], 64)

    def test_expanded_stream_capacities_fill_real_flash_and_reject_oversize(self):
        avr, node = self.tools()
        for packing, prefix, capacity in (('raw', 48, 673), ('nibble', 56, 669)):
            frames, durations = probe.compaction.fixtures.maximum_fixture(capacity, False)
            payload = pack_stream(frames, durations)
            self.assertEqual(len(payload), capacity)
            book = np.zeros((4, 16), np.int8)
            report, output = self.image('maximum-'+packing, payload, book, packing)
            self.assertEqual(report['flash_bytes'], 1024)
            self.assertEqual(report['maximum_stream_bytes'], capacity)
            self.assertEqual(code_bytes(4, packing, prefix), report['code_bytes'])
            with self.assertRaisesRegex(ValueError, '1024 Flash'):
                probe.build(payload+b'\x40\x40', book, 4, packing, prefix, output/'oversize', avr, node)

    def test_actual_nibble_paths_prefix_seams_and_interrupt_preservation(self):
        _, node = self.tools()
        images = []
        for width in (4, 8, 16):
          for packing in ('raw', 'nibble'):
            report, output = self.mixed(packing, width=width)
            symbols = report['symbols']
            images.append(dict(width=width, image=str(output/'firmware.bin'), eeprom=str(output/'eeprom.bin'),
                payload=str(output/'speech.hq'), prefix=report['speech_prefix_bytes'], start=report['prefix_start'],
                voice=symbols['voice_data'], lookup=symbols['pulse_lookup'], address=symbols['pulse_address_ready'],
                filter=symbols['filter'], lag=symbols['pulse_lag'], reader=symbols.get('read_byte'),
                advance=symbols.get('prefix_advance')))
        script = '''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from REFERENCE;
import {AVRCore as Wasm} from WASM;
const images=IMAGES;let excitation=0,tails=0,reads=0;
for(const image of images){
 const bytes=readFileSync(image.image),ee=readFileSync(image.eeprom),payload=readFileSync(image.payload);
 for(const cpu of [new Reference(bytes,ee),new Wasm(bytes,ee),new Wasm(bytes,ee,{fastIdle:false,fastBlocks:false})]){
  for(let mode=0;mode<4;mode++)for(let lag=0;lag<image.width;lag++)for(let gain=0;gain<16;gain++)
   for(const flags of [0,0x35,0xff])for(const inject of [false,true]){
    cpu.pc=image.lookup/2;cpu.sp=0x9f;cpu.r[3]=gain;cpu.r[14]=mode*16;cpu.r[18]=lag;
    cpu.r[22]=5;cpu.r[8]=0;cpu.r[27]=0;cpu.sreg=flags;cpu.io[0x39]=2;cpu.pending=false;cpu.irqDelay=0;
    let steps=0;while(cpu.pc!==image.address/2&&steps++<32)cpu.step();assert.equal(cpu.pc,image.address/2);
    const before=cpu.irqCount;if(inject){cpu.r[22]=1;cpu.i=1;cpu.pending=true;cpu.interrupt();}
    while(cpu.pc!==image.filter/2&&steps++<300)cpu.step();
    assert.equal(cpu.pc,image.filter/2);assert.equal(cpu.r[18],(((mode*image.width+lag)%15)-7)*gain&255);
    assert.equal(cpu.sreg&64,flags&64);assert.equal(cpu.sp,0x9f);
    assert.equal(cpu.irqCount-before,inject?1:0);assert.equal(cpu.r[22],5);excitation++;
   }
  const tailLags=Array.from(new Set([image.width,image.width+1,Math.max(image.width,15),Math.max(image.width,16),125]));
  for(let mode=0;mode<4;mode++)for(const lag of tailLags){
   cpu.pc=image.lag/2;cpu.sp=0x9f;cpu.sreg=0;cpu.r[4]=126;cpu.r[2]=126-lag;
   cpu.r[14]=mode*16;cpu.r[18]=99;cpu.io[0x1e]=63;cpu.pending=false;
   let steps=0;while(cpu.pc!==image.filter/2&&steps++<32)cpu.step();
   assert.equal(cpu.pc,image.filter/2);assert.equal(cpu.r[18],0);assert.equal(cpu.io[0x1e],63);tails++;
  }
  if(image.prefix)for(const flags of [0,0x35,0x7f])for(const inject of [false,true]){
   cpu.r[30]=image.start;cpu.r[31]=0;
   for(let index=0;index<=payload.length;index++){
    cpu.pc=image.reader/2;cpu.sp=0x9f;cpu.sreg=flags;cpu.pending=false;cpu.r[22]=5;cpu.r[8]=0;cpu.pushPC(511);
    let steps=0,interrupted=false;
    while(cpu.pc!==511&&steps++<100){
     if(inject&&!interrupted&&cpu.pc===image.advance/2){
      cpu.r[22]=1;cpu.i=1;cpu.pending=true;cpu.interrupt();interrupted=true;
     }else cpu.step();
    }
    assert.equal(cpu.pc,511);assert.equal(cpu.r[16],index===payload.length?255:payload[index]);
    assert.equal(cpu.sp,0x9f);assert.equal(cpu.sreg&64,flags&64);
    assert.equal(interrupted,inject&&index<image.prefix);
    const expected=index+1<image.prefix?image.start+index+1:image.voice+index+1-image.prefix;
    assert.equal(cpu.r[30]+256*cpu.r[31],expected);reads++;
   }
  }
  assert.deepEqual(Array.from(cpu.eeprom),Array.from(ee));
 }
}
assert.equal(excitation,64512);assert.equal(tails,312);
const expectedReads=images.reduce((sum,image)=>sum+(image.prefix?(readFileSync(image.payload).length+1)*18:0),0);
assert.equal(reads,expectedReads);console.log(JSON.stringify({pass:true,excitation,tails,reads}));
'''
        for key, value in (('REFERENCE', (ROOT/'web-player/lib/avr-reference.js').as_uri()),
                           ('WASM', (ROOT/'web-player/lib/avr-core.js').as_uri()), ('IMAGES', images)):
            script = script.replace(key, json.dumps(value))
        path = ROOT/'build/q3-short-eeprom-validation/scalar-checks.mjs'
        path.write_text(script, encoding='utf-8', newline='\n')
        result = json.loads(probe.helpers.run([node, path], ROOT).stdout)
        self.assertTrue(result['pass'])
        (path.parent/'scalar-checks.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
