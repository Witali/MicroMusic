"""Run existing checkpoint checks plus quiet-voice encoder regressions."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD = ROOT / 'Codecs/LPX/research/v5-encoder-quality-2026-10-28/reproduction/verify_checkpoint.py'
spec = importlib.util.spec_from_file_location('previous_checkpoint_checks', OLD)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
checks.MODULES += ['test_voice_character', 'test_speech_voice_objective',
                   'test_reseed_speech_excitation', 'test_speech_zero_scale',
                   'test_encode_speech_voice', 'test_speech_v4']

if __name__ == '__main__':
    raise SystemExit(checks.main())
