#!/bin/sh
set -eu
cd "$(dirname "$0")"
clang -target avr -mmcu=attiny13 -x assembler-with-cpp -Isrc -c src/tiny13_pwm_resonator_demo.S -o build/demo.o
llvm-objcopy -O binary -j .text build/demo.o build/unlinked.bin
python3 tests/link_and_hex.py
python3 tests/test_resonator.py
