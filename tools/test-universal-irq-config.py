"""Compile and check the explicit UM88 IRQ scratch-resource selection."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('irq_builder',ROOT/'tools/build-universal-music.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class IRQConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools=builder.legacy.toolchain(None)
        (ROOT/'build/universal').mkdir(parents=True,exist_ok=True)

    def evaluate(self,definition='',request=None,assembly=False):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='irq-header-') as work:
            folder=Path(work);source=folder/('irq.S' if assembly else 'irq.c')
            obj=folder/'irq.o';binary=folder/'irq.bin'
            value=('.section .choice,"a",@progbits\n.byte UM_IRQ_GPIOR_SCRATCH\n' if assembly else
                   '#include <stdint.h>\nconst uint8_t choice __attribute__((section(".choice")))=UM_IRQ_GPIOR_SCRATCH;\n')
            source.write_text(definition+'\n#include "irq-scratch.h"\n'+value)
            command=[str(self.tools['avr-gcc']),'-mmcu=attiny88','-I'+str(ROOT/'ATtiny88/Music/universal')]
            if request is not None:command+=['-DUM_REQUESTED_IRQ_GPIOR_SCRATCH='+str(request)]
            result=subprocess.run(command+['-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:return None,result.stderr
            builder.legacy.run(self.tools['avr-objcopy'],'-O','binary','-j','.choice',obj,binary)
            return int.from_bytes(binary.read_bytes(),'little'),''

    def test_header_defaults_opt_in_and_assembler(self):
        for assembly in (False,True):
            self.assertEqual(self.evaluate(assembly=assembly)[0],0)
            for selection in (0,1):
                self.assertEqual(self.evaluate(request=selection,assembly=assembly)[0],selection)
            self.assertEqual(self.evaluate('#define UM_IRQ_GPIOR_SCRATCH (1 - 0)',1,assembly)[0],1)

    def test_conflicting_or_invalid_header_rejected(self):
        for assembly in (False,True):
            value,message=self.evaluate('#define UM_IRQ_GPIOR_SCRATCH 1',0,assembly)
            self.assertIsNone(value);self.assertIn('disagrees',message)
            for selection in (-1,2,3):
                self.assertIsNone(self.evaluate(request=selection,assembly=assembly)[0])
                self.assertIsNone(self.evaluate('#define UM_IRQ_GPIOR_SCRATCH '+str(selection),assembly=assembly)[0])

    def build(self,output,backend,selection=None,header=None):
        command=[sys.executable,str(ROOT/'tools/build-universal-music.py'),'--backend',backend,
                 '--score',str(ROOT/'ATtiny88/Music/universal/songs/greensleeves/score.json'),
                 '--output-dir',str(output)]
        if selection is not None:command+=['--irq-scratch',selection]
        if header is not None:command+=['--platform-header',str(header)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        return result

    def test_both_resource_choices_and_c_fallback(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='irq-builder-') as work:
            folder=Path(work);images={};scores={}
            for backend in ('c','avr-asm'):
                for selection in ('stack','gpior'):
                    output=folder/(backend+'-'+selection)
                    result=self.build(output,backend,selection)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    song=output/'greensleeves';report=json.loads((song/'build-report.json').read_text())
                    self.assertEqual(report['irqScratchSelection'],selection)
                    self.assertEqual(report['irqScratch'],selection if backend=='avr-asm' else 'compiler')
                    self.assertEqual(report['reservedIORegisters'],
                                     ['GPIOR0','GPIOR1','GPIOR2'] if backend=='avr-asm' and selection=='gpior' else [])
                    self.assertIn('ATtiny88/Music/universal/irq-scratch.h',report['sourceInputs'])
                    images[backend,selection]=(song/'synth.bin').read_bytes()
                    scores[backend,selection]=(song/'score.json').read_bytes()
            self.assertEqual(images['c','stack'],images['c','gpior'],'C fallback never reserves GPIOR')
            self.assertNotEqual(images['avr-asm','stack'],images['avr-asm','gpior'])
            self.assertEqual(len(set(scores.values())),1,'Scratch selection never changes musical data')

    def test_default_builder_does_not_reserve_gpior(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='irq-default-') as work:
            output=Path(work)/'output';result=self.build(output,'avr-asm')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads((output/'greensleeves/build-report.json').read_text())
            self.assertEqual(report['irqScratch'],'stack')
            self.assertEqual(report['reservedIORegisters'],[])

    def test_platform_conflict_fails_before_publishing(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='irq-conflict-') as work:
            folder=Path(work);header=folder/'platform.h';output=folder/'output'
            header.write_text('#define UM_IRQ_GPIOR_SCRATCH 1\n')
            result=self.build(output,'avr-asm','stack',header)
            self.assertNotEqual(result.returncode,0);self.assertIn('disagrees',result.stderr)
            self.assertFalse(output.exists(),'A rejected resource contract must publish nothing')


if __name__=='__main__':unittest.main()
