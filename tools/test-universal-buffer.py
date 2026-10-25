"""Compile-time buffer settings and full IRQ admission for different capacities."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
tooling=module('buffer_tooling','build-attiny88-music.py')
fixtures=module('buffer_fixtures','test-universal-admission.py')

class Buffer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools=tooling.toolchain(None);(ROOT/'build/universal').mkdir(parents=True,exist_ok=True)

    def evaluate(self,definition='',request=None):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal') as work:
            folder=Path(work);source=folder/'buffer.c';obj=folder/'buffer.o';binary=folder/'buffer.bin'
            source.write_text(definition+'\n#include <stdint.h>\n#include "audio-buffer.h"\nconst uint16_t capacity __attribute__((section(".capacity")))=UM_PWM_BUFFER_FRAMES;\n')
            command=[str(self.tools['avr-gcc']),'-mmcu=attiny88','-I'+str(ROOT/'ATtiny88/Music/universal')]
            if request is not None:command+=['-DUM_REQUESTED_BUFFER_FRAMES='+str(request)]
            result=subprocess.run(command+['-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:return None,result.stderr
            tooling.run(self.tools['avr-objcopy'],'-O','binary','-j','.capacity',obj,binary)
            return int.from_bytes(binary.read_bytes(),'little'),''

    def test_default_and_explicit_capacity(self):
        self.assertEqual(self.evaluate()[0],192)
        for size in (8,16,64,128,192):self.assertEqual(self.evaluate(request=size)[0],size)

    def test_platform_expression_and_cli_agreement(self):
        self.assertEqual(self.evaluate('#define UM_PWM_BUFFER_FRAMES (32 * 4)',128)[0],128)
        value,message=self.evaluate('#define UM_PWM_BUFFER_FRAMES 64',128)
        self.assertIsNone(value);self.assertIn('disagrees',message)

    def test_invalid_capacities_rejected(self):
        for size in (-4,0,4,9,190,196,256):self.assertIsNone(self.evaluate(request=size)[0])

    def test_complete_playback_with_configured_ring(self):
        cases=[]
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='buffer-test-') as work:
            folder=Path(work)
            for backend,size,voices,stress,passed in [('avr-asm',8,1,False,False),('avr-asm',64,8,True,False),
                    ('avr-asm',128,8,True,True),('avr-asm',192,8,True,True),('c',128,1,False,True)]:
                name=f'{backend}-{size}-{voices}';source=folder/(name+'.json')
                source.write_text(json.dumps(fixtures.fixture(name,voices,stress)))
                tooling.run(sys.executable,ROOT/'tools/build-universal-music.py','--backend',backend,
                            '--score',source,'--buffer-frames',size,'--output-dir',folder)
                result=subprocess.run(['node',str(ROOT/'tools/audit-universal-music.mjs'),'--directory='+str(folder),name],capture_output=True,text=True)
                measured=json.loads((folder/name/'verification.json').read_text())
                build=json.loads((folder/name/'build-report.json').read_text())
                self.assertEqual(build['packingMode'],'compact' if size==192 else 'fast')
                self.assertEqual(build['grammarFormat'],9 if size==192 else 0)
                self.assertEqual(measured['fifoCapacityFrames'],size)
                self.assertEqual(measured['passed'],passed,measured)
                self.assertEqual(result.returncode==0,passed)
                if passed:self.assertGreater(measured['stackMarginBytes'],0)
                else:self.assertGreater(measured['fifoUnderruns'],0)
                cases.append(dict(bufferFrames=size,voices=voices,verification=measured))
        report=ROOT/'ATtiny88/Music/universal/reports/buffer-verification.json'
        report.write_text(json.dumps(dict(schema='micromusic-um88-buffer-verification',version=1,
                             hardwareTested=False,cases=cases),indent=2)+'\n',encoding='utf-8')

    def test_explicit_dictionary_layouts_preserve_the_same_score(self):
        score=ROOT/'ATtiny88/Music/universal/examples/polyphony-study/generated/score.json'
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='packing-test-') as work:
            folder=Path(work);hashes=[]
            for packing,size,format_id in [('compact',128,9),('fast',192,0)]:
                output=folder/packing
                tooling.run(sys.executable,ROOT/'tools/build-universal-music.py','--backend','avr-asm',
                            '--score',score,'--packing',packing,'--buffer-frames',size,'--output-dir',output)
                name=json.loads(score.read_text(encoding='utf-8'))['name']
                tooling.run('node',ROOT/'tools/audit-universal-music.mjs','--directory='+str(output),name)
                build=json.loads((output/name/'build-report.json').read_text())
                self.assertEqual(build['grammarFormat'],format_id)
                self.assertEqual(build['packingMode'],packing)
                self.assertEqual(json.loads((output/name/'score.json').read_text(encoding='utf-8')),
                                 json.loads(score.read_text(encoding='utf-8')))
                hashes.append(build['decodedCommandsSha256'])
            self.assertEqual(*hashes)

if __name__=='__main__':unittest.main()
