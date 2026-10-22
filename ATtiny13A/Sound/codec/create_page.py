#!/usr/bin/env python3
from pathlib import Path
from base64 import b64encode
P=Path(__file__).resolve().parent
s=(P/'page_template.html').read_text(encoding='utf-8')
for token,path in {'AVR_CORE':'avr_emulator.js','LPC_MATH':'lpc_math.js','HEX_FIRMWARE':'tinylpc.hex'}.items():s=s.replace('__'+token+'__',(P/path).read_text())
for token,path in {'BASE64_FRAMES':'voice_tinylpc.bin','BASE64_LPC1':'phrase_lpc1.lpc','BASE64_LPC2':'phrase_lpc2.lp2','BASE64_REFERENCE':'speech_trimmed_7500.wav','BASE64_FULL':'source_original.mp3','SPECTRO_B64':'spectrogram_compare_v3.webp'}.items():s=s.replace('__'+token+'__',b64encode((P/path).read_bytes()).decode('ascii'))
assert '__BASE64_' not in s and '__AVR_' not in s and '__LPC_MATH__' not in s
(P/'index.html').write_text(s,encoding='utf-8')
print('Generated standalone index.html:',len(s.encode('utf-8')),'bytes')
