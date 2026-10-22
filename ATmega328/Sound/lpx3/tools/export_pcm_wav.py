#!/usr/bin/env python3
"""Turn L3AV unsigned PCM8 output into mono 16-bit 8kHz WAV."""
import argparse, struct, wave
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('input',type=Path);p.add_argument('output',type=Path)
a=p.parse_args(); data=a.input.read_bytes()
with wave.open(str(a.output),'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
 w.writeframes(struct.pack('<%dh'%len(data),*((v-128)*256 for v in data)))
print(f'WAV created: {a.output} / {len(data)/8000:.3f} sec')
