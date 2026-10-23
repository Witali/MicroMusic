#!/bin/sh
set -eu
cc -O3 -std=c11 -Wall -Wextra test_0007_0021_fast.c -o ./test_8080
./test_8080 ./dual_crc_0007_0021_onepass.bin
python3 verify_polynomials.py
python3 patch_rom_0007_0021.py ./dual_crc_0007_0021_onepass.bin ./demo64k.bin
c++ -O3 -std=c++17 count_local_4bit.cpp -o ./count4
./count4 4096 000E003F 002600E7
