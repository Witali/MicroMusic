"""32-tap nibble packing, real IRQ carry preservation, legacy PCM and budgets."""
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
from hq4_q3 import render as floor_render
from hq4_q3_rounded import render as rounded_render
from q3_pulsebook32 import legacy_tables,pack_book,SCHEMA

spec = importlib.util.spec_from_file_location('pulsebook32_avr_builder',ROOT/'tools/build-q3-pulsebook32.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Pulsebook32AvrTests(unittest.TestCase):
    def tools(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE',ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the repository toolchains')
        return avr,node

    def execute(self,name,frames,durations,table,rounded):
        avr,node = self.tools()
        output = ROOT/'build/q3-pulsebook32-validation'/name
        output.mkdir(parents=True,exist_ok=True)
        source,table_path = output/'source.hq',output/'table.bin'
        source.write_bytes(pack_stream(frames,durations))
        table_path.write_bytes(pack_book(table))
        report = builder.build(source,table_path,output/'avr',avr,node,rounded=rounded,
                               expected_samples=int(durations.sum()))
        self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
        self.assertEqual(report['codeBytes'],404 if rounded else 402)
        self.assertEqual(report['eepromUsedBytes'],64)
        self.assertEqual(report['verification']['verifiedSamples'],int(durations.sum())*3)
        self.assertEqual(report['verification']['engines'],['reference','wasm','wasm-unoptimized'])
        self.assertEqual(report['verification']['mismatches'],0)
        self.assertEqual(report['verification']['lostOverflows'],0)
        self.assertEqual(report['verification']['missedSamples'],0)
        self.assertEqual(report['verification']['eepromSha256'],builder.sha(pack_book(table)))
        self.assertGreater(report['verification']['foregroundTiming']['minimumSlackCycles'],0)
        return report,output/'avr'

    def test_legacy_zero_padding_preserves_full_vinni_pcm_and_counts(self):
        source = ROOT/'ATtiny13A/Sound/research/hq4-q3/public-vinni/speech.hq'
        frames,durations = unpack_stream(source.read_bytes())
        for rounded,oracle in ((False,floor_render),(True,rounded_render)):
            report,output = self.execute('legacy-'+str(rounded),frames,durations,legacy_tables(),rounded)
            pcm,counts = oracle(frames,durations,1)
            self.assertEqual(report['phrasePcmSha256'],builder.sha(pcm.tobytes()))
            self.assertEqual((output/'actual.raw').read_bytes()[:len(pcm)],pcm.tobytes())
            np.testing.assert_array_equal(report['intermediateWraps'],counts)
            self.assertEqual(report['flashBytes'],1008 if rounded else 1006)
            self.assertEqual(report['verification']['verifiedSamples'],66816)

    def test_new_lags16_through31_all_modes_and_eeprom_address63(self):
        table = ((np.arange(128).reshape(4,32)%15)-7).astype(np.int8)
        table[3,30],table[3,31] = 7,-7
        frames = np.array([[64,3 | mode*16,0x88,0x88,0x88,0x88] for mode in range(4)]+
                          [[0,3,0x88,0x88,0x88,0x88]],np.uint8)
        durations = np.array([128,192,256,128,64],np.uint16)
        for rounded in (False,True):
            self.execute('extended-'+str(rounded),frames,durations,table,rounded)

    def test_carry_nibble_selection_survives_a_forced_real_timer_irq_for_every_lag(self):
        _,node = self.tools()
        table = ((np.arange(128).reshape(4,32)%15)-7).astype(np.int8)
        images = []
        for rounded in (False,True):
            frames = np.array([[64,1,0x88,0x88,0x88,0x88]],np.uint8)
            durations = np.array([256],np.uint16)
            report,folder = self.execute('lookup-'+str(rounded),frames,durations,table,rounded)
            images.append(dict(image=str(folder/'firmware.bin'),eeprom=str(folder/'eeprom.bin'),
                               lookup=report['symbols']['pulse_lookup'],filter=report['symbols']['filter']))
        script = ROOT/'build/q3-pulsebook32-validation/irq-lookups.mjs'
        script.write_text('''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '''+json.dumps((ROOT/'web-player/lib/avr-reference.js').as_uri())+''';
import {AVRCore as Wasm} from '''+json.dumps((ROOT/'web-player/lib/avr-core.js').as_uri())+''';
const images='''+json.dumps(images)+''',table='''+json.dumps(table.tolist())+''';let checked=0;
for(const image of images){
 const bytes=readFileSync(image.image),ee=readFileSync(image.eeprom);
 const engines=[new Reference(bytes,ee),new Wasm(bytes,ee),new Wasm(bytes,ee,{fastIdle:false,fastBlocks:false})];
 for(const cpu of engines)for(let mode=0;mode<4;mode++)for(let lag=0;lag<32;lag++)for(const interrupt of [false,true]){
  const gain=1+(lag+mode)%15;
  cpu.pc=image.lookup/2;cpu.sp=0x9f;cpu.r[18]=lag;cpu.r[22]=mode*16;cpu.r[3]=gain;cpu.r[27]=0;
  cpu.r[9]=1;cpu.r[8]=0;cpu.sreg=0;cpu.io[0x39]=2;cpu.pending=false;cpu.irqDelay=0;
  cpu.step();assert.equal(cpu.c,lag&1,'LSR did not expose nibble parity');
  const beforeIrqs=cpu.irqCount;
  if(interrupt){cpu.i=1;cpu.pending=true;cpu.interrupt();}
  let steps=0;while(cpu.pc!==image.filter/2&&steps++<250)cpu.step();
  assert.equal(cpu.pc,image.filter/2,'Lookup did not reach lattice entry');
  const expected=table[mode][lag]*gain;
  assert.equal(cpu.r[18],expected&255,JSON.stringify({mode,lag,gain,interrupt}));
  assert.equal(cpu.sp,0x9f);assert.equal(cpu.r[27],0);
  assert.equal(cpu.irqCount-beforeIrqs,interrupt?1:0);checked++;
 }
}assert.equal(checked,1536);console.log(JSON.stringify({checked}));
''',encoding='utf-8',newline='\n')
        self.assertEqual(json.loads(builder.run([node,script],ROOT).stdout)['checked'],1536)

    def test_maximum621_and619_byte_streams_fit_complete1024_flash(self):
        for rounded in (False,True):
            frames = [[40,1 | ((i%4)<<4),*([0x79 if i%2 else 0x97]*4)] for i in range(102)]
            frames += [[90,1,0x88,0x88,0x88,0x88]]
            durations = [64]*102+[192]
            if not rounded:
                frames += [[40,1,0x88,0x88,0x88,0x88]]
                durations += [64]
            frames,durations = np.array(frames,np.uint8),np.array(durations,np.uint16)
            payload = pack_stream(frames,durations)
            self.assertEqual(len(payload),619 if rounded else 621)
            report,folder = self.execute('maximum-'+str(rounded),frames,durations,legacy_tables(),rounded)
            self.assertEqual(report['flashBytes'],1024)
            self.assertEqual(report['maximumStreamBytes'],len(payload))
            oversized = folder.parent/'excessive.hq'
            oversized.write_bytes(payload+b'\0')
            with self.assertRaisesRegex(ValueError,'stream bytes'):
                builder.load_stream(oversized,legacy_tables(),rounded=rounded)

    def test_independent_nibble_packing_and_invalid_eeprom_or_old_schema_rejection(self):
        output = ROOT/'build/q3-pulsebook32-validation/invalid'
        output.mkdir(parents=True,exist_ok=True)
        table = ((np.arange(128).reshape(4,32)%15)-7).astype(np.int8)
        packed = builder.pack_table(table)
        self.assertEqual(packed,pack_book(table))
        self.assertEqual(len(packed),64)
        source = output/'table.bin'
        source.write_bytes(packed)
        np.testing.assert_array_equal(builder.load_table(source),table)
        for raw in (packed[:63],packed+b'\0',b'\x80'*64,b'\x00'*64):
            source.write_bytes(raw)
            with self.assertRaises(ValueError):
                builder.load_table(source)
        source = output/'model.json'
        source.write_text(json.dumps(dict(schema=SCHEMA,pulsebook=table.tolist())))
        np.testing.assert_array_equal(builder.load_table(source),table)
        source.write_text(json.dumps(dict(schema='hq4-q3-pulsebook-v1',pulsebook=table.tolist())))
        with self.assertRaisesRegex(ValueError,'explicitly tagged'):
            builder.load_table(source)


if __name__ == '__main__':
    unittest.main()
