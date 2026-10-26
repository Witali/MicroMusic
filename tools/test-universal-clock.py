"""Check the compiler-evaluated F_CPU, defaults, board expressions and conflicts."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('um_tools',ROOT/'tools/build-attiny88-music.py')
tooling=importlib.util.module_from_spec(spec);spec.loader.exec_module(tooling)

class Clock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools=tooling.toolchain(None)
        (ROOT/'build/universal').mkdir(parents=True,exist_ok=True)

    def evaluate(self,definition='',request=None,board=False):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal') as work:
            folder=Path(work);source=folder/'clock.c';obj=folder/'clock.o';binary=folder/'clock.bin'
            source.write_text(definition+'\n#include <stdint.h>\n#include "clock.h"\nconst uint32_t f __attribute__((section(".umclock")))=F_CPU;\n')
            command=[str(self.tools['avr-gcc']),'-mmcu=attiny88','-I'+str(ROOT/'ATtiny88/Music/universal')]
            if request is not None:command+=['-DUM_REQUESTED_CPU_HZ='+str(request)]
            if board:command+=['-DUM_BOARD_MH_ET_LIVE_16MHZ=1']
            result=subprocess.run(command+['-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:return None,result.stderr
            tooling.run(self.tools['avr-objcopy'],'-O','binary','-j','.umclock',obj,binary)
            return int.from_bytes(binary.read_bytes(),'little'),''

    def test_default_and_requested(self):
        self.assertEqual(self.evaluate()[0],8000000)
        self.assertEqual(self.evaluate(request=12000000)[0],12000000)

    def test_board_expression(self):
        self.assertEqual(self.evaluate('#define F_CPU (12UL * 1000000UL)')[0],12000000)
        self.assertEqual(self.evaluate('#define F_CPU (8UL << 20)')[0],8388608)

    def test_conflict_and_range(self):
        value,message=self.evaluate('#define F_CPU 12000000UL',8000000)
        self.assertIsNone(value);self.assertIn('disagrees',message)
        self.assertIsNone(self.evaluate('#define F_CPU 13000000UL')[0])

    def test_explicit_micronucleus_board_clock(self):
        self.assertEqual(self.evaluate(request=16000000,board=True)[0],16000000)
        self.assertEqual(self.evaluate('#define F_CPU (16UL * 1000000UL)',board=True)[0],16000000)
        value,message=self.evaluate(request=16000000)
        self.assertIsNone(value);self.assertIn('75000..12000000',message)

    def test_board_frequency_conflicts(self):
        value,message=self.evaluate(request=8000000,board=True)
        self.assertIsNone(value);self.assertIn('requires F_CPU=16000000',message)
        value,message=self.evaluate('#define F_CPU 8000000UL',16000000,board=True)
        self.assertIsNone(value);self.assertIn('disagrees',message)

if __name__=='__main__':unittest.main()
