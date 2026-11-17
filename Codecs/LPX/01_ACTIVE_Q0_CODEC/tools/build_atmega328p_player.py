"""Build the shared universal v9 player for Nano D3/OC2B at 16 MHz."""
from build_attiny88_player import build as build_avr


def build(sources, output, *, assembly=True, asm_isr=True, queue=32,
          output_gain=128, rom_output_gain=True, wsl=None, repeat=1,
          avr_bin=None, extra_flags=(), sample_rate=8000):
    return build_avr(sources, output, assembly=assembly, asm_isr=asm_isr,
        queue=queue, repeat=repeat, output_gain=output_gain,
        rom_output_gain=rom_output_gain, wsl=wsl, avr_bin=avr_bin,
        extra_flags=extra_flags, flash_limit=30720, universal=True,
        target='atmega328p', nano_pwm=True, sample_rate=sample_rate)
