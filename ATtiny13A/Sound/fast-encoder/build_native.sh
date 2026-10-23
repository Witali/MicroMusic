#!/bin/sh
set -eu
cd "$(dirname "$0")"
cc -O3 -std=c11 -fPIC -shared -Wall -Wextra -Wno-unused-variable fast_core.c -o libmicrolpc.so -l:libfftw3.so.3 -lm
