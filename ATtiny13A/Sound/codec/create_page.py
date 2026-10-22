from pathlib import Path
import base64
p=Path(__file__).resolve().parent
h=(p/'page_template.html').read_text()
for k,path in [('AVR_CORE', 'avr_emulator.js'),('LPC_MATH','lpc_math.js'),('FIRMWARE_HEX','tinylpc.hex')]:
 h=h.replace('/*__'+k+'__*/',(p/path).read_text())
for k,path in [('LPC1','phrase_lpc1.lpc'),('LPC2','phrase_lpc2.lp2'),('ORIG','tts_source.mp3'),('FRAMES','voice_tinylpc.bin')]:
 h=h.replace('/*__'+k+'__*/',base64.b64encode((p/path).read_bytes()).decode('ascii'))
(p/'index.html').write_text(h)
print('page',len(h.encode('utf8')),'bytes')
