#!/usr/bin/env python3
"""Inline modules for standalone file:// player, no HTTP server or build tools."""
import re,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
web=ROOT/'web'
html=(web/'player_template.html').read_text()
assets=(web/'music-assets.mjs').read_text().replace('export const MUSIC_ASSETS', 'const MUSIC_ASSETS')
model=(web/'synth-model.mjs').read_text();model=re.sub(r"import \{MUSIC_ASSETS as A\} from '\./music-assets\.mjs';",'const A=MUSIC_ASSETS;',model)
model=model.replace('export class SoundModel','class SoundModel')
cpu=(web/'pic16-core.mjs').read_text().replace('export class PIC16F1503','class PIC16F1503').replace('export function readPIC16Hex','function readPIC16Hex')
demo=(ROOT/'firmware'/'diagnostic_pwm_irq.hex').read_text()
for tok,content in [('/*__MUSIC_ASSETS__*/',assets),('/*__MODEL_CODE__*/',model),('/*__CPU_CODE__*/',cpu),('/*__DEMO_HEX__*/','const DIAGNOSTIC_HEX='+json.dumps(demo)+';')]:
    assert tok in html;html=html.replace(tok,content)
(web/'player.html').write_text(html)
print('Standalone player bytes',len(html.encode('utf-8')))
