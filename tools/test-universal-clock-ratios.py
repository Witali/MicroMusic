"""Compiler-checked widths and exact original/reduced clock sequences."""
from pathlib import Path
import importlib.util
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ratio_tooling',ROOT/'tools/build-attiny88-music.py')
tooling=importlib.util.module_from_spec(spec);spec.loader.exec_module(tooling)

class Ratios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools=tooling.toolchain(None);(ROOT/'build/universal').mkdir(parents=True,exist_ok=True)

    def configuration(self,cpu):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='ratio-test-') as work:
            folder=Path(work);src=folder/'ratios.c';obj=folder/'ratios.o';binary=folder/'ratios.bin'
            src.write_text('#include "rational-clocks.h"\nconst uint32_t cfg[8] __attribute__((section(".ratios")))={UM_CONTROL_INCREMENT,UM_CONTROL_PERIOD,UM_DRUM_FRACTION_INCREMENT,UM_DRUM_FRACTION_PERIOD,sizeof(UMMusicClock),sizeof(UMFraction),UM_CONTROL_UNIT,UM_DRUM_UNIT};\n',encoding='utf-8')
            tooling.run(self.tools['avr-gcc'],'-mmcu=attiny88','-std=c11','-Os','-DF_CPU='+str(cpu)+'UL',
                        '-I'+str(ROOT/'ATtiny88/Music/universal'),'-c',src,'-o',obj)
            tooling.run(self.tools['avr-objcopy'],'-O','binary','-j','.ratios',obj,binary)
            return struct.unpack('<8I',binary.read_bytes())

    def test_compiled_common_clock_widths(self):
        self.assertEqual(self.configuration(8000000)[:6],(3,320,2,5,2,1))
        self.assertEqual(self.configuration(12000000)[:6],(1,160,3,5,1,1))
        # Only the timing helper is checked at 16 MHz, not this mono board driver.
        self.assertEqual(self.configuration(16000000)[:6],(3,640,1,5,2,1))
        self.assertEqual(self.configuration(8388608)[4:6],(4,4))

    def test_every_tick_and_percussion_carry_matches_original(self):
        for cpu in (75000,80000,1000000,4800000,8000000,9600000,12000000,8388608,16000000):
            with self.subTest(cpu=cpu):
                inc,period,frac_inc,frac_period,clock_bytes,frac_bytes,unit,frac_unit=self.configuration(cpu)
                self.assertEqual(inc*unit,75000);self.assertEqual(period*unit,cpu)
                self.assertEqual(frac_inc*frac_unit,19200000%cpu);self.assertEqual(frac_period*frac_unit,cpu)
                old_clock=new_clock=old_fraction=new_fraction=0
                for sample in range(10000):
                    old_clock+=75000;new_clock+=inc
                    self.assertLess(new_clock,1<<(8*clock_bytes))
                    old_tick=old_clock>=cpu;new_tick=new_clock>=period
                    self.assertEqual(old_tick,new_tick)
                    if old_tick:old_clock-=cpu
                    if new_tick:new_clock-=period
                    self.assertEqual(new_clock*unit,old_clock)
                    old_fraction+=19200000%cpu;new_fraction+=frac_inc
                    self.assertLess(new_fraction,1<<(8*frac_bytes))
                    old_carry=old_fraction>=cpu;new_carry=new_fraction>=frac_period
                    self.assertEqual(old_carry,new_carry)
                    if old_carry:old_fraction-=cpu
                    if new_carry:new_fraction-=frac_period
                    self.assertEqual(new_fraction*frac_unit,old_fraction)

if __name__=='__main__':unittest.main()
