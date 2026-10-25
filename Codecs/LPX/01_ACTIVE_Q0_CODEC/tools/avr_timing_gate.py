"""Exact full-ELF timing gate for a bounded shortlist of encoder candidates."""
import hashlib
from pathlib import Path
from profile_avr import run as profile


class AvrTimingGate:
    def __init__(self,baseline,output,avr_bin,runner,lib=None,wsl=None,**settings):
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.arguments=(avr_bin,runner,lib,wsl)
        self.settings={'enable_asm':True,**settings};self.cache={}
        self.baseline=self.measure(baseline)
        if self.baseline['underruns']:raise ValueError('Baseline already underruns in selected AVR profile')
        self.avr_cycles_measured=True

    def measure(self,blob):
        key=hashlib.sha256(blob).hexdigest()
        if key not in self.cache:
            source=self.output/(key+'.l4hy');source.write_bytes(blob)
            report=profile(source,self.output/key,*self.arguments,**self.settings)
            self.cache[key]={k:report[k] for k in ('mean_decode_wall_cycles','decode_wall_cycles_max_160',
                'underruns','min_queue_before_producer_eos','flash_bytes','pwm_native_exact','input_sha256')}
        return self.cache[key]

    def __call__(self,blob):
        measured=self.measure(blob)
        accepted=(measured['underruns']==0 and measured['flash_bytes']<=32768 and
            measured['mean_decode_wall_cycles']<=self.baseline['mean_decode_wall_cycles'] and
            measured['decode_wall_cycles_max_160']<=self.baseline['decode_wall_cycles_max_160'])
        return {'accepted':accepted,**measured}
