#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
clang -target avr -mmcu=attiny13 -x assembler -c src/codec2tiny3200.S -o build/codec2tiny3200.o
llvm-objcopy -O binary -j .text build/codec2tiny3200.o build/codec2tiny3200.bin
clang -target avr -mmcu=attiny13 -x assembler-with-cpp -Isrc -c src/tiny13_pwm_oneframe_demo.S -o build/tiny13_pwm_oneframe_demo.o
llvm-objcopy -O binary -j .text build/tiny13_pwm_oneframe_demo.o build/tiny13_pwm_oneframe_demo.bin
python3 tests/resolve_avr_demo.py
echo "[INFO] Full AVR + audio regression: python3 tests/test_codec2tiny.py (longer, run separately)"
python3 tests/test_stress.py
python3 tests/test_lspd_reference.py
python3 tests/test_timer_isr.py
