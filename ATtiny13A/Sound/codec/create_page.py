from pathlib import Path
import base64
p=Path(__file__).resolve().parent
h=(p/'page_template.html').read_text()
for name,src in [('AVR_CORE','avr_emulator.js'),('LPC_MATH','lpc_math.js'),('FIRMWARE_HEX','tinylpc.hex'),('OLD_HEX','tinylpc_v1.hex')]:
 h=h.replace('/*__'+name+'__*/',(p/src).read_text())
for name,src in [('LPC1','phrase_lpc1.lpc'),('LPC2','phrase_lpc2.lp2'),('ORIG','tts_source.mp3'),('FRAMES','voice_tinylpc.bin')]:
 h=h.replace('/*__'+name+'__*/',base64.b64encode((p/src).read_bytes()).decode('ascii'))
assert '/*__' not in h
(p/'index.html').write_text(h)
print('Created',p/'index.html','bytes',len(h.encode()))
