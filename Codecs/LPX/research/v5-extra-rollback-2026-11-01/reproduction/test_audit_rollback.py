"""Pure saved-audit formatting and import contracts; no corpus/signal calls."""
from pathlib import Path
import subprocess
import sys
import unittest
from audit_rollback import measured_with_bytes,movement


def value(score,size,sse,stoi,coverage,clips):
    metric=dict(error_energy=sse,ser_db=5.,stoi=stoi)
    return dict(score=score,stream_bytes=size,clipped_samples=clips,voice={'within_tolerance_frames':coverage},
        pwm_voice={'within_tolerance_frames':coverage},metrics={'pcm16':metric.copy(),'pwm8':metric.copy()})


class SavedAudit(unittest.TestCase):
    def test_existing_byte_field_is_overwritten_without_keyword_collision(self):
        item={'value':{'score':1.,'stream_bytes':99},'stream_bytes':100}
        self.assertEqual(measured_with_bytes(item),{'score':1.,'stream_bytes':100})

    def test_all_requested_movements_use_only_saved_values(self):
        result=movement(value(.9,99,80,.8,6,0),value(1.,100,100,.7,5,1))
        self.assertEqual(result['byte_delta'],-1);self.assertEqual(result['pcm_sse_delta'],-20)
        self.assertAlmostEqual(result['pcm_stoi_delta'],.1)
        self.assertEqual(result['pwm_period_coverage_delta'],1);self.assertEqual(result['clipped_samples_delta'],-1)
        self.assertIsNone(movement(value(.9,99,80,None,6,0),value(1.,100,100,None,5,0))['pcm_stoi_delta'])

    def test_postcheck_import_does_not_load_any_production_module(self):
        script=('import sys; import audit_rollback; '
            'assert not any(getattr(m,"__file__",None) and "/01_ACTIVE_Q0_CODEC/tools/" in '
            'str(m.__file__).replace(chr(92),"/") for m in list(sys.modules.values()))')
        subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,check=True,capture_output=True)


if __name__=='__main__':unittest.main()
