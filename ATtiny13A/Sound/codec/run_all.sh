#!/bin/sh
set -eu
python build_hq.py
node verify.js
python make_player.py
node ui_smoke.js
