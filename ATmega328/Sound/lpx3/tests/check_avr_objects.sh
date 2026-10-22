#!/usr/bin/env bash
# Syntax/relocatable AVR object checks only: NOT a true Arduino ELF/HEX link.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p profiling
CFLAGS=(--target=avr -mmcu=atmega328p -std=c++11 -Os -fno-exceptions -fno-rtti -fno-threadsafe-statics -nostdinc++ -Itests/avr_stub)
clang "${CFLAGS[@]}" -c examples/LPX3_FAST2_PLAYER/Lpx3AvrCore.cpp -o profiling/fast2_core.avr.o
clang "${CFLAGS[@]}" -x c++ -c examples/LPX3_FAST2_PLAYER/LPX3_FAST2_PLAYER.ino -o profiling/fast2_player.avr.o
clang "${CFLAGS[@]}" -c examples/LPX3_FAST2_PROFILING/Lpx3AvrCore.cpp -o profiling/fast2_diag_core.avr.o
clang "${CFLAGS[@]}" -x c++ -c examples/LPX3_FAST2_PROFILING/LPX3_FAST2_PROFILING.ino -o profiling/fast2_diag.avr.o
size profiling/fast2_core.avr.o profiling/fast2_player.avr.o profiling/fast2_diag_core.avr.o profiling/fast2_diag.avr.o
printf 'PASS: Clang AVR syntax and relocatable object checks; NOT linked firmware.\n'
