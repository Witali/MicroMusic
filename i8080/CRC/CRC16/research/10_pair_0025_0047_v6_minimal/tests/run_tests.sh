#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 tools/verify_and_build.py
cc -O3 -std=c11 -Wall -Wextra tests/test_compact.c -o ./test_compact
for file in bin/*.bin; do ./test_compact "$file"; done
