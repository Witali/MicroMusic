"""Extended-pole actual AVR multiplication, pulsebook EEPROM and Flash limits."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from hq4_core import pack_stream
from q3_pulsebook_pole import legacy_tables

spec = importlib.util.spec_from_file_location('pulsebook_pole_avr_builder',ROOT/'tools/build-q3-pulsebook-pole.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PulsebookPoleAvrTests(unittest.TestCase):
    def tools(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE',ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the repository toolchains')
        return avr,node

    def execute(self,name,frames,durations,table,rounded):
        avr,node = self.tools()
        output = ROOT/'build/q3-pulsebook-pole-validation'/name
        output.mkdir(parents=True,exist_ok=True)
        stream,table_path = output/'source.hq',output/'table.bin'
        stream.write_bytes(pack_stream(frames,durations))
        table_path.write_bytes(table.tobytes())
        report = builder.build(stream,table_path,output/'avr',avr,node,rounded=rounded,
                               expected_samples=int(durations.sum()))
        self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
        self.assertEqual(report['codeBytes'],434 if rounded else 430)
        self.assertEqual(report['eepromUsedBytes'],64)
        self.assertEqual(report['verification']['verifiedSamples'],int(durations.sum())*3)
        self.assertEqual(report['verification']['engines'],['reference','wasm','wasm-unoptimized'])
        self.assertEqual(report['verification']['mismatches'],0)
        self.assertEqual(report['verification']['lostOverflows'],0)
        self.assertEqual(report['verification']['missedSamples'],0)
        self.assertEqual(report['verification']['eepromSha256'],builder.sha(table.tobytes()))
        self.assertGreater(report['verification']['foregroundTiming']['minimumSlackCycles'],0)
        return report,output/'avr'

    def test_every_actual_avr_product_including_negative128_in_all_three_engines(self):
        _,node = self.tools()
        images = []
        for rounded in (False,True):
            frames = np.array([[40,1,0x80,0x88,0x88,0x88]],np.uint8)
            durations = np.array([256],np.uint16)
            report,folder = self.execute('scalar-'+str(rounded),frames,durations,legacy_tables(),rounded)
            images.append(dict(image=str(folder/'firmware.bin'),entry=report['symbols']['mul_q3'],rounded=rounded))
        # Execute the actual assembled multiplier directly. Independent scalar
        # expectations cover all256 signed inputs and16 coefficient codes;
        # this explicitly reaches -128 with the special -15/16 path.
        script = ROOT/'build/q3-pulsebook-pole-validation/scalar-products.mjs'
        script.write_text('''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '''+json.dumps((ROOT/'web-player/lib/avr-reference.js').as_uri())+''';
import {AVRCore as Wasm} from '''+json.dumps((ROOT/'web-player/lib/avr-core.js').as_uri())+''';
const images='''+json.dumps(images)+''';
let checked=0;
for(const image of images){
 const bytes=readFileSync(image.image);
 const engines=[new Reference(bytes),new Wasm(bytes),new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})];
 for(const cpu of engines)for(let value=-128;value<128;value++)for(let coefficient=-8;coefficient<8;coefficient++){
  let expected;
  if(coefficient===-8)expected=Math.floor((-15*value+(image.rounded?8:0))/16);
  else{
   const adjusted=coefficient<0?(((-value+128)&255)-128):value;
   expected=Math.floor((adjusted*Math.abs(coefficient)+(image.rounded?4:0))/8);
  }
  cpu.pc=image.entry/2;cpu.sp=0x9f;cpu.sreg=0x35;
  cpu.r[21]=value&255;cpu.r[23]=coefficient&255;cpu.r[27]=0;
  cpu.pushPC(511);
  let steps=0;while(cpu.pc!==511&&steps++<200)cpu.step();
  assert.equal(cpu.pc,511,'Multiplier failed to return');
  assert.equal(cpu.r[24],expected&255,JSON.stringify({value,coefficient,rounded:image.rounded}));
  assert.equal(cpu.r[27],0,'Zero-register ABI changed');
  assert.equal(cpu.sp,0x9f,'Multiplier unbalanced stack');checked++;
 }
}
assert.equal(checked,24576);console.log(JSON.stringify({checked,engines:3,profiles:2}));
''',encoding='utf-8',newline='\n')
        result = builder.run([node,script],ROOT)
        self.assertEqual(json.loads(result.stdout)['checked'],24576)

    def test_special_coefficients_all_modes_signed_table_extremes_and_eeprom_address63(self):
        table = np.array([[-7,7]*8,[7,-7]*8,[-7]*16,[7]*16],np.int8)
        table[3,15] = -7
        frames = np.array([[17,15,0x00,0x90,0x70,0x08],
                           [31,0x1f,0x70,0x00,0x09,0x80],
                           [90,0x2f,0x00,0x07,0x00,0x90],
                           [17,0x3f,0x70,0x00,0x09,0x08],
                           [0,3,0x00,0x88,0x00,0x88]],np.uint8)
        durations = np.array([64,128,192,256,64],np.uint16)
        for rounded in (False,True):
            self.execute('extreme-'+str(rounded),frames,durations,table,rounded)

    def test_exact593_and589_byte_streams_fill_1024_flash_and_larger_input_rejects(self):
        for rounded in (False,True):
            count = 97 if rounded else 98
            frames = [[40,1 | ((i%4)<<4),*([0x90 if i%2 else 0x09]*4)] for i in range(count)]
            if rounded:
                frames.append([90,1,*([0x88]*4)])
            else:
                frames.append([90,1,0x88,0x88,*frames[-1][4:]])
            frames = np.array(frames,np.uint8)
            durations = np.array([64]*count+[192],np.uint16)
            payload = pack_stream(frames,durations)
            self.assertEqual(len(payload),589 if rounded else 593)
            report,folder = self.execute('maximum-'+str(rounded),frames,durations,legacy_tables(),rounded)
            self.assertEqual(report['flashBytes'],1024)
            self.assertEqual(report['maximumStreamBytes'],len(payload))
            excessive = folder.parent/'excessive.hq'
            excessive.write_bytes(payload+b'\0')
            with self.assertRaisesRegex(ValueError,'stream bytes'):
                builder.load_stream(excessive,legacy_tables(),rounded=rounded)

    def test_malformed_tables_and_changed_duration_are_rejected(self):
        output = ROOT/'build/q3-pulsebook-pole-validation/invalid'
        output.mkdir(parents=True,exist_ok=True)
        table = output/'table.bin'
        for payload in (b'\0'*63,b'\0'*65,b'\x80'*64):
            table.write_bytes(payload)
            with self.assertRaises(ValueError):
                builder.load_table(table)
        source = output/'speech.hq'
        source.write_bytes(pack_stream(np.array([[40,1,0x80,0x88,0x88,0x88]],np.uint8),np.array([256],np.uint16)))
        with self.assertRaisesRegex(ValueError,'complete requested'):
            builder.load_stream(source,legacy_tables(),expected_samples=192)


if __name__ == '__main__':
    unittest.main()
