"""Report I/O and matched-level listening artifacts for speech research."""
import hashlib
import json
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def matched_audio(output, clips, objective, order):
    balanced = {name:sosfilt(objective.hp, audio) for name,audio in clips.items()}
    balanced = {name:audio*objective.rms/(np.sqrt(np.mean(audio*audio))+1e-12) for name,audio in balanced.items()}
    scale = .85/max(np.max(abs(audio)) for audio in balanced.values())
    for name,audio in balanced.items():
        sf.write(output / (name.lower()+'.wav'), audio*scale, objective.sr, subtype='PCM_16')
    sequence = np.concatenate([np.r_[balanced[name]*scale, np.zeros(round(objective.sr*.3))] for name in order])
    sf.write(output / 'comparison.wav', sequence, objective.sr, subtype='PCM_16')
