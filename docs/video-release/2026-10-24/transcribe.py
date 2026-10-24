"""Locally transcribe Russian speech for reviewed English subtitle translation."""
import dataclasses
import json
from pathlib import Path
import subprocess
import sys
import wave

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, 'C:/Work/MicroMusic/build/video-asr-packages')
from faster_whisper import WhisperModel
from huggingface_hub import HfApi, snapshot_download
import numpy as np

ROOT = Path('C:/Work/YouTube Videos/MicroMusic/materials/work')
MODEL = Path('C:/Work/YouTube Videos/MicroMusic/materials/models/faster-whisper-small')
WAV = ROOT / 'transcription-16k.wav'
result = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i',
                         str(ROOT / 'soundtrack-normalized.wav'), '-ar', '16000',
                         '-ac', '1', '-c:a', 'pcm_s16le', str(WAV)], capture_output=True)
result.check_returncode()
repo = 'Systran/faster-whisper-small'
revision = HfApi().model_info(repo).sha
print(f'Downloading {repo} at {revision}', flush=True)
snapshot_download(repo, revision=revision, local_dir=str(MODEL),
                  allow_patterns=['config.json', 'model.bin', 'tokenizer.json',
                                  'vocabulary.*', 'preprocessor_config.json', 'README.md'])
model = WhisperModel(str(MODEL), device='cpu', compute_type='int8', cpu_threads=8)
with wave.open(str(WAV), 'rb') as stream:
    assert stream.getframerate() == 16000 and stream.getnchannels() == 1
    audio = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(np.float32) / 32768
segments, info = model.transcribe(
    audio, language='ru', beam_size=5, word_timestamps=True, vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=500),
    condition_on_previous_text=False,
    initial_prompt='Обзор сайтов MicroMusic и Z80 Lab. ATtiny13A, ATtiny88, Intel 8080, Z80, Flash, EEPROM, SRAM, ШИМ, LPC, LPC2, Vorbis, Opus, Люмьер, Алисия, Mariachi.')
rows = []
for segment in segments:
    row = dataclasses.asdict(segment)
    rows.append(row)
    print(f"{segment.start:.2f}--{segment.end:.2f} {segment.text}", flush=True)
    (ROOT / 'transcript-Russian.json').write_text(
        json.dumps(dict(model=repo, revision=revision, language=info.language,
                        segments=rows), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Transcribed {len(rows)} segments', flush=True)
