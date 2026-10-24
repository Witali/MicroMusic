"""Eight real AVR forms, unchanged gains, header transitions and IRQ lookups."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from q3_pulsebook8 import pack_stream
spec=importlib.util.spec_from_file_location('eight_form_avr_builder',ROOT/'tools/build-q3-pulsebook8.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class Pulsebook8AvrTests(unittest.TestCase):
    images={}

    def tools(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        return avr,node

    def image(self,name,frames,durations,book,width=4,packing='nibble'):
        if name not in self.images:
            avr,node=self.tools();out=ROOT/'build/q3-pulsebook8-validation'/name
            self.images[name]=builder.build(frames,durations,book,out,avr,node,width=width,packing=packing),out
        report,out=self.images[name];v=report['verification']
        self.assertEqual(report['status'],'verified');self.assertEqual(v['mismatches'],0)
        self.assertEqual(v['missedSamples'],0);self.assertEqual(v['lostOverflows'],0)
        self.assertEqual(v['verifiedSamples'],report['phrase_samples']*3)
        self.assertEqual(v['silenceSamplesVerified'],report['phrase_samples']*2)
        self.assertGreater(v['foregroundTiming']['minimumSlackCycles'],0)
        return report,out

    def mixed(self,width=4,packing='nibble'):
        f,d=builder.short.compaction.fixtures.mixed_fixture(False)
        f=np.vstack((f,f));f[:len(f)//2,1]|=64
        d=np.tile(d,2)
        book=np.zeros((8,16),np.int8);book[:,:width]=(np.arange(8*width).reshape(8,width)%15)-7
        return self.image(f'mixed-{width}-{packing}',f,d,book,width,packing)

    def test_four_form_conversion_retains_full_vinni_pcm_and_all_gain_levels(self):
        f,d,b,_=builder.load_model(ROOT/'ATtiny13A/Sound/research/q3-perceptual-fit/stronger32-start/before/model.json')
        report,_=self.image('vinni-control',f,d,b)
        self.assertEqual((report['code_bytes'],report['flash_bytes'],report['maximum_stream_bytes']),(422,996,649))
        self.assertEqual(report['phrase_pcm_sha256'],'4155925af8a10464f0b3b7c26973ee2963adc514bb670ed6f93d9533ae7c4e12')
        self.assertEqual(report['intermediate_wraps'],[0,0,0,0])
        self.assertEqual(report['gain_levels'],16)

    def test_high_and_low_selectors_cross_every_header_duration_and_packet_mode(self):
        for width,packing in ((4,'raw'),(4,'nibble'),(8,'nibble'),(16,'nibble')):self.mixed(width,packing)
        frames=np.array([[p,m*16+1,0x88,0x88,0x88,0x88]
            for m in (7,0,4,1,6,2,5,3) for p in (0,1,4,40,63,64,126) for _ in range(4)],np.uint8)
        durations=np.tile(np.array([64,128,192,256],np.uint16),len(frames)//4)
        book=np.zeros((8,16),np.int8);book[:,:4]=(np.arange(32).reshape(8,4)%15)-7
        self.image('all-headers',frames,durations,book)

    def test_maximum_payloads_really_fit_1024_flash_and_64_eeprom(self):
        for width,capacity in ((4,649),(8,633)):
            f,d=builder.short.compaction.fixtures.maximum_fixture(capacity,False)
            extended=np.flatnonzero((f[:,0]>63)|(d==192))
            f[extended[-1],1]|=64
            self.assertEqual(len(pack_stream(f,d)),capacity)
            report,out=self.image('maximum-'+str(width),f,d,np.zeros((8,16),np.int8),width)
            self.assertEqual(report['flash_bytes'],1024)
            self.assertEqual(report['eeprom_bytes'],64)
            avr,node=self.tools()
            f=np.vstack((f,np.array([[0,0,*f[-1,2:]]],np.uint8)));d=np.r_[d,np.uint16(64)]
            with self.assertRaisesRegex(ValueError,'1024 Flash'):
                builder.build(f,d,np.zeros((8,16),np.int8),out/'oversize',avr,node,width=width)

    def test_all_real_lookup_addresses_gains_flags_and_interrupts(self):
        _,node=self.tools();images=[]
        for width,packing in ((4,'raw'),(4,'nibble'),(8,'nibble'),(16,'nibble')):
            report,out=self.mixed(width,packing);s=report['symbols']
            images.append(dict(width=width,packing=packing,image=str(out/'firmware.bin'),eeprom=str(out/'eeprom.bin'),
                lookup=s['pulse_lookup'],address=s['pulse_address_ready'],filter=s['filter']))
        script='''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from REFERENCE;
import {AVRCore as Wasm} from WASM;
const images=IMAGES;let checked=0;
for(const image of images){
 const bytes=readFileSync(image.image),ee=readFileSync(image.eeprom);
 const stride=image.packing==='raw'?image.width:image.width/2;
 for(const cpu of [new Reference(bytes,ee),new Wasm(bytes,ee),new Wasm(bytes,ee,{fastIdle:false,fastBlocks:false})])
  for(let mode=0;mode<8;mode++)for(let lag=0;lag<image.width;lag++)for(let gain=0;gain<16;gain++)
   for(const flags of [0,0x35,0xff])for(const inject of [false,true]){
    cpu.pc=image.lookup/2;cpu.sp=0x9f;cpu.sreg=flags;cpu.r[3]=gain;
    cpu.r[14]=0xc0+(mode&3)*16;cpu.r[13]=(mode>>2)*4*stride;cpu.r[18]=lag;
    cpu.r[22]=5;cpu.r[8]=0;cpu.r[27]=0;cpu.io[0x39]=2;cpu.pending=false;cpu.irqDelay=0;
    let steps=0;while(cpu.pc!==image.address/2&&steps++<32)cpu.step();assert.equal(cpu.pc,image.address/2);
    const before=cpu.irqCount;if(inject){cpu.r[22]=1;cpu.i=1;cpu.pending=true;cpu.interrupt();}
    while(cpu.pc!==image.filter/2&&steps++<300)cpu.step();
    assert.equal(cpu.pc,image.filter/2);assert.equal(cpu.r[18],(((mode*image.width+lag)%15)-7)*gain&255);
    assert.equal(cpu.r[13],(mode>>2)*4*stride);assert.equal(cpu.sp,0x9f);
    assert.equal(cpu.sreg&64,flags&64);assert.equal(cpu.irqCount-before,inject?1:0);checked++;
   }
}assert.equal(checked,73728);console.log(JSON.stringify({checked,pass:true}));
'''
        for key,value in (('REFERENCE',(ROOT/'web-player/lib/avr-reference.js').as_uri()),
                          ('WASM',(ROOT/'web-player/lib/avr-core.js').as_uri()),('IMAGES',images)):
            script=script.replace(key,json.dumps(value))
        out=ROOT/'build/q3-pulsebook8-validation';path=out/'lookups.mjs'
        path.write_text(script,encoding='utf-8',newline='\n')
        result=json.loads(builder.helpers.run([node,path],ROOT).stdout)
        self.assertTrue(result['pass']);self.assertEqual(result['checked'],73728)
        (out/'lookups.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':unittest.main()
