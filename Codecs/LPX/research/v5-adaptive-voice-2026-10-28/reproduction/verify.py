"""Run prior codec checks and unified voice/input/noise regressions."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD = ROOT/'Codecs/LPX/research/v5-quiet-voice-encoder-2026-10-28/reproduction/verify.py'
spec = importlib.util.spec_from_file_location('quiet_voice_checkpoint_checks', OLD)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
previous.checks.MODULES += ['test_speech_noise_objective', 'test_voice_input',
                           'test_adaptive_speech_voice']

if __name__ == '__main__':
    raise SystemExit(previous.checks.main())
